import os
import json
from pathlib import Path
from utils.supabase_client import get_supabase_client
from schemas.export_schema import LocalizedMeta
from openai import OpenAI


import os
import json
from pathlib import Path
from utils.supabase_client import get_supabase_client
from openai import OpenAI
from pydantic import BaseModel


class LocalizedMeta(BaseModel):
    localized_title: str
    localized_author: str


def fetch_localized_title_and_author(title: str, author: str, year: str, target_lang: str) -> LocalizedMeta:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    lang_map = {
        "en": "английском",
        "es": "испанском",
        "fr": "французском",
        "de": "немецком",
        "it": "итальянском",
        "ru": "русском"
    }

    # если язык неизвестен — обобщённо
    selected_lang = lang_map.get(target_lang, "изначальном")

    system_prompt = (
        f"Верни название книги '{title}', {author}, {year}, под которым она публиковалась ранее на {selected_lang} языке.\n"
        f"Проверь, чтобы это название было не от другого похожего произведения автора.\n"
        f"Если у тебя нет точной информации – дай литературный перевод, как бы сказали носители на {selected_lang} языке.\n"
        f"Также дай имя автора на {selected_lang} языке, если оно имеет общепринятый перевод.\n"
        f"Верни строго JSON-объект в соответствии со схемой."
    )

    completion = client.beta.chat.completions.parse(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"title: {title}\nauthor: {author}\nyear: {year}"}
        ],
        response_format=LocalizedMeta,
    )

    return completion.choices[0].message.parsed


def export_book_json(book_id: int, source_lang: str, target_lang: str):
    supabase = get_supabase_client()

    # 📦 Экспорт всех книг
    if book_id == -1:
        response = supabase.table("books").select("id").execute()
        ids = [item["id"] for item in response.data]
        print(f"📚 Найдено книг: {len(ids)}")
        for i in ids:
            export_book_json(i, source_lang, target_lang)
        return

    print(f"📦 Экспорт книги ID {book_id}...")

    # Получаем метаданные книги
    meta_response = supabase.table("books_full_view").select(
        "title, author, year, words, genre, set"
    ).eq("id", book_id).single().execute()

    if not meta_response.data:
        print("❌ Не удалось получить метаданные книги.")
        return

    meta = meta_response.data
    title = meta.get("title", "")
    author = meta.get("author", "")
    year = meta.get("year", "")

    # Загрузка текстов
    def fetch_json(field):
        response = supabase.table("books").select(
            field).eq("id", book_id).single().execute()
        return json.loads(response.data[field]) if response.data.get(field) else None

    original_text = fetch_json("text_by_chapters_sentence_translation_words")
    simplified_text = fetch_json(
        "text_by_chapters_simplified_sentence_translation_words")
    original_tasks = fetch_json("tasks_truefalse_howto_words")
    simplified_tasks = fetch_json("tasks_truefalse_howto_words_simplified")

    # 🔧 Если нет текста — создаём одну главу с одним пустым абзацем
    if not original_text:
        print("⚠️ Текст отсутствует — создаём пустую структуру...")
        original_text = {
            "chapters": [{
                "chapter_number": 1,
                "paragraphs": [{
                    "paragraph_number": 1,
                    "sentences": []
                }]
            }]
        }

    # 🌍 Получение локализованного названия и автора
    try:
        localized = fetch_localized_title_and_author(
            title, author, str(year), target_lang)
        localized_title = localized.localized_title
        localized_author = localized.localized_author
        print(f"✅ Название на {target_lang}: {localized_title}")
        print(f"✅ Автор на {target_lang}: {localized_author}")
    except Exception as e:
        print(f"⚠️ Ошибка при получении перевода названия и автора: {e}")
        localized_title = title
        localized_author = author

    # Подготовка директорий
    export_base = Path("export")
    export_base.mkdir(exist_ok=True)

    book_dir = export_base / f"book_{book_id}_{source_lang}"
    book_dir.mkdir(exist_ok=True)

    content_dir = book_dir / f"book_{book_id}_content"
    content_dir.mkdir(exist_ok=True)

    # Экспорт по главам
    for orig_ch in original_text["chapters"]:
        chapter_number = orig_ch["chapter_number"]
        simp_ch = next((c for c in (simplified_text or {}).get(
            "chapters", []) if c["chapter_number"] == chapter_number), {})
        task_ch = next((c for c in (original_tasks or {}).get(
            "chapters", []) if c["chapter_number"] == chapter_number), {})
        simp_task_ch = next((c for c in (simplified_tasks or {}).get(
            "chapters", []) if c["chapter_number"] == chapter_number), {})

        paragraphs = []
        for orig_p in orig_ch["paragraphs"]:
            para_num = orig_p["paragraph_number"]

            simp_p = next((p for p in simp_ch.get("paragraphs", [])
                          if p["paragraph_number"] == para_num), {})
            task_p = next((p for p in task_ch.get("paragraphs", [])
                          if p["paragraph_number"] == para_num), {})
            simp_task_p = next((p for p in simp_task_ch.get(
                "paragraphs", []) if p["paragraph_number"] == para_num), {})

            paragraphs.append({
                "paragraph_number": para_num,
                "sentences_original": orig_p.get("sentences", []),
                "sentences_simplified": simp_p.get("sentences", []),
                "tasks_original": {
                    "true_or_false": task_p.get("true_or_false"),
                    "how_to_translate": task_p.get("how_to_translate"),
                    "two_words": task_p.get("two_words")
                },
                "tasks_simplified": {
                    "true_or_false": simp_task_p.get("true_or_false"),
                    "how_to_translate": simp_task_p.get("how_to_translate"),
                    "two_words": simp_task_p.get("two_words")
                }
            })

        chapter_data = {
            "chapter_number": chapter_number,
            "paragraphs": paragraphs
        }

        chapter_path = content_dir / \
            f"book_{book_id}_chapter{chapter_number}_{source_lang}_{target_lang}.json"
        with open(chapter_path, "w", encoding="utf-8") as f:
            json.dump(chapter_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Сохранена глава: {chapter_path}")

    # 📄 Сохраняем мета-информацию
    info_data = {
        "title": localized_title,
        "author": localized_author,
        "year": year,
        "words": meta.get("words"),
        "genre": meta.get("genre"),
        "set": meta.get("set"),
        "source_lang": source_lang,
        "target_lang": target_lang
    }

    info_path = book_dir / \
        f"book_{book_id}_info_{source_lang}_{target_lang}.json"
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info_data, f, ensure_ascii=False, indent=2)
    print(f"✅ Сохранена информация о книге: {info_path}")


def fetch_localized_title_and_author(title: str, author: str, year: str, target_lang: str) -> LocalizedMeta:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = (
        f"Ты литературный редактор. "
        f"Определи, под каким названием книга '{title}' автора '{author}' {year} года "
        f"чаще всего публиковалась на языке {target_lang}. "
        f"Также переведи имя автора на язык {target_lang}, если оно имеет общепринятый перевод. "
        f"Верни строго JSON-объект в соответствии со схемой."
    )

    completion = client.beta.chat.completions.parse(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"title: {title}\nauthor: {author}\nyear: {year}"}
        ],
        response_format=LocalizedMeta,
    )

    return completion.choices[0].message.parsed

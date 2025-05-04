import os
import json
from pathlib import Path
from utils.supabase_client import get_supabase_client
from schemas.export_schema import LocalizedMeta
from openai import OpenAI


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

    result = {
        "title": localized_title,
        "author": localized_author,
        "year": year,
        "words": meta.get("words"),
        "genre": meta.get("genre"),
        "set": meta.get("set"),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "chapters": []
    }

    # Сборка всех параграфов
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

        result["chapters"].append({
            "chapter_number": chapter_number,
            "paragraphs": paragraphs
        })

    # Папка для сохранения
    output_dir = Path("export") / f"book_{book_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    full_path = output_dir / f"book_{book_id}_merged.json"
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"✅ Экспортировано: {full_path}")

    # Только первая глава
    chapter1_path = output_dir / f"book_{book_id}_merged_chapter1.json"
    chapter1_data = {**result, "chapters": [result["chapters"][0]]}
    with open(chapter1_path, "w", encoding="utf-8") as f:
        json.dump(chapter1_data, f, ensure_ascii=False, indent=2)
    print(f"✅ Экспортировано: {chapter1_path}")


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

import os
import json
from pathlib import Path
from utils.supabase_client import get_supabase_client
from schemas.export_schema import LocalizedMeta
from openai import OpenAI
from tqdm import tqdm


def fetch_localized_title_and_author(title: str, author: str, year: str, target_lang: str) -> LocalizedMeta:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    lang_map = {
        "en": "английском",
        "es": "испанском",
        "fr": "французском",
        "de": "немецком",
        "it": "итальянском",
        "ru": "русском",
        "pt": "португальском",
        "tr": "турецком",
        "ja": "японском"

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


def extract_task(task_data, chapter_number, para_number, field):
    chapter = next((c for c in (task_data or {}).get(
        "chapters", []) if c["chapter_number"] == chapter_number), {})
    paragraph = next((p for p in chapter.get("paragraphs", [])
                     if p["paragraph_number"] == para_number), {})
    return paragraph.get(field)


def export_book_json(book_id_start: int, book_id_end: int, source_lang: str, target_langs: list[str]):
    print(
        f"🚀 Экспорт книг с ID {book_id_start}–{book_id_end} для языков: {', '.join(target_langs)}")

    supabase = get_supabase_client()
    export_dir = Path("export/content")
    export_dir.mkdir(parents=True, exist_ok=True)

    books_info = []

    for book_id in tqdm(range(book_id_start, book_id_end + 1), desc="📦 Книги", unit="кн"):
        exists_response = supabase.table("books").select(
            "id").eq("id", book_id).maybe_single().execute()
        if not exists_response or not exists_response.data:
            print(f"⏭ Пропуск ID {book_id} — книги нет в таблице books.")
            continue

        # meta_response = supabase.table("books_full_view").select(
        #    "year, words, genre, set"
        # ).eq("id", book_id).single().execute()

        for target_lang in target_langs:

            meta_response = supabase.table("book_export_view").select(
                "year, words, genre, set"
            ).eq("book_id", book_id).eq("language", target_lang).maybe_single().execute()

            if not meta_response.data:
                print(
                    f"⚠️ Пропуск ID {book_id} — нет данных в book_export_view.")
                continue

            meta = meta_response.data
            year = meta.get("year", "")
            words = meta.get("words", "")
            genre = meta.get("genre", "")
            book_set = meta.get("set", "")

            trans_response = supabase.table("books_translations").select(
                "title, author, "
                "text_by_chapters_sentence_translation_words, "
                "text_by_chapters_simplified_sentence_translation_words, "
                "tasks_true_or_false, "
                "tasks_true_or_false_simplified, "
                "tasks_truefalse_howto, "
                "tasks_truefalse_howto_simplified, "
                "tasks_truefalse_howto_words, "
                "tasks_truefalse_howto_words_simplified"
            ).eq("book_id", book_id).eq("language", target_lang).maybe_single().execute()

            if not trans_response.data:
                print(f"   ⏭ Язык {target_lang} — перевода нет.")
                continue

            data = trans_response.data
            localized_title = data.get("title", "")
            localized_author = data.get("author", "")

            original_text = json.loads(data["text_by_chapters_sentence_translation_words"]) if data.get(
                "text_by_chapters_sentence_translation_words") else None
            simplified_text = json.loads(data["text_by_chapters_simplified_sentence_translation_words"]) if data.get(
                "text_by_chapters_simplified_sentence_translation_words") else None

            # Tasks по типам
            tasks_true_or_false = json.loads(data["tasks_true_or_false"]) if data.get(
                "tasks_true_or_false") else None
            tasks_true_or_false_s = json.loads(data["tasks_true_or_false_simplified"]) if data.get(
                "tasks_true_or_false_simplified") else None

            tasks_how_to_translate = json.loads(data["tasks_truefalse_howto"]) if data.get(
                "tasks_truefalse_howto") else None
            tasks_how_to_translate_s = json.loads(data["tasks_truefalse_howto_simplified"]) if data.get(
                "tasks_truefalse_howto_simplified") else None

            tasks_two_words = json.loads(data["tasks_truefalse_howto_words"]) if data.get(
                "tasks_truefalse_howto_words") else None
            tasks_two_words_s = json.loads(data["tasks_truefalse_howto_words_simplified"]) if data.get(
                "tasks_truefalse_howto_words_simplified") else None

            if not original_text:
                print(f"   ⚠️ Нет основного текста — создаём заглушку.")
                original_text = {
                    "chapters": [{
                        "chapter_number": 1,
                        "paragraphs": [{
                            "paragraph_number": 1,
                            "sentences": []
                        }]
                    }]
                }

            for orig_ch in original_text["chapters"]:
                chapter_number = orig_ch["chapter_number"]
                simp_ch = next((c for c in (simplified_text or {}).get(
                    "chapters", []) if c["chapter_number"] == chapter_number), {})

                paragraphs = []
                for orig_p in orig_ch["paragraphs"]:
                    para_num = orig_p["paragraph_number"]

                    simp_p = next((p for p in simp_ch.get(
                        "paragraphs", []) if p["paragraph_number"] == para_num), {})

                    paragraphs.append({
                        "paragraph_number": para_num,
                        "sentences_original": orig_p.get("sentences", []),
                        "sentences_simplified": simp_p.get("sentences", []),
                        "tasks_original": {
                            "true_or_false": extract_task(tasks_true_or_false, chapter_number, para_num, "true_or_false"),
                            "how_to_translate": extract_task(tasks_how_to_translate, chapter_number, para_num, "how_to_translate"),
                            "two_words": extract_task(tasks_two_words, chapter_number, para_num, "two_words")
                        },
                        "tasks_simplified": {
                            "true_or_false": extract_task(tasks_true_or_false_s, chapter_number, para_num, "true_or_false"),
                            "how_to_translate": extract_task(tasks_how_to_translate_s, chapter_number, para_num, "how_to_translate"),
                            "two_words": extract_task(tasks_two_words_s, chapter_number, para_num, "two_words")
                        }
                    })

                chapter_data = {
                    "chapter_number": chapter_number,
                    "paragraphs": paragraphs
                }

                chapter_path = export_dir / \
                    f"book_{book_id}_{source_lang}_{target_lang}_chapter{chapter_number}.json"
                with open(chapter_path, "w", encoding="utf-8") as f:
                    json.dump(chapter_data, f, ensure_ascii=False, indent=2)
                print(f"✅ Сохранена глава: {chapter_path.name}")

            books_info.append({
                "id": f"book_{book_id}",
                "title": localized_title,
                "author": localized_author,
                "year": year,
                "words": words,
                "genre": genre,
                "set": book_set,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "chapters": len(original_text["chapters"])
            })

    # Сохраняем общий список книг выше папки content
    books_path = export_dir.parent / "books.json"
    with open(books_path, "w", encoding="utf-8") as f:
        json.dump(books_info, f, ensure_ascii=False, indent=2)
    print(f"\n📘 Экспорт завершён. Список книг сохранён в: {books_path}")

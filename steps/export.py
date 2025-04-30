import os
import json
from pathlib import Path
from utils.supabase_client import get_supabase_client


def export_book_json(book_id: int, source_lang: str, target_lang: str):
    supabase = get_supabase_client()

    print(f"📦 Экспорт книги ID {book_id}...")

    # Получаем метаданные книги из представления
    meta_response = supabase.table("books_full_view").select(
        "title, author, year, words, genre, set"
    ).eq("id", book_id).single().execute()

    if not meta_response.data:
        print("❌ Не удалось получить метаданные книги.")
        return

    meta = meta_response.data

    fields = [
        ("text_by_chapters_sentence_translation_words", ""),
        ("text_by_chapters_simplified_sentence_translation_words", "_s")
    ]

    for text_field, suffix in fields:
        response = supabase.table("books").select(
            text_field).eq("id", book_id).single().execute()
        content = response.data.get(text_field)

        if not content:
            print(f"⚠️ Нет данных в поле {text_field}, пропускаем.")
            continue

        try:
            book_json = json.loads(content) if isinstance(
                content, str) else content
        except Exception as e:
            print(f"❌ Ошибка разбора JSON в {text_field}: {e}")
            continue

        export_data = {
            "title": meta.get("title"),
            "author": meta.get("author"),
            "year": meta.get("year"),
            "words": meta.get("words"),
            "genre": meta.get("genre"),
            "set": meta.get("set"),
            "source_lang": source_lang,
            "target_lang": target_lang,
            "chapters": book_json["chapters"]
        }

        output_dir = Path("export")
        output_dir.mkdir(exist_ok=True)

        output_path = output_dir / f"book_{book_id}{suffix}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        print(f"✅ Экспортировано: {output_path}")

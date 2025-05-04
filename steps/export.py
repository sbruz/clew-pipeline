import os
import json
from pathlib import Path
from utils.supabase_client import get_supabase_client


def export_book_json(book_id: int, source_lang: str, target_lang: str):
    supabase = get_supabase_client()
    print(f"📦 Экспорт книги ID {book_id}...")

    # Метаданные
    meta_response = supabase.table("books_full_view").select(
        "title, author, year, words, genre, set"
    ).eq("id", book_id).single().execute()

    if not meta_response.data:
        print("❌ Не удалось получить метаданные книги.")
        return

    meta = meta_response.data

    # Загрузка всех нужных полей
    def fetch_json(field):
        response = supabase.table("books").select(
            field).eq("id", book_id).single().execute()
        return json.loads(response.data[field]) if response.data.get(field) else None

    original_text = fetch_json("text_by_chapters_sentence_translation_words")
    simplified_text = fetch_json(
        "text_by_chapters_simplified_sentence_translation_words")
    original_tasks = fetch_json("tasks_truefalse_howto_words")
    simplified_tasks = fetch_json("tasks_truefalse_howto_words_simplified")

    if not original_text:
        print("❌ Нет данных в оригинальном тексте.")
        return

    result = {
        "title": meta.get("title"),
        "author": meta.get("author"),
        "year": meta.get("year"),
        "words": meta.get("words"),
        "genre": meta.get("genre"),
        "set": meta.get("set"),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "chapters": []
    }

    missing_simplified = []
    missing_tasks = []

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

            # Проверка на пропущенные
            if not simp_p:
                missing_simplified.append(f"{chapter_number}.{para_num}")
            if not task_p or not simp_task_p:
                missing_tasks.append(f"{chapter_number}.{para_num}")

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

    # Сообщаем, если были пропущенные абзацы
    if missing_simplified:
        print(f"⚠️ Не найдены упрощённые абзацы: {missing_simplified}")
    if missing_tasks:
        print(f"⚠️ Не найдены задания для: {missing_tasks}")

    # Сохраняем
    output_dir = Path(f"export_book_{book_id}")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"book_{book_id}_merged.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ Экспортировано: {output_path}")

    # Только первая глава
    chapter1 = {
        **result,
        "chapters": [result["chapters"][0]]
    }

    chapter1_path = output_dir / f"book_{book_id}_merged_chapter1.json"
    with open(chapter1_path, "w", encoding="utf-8") as f:
        json.dump(chapter1, f, ensure_ascii=False, indent=2)
    print(f"✅ Экспортировано: {chapter1_path}")

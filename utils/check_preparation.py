import json
from utils.supabase_client import get_supabase_client


def check_before_translate(book_id: int):
    supabase = get_supabase_client()

    print(f"📥 Проверка книги ID {book_id} перед переводом...")

    # 1. Загружаем данные из таблицы books
    fields = [
        "original_text",
        "formated_text",
        "splitted_text",
        "separated_text",
        "separated_text_verified",
        "text_by_chapters",
        "text_by_chapters_simplified"
    ]

    response = supabase.table("books").select(
        ", ".join(fields)).eq("id", book_id).single().execute()
    data = response.data

    original_text = data.get("original_text") or ""

    def check_length_ratio(field_name):
        field_value = data.get(field_name) or ""
        ratio = len(field_value) / len(original_text) if original_text else 1
        if ratio < 0.95:
            print(
                f"❌ FAILED: {field_name} содержит только {ratio * 100:.2f}% символов от original_text")
        else:
            print(
                f"✅ OK: {field_name} содержит {ratio * 100:.2f}% символов от original_text")

    for field in [
        "formated_text",
        "splitted_text",
        "separated_text",
        "separated_text_verified"
    ]:
        check_length_ratio(field)

    # Очистка text_by_chapters и text_by_chapters_simplified от форматирования
    def extract_text(json_text):
        try:
            obj = json.loads(json_text)
            paragraphs = [
                p["paragraph_content"]
                for chapter in obj.get("chapters", [])
                for p in chapter.get("paragraphs", [])
            ]
            return paragraphs
        except Exception as e:
            print(f"⚠️ Ошибка при разборе текста: {e}")
            return []

    chapters_paragraphs = extract_text(data.get("text_by_chapters") or "")
    simplified_paragraphs = extract_text(
        data.get("text_by_chapters_simplified") or "")

    joined_chapters_text = " ".join(chapters_paragraphs)
    length_ratio = len(joined_chapters_text) / \
        len(original_text) if original_text else 1
    if length_ratio < 0.95:
        print(
            f"❌ FAILED: text_by_chapters содержит только {length_ratio * 100:.2f}% символов от original_text")
    else:
        print("✅ OK: text_by_chapters содержит достаточный объём текста")

    # 4. Проверка совпадения количества абзацев по главам
    def get_paragraph_counts(json_text):
        try:
            obj = json.loads(json_text)
            return {
                chapter["chapter_number"]: len(chapter.get("paragraphs", []))
                for chapter in obj.get("chapters", [])
            }
        except Exception as e:
            print(f"⚠️ Ошибка при разборе глав: {e}")
            return {}

    chapter_counts = get_paragraph_counts(data.get("text_by_chapters") or "")
    simplified_counts = get_paragraph_counts(
        data.get("text_by_chapters_simplified") or "")

    all_ok = True
    for chapter_num, count in chapter_counts.items():
        simplified_count = simplified_counts.get(chapter_num)
        if simplified_count != count:
            print(
                f"❌ FAILED: Глава {chapter_num} — {count} абзацев в оригинале, {simplified_count} в упрощённом")
            all_ok = False

    if all_ok:
        print("✅ OK: количество абзацев по главам совпадает")

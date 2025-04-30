import os
from supabase import create_client, Client


def get_supabase_client() -> Client:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("❌ SUPABASE_URL или SUPABASE_KEY не заданы.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def load_book_text(book_id: int) -> str:
    supabase = get_supabase_client()
    print(f"📥 Загрузка original_text для книги {book_id}...")
    response = supabase.table("books").select(
        "original_text").eq("id", book_id).single().execute()
    if response.data and response.data.get("original_text"):
        return response.data["original_text"]
    raise ValueError("❌ Не удалось загрузить текст книги.")


def save_formatted_text(book_id: int, formatted_text: str):
    supabase = get_supabase_client()
    print(f"📤 Сохраняем formated_text для книги {book_id}...")
    supabase.table("books").update(
        {"formated_text": formatted_text}).eq("id", book_id).execute()
    print("✅ Сохранение завершено.")


def check_supabase_connection():
    supabase = get_supabase_client()
    try:
        response = supabase.table("books").select("id").execute()
        if response.data:
            print(
                f"✅ Успешное подключение. Найдено {len(response.data)} записей.")
        else:
            print("⚠️ Подключение успешно, но записей нет.")
    except Exception as e:
        print("❌ Ошибка при подключении к Supabase:", e)

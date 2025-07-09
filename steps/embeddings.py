import os
from openai import OpenAI
from utils.supabase_client import get_supabase_client


def generate_embedding(book_id: int):
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print(f"EMB[{book_id}] 📥 Загружаем жанр и автора книги...")
    # Получаем автора и жанр (внимание: поле genre, не genres!)
    response = supabase.table("book_export_view").select(
        "author, genre"
    ).eq("book_id", book_id).eq("language", "ru").single().execute()

    # Проверка на ошибки и корректность данных
    if not response.data or not isinstance(response.data, dict):
        print(
            f"EMB[{book_id}] ❌ Не найдены жанр или автор, либо некорректный ответ.")
        print(f"EMB[{book_id}] ⛔ Ответ: {response.data}")
        if hasattr(response, "error") and response.error:
            print(f"EMB[{book_id}] ❌ Ошибка Supabase: {response.error}")
        return

    author = response.data.get("author", "")
    genre = response.data.get("genre", "")

    print(f"EMB[{book_id}] ✍️ Автор: '{author}' | Жанр: '{genre}'")

    combined = f"{author} {genre}".replace(",", " ")
    combined = " ".join(combined.split())

    print(f"EMB[{book_id}] 🔄 Итоговая строка для embedding: '{combined}'")

    # Генерируем embedding
    try:
        print(f"EMB[{book_id}] 🧠 Запрашиваем embedding через OpenAI...")
        embedding_response = client.embeddings.create(
            input=combined,
            model="text-embedding-3-small"
        )
        embedding = embedding_response.data[0].embedding
        print(f"EMB[{book_id}] ✅ Получен embedding длиной {len(embedding)}")
    except Exception as e:
        print(f"EMB[{book_id}] ❌ Ошибка при генерации embedding: {e}")
        return

    # --- Формируем строку для real[] ---
    embedding_str = "{" + ",".join(str(x) for x in embedding) + "}"

    # Сохраняем embedding в таблицу books
    try:
        print(f"EMB[{book_id}] 💾 Сохраняем embedding в таблицу books...")
        supabase.table("books").update(
            {"embedding": embedding_str}
        ).eq("id", book_id).execute()
        print(f"EMB[{book_id}] ✅ Embedding успешно сохранён.")
    except Exception as e:
        print(f"EMB[{book_id}] ❌ Ошибка при сохранении embedding: {e}")
        return

import os
import json
import base64
import yaml
from pathlib import Path
from openai import OpenAI
from utils.supabase_client import get_supabase_client
from schemas.pictures import BookObject, BookObjectsResponse
from PIL import Image
import numpy as np
import io


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def enhance_highlights_and_shadows(image_bytes):
    # Открыть изображение из байтов
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    arr = np.array(image).astype(np.float32) / 255.0

    # Крутая S-кривая: экстремальный контраст
    def contrast_boost(x):
        return np.clip((x - 0.5) * 4 + 0.5, 0, 1)
    arr_boosted = contrast_boost(arr)
    arr_boosted = (arr_boosted * 255).astype(np.uint8)
    result_image = Image.fromarray(arr_boosted, mode="RGB")
    # Ресайз до 512x512
    result_image = result_image.resize((512, 512), Image.LANCZOS)

    return result_image


def get_image_score_via_openai(client, eval_prompt, pil_image):
    import base64
    import io
    buffered = io.BytesIO()
    pil_image.save(buffered, format="WEBP")
    image_bytes = buffered.getvalue()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    messages = [
        {"role": "system", "content": "Ты — эксперт по иллюстрациям книг и визуальному анализу."},
        {"role": "user", "content": [
            {"type": "text", "text": eval_prompt},
            {"type": "image_url", "image_url": {
                "url": f"data:image/webp;base64,{image_base64}"}}
        ]}
    ]
    response = client.chat.completions.create(
        model="gpt-4o",  # Важно: vision модель!
        messages=messages,
        max_tokens=4
    )
    try:
        score = int(response.choices[0].message.content.strip())
    except Exception:
        score = 1
    return score


def generate_object_pictures_for_book(
    book_id: int,
    config_path: str = "config.yaml"
):
    import base64
    import io
    from pathlib import Path

    print("🚀 Запуск генерации иллюстраций для книги.")
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    config = load_config(config_path)

    # 1. Получение данных о книге
    print(f"📚 Получаем данные книги (book_id={book_id}) ...")
    response = supabase.table("books").select(
        "title, author, text_by_chapters"
    ).eq("id", book_id).single().execute()
    if not response.data:
        print("❌ Книга не найдена")
        return

    data = response.data
    title = data["title"]
    author = data["author"]
    chapters = json.loads(data["text_by_chapters"])["chapters"]
    print(f"✅ Книга найдена: {title} ({author}). Глав: {len(chapters)}")

    # 2. Формируем единый список абзацев с уникальным id
    paragraphs_with_id = []
    total_paragraphs = 0
    for chapter in chapters:
        chapter_number = chapter["chapter_number"]
        if chapter_number > 2:
            continue
        for idx, paragraph in enumerate(chapter["paragraphs"]):
            para_id = f"book_{book_id}_{chapter_number}_{idx+1}"
            paragraphs_with_id.append({
                "id": para_id,
                "text": paragraph
            })
            total_paragraphs += 1
    print(f"📝 Всего абзацев: {total_paragraphs}")

    # 3. Запрос в OpenAI для определения ключевых объектов
    print("🤖 Запрос к OpenAI: определение предметов для иллюстрации ...")
    book_text = "\n\n".join(
        [f"[{p['id']}]\n{p['text']}" for p in paragraphs_with_id]
    )
    system_prompt = (
        "Ты — литературовед и эксперт по визуальному сторителлингу.\n"
        f"Перед тобой текст книги '{title}' автора {author}, разбитый на абзацы с уникальными идентификаторами.\n"
        "Проанализируй абзацы и определи те, в которых первый раз появляются самые важные сюжета предметы или объекты.\n"
        "Не учитывай предметы, о которых говорят, но их нет в кадре.\n"
        "Для каждого такого абзаца дай такое детальное описание этого предмета или объекта, как задание на создание иллюстрации, чтобы его можно было нарисовать согласно сюжета и атмосферы книги. Не пиши имена персонажей, только предметы и объекты.\n"
        "Верни результат как экземпляр BookObjectsResponse, в котором objects — это массив объектов BookObject.\n"
        "BookObject: {\"paragraph_id\": ..., \"object_description\": ...}"
    )

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": book_text[:100000]}
            ],
            response_format=BookObjectsResponse
        )
        result = completion.choices[0].message.parsed
        object_list = result.objects
        print(f"✅ Получено {len(object_list)} объектов для иллюстраций.")
        for i, obj in enumerate(object_list, 1):
            print(f"   {i}. [{obj.paragraph_id}] {obj.object_description}")
    except Exception as e:
        print(f"❌ Ошибка при анализе книги: {e}")
        return

    # 4. Подготовка папки для экспорта
    output_dir = Path(f"export/pictures/book_{book_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📂 Папка для экспорта: {output_dir.resolve()}")

    # 5. Генерация изображений для каждого объекта (черный и белый фон)
    total_tasks = len(object_list) * 2
    task_count = 0
    print(f"🎨 Генерация {total_tasks} изображений ...")
    for obj_idx, obj in enumerate(object_list, 1):
        for bg in ["b", "w"]:  # b=black, w=white
            task_count += 1
            prompt_bg = config["styles"]["prompt_black_bg"] if bg == "b" else config["styles"]["prompt_white_bg"]

            prompt = (
                f"Style: {prompt_bg}\n"
                f"Object: {obj.object_description}. Draw only it.\n"
                f"Book: '{title}', author: {author}. Use it to draw according to the genre and period of time.\n"
                f"Focus on the main object and leave background clean. "
            )
            bg_label = "чёрный" if bg == "b" else "белый"
            print(
                f"[{task_count}/{total_tasks}] 🖼️ Генерация: [{obj.paragraph_id}] '{obj.object_description}', фон: {bg_label}")

            try:
                # === Первая генерация изображения ===
                response = client.images.generate(
                    model="gpt-image-1",
                    prompt=prompt,
                    n=1,
                    size="1024x1024"
                )
                image_base64_1 = response.data[0].b64_json
                if not image_base64_1:
                    print(
                        f"   ❌ Нет base64 для [{obj.paragraph_id}] ({bg_label})")
                    continue

                # --- Обработка контрастности и resize ---
                image_bytes_1 = base64.b64decode(image_base64_1)
                enhanced_image_1 = enhance_highlights_and_shadows(
                    image_bytes_1)

                # --- Оценка изображения OpenAI ---
                print(
                    "   📝 Оцениваем соответствие изображения описанию через OpenAI ...")
                eval_prompt = (
                    f"Оцени по 10-балльной шкале, насколько это изображение естественно, не содержит ошибок, соответствует текстовому описанию предмета.\n"
                    f"Описание предмета: {obj.object_description}\n"
                    f"Пожалуйста, верни только целое число от 1 до 10 без пояснений."
                )
                score_1 = get_image_score_via_openai(
                    client, eval_prompt, enhanced_image_1)
                print(f"   🔎 Оценка OpenAI: {score_1}/10")

                # Если оценка >=7 — сразу сохраняем
                if score_1 >= 7:
                    file_path = output_dir / f"{obj.paragraph_id}_{bg}.webp"
                    enhanced_image_1.save(file_path, format="WEBP")
                    print(
                        f"   ✅ Сохранено: {file_path.name} (оценка {score_1}/10)")
                    continue

                # === Повторная генерация изображения ===
                print("   ↩️ Оценка ниже 7, повторяем генерацию ...")
                response2 = client.images.generate(
                    model="gpt-image-1",
                    prompt=prompt,
                    n=1,
                    size="1024x1024"
                )
                image_base64_2 = response2.data[0].b64_json
                if not image_base64_2:
                    print(
                        f"   ❌ Нет base64 (2) для [{obj.paragraph_id}] ({bg_label})")
                    file_path = output_dir / f"{obj.paragraph_id}_{bg}.webp"
                    enhanced_image_1.save(file_path, format="WEBP")
                    print(
                        f"   ✅ Сохранено (первое изображение): {file_path.name}")
                    continue

                image_bytes_2 = base64.b64decode(image_base64_2)
                enhanced_image_2 = enhance_highlights_and_shadows(
                    image_bytes_2)
                score_2 = get_image_score_via_openai(
                    client, eval_prompt, enhanced_image_2)
                print(f"   🔎 Оценка OpenAI (2): {score_2}/10")

                # Выбираем лучшее изображение
                if score_2 > score_1:
                    file_path = output_dir / f"{obj.paragraph_id}_{bg}.webp"
                    enhanced_image_2.save(file_path, format="WEBP")
                    print(
                        f"   ✅ Сохранено: {file_path.name} (оценка {score_2}/10)")
                else:
                    file_path = output_dir / f"{obj.paragraph_id}_{bg}.webp"
                    enhanced_image_1.save(file_path, format="WEBP")
                    print(
                        f"   ✅ Сохранено (первое изображение): {file_path.name} (оценка {score_1}/10)")

            except Exception as e:
                print(
                    f"   ❌ Ошибка генерации для [{obj.paragraph_id}] ({bg_label}): {e}")

    print(f"🏁 Готово! Сгенерировано {task_count} файлов для книги '{title}'.")

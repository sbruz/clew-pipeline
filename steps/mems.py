import os
import io
import json
from pathlib import Path
from PIL import Image
from datetime import datetime, timezone
from openai import OpenAI
from utils.supabase_client import get_supabase_client
from schemas.mems import MemeIdea


def generate_memes_for_book(book_id: int, source_lang: str = "en"):
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = supabase.table("books").select(
        "title, author, text_by_chapters"
    ).eq("id", book_id).single().execute()

    data = response.data
    title = data["title"]
    author = data["author"]
    chapters = json.loads(data["text_by_chapters"])["chapters"]

    total_chapters = len(chapters)
    output_dir = Path(f"export/pictures/book_{book_id}")
    output_dir.mkdir(parents=True, exist_ok=True)

    lang_names_pr = {
        "en": "английском",
        "es": "испанском",
        "fr": "французском",
        "de": "немецком",
        "ru": "русском",
        "it": "итальянском",
        "pt": "португальском (бразильском)",
        "tr": "турецком",
        "ja": "японском"
    }
    readable_target_pr = lang_names_pr.get(source_lang, source_lang)

    for i, chapter in enumerate(chapters):
        chapter_number = chapter["chapter_number"]
        if chapter_number != 2:
            continue
        paragraphs = chapter["paragraphs"]
        print(f"\n📘 Глава {chapter_number} ({i+1}/{total_chapters})")

        chapter_text = "\n".join(
            [f"[{idx+1}] {p}" for idx, p in enumerate(paragraphs)])

        system_prompt_mem = (
            f"Ты — эксперт по визуальному сторителлингу и мемам.\n"
            f"Перед тобой текст главы из книги '{title}' автора {author}.\n"
            f"Выбери один абзац (нумерация начинается с единицы от начала главы) и придумай легкий для понимания мем — ироничный, саркастичный, самоироничный, эмоциональный и так далее.\n"
            f"Старайся использовать узнаваемую идею из существующих мемов. \n"
            f"Укажи в picture_description описание изображения сцены, героя мема или одушевленного предмета.\n"
            f"Укажи в picture_phrase слово или ключевую фразу до 5 слов из абзаца на {readable_target_pr} языке.\n"
            f"Напиши короткое лаконичное ТЗ на создание этого мема. Стиль рисования не описывай.\n"
            f"Верни ответ по формату."
        )

        system_prompt_comix = (
            f"Ты — эксперт по визуальному сторителлингу, комиксам и обучению чтению на {readable_target_pr} языке.\n"
            f"Перед тобой текст главы из книги '{title}' автора {author}.\n"
            f"Выбери абзац (нумерация начинается с единицы от начала главы), после которого мы добавим комикс для иллюстрации текста – ироничный, самоироничный, эмоциональный и так далее..\n"
            f"Придумай легкий для понимания комикс про прочитанному до этого абзаца материалу.\n"
            f"Укажи в picture_phrase какую короткую фразу или фразы из текста на {readable_target_pr} языке, нужно разместить на комиксе.\n"
            f"Укажи в picture_description имена героев, компоновку комиска, детали внешности героев и обстановки, соответствующие книге.\n"
            f"Стиль рисования не описывай.\n"
            f"Верни ответ по формату."
        )

        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4.1",
                messages=[
                    # поменять промт
                    {"role": "system", "content": system_prompt_comix},
                    {"role": "user", "content": chapter_text[:12000]}
                ],
                response_format=MemeIdea
            )
            result = completion.choices[0].message.parsed

            para_idx = result.paragraph_index
            meme_prompt = f"Описание комикса: {result.picture_description}\nРазмести текст: {result.picture_phrase}"

            generate_meme_image(
                book_id=book_id,
                chapter_id=chapter_number,
                paragraph_id=para_idx,
                prompt=meme_prompt,
                title=title,
                author=author
            )

        except Exception as e:
            print(f"❌ Ошибка генерации для главы {chapter_number}: {e}")

        print(f"📈 Прогресс: {round((i + 1) / total_chapters * 100)}%")


def generate_meme_image(book_id: int, chapter_id: int, paragraph_id: int, prompt: str, title: str, author: str):
    import base64
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    input_folder = Path(f"export/pictures/book_{book_id}")
    image_files = list(input_folder.glob("*.webp"))

    image_files = []
    for img_path in input_folder.glob("*.webp"):
        try:
            img = Image.open(img_path)
            w, h = img.size
            if w >= h:
                new_w, new_h = 512, int(h * (512 / w))
            else:
                new_h, new_w = 512, int(w * (512 / h))
            img = img.resize((new_w, new_h))
            buf = io.BytesIO()
            img.save(buf, format="WEBP")
            buf.seek(0)
            image_files.append(("image.webp", buf))
            img.close()
        except Exception:
            continue

    prompt_full_mem = (
        f"Нарисуй мем по мотивам книги '{title}' автора {author}.\n"
        f"Визуальный стиль и изображение персонажей должен соответствовать другим изображениям, если они даны.\n"
        f"{prompt}"
    )

    prompt_full_comix = (
        f"Нарисуй комикс по мотивам книги '{title}' автора {author}.\n"
        f"Визуальный стиль и изображение персонажей должен соответствовать другим изображениям, если они даны.\n"
        f"{prompt}"
    )

    # поменять промт
    print(f"🖼 Параграф {paragraph_id}\nРисуем: {prompt_full_comix}")
    model = "gpt-image-1"
    size = "1024x1024"

    if image_files:
        print("      🖼️ Примеры стиля: переданы")
        response = client.images.edit(
            model=model,
            image=image_files,
            prompt=prompt_full_comix,   # поменять промт
            n=1,
            size=size,
            user=f"book-meme:{int(datetime.now(timezone.utc).timestamp())}"
        )
        image_base64 = response.data[0].b64_json

        # Закрываем буферы
        for _, buf in image_files:
            buf.close()
    else:
        print("      🎨 Примеры стиля: отсутствуют")
        response = client.images.generate(
            model=model,
            prompt=prompt_full_comix,   # поменять промт
            n=1,
            size=size,
            user=f"book-meme:{int(datetime.now(timezone.utc).timestamp())}"
        )
        image_base64 = response.data[0].b64_json

    if not image_base64:
        raise ValueError("❌ OpenAI не вернул base64 изображение.")

    filepath = Path(
        f"export/pictures/book_{book_id}/book_{book_id}_{chapter_id}_{paragraph_id}.webp")
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(image_base64))
    print(f"✅ Сохранено: {filepath}")

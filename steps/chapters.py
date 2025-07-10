import os
import json
import time
import glob
import base64
import google.generativeai as genai
from openai import OpenAI
from utils.supabase_client import get_supabase_client
from PIL import Image
from PIL import ImageEnhance
from io import BytesIO

ICON_STYLE_PAOLINI = "Cheerful, storybook illustration style with playful ink lines and bright, soft watercolors; friendly, round-faced characters in simple, expressive poses; light, sunny palette with creamy whites, warm yellows, and cheerful greens; scenes filled with animals, flowers, and handcrafted details; evokes joy, innocence, and a gentle sense of adventure — perfect for light-hearted fantasy or cozy rural tales."
ICON_STYLE = "Bold, optimized for high visual clarity at small sizes illustration; characters shown in close-up or bust format with simplified, expressive forms and thick, readable silhouettes; flat or slightly gradient shading with minimal texture for sharp edge definition; strong contrast between character and background — clean color blocking and focused rim lighting for instant legibility; color palette tuned for recognizability: vibrant key tones (warm reds, cool cyans, bright yellows) over muted or monochrome backdrops; minimalistic composition with centered framing and balanced negative space; no visual noise or fine details that blur when downscaled; illustration rendered on a solid, non-transparent background for consistent appearance across all platforms; evokes personality and clarity in a format designed for avatars, buttons, app icons, and UI thumbnails."
ICON_STYLE_ICON = "Bold, icon-optimized stylized illustration with high visual clarity at small sizes; characters shown in close-up or bust format with simplified, expressive forms and thick, readable silhouettes; flat or slightly gradient shading with minimal texture for sharp edge definition; strong contrast between character and background — clean color blocking and focused rim lighting for instant legibility; color palette tuned for recognizability: vibrant key tones (warm reds, cool cyans, bright yellows) over muted or monochrome backdrops; minimalistic composition with centered framing and balanced negative space; no visual noise or fine details that blur when downscaled; illustration rendered on a solid, non-transparent background for consistent appearance across all platforms; evokes personality and clarity in a format designed for avatars, buttons, app icons, and UI thumbnails."
ICON_STYLE_GOOD_LIGHTER = "Bold illustration with high visual clarity at small sizes; characters shown in close-up or bust format with simplified, expressive forms and thick, readable silhouettes; flat or slightly gradient shading with minimal texture for sharp edge definition; strong contrast between character and background — clean color blocking and focused rim lighting for instant legibility; color palette tuned for recognizability: vibrant key tones over muted or monochrome backdrops; minimalistic composition with centered framing and balanced negative space; no visual noise or fine details that blur when downscaled; icon rendered on a solid, non-transparent background for consistent appearance across all platforms; evokes personality and clarity in a format designed for avatars, buttons, app icons, and UI thumbnails. Use a slightly brighter palette, preserving contrast but shifting away from overly dark or muted tones."
ICON_STYLE_LIGHT_DISNEY = "Stylized digital illustration with a clean, high-clarity look optimized for modern UI thumbnails and avatars. Characters appear in close-up or bust format with bold, simplified forms and smooth, readable contours. Shading is flat or uses subtle soft gradients with no heavy textures, giving a polished, digital-native feel. Strong silhouette design and rim lighting enhance edge separation. Color palette emphasizes slightly brighter, saturated key tones layered over soft desaturated backgrounds for visual pop — avoiding muddy or overly dark tones. Composition is tightly framed, centered, with minimal internal padding and no visual clutter. No transparency; background is solid and consistent. Designed to retain character and emotion even at small scales — with a contemporary gloss, UI friendliness, and cross-platform adaptability."
ICON_STYLE_BRIGHT = "Bold, icon-optimized stylized illustration with high visual clarity at small sizes; characters shown in close-up or bust format with simplified, expressive forms and thick, readable silhouettes; flat or slightly gradient shading with minimal texture for sharp edge definition; strong contrast between character and background — clean color blocking and focused rim lighting for instant legibility; color palette tuned for recognizability: vibrant key tones (warm reds, cool cyans, bright yellows) over softened, gently tinted backdrops instead of dark or muted tones; overall brightness slightly elevated to avoid murky or overly shadowed areas, ensuring a light, approachable feel; minimalistic composition with centered framing and balanced negative space; no visual noise or fine details that blur when downscaled; illustration rendered on a solid, non-transparent background for consistent appearance across all platforms; evokes personality and clarity in a format designed for avatars, buttons, app icons, and UI thumbnails."

LANG_NAME_RU_CASE = {
    "ru": "русский",
    "en": "английский",
    "es": "испанский",
    "fr": "французский",
    "it": "итальянский",
    "ja": "японский",
    "pt": "португальский",
    "tr": "турецкий",
    "de": "немецкий",
}


def generate_titles(book_id: int, book_title: str, book_author: str):
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print(f"CHAP[{book_id}] 📥 Загружаем text_by_chapters...")
    response = supabase.table("books").select(
        "text_by_chapters"
    ).eq("id", book_id).single().execute()
    text_data = response.data.get("text_by_chapters")

    if not text_data:
        print(f"CHAP[{book_id}] ❌ Нет text_by_chapters для книги.")
        return

    data = json.loads(text_data)
    chapters = data["chapters"]
    result = {"chapters": []}

    prev_summaries = []
    # Шаг 1: генерируем summary для каждой главы (с retry)
    for chapter in chapters:
        chapter_number = chapter.get("chapter_number")
        print(
            f"\nCHAP[{book_id}] 📘 Глава {chapter_number}: Генерируем краткое содержание...")

        # Склеиваем параграфы в один текст
        full_text = "\n".join(
            p["paragraph_content"] for p in chapter.get("paragraphs", [])
        )

        context = ""
        if prev_summaries:
            context = "Вот что было до этой главы:\n" + \
                "\n".join(prev_summaries) + "\n\n"

        system_prompt = (
            f"Ты литературный редактор. Прочитай текст главы из книги '{book_title}' автора {book_author}. "
            f"Сделай очень краткое содержание главы на английском: ключевые факты без воды.\n"
            f"{'Используй контекст предыдущих глав. ' + context if context else ''}"
            f"\nВерни только краткое содержание (summary), никаких пояснений и метаданных."
        )
        user_prompt = f"{context}Текст главы:\n{full_text}"

        summary = None
        for attempt in range(2):
            try:
                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                summary = completion.choices[0].message.content.strip()
                print(f"CHAP[{book_id}] ✅ Summary получен.")
                break
            except Exception as e:
                print(
                    f"CHAP[{book_id}] ❌ Ошибка при генерации summary (попытка {attempt+1}): {e}")
                time.sleep(1)
        if summary is None:
            print(
                f"CHAP[{book_id}] ❌ Не удалось сгенерировать summary для главы {chapter_number} за 2 попытки. Останавливаем функцию.")
            return
        prev_summaries.append(summary)
        chapter["summary"] = summary

    # Шаг 2: генерируем кликбейтные заголовки (с retry)
    prev_summaries = []
    for chapter in chapters:
        chapter_number = chapter.get("chapter_number")
        summary = chapter["summary"]

        context = ""
        if prev_summaries:
            context = "Вот что было до этой главы:\n" + \
                "\n".join(prev_summaries) + "\n\n"

        print(
            f"CHAP[{book_id}] 🏷 Генерируем кликбейтный заголовок для главы {chapter_number}...")

        system_prompt = (
            f"Ты креативный редактор. Придумай очень короткий кликбейтный заголовок до 8 слов на английском языке для главы из книги '{book_title}' автора {book_author}, опираясь на её краткое содержание.\n"
            f"Сфокусируйся на том, что максимально интересно простым людям: сложные отношения людей, преодоление, сомнения, опасности, победы, все что удерживает в телешоу и сериалах....\n"
            f"Это должно быть одно простое предложение.\n"
            f"Избегай перечислений.\n"
            f"{'Используй контекст предыдущих глав. ' + context if context else ''}"
            f"\nВерни только заголовок, без кавычек, без пояснений."
        )
        user_prompt = f"{context}Краткое содержание главы:\n{summary}"

        title = None
        for attempt in range(2):
            try:
                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                )
                title = completion.choices[0].message.content.strip()
                print(f"CHAP[{book_id}] ✅ Title получен: {title}")
                break
            except Exception as e:
                print(
                    f"CHAP[{book_id}] ❌ Ошибка при генерации title (попытка {attempt+1}): {e}")
                time.sleep(1)
        if title is None:
            print(
                f"CHAP[{book_id}] ❌ Не удалось сгенерировать title для главы {chapter_number} за 2 попытки. Останавливаем функцию.")
            return
        chapter["title"] = title
        prev_summaries.append(summary)

    # Формируем итоговый JSON (только номера, title, summary)
    result["chapters"] = [
        {
            "chapter_number": chapter.get("chapter_number"),
            "title": chapter.get("title"),
            "summary": chapter.get("summary")
        }
        for chapter in chapters
    ]

    # Сохраняем результат
    print(f"CHAP[{book_id}] 💾 Сохраняем chapters_titles...")
    supabase.table("books").update(
        {"chapters_titles": json.dumps(result, ensure_ascii=False, indent=2)}
    ).eq("id", book_id).execute()
    print(f"CHAP[{book_id}] ✅ chapters_titles успешно сохранены.")


def generate_image_icon(user_ref, title, author, content, style, model="gpt-image-1", size="1024x1024"):
    prompt = (
        f"Нарисуй иллюстрацию для главы книги '{title}' автора {author} по описанию сцены '{content}'.\n"
        f"Не выводи никаких надписей на иконке. И не пиши название и автора.\n"
        f"Стиль должен быть таким: {style}. Цветовая палитра соответствует настроению книги и содержанию главы."
    )
    print("   🔍 Отправка запроса в OpenAI:")
    print(f"      📝 Промпт: {prompt}")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.images.generate(
        model=model,
        prompt=prompt,
        n=1,
        size=size,
        user=user_ref
    )

    image_base64 = response.data[0].b64_json
    if not image_base64:
        raise ValueError("❌ OpenAI не вернул base64 изображение.")

    image_bytes = base64.b64decode(image_base64)
    return image_bytes


def generate_scene_description(summary, chapter_number, title, author, prev_scene=None):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    context = ""
    if prev_scene:
        context = (
            "Если в кадре есть те же герои, что и в иллюстрациях к предыдущим главам, то их одежда и внешность не должны противоречить их последнему описанию, но обязательно отражай в задании изменения внешности, описанные в новой главе.\n"
            f"Вот описание из прыдыдущей главы: {prev_scene}\n\n"

        )

    system_prompt = (
        "Ты креативный иллюстратор художественных книг. "
        "На основе краткого содержания главы и твоих знаний о чем книга, создай краткое техническое задание на отрисовку иллюстрации, для главы книги. "
        "Выбирай момент, оставляющую интригу, порождающий вопросы.\n"
        "Опиши только зрительную сцену, без пояснений, без деталей не относящихся к иллюстрации: композиция, передний план, задний план.\n"
        "Назови каждого персонажа, который присутствует на сцене, укажи его роль в книге и подбробно опиши:\n"
        "– Внешность: лицо, волосы, борода, усы, телосложение, руки, ноги и так далее (форма, цвет, особенности).\n"
        "– Одежда и обувь: есть ли головной убор, что одето, что на ногах (фасон, цвет, особенности).\n"
        "– Аксессуары: есть ли что-то на одежде, если что-то в руках (форма, цвет, особенности).\n\n"
        "Учти в задании, что иллюстрация должна быть оптимизирована для использования в маленьком размере, без множества мелких предметов, крупно основное действие или объект.\n"
        f"{context}\n"
        "Избегай изображать отражение в зеркале.\n"
        "Верни только техническое задание."
    )
    user_prompt = (
        f"Глава {chapter_number} из книги '{title}' автора {author}:\n"
        f"{summary}"
    )

    for attempt in range(2):
        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )
            scene = completion.choices[0].message.content.strip()
            print(f"      ✅ Описание сцены получено.")
            return scene
        except Exception as e:
            print(
                f"      ❌ Ошибка генерации описания сцены (попытка {attempt+1}): {e}")
            time.sleep(1)
    return None


def check_icons_style_similarity(prev_image: Image.Image, curr_image: Image.Image) -> bool:
    """
    Сравнивает стилистическое и техническое сходство двух иконок через OpenAI.
    prev_image — PIL.Image.Image предыдущей главы (уже 256x256 или 512x512)
    curr_image — PIL.Image.Image текущей главы (уже 256x256 или 512x512)
    Возвращает True если всё ок, иначе False.
    """
    import base64
    import io
    from openai import OpenAI
    import os

    def image_to_base64(img):
        with io.BytesIO() as output:
            img.save(output, format="WEBP")
            return base64.b64encode(output.getvalue()).decode("utf-8")

    prev_b64 = image_to_base64(prev_image)
    curr_b64 = image_to_base64(curr_image)

    compare_prompt = (
        "Ты — эксперт по визуальному стилю иллюстраций. "
        "Перед тобой две иконки для последовательных глав одной книги. "
        "Тебе нужно сравнить техническое исполнение и стиль обеих иконок. "
        "Если стиль и техническое исполнение более менее похожи и изображения будут выглядеть гармонично рядом друг с другом в интерфейсе, ответь одним словом: TRUE. "
        "Если есть явные различия по технике, что сильно выбивается из общего стиля — ответь одним словом: FALSE."
    )
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        completion = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": compare_prompt},
                {"role": "user",
                    "content": "Первая иконка (base64): " + prev_b64},
                {"role": "user",
                    "content": "Вторая иконка (base64): " + curr_b64},
            ]
        )
        result = completion.choices[0].message.content.strip().upper()
        print(f"🔎 Сравнение иконок: {result}")
        return result == "TRUE"
    except Exception as e:
        print(f"❗ Ошибка сравнения стиля: {e}")
        return True  # чтобы не блокировать, если не получилось проверить


def generate_icons(book_id: int, title: str, author: str):

    user_ref = f"book-{book_id}-chapter-icon-generator:{int(time.time())}"

    supabase = get_supabase_client()
    print(f"ICONS[{book_id}] 📥 Загружаем chapters_titles...")
    response = supabase.table("books").select(
        "chapters_titles"
    ).eq("id", book_id).single().execute()
    chapters_titles = response.data.get("chapters_titles")

    if not chapters_titles:
        print(f"ICONS[{book_id}] ❌ Нет chapters_titles для книги.")
        return

    data = json.loads(chapters_titles)
    chapters = data.get("chapters", [])
    errors = []

    outdir = f"./export/chapters"
    os.makedirs(outdir, exist_ok=True)

    n_chapters = len(chapters)
    # Проверяем, сколько уже маленьких картинок есть для этой книги
    pattern_small = os.path.join(outdir, f"book_{book_id}_*.webp")
    existing_small = sorted(glob.glob(pattern_small))
    existing_small = [f for f in existing_small if not f.endswith('_big.webp')]

    if len(existing_small) == n_chapters:
        print(
            f"ICONS[{book_id}] ✅ Все иконки уже есть ({n_chapters} шт). Генерация не требуется.")
        return
    elif len(existing_small) > 0:
        print(f"ICONS[{book_id}] ⚠️ Есть {len(existing_small)} иконок из {n_chapters}. Удаляем все для этой книги и начинаем заново.")
        # Удаляем и маленькие, и большие файлы
        pattern_all = os.path.join(outdir, f"book_{book_id}_*.webp")
        for f in glob.glob(pattern_all):
            os.remove(f)

    prev_scenes = []  # Описания предыдущих сцен
    prev_image_small = None  # Сжатое изображение предыдущей главы (PIL.Image)

    for chapter in chapters:
        chapter_number = chapter.get("chapter_number")
        summary = chapter.get("summary", "").strip()
        if not summary:
            print(
                f"ICONS[{book_id}] ⚠️ Нет summary для главы {chapter_number}. Пропускаем.")
            errors.append(f"Глава {chapter_number}")
            continue

        # --- Контекст всех предыдущих сцен
        if prev_scenes:
            prev_scene_text = "Описание сцен предыдущих глав:\n" + \
                "\n".join(
                    [f"Сцена {i+1}: {s}" for i, s in enumerate(prev_scenes)]
                ) + "\n\n"
        else:
            prev_scene_text = ""

        file_big = os.path.join(
            outdir, f"book_{book_id}_{chapter_number}_big.webp")
        file_small = os.path.join(
            outdir, f"book_{book_id}_{chapter_number}.webp")

        success = False
        for attempt in range(5):
            print(
                f"\nICONS[{book_id}] 📝 Глава {chapter_number}: Генерируем описание сцены для иллюстрации... (попытка {attempt+1})")
            scene_description = generate_scene_description(
                summary, chapter_number, title, author, prev_scene_text
            )
            if not scene_description:
                print(
                    f"ICONS[{book_id}] ❌ Не удалось сгенерировать описание сцены для главы {chapter_number}.")
                continue

            print(
                f"ICONS[{book_id}] 🎨 Глава {chapter_number}: Генерируем иконку...")
            try:
                icon_bytes = generate_image_icon(
                    user_ref=user_ref,
                    title=title,
                    author=author,
                    content=scene_description,
                    style=ICON_STYLE
                )
                print(f"ICONS[{book_id}] ✅ Изображение получено.")
            except Exception as e:
                print(
                    f"ICONS[{book_id}] ❌ Ошибка генерации иконки (попытка {attempt+1}): {e}")
                time.sleep(1)
                continue

            # --- Экспозиция, сжатие и сравнение стиля ---
            try:
                image = Image.open(BytesIO(icon_bytes)).convert("RGBA")
                enhancer = ImageEnhance.Brightness(image)
                image_exposed = enhancer.enhance(1.10)
                image_small = image_exposed.resize((512, 512), Image.LANCZOS)

                need_regenerate = False
                if prev_image_small is not None:
                    print(
                        f"ICONS[{book_id}] 🧐 Сравниваем стиль с предыдущей главой...")
                    is_similar = check_icons_style_similarity(
                        prev_image_small, image_small)
                    if not is_similar:
                        print(
                            f"ICONS[{book_id}] ❌ Стиль отличается — перегенерируем, попытка {attempt+1}...")
                        need_regenerate = True

                if need_regenerate:
                    time.sleep(1)
                    continue  # Переходим к следующей попытке
                else:
                    # Сохраняем только если всё хорошо
                    image_small.save(file_small, "WEBP")
                    print(f"ICONS[{book_id}] 💾 Сохранено: {file_small}")
                    prev_image_small = image_small
                    prev_scenes.append(scene_description)
                    success = True
                    break
            except Exception as e:
                print(f"ICONS[{book_id}] ❌ Ошибка при сохранении файлов: {e}")
                time.sleep(1)

        if not success:
            print(
                f"ICONS[{book_id}] ❌ Не удалось сгенерировать иконку для главы {chapter_number} за 2 попытки.")
            errors.append(f"Глава {chapter_number}")

    # Итог: список ошибок
    if errors:
        print("\n\n***** НЕ УДАЛОСЬ СГЕНЕРИРОВАТЬ ИКОНКУ ДЛЯ СЛЕДУЮЩИХ ГЛАВ *****")
        for err in errors:
            print(f"   {err}")
        print("***************************************************************")
    else:
        print("\nВСЕ ИКОНКИ УСПЕШНО СГЕНЕРИРОВАНЫ!")


def refine_title_with_gemini_sdk(book_title, book_author, orig_title, title, target_lang):
    try:
        lang_names = {
            "ru": "русский",
            "en": "английский",
            "es": "испанский",
            "fr": "французский",
            "it": "итальянский",
            "ja": "японский",
            "pt": "португальский",
            "tr": "турецкий",
            "de": "немецкий",
        }
        lang_name = lang_names.get(target_lang, target_lang)

        prompt = (
            f"Проверь этот перевод оригинального заголовка '{orig_title}' главы из книги {book_title} автора {book_author} на {lang_name} язык:\n"
            f"'{title}'\n\n"
            "Если перевод звучит ествественно и не искажает смысл оригинала, то верни его без изменений.\n"
            "Если же есть очень грубая ошибка - исправь.\n"
            "Верни только перевод, без кавычек, без пояснений.\n\n"
        )
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)

        new_title = response.text.strip()
        if new_title and new_title.lower() != title.lower():
            print(f"   Gemini корректировка: {new_title}")
            return new_title
        return title
    except Exception as e:
        print(f"   Gemini ❌ Ошибка проверки заголовка: {e}")
        return title


def translate_titles(
    book_id: int,
    source_field: str,
    result_field: str,
    target_lang: str,
    gemini_refine: bool = True
):
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print(f"TRANSLATE[{book_id}] 📥 Загружаем {source_field}...")
    response = supabase.table("books").select(
        f"{source_field}, title, author"
    ).eq("id", book_id).single().execute()
    book_data = response.data
    if not book_data or not book_data.get(source_field):
        print(f"TRANSLATE[{book_id}] ❌ Нет {source_field} для книги.")
        return

    source_json = json.loads(book_data[source_field])
    book_title = book_data.get("title", "")
    book_author = book_data.get("author", "")

    lang_name = LANG_NAME_RU_CASE.get(target_lang, target_lang)
    chapters = source_json.get("chapters", [])
    result = {"chapters": []}

    for idx, chapter in enumerate(chapters):
        chapter_number = idx + 1
        orig_title = chapter.get("title", "").strip()
        if not orig_title:
            print(
                f"TRANSLATE[{book_id}] ⚠️ Нет title для главы {chapter_number}. Пропускаем.")
            continue

        print(
            f"TRANSLATE[{book_id}] 🌎 Глава {chapter_number}: Переводим заголовок...")

        # Формируем промт на перевод
        prompt = (
            f"Переведи следующий заголовок главы книги '{book_title}' автора {book_author} на {lang_name} язык. "
            f"Это заголовок главы номер {chapter_number}. Сделай перевод естественным для носителя языка, живым и лаконичным. "
            f"Сохрани суть и привлекательность заголовка.\n\n"
            f"Заголовок: {orig_title}\n"
            f"Верни только перевод, без кавычек, без пояснений."
        )

        translation = None
        for attempt in range(3):
            try:
                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": prompt},
                    ]
                )
                translation = completion.choices[0].message.content.strip()
                print(f"TRANSLATE[{book_id}] ✅ Перевод: {translation}")
                break
            except Exception as e:
                print(
                    f"TRANSLATE[{book_id}] ❌ Ошибка при переводе (попытка {attempt+1}): {e}")
                time.sleep(1)
        if not translation:
            print(
                f"TRANSLATE[{book_id}] ❌ Не удалось перевести title для главы {chapter_number}. Пропускаем.")
            continue

        # Gemini: refine if needed
        if gemini_refine:
            translation = refine_title_with_gemini_sdk(
                book_title, book_author, orig_title, translation, target_lang)

        # Доп. цикл — если слишком длинно, просим короче
        while len(translation) > 55:
            print(
                f"TRANSLATE[{book_id}] 🔄 Перевод длиннее 55 символов, просим короче...")
            shorten_prompt_direct = (
                f"Сделай чуть чуть короче этот перевод заголовка главы {chapter_number} книги '{book_title}' автора {book_author} на {lang_name} язык. "
                f"Сохрани естественность, смысл и легкость чтения.\n"
                f"Перевод: '{translation}'\n"
                f"Оригинал: '{orig_title}'\n"
                f"Верни только перевод, без кавычек и пояснений."
            )
            shorten_prompt_reprase = (
                f"Перефразируй перевод заголовка главы {chapter_number} книги '{book_title}' автора {book_author} на {lang_name} язык, чтобы он был не дословным, а более естественным, и при этом он был чуть чуть покороче. "
                f"Сохрани естественность, смысл и легкость чтения.\n"
                f"Перевод: '{translation}'\n"
                f"Оригинал: '{orig_title}'\n"
                f"Верни только перевод, без кавычек и пояснений."
            )
            try:
                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": shorten_prompt_reprase},
                    ]
                )
                translation = completion.choices[0].message.content.strip()
                print(f"TRANSLATE[{book_id}] ✅ Новый перевод: {translation}")
                # Gemini-проверка для укороченного варианта
                if gemini_refine:
                    translation = refine_title_with_gemini_sdk(
                        book_title, book_author, orig_title, translation, target_lang)
            except Exception as e:
                print(f"TRANSLATE[{book_id}] ❌ Ошибка при сокращении: {e}")
                break

        # Добавляем в результат (без summary!)
        result["chapters"].append({
            "chapter_number": chapter_number,
            "title": translation
        })

    # Сохраняем результат в books_translations
    print(f"TRANSLATE[{book_id}] 💾 Сохраняем результат в {result_field}...")
    supabase.table("books_translations").update(
        {result_field: json.dumps(result, ensure_ascii=False, indent=2)}
    ).eq("book_id", book_id).eq("language", target_lang).execute()
    print(f"TRANSLATE[{book_id}] ✅ Переводы сохранены.")

import shutil
import os
import json
import yaml
import base64
from PIL import Image
from pathlib import Path
import io
from datetime import datetime, timezone
from openai import OpenAI
from utils.supabase_client import get_supabase_client
from schemas.characters import (
    Names, Appearance, CharacterAppearanceSummary, CharactersInParagraph,
    AppearanceItem, CharacterRoles, CharacterMention, CharacterMentions
)


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clean_characters_and_appearance(supabase, book_id):
    old_chars = supabase.table("books_characters").select(
        "id").eq("book_id", book_id).execute().data or []
    char_ids = [c["id"] for c in old_chars]
    if char_ids:
        supabase.table("characters_roles").delete().in_(
            "character_id", char_ids).execute()
        supabase.table("characters_appearance").delete().in_(
            "character_id", char_ids).execute()
        supabase.table("books_characters").delete().in_(
            "id", char_ids).execute()


def clean_roles(supabase, book_id):
    supabase.table("characters_roles").delete().eq(
        "book_id", book_id).execute()


def step_find_characters_and_appearance(book_id, data, paragraphs_with_id, supabase, client):
    characters_by_id = {}
    character_names_by_id = {}
    total_paragraphs = len(paragraphs_with_id)
    processed = 0

    for idx, para in enumerate(paragraphs_with_id, start=1):
        paragraph_num = idx
        para_text = para["text"]
        percent = idx * 100 // total_paragraphs
        print(
            f"[{idx}/{total_paragraphs}] ({percent}%) Анализ абзаца {paragraph_num}...")

        known_characters_for_prompt = [
            {
                "id": char_id,
                "main": character_names_by_id[char_id].main,
                "additional_names": character_names_by_id[char_id].additional_names
            }
            for char_id in characters_by_id.keys()
        ]

        prompt_old = (
            f"Книга: {data['title']}\n"
            f"Автор: {data['author']}\n"
            f"Абзац: {para_text}\n"
            f"Текущий список персонажей: {json.dumps(known_characters_for_prompt, ensure_ascii=False)}\n"
            "Найди в абзаце персонажей, у которых в этом абзаце есть прямое или косвенное описание внешности, характера или одежды."
            "Если таких персонажей нет, верни пустой список по схеме CharactersInParagraph.\n"
            "Не учитывай описание, если оно носит субъективный характер, например, если кто-то называет персонажа глупым или умницей."
            "Для каждого найденного персонажа верни:\n"
            "1. Объект Names с основным именем и всеми известными прозвищами/именами (измени основное имя и добавь дополнительные, если в абзаце появилось уточнение, или персонаж преобразился в нового персонаж).\n"
            "2. Appearance с цитатой, касающейся внешности в этом абзаце. Пиши только выжимку из оригинального текста (например, желтое платье, красивый, высокий). Не возвращай деталей, которые не упоминаются в абзаце.\n"
            "Если персонаж новый, верни id=0. Вернуть список объектов, строго по схеме CharactersInParagraph."
        )

        prompt = (
            f"Книга: {data['title']}\n"
            f"Автор: {data['author']}\n"
            f"Абзац: {para_text}\n"
            f"Текущий список персонажей: {json.dumps(known_characters_for_prompt, ensure_ascii=False)}\n"
            "Найди в абзаце персонажей, которые являются ключевыми для сюжета книги. Малозначимых второстепенных персонажей пропускай."
            "Если таких персонажей нет, верни пустой список по схеме CharactersInParagraph.\n"
            "Не учитывай описание, если оно носит субъективный характер, например, если кто-то называет персонажа глупым или умницей."
            "Для каждого найденного персонажа верни:\n"
            "1. Объект Names с основным именем и всеми известными прозвищами/именами (измени основное имя и добавь дополнительные, если в абзаце появилось уточнение, или персонаж преобразился в нового персонаж).\n"
            "2. Appearance с цитатой, касающейся внешности в этом абзаце. Пиши только выжимку из оригинального текста (например, желтое платье, красивый, высокий). Не возвращай деталей, которые не упоминаются в абзаце.\n"
            "Если персонаж новый, верни id=0. Вернуть список объектов, строго по схеме CharactersInParagraph."
        )

        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4.1",
                messages=[{"role": "user", "content": prompt}],
                response_format=CharactersInParagraph
            )
            response_obj = completion.choices[0].message.parsed
        except Exception as e:
            print(f"❌ Ошибка OpenAI на абзаце {idx}: {e}")
            continue

        new_person_count = 0
        for char_obj in response_obj.characters:
            names = char_obj.names
            appearance = char_obj.appearance
            names_json = names.json()
            appearance_json = appearance.json()

            if char_obj.id == 0:
                insert_result = supabase.table("books_characters").insert({
                    "book_id": book_id,
                    "name": names_json
                }).execute()
                char_id = insert_result.data[0]["id"]
                summary = CharacterAppearanceSummary(
                    appearances=[AppearanceItem(
                        paragraph=paragraph_num, appearance=appearance)]
                )
                characters_by_id[char_id] = summary
                character_names_by_id[char_id] = names
                new_person_count += 1
            else:
                char_id = char_obj.id
                summary = characters_by_id.get(char_id)
                if summary:
                    prev_names = character_names_by_id[char_id]
                    if set(names.additional_names) != set(prev_names.additional_names) or names.main != prev_names.main:
                        character_names_by_id[char_id] = names
                        supabase.table("books_characters").update({
                            "name": names_json
                        }).eq("id", char_id).execute()
                    summary.appearances.append(AppearanceItem(
                        paragraph=paragraph_num, appearance=appearance))
                else:
                    char_row = supabase.table("books_characters").select(
                        "*").eq("id", char_id).single().execute().data
                    char_names = Names.parse_raw(char_row["name"])
                    summary = CharacterAppearanceSummary(
                        appearances=[AppearanceItem(
                            paragraph=paragraph_num, appearance=appearance)]
                    )
                    characters_by_id[char_id] = summary
                    character_names_by_id[char_id] = char_names

            if any([appearance.basic, appearance.face, appearance.body, appearance.hair, appearance.clothes]):
                supabase.table("characters_appearance").insert({
                    "character_id": char_id,
                    "paragraph": paragraph_num,
                    "appearance": appearance_json
                }).execute()

        print(
            f"    ✅ {len(response_obj.characters)} персонажей обработано, новых: {new_person_count}")
        processed += 1

    # Анализ истории изменений внешности
    print("\n🔍 Анализ истории изменений внешности для каждого персонажа...")
    all_chars = supabase.table("books_characters").select(
        "id", "name").eq("book_id", book_id).execute().data or []
    for i, char in enumerate(all_chars, 1):
        char_id = char["id"]
        names = Names.parse_raw(char["name"])
        appearances_rows = supabase.table("characters_appearance").select(
            "paragraph, appearance").eq("character_id", char_id).order("paragraph").execute().data or []
        appearances = [
            AppearanceItem(paragraph=int(
                row["paragraph"]), appearance=Appearance.parse_raw(row["appearance"]))
            for row in appearances_rows
        ]

        prompt = (
            f"Книга: {data['title']}\n"
            f"Автор: {data['author']}\n"
            f"Имя персонажа: {names.main}\n"
            f"Вот история уточнений внешности персонажа по ходу книги по абзацам:\n"
            f"{json.dumps([ai.dict() for ai in appearances], ensure_ascii=False)}\n"
            "Проанализируй изменения внешности героя по мере повествования. "
            "Верни итоговую структуру CharacterAppearanceSummary, где appearances — список объектов с ключами paragraph (номер абзаца) и appearance (объект Appearance).\n"
            "Объект Appearance - это собранный по всем абзацам образ персонажа.\n"
            "Например, если в абзаце 1 мы узнаем, что персонаж красивый, во 2 абзаце, что у него длинные черные волосы, а в третьем, что он одет в желтое платье, то пишем это описание к 1 абзацу, потому что он так выглядел с самого начала.\n"
            "Далее, если его внешность меняется, например, в 10 абзаце он заплелел волосы в косичку, то нужно создать новый самодостаточный объект суммарной измененной внешности и привязать к этому абзацу.\n"
            "Создай полное описание каждого персонажа для абзаца 1 - то, как персонаж выглядит в начале книги.\n"
            "Дополни описание пустых полей с учетом общего описания внешности, роли в произведении, привычных изображений персонажа в современном искусстве.\n"
            "Додумай цвета и детали для высокой повторяемости на иллюстрациях.\n"
            "Описывай внешность персонажей так, как если бы они в этот момент давали интервью, например, на шоу Celebrity Big Brother – негативные персонажи стараются скрыть свои негативные эмоции и скрытые мотивы, а нейтральные и положительные персонажи более открыты и естественны."
        )

        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4.1",
                messages=[{"role": "user", "content": prompt}],
                response_format=CharacterAppearanceSummary
            )
            summary = completion.choices[0].message.parsed
        except Exception as e:
            print(
                f"❌ Ошибка OpenAI при анализе истории внешности персонажа '{names.main}': {e}")
            continue

        summary_dict = summary.model_dump()
        summary_json = json.dumps(summary_dict, indent=2, ensure_ascii=False)
        supabase.table("books_characters").update({
            "appearance": summary_json
        }).eq("id", char_id).execute()
        print(
            f"    🧑‍🔬 [{i}/{len(all_chars)}] Итоговое описание для '{names.main}' сохранено.")

    print(
        f"\n🏁 Готово! Проанализировано {processed} абзацев и {len(all_chars)} персонажей книги '{data['title']}'.")

    # === Определяем первый уникальный абзац появления каждого персонажа ===
    print("🔎 Определяем абзацы первого упоминания персонажей...")

    # Загружаем всех персонажей с именами
    all_chars_for_mentions = supabase.table("books_characters").select(
        "id", "name").eq("book_id", book_id).execute().data or []
    characters_with_names = [
        {"id": c["id"], "names": Names.parse_raw(c["name"]).dict()}
        for c in all_chars_for_mentions
    ]

    book_text = ""
    for idx, para in enumerate(paragraphs_with_id, start=1):
        book_text += f"{idx}. {para['text']}\n"

    mentions_prompt = (
        f"Книга: {data['title']}\n"
        f"Автор: {data['author']}\n"
        f"Текст книги с номерами абзацев:\n{book_text}\n"
        f"Список персонажей: {json.dumps(characters_with_names, ensure_ascii=False)}\n"
        "Для каждого персонажа укажи номер абзаца, в котором он впервые появляется в тексте (как число). "
        "Верни объект mentions — список из CharacterMention с полями id и first_paragraph."
    )

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4.1",
            messages=[{"role": "user", "content": mentions_prompt}],
            response_format=CharacterMentions
        )
        mentions_obj = completion.choices[0].message.parsed
    except Exception as e:
        print(f"❌ Ошибка OpenAI при поиске первого упоминания: {e}")
        return

    print("📥 Сохраняем уникальные номера первых абзацев в таблицу books_characters...")

    # Соберём все first_paragraph
    used_paragraphs = set()
    updates = []
    # Сортируем чтобы обработка шла в одном порядке всегда
    mentions_sorted = sorted(mentions_obj.mentions, key=lambda x: x.id)
    for mention in mentions_sorted:
        first_para = mention.first_paragraph
        # Если первый параграф == 1, увеличиваем на 1
        if first_para == 1:
            first_para += 1
        # Делаем уникальным среди уже встречавшихся
        while first_para in used_paragraphs:
            first_para += 1
        used_paragraphs.add(first_para)
        updates.append((mention.id, first_para))

    for char_id, para in updates:
        supabase.table("books_characters").update({
            "first_paragraph": para
        }).eq("id", char_id).execute()

    print("✅ Уникальные первые упоминания сохранены в books_characters!")


def step_roles(book_id, data, paragraphs_with_id, supabase, client):
    print("\n🧩 Определяем роли персонажей...")

    all_chars_for_roles = supabase.table("books_characters").select(
        "id", "name").eq("book_id", book_id).execute().data or []
    characters_list = [{"id": c["id"], "names": Names.parse_raw(
        c["name"]).dict()} for c in all_chars_for_roles]

    roles_prompt = (
        f"Книга: {data['title']}\n"
        f"Автор: {data['author']}\n"
        f"Вот список персонажей: {json.dumps(characters_list, ensure_ascii=False)}\n"
        "Назови id персонажей для следующих ролей: hero (main protagonist), antagonist (main opponent), ally (helps the hero, provides wisdom), trickster (minor Antagonist, brings chaos), victim (suffers to further the plot).\n"
        "Если роль не нашлась, оставь None. Верни объект строго по схеме CharacterRoles."
    )

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4.1",
            messages=[{"role": "user", "content": roles_prompt}],
            response_format=CharacterRoles
        )
        roles_obj = completion.choices[0].message.parsed
    except Exception as e:
        print(f"❌ Ошибка OpenAI при определении ролей: {e}")
        return

    print("📥 Сохраняем роли в БД...")

    # Соберём все id персонажей
    all_ids = set(c["id"] for c in all_chars_for_roles)

    # Словарь: роль -> id персонажа
    roles_map = {
        "hero": roles_obj.hero,
        "ally": roles_obj.ally,
        "antagonist": roles_obj.antagonist,
        "trickster": roles_obj.trickster,
        "victim": roles_obj.victim,
    }

    # id персонажей с целевыми ролями
    assigned_ids = set(x for x in roles_map.values() if x is not None)
    # все персонажи без целевых ролей -> роль "other"
    other_ids = all_ids - assigned_ids

    # Сохраняем целевые роли
    for role, char_id in roles_map.items():
        if char_id is not None:
            exists = supabase.table("characters_roles").select("id").eq(
                "book_id", book_id).eq("character_id", char_id).execute().data
            role_values = {
                "hero": False,
                "ally": False,
                "antagonist": False,
                "trickster": False,
                "victim": False,
                "other": False
            }
            role_values[role] = True

            if exists:
                supabase.table("characters_roles").update(role_values).eq(
                    "book_id", book_id).eq("character_id", char_id).execute()
            else:
                supabase.table("characters_roles").insert({
                    "book_id": book_id,
                    "character_id": char_id,
                    **role_values
                }).execute()

    # Сохраняем "other" роль для всех остальных
    for char_id in other_ids:
        exists = supabase.table("characters_roles").select("id").eq(
            "book_id", book_id).eq("character_id", char_id).execute().data
        role_values = {
            "hero": False,
            "ally": False,
            "antagonist": False,
            "trickster": False,
            "victim": False,
            "other": True
        }
        if exists:
            supabase.table("characters_roles").update(role_values).eq(
                "book_id", book_id).eq("character_id", char_id).execute()
        else:
            supabase.table("characters_roles").insert({
                "book_id": book_id,
                "character_id": char_id,
                **role_values
            }).execute()

    print("🔎 Определяем абзацы первого упоминания персонажей...")

    # Создаём полный список персонажей для поиска упоминаний (все, а не только с ролями)
    characters_with_roles = [
        {"id": c["id"], "names": c["names"]}
        for c in characters_list
    ]

    book_text = ""
    for idx, para in enumerate(paragraphs_with_id, start=1):
        book_text += f"{idx}. {para['text']}\n"

    mentions_prompt = (
        f"Книга: {data['title']}\n"
        f"Автор: {data['author']}\n"
        f"Текст книги с номерами абзацев:\n{book_text}\n"
        f"Список персонажей: {json.dumps(characters_with_roles, ensure_ascii=False)}\n"
        "Для каждого персонажа укажи номер абзаца, в котором он впервые появляется в тексте (как число). "
        "Верни объект mentions — список из CharacterMention с полями id и first_paragraph."
    )

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4.1",
            messages=[{"role": "user", "content": mentions_prompt}],
            response_format=CharacterMentions
        )
        mentions_obj = completion.choices[0].message.parsed
    except Exception as e:
        print(f"❌ Ошибка OpenAI при поиске первого упоминания: {e}")
        return

    print("📥 Сохраняем уникальные номера первых абзацев в таблицу characters_roles...")

    # Соберём все first_paragraph
    used_paragraphs = set()
    updates = []
    # Сортируем чтобы обработка шла в одном порядке всегда
    mentions_sorted = sorted(mentions_obj.mentions, key=lambda x: x.id)
    for mention in mentions_sorted:
        first_para = mention.first_paragraph
        # Если первый параграф == 1, увеличиваем на 1
        if first_para == 1:
            first_para += 1
        # Делаем уникальным среди уже встречавшихся
        while first_para in used_paragraphs:
            first_para += 1
        used_paragraphs.add(first_para)
        updates.append((mention.id, first_para))

    for char_id, para in updates:
        supabase.table("characters_roles").update({
            "first_paragraph": para
        }).eq("book_id", book_id).eq("character_id", char_id).execute()

    print("✅ Роли и уникальные первые упоминания успешно сохранены!")


def create_resized_buffer(image_path):
    img = Image.open(image_path)
    w, h = img.size
    if w >= h:
        new_w, new_h = 512, int(h * (512 / w))
    else:
        new_h, new_w = 512, int(w * (512 / w))
    img = img.resize((new_w, new_h))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    buf.seek(0)
    img.close()
    return ("image.webp", buf)


def step_draw(book_id, data, paragraphs_with_id, supabase, client):
    print("🎨 Генерация иллюстраций для персонажей...")

    # --- Patch: гарантируем наличие chapters ---
    if "chapters" in data:
        chapters = data["chapters"]
    elif "text_by_chapters" in data:
        chapters = json.loads(data["text_by_chapters"])["chapters"]
    else:
        raise KeyError(
            "В объекте data нет ключа chapters или text_by_chapters")

    title = data['title']
    author = data['author']
    all_chars = supabase.table("books_characters").select(
        "id", "name", "appearance", "first_paragraph").eq("book_id", book_id).execute().data or []
    characters = []
    for c in all_chars:
        names = Names.parse_raw(c["name"])
        appearance_data = None
        if c.get("appearance"):
            try:
                appearance_data = json.loads(c["appearance"])
            except Exception:
                appearance_data = None
        characters.append({
            "id": c["id"],
            "names": names,
            "appearance_data": appearance_data,
            "first_paragraph": c.get("first_paragraph")
        })

    config = load_config()
    emotions_config = config.get("characters_emotions", {})
    emotions = [k for k, v in emotions_config.items() if v]
    print(f"Эмоции: {emotions}")

    input_folder = Path("./export/previews")
    cover_path = input_folder / f"book_{book_id}.webp"

    # Папки
    out_dir = Path(f"./characters/book{book_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    export_dir = Path("./export/characters")
    export_dir.mkdir(parents=True, exist_ok=True)

    style = (
        "Transparent background; stylized digital character rendering; character shown from the waist up; directly facing the viewer with a clear, confident gaze; realistic anatomy with polished, high-definition finish — smooth skin, sharp clothing detail, subtle specular light on hair and fabric; bold color grading with warm highlights and cinematic shadow; facial features fully visible and expressive, with personality-driven attitude; background fully transparent, characters cleanly cut out with soft rim light or drop shadow for depth; evokes modern, attitude-rich, polished realism in a format ready for covers, avatars, or motion graphics."
    )

    model = "gpt-image-1"
    size = "1024x1024"

    # Для быстрого поиска главы и параграфа в главе по глобальному индексу
    para_map = {}
    idx_counter = 1
    for chapter in chapters:
        chapter_number = chapter["chapter_number"]
        for idx, paragraph in enumerate(chapter["paragraphs"], start=1):
            para_map[idx_counter] = (chapter_number, idx)
            idx_counter += 1

    for char in characters:
        char_id = char["id"]
        names = char["names"]
        first_paragraph = char.get("first_paragraph")
        print(f"\n🧑 Персонаж: {names.main}")

        char_folder = out_dir
        version = 1
        existing_versions = []
        for fname in char_folder.glob(f"{char_id}_p*_v*_*.webp"):
            stem = fname.stem
            try:
                v = int(stem.split("_v")[1].split("_")[0])
                existing_versions.append(v)
            except Exception:
                continue
        if existing_versions:
            version = max(existing_versions) + 1
        print(f"Версия иллюстраций: {version}")

        appearances = []
        if char["appearance_data"] and "appearances" in char["appearance_data"]:
            for a in char["appearance_data"]["appearances"]:
                para = a.get("paragraph")
                appearance = a.get("appearance")
                appearances.append((para, appearance))
        else:
            print(f"  Нет appearance для персонажа {names.main}")
            continue

        for para_num, appearance in appearances:
            if para_num > 1:
                continue

            first_emotion = True
            for emotion_code in emotions:
                files_for_openai = []

                if first_emotion:
                    prompt = (
                        f"Нарисуй иллюстрацию персонажа по мотивам книги '{title}' автора {author}.\n"
                        f"Имя персонажа: {names.main}.\n"
                        f"Изображение персонажа должно соответствовать другим изображениям, если они даны.\n"
                        f"Но учитывай изменение во внешности по ходу книги (для абзаца {para_num}): {appearance}.\n"
                        f"Передай персонажа в эмоции: {emotion_code}.\n"
                        f"Стиль должен быть таким: {style}.\n"
                        "Оставь верхнюю часть изображения пустой."
                    )
                else:
                    prompt = (
                        f"Повтори персонажа в новой эмоции: {emotion_code}.\n"
                        f"Прозрачный фон.\n"
                        "Оставь верхнюю часть изображения пустой."
                    )

                print(f"    ➡️ Абзац: {para_num} | Эмоция: {emotion_code}")
                image_base64 = None

                response = client.images.generate(
                    model=model,
                    prompt=prompt,
                    n=1,
                    size=size,
                    user=f"book-characters:{int(datetime.now(timezone.utc).timestamp())}"
                )
                image_base64 = response.data[0].b64_json

                if not image_base64:
                    print("❌ OpenAI не вернул base64 изображение.")
                    continue

                # 1. Сохраняем ОРИГИНАЛ в characters/book<id>
                output_file = char_folder / \
                    f"{char_id}_p{para_num}_v{version}_{emotion_code}.webp"
                img_bytes = io.BytesIO()
                img_bytes.write(base64.b64decode(image_base64))
                img_bytes.seek(0)
                with open(output_file, "wb") as f:
                    f.write(img_bytes.read())
                print(f"      💾 Иллюстрация сохранена: {output_file}")

                # 2. Если это первая эмоция p1 — Сохраняем уменьшенную копию в ./export/characters
                if para_num == 1 and first_emotion and first_paragraph:
                    chapter_num, para_in_chap = para_map.get(
                        first_paragraph, (None, None))
                    if chapter_num is not None:
                        export_name = f"book_{book_id}_{chapter_num}_{para_in_chap}.webp"
                        export_path = export_dir / export_name
                        # Уменьшаем до 512x512:
                        img_bytes.seek(0)
                        img = Image.open(img_bytes)
                        img = img.convert("RGBA")  # для прозрачности
                        img = img.resize((512, 512))
                        img.save(export_path, format="WEBP")
                        img.close()
                        print(f"      📤 Копия для экспорта: {export_path}")

                first_emotion = False

    print("✅ Иллюстрации персонажей успешно сгенерированы и сохранены.")


def step_comments(book_id, data, paragraphs_with_id, supabase, client):
    print("💬 Генерация реплик персонажей — функция пока не реализована.")


def get_characters_appearance(
    book_id: int,
    config_path: str = "config.yaml"
):
    print("🚀 Начинаю обработку персонажей книги.")
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    config = load_config(config_path)
    characters_config = config.get("characters", {})

    # Получаем данные книги
    response = supabase.table("books").select(
        "title, author, text_by_chapters").eq("id", book_id).single().execute()
    if not response.data:
        print("❌ Книга не найдена")
        return
    data = response.data
    title = data["title"]
    author = data["author"]
    chapters = json.loads(data["text_by_chapters"])["chapters"]
    print(f"✅ Книга найдена: {title} ({author}). Глав: {len(chapters)}")
    paragraphs_with_id = []
    for chapter in chapters:
        chapter_number = chapter["chapter_number"]
        for idx, paragraph in enumerate(chapter["paragraphs"]):
            paragraphs_with_id.append({
                "chapter": chapter_number,
                "paragraph_idx": idx + 1,
                "text": paragraph
            })
    total_paragraphs = len(paragraphs_with_id)
    print(f"📝 Всего абзацев: {total_paragraphs}")

    # Этапы по конфигу
    if characters_config.get("find"):
        clean_characters_and_appearance(supabase, book_id)
        step_find_characters_and_appearance(
            book_id, data, paragraphs_with_id, supabase, client)
    if characters_config.get("roles"):
        clean_roles(supabase, book_id)
        step_roles(book_id, data, paragraphs_with_id, supabase, client)
    if characters_config.get("draw"):
        step_draw(book_id, data, paragraphs_with_id, supabase, client)
    if characters_config.get("comments"):
        step_comments(book_id, data, paragraphs_with_id, supabase, client)

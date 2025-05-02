import os
import json
import time
import random
from openai import OpenAI
from schemas.chapter_goals import WordGroups
from utils.supabase_client import get_supabase_client


def generate_chapter_goals(book_id: int, source_field: str, result_field: str, target_lang: str):
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print(f"📥 Загружаем {source_field} для книги {book_id}...")
    response = supabase.table("books").select(
        source_field).eq("id", book_id).single().execute()
    text_data = response.data.get(source_field)

    if not text_data:
        print("❌ Нет текста для анализа.")
        return

    data = json.loads(text_data)
    chapters = data["chapters"]
    result = {"chapters": []}

    for chapter in chapters:
        print(f"\n📘 Глава {chapter['chapter_number']}")
        word_list = []

        for paragraph in chapter["paragraphs"]:
            for sentence in paragraph["sentences"]:
                for word_idx, word in enumerate(sentence.get("words", [])):
                    word_id = f"{chapter['chapter_number']}_{paragraph['paragraph_number']}_{sentence['sentence_number']}_{word_idx + 1}"
                    word_list.append({
                        "id": word_id,
                        "original": word["o"],
                        "translation": word["o_t"]
                    })

        if len(word_list) < 5:
            print("⚠️ Недостаточно слов для группировки. Пропускаем.")
            continue

        word_lookup = {w["id"]: {"original": w["original"],
                                 "translation": w["translation"]} for w in word_list}

        # 🔍 Выводим первые 50 слов для проверки
        # print("\n🧪 Топ 50 слов:")
        # for w in word_list[:50]:
        #     print(f"  {w['id']:10} | {w['original']:20} → {w['translation']}")

        random.shuffle(word_list)
        input_json = json.dumps(word_list, ensure_ascii=False, indent=2)

        # --- Шаг 1: Генерация групп ---
        system_prompt_1 = (
            f"Ты — языковой помощник. У тебя есть список слов из главы книги. "
            f"Попробуй найти 5 существительных, глаголов, прилагательных или наречий, объединенных общей темой. Например: предметы одежды, глаголы движения, описания внешности, эмоции и т.д.\n\n"
            f"Формат:\n- label (на языке {target_lang}): краткое название темы\n"
            f"- ids: список из 5 id слов, имеющих эту общую тему.\n\n"
            f"Важно:\n- Не придумывай слова. Используй только переданные id.\n"
            f"- В каждой теме должно быть ровно 5 id.\n"
            f"- Несколько раз использовать id нельзя.\n"
            f"- Верни только JSON-объект строго по схеме."
        )

        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": system_prompt_1},
                    {"role": "user", "content": input_json[:3000]}
                ],
                response_format=WordGroups
            )
            groups_raw = completion.choices[0].message.parsed
            print(f"✅ Получено групп: {len(groups_raw.groups)}")

        except Exception as e:
            print(f"❌ Ошибка на этапе генерации групп: {e}")
            continue

        # --- Шаг 2: Ранжирование ---
        try:
            system_prompt_2 = (
                "Вот список групп из слов. Каждая содержит label и 5 id слов.\n"
                "Вот словарь, по которому ты можешь определить, какие слова стоят за каждым id.\n\n"
                "Отсортируй группы по степени соответствия между словами внутри одной группы.\n"
                "На первом месте — те, где слова действительно хорошо объединены общей темой.\n"
                "Верни только ТОП-3 группы с 5 словами в том же формате."
            )

            completion = client.beta.chat.completions.parse(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": system_prompt_2},
                    {"role": "user", "content": "Словарь слов:\n" +
                        json.dumps(word_lookup, ensure_ascii=False, indent=2)[:2000]},
                    {"role": "user", "content": "Группы:\n" +
                        groups_raw.model_dump_json(indent=2)[:2000]}
                ],
                response_format=WordGroups
            )

            top_groups = completion.choices[0].message.parsed
            print(f"🏅 Топ-групп: {len(top_groups.groups)}")

            # Создаем словарь для быстрого поиска слов по id
            word_lookup = {w["id"]: w for w in word_list}

            # Выводим слова из каждой группы
            for group in top_groups.groups:
                print(f"\n📚 Группа: {group.label}")
                for wid in group.ids:
                    word = word_lookup.get(wid)
                    if word:
                        print(
                            f"{wid:10} | {word['original']:20} → {word['translation']}")
                    else:
                        print(f"{wid:10} | ⚠️ ID не найден в словаре")

            result["chapters"].append({
                "chapter_number": chapter["chapter_number"],
                "goals": [g.model_dump() for g in top_groups.groups]
            })

        except Exception as e:
            print(f"❌ Ошибка на этапе ранжирования: {e}")
            continue

        time.sleep(1)

    # --- Сохраняем результат ---
    print(f"\n💾 Сохраняем {result_field}...")
    supabase.table("books").update(
        {result_field: json.dumps(result, ensure_ascii=False, indent=2)}
    ).eq("id", book_id).execute()

    print("✅ Цели по главам сохранены.")

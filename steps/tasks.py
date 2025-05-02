from schemas.paragraph_translate import HowToTranslateTask
import os
import json
import time
import random
from openai import OpenAI
from utils.supabase_client import get_supabase_client
from schemas.paragraph_tf import ParagraphTFItem, ParagraphTFQuestionOnly
from schemas.paragraph_translate import HowToTranslateTask
from schemas.paragraph_two_words import TwoWordsTask


def generate_paragraph_tasks(book_id: int, source_field: str, result_field: str, target_lang: str):
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
        chapter_output = {
            "chapter_number": chapter["chapter_number"], "paragraphs": []}

        for paragraph in chapter["paragraphs"]:
            paragraph_text = " ".join(
                sentence["sentence_original"] for sentence in paragraph["sentences"]
            ).strip()

            if not paragraph_text:
                continue

            print(f"  ✂️ Абзац {paragraph['paragraph_number']}")

            # 🎲 Выбор типа утверждения
            expected_answer = "true" if random.random() < 0.6 else "false"

            # ✍️ Промт в зависимости от типа утверждения
            if expected_answer == "true":
                system_prompt = (
                    f"Ты — помощник по чтению книг. Сформулируй верное утверждение по содержанию абзаца.\n\n"
                    f"Утверждение должно:\n"
                    f"- быть на языке {target_lang};\n"
                    f"- отражать суть происходящего;\n"
                    f"- быть легко проверяемым по содержанию;\n"
                    f"- быть достаточно очевидным для вдумчивого читателя;\n"
                    f"- быть коротким, до 7 слов;\n"
                    f"- не содержать двусмысленностей.\n\n"
                    f"Верни объект строго по схеме: {{ question: '...' }}"
                )
            else:
                system_prompt = (
                    f"Ты — помощник по чтению книг. Сформулируй заведомо ложное утверждение по содержанию абзаца.\n\n"
                    f"Утверждение должно:\n"
                    f"- быть на языке {target_lang};\n"
                    f"- отражать вымышленный факт относительно происходящего;\n"
                    f"- быть легко проверяемым по содержанию;\n"
                    f"- быть достаточно очевидным для вдумчивого читателя;\n"
                    f"- быть коротким, до 7 слов;\n"
                    f"- не содержать двусмысленностей.\n\n"
                    f"Верни объект строго по схеме: {{ question: '...' }}"
                )

            try:
                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": paragraph_text[:2000]}
                    ],
                    response_format=ParagraphTFQuestionOnly
                )
                q_obj = completion.choices[0].message.parsed

                # Удаляем точку в конце вопроса
                cleaned_question = q_obj.question.strip()
                if cleaned_question.endswith("."):
                    cleaned_question = cleaned_question[:-1]

                print(f"    🏅 Вопрос: {cleaned_question} [{expected_answer}]")

                paragraph_output = {
                    "paragraph_number": paragraph["paragraph_number"],
                    "true_or_false": ParagraphTFItem(
                        question=cleaned_question,
                        answer=expected_answer
                    ).model_dump()
                }

            except Exception as e:
                print(f"    ⚠️ Ошибка или нет ответа: {e}")
                paragraph_output = {
                    "paragraph_number": paragraph["paragraph_number"],
                    "true_or_false": None
                }

            chapter_output["paragraphs"].append(paragraph_output)
            time.sleep(1)

        result["chapters"].append(chapter_output)

    print(f"\n💾 Сохраняем {result_field}...")
    supabase.table("books").update({
        result_field: json.dumps(result, ensure_ascii=False, indent=2)
    }).eq("id", book_id).execute()
    print("✅ Вопросы по абзацам сохранены.")


def add_how_to_translate_tasks(book_id: int, words_field: str, base_task_field: str, result_field: str, target_lang: str, source_lang: str):
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print(
        f"📥 Загружаем {words_field} и {base_task_field} для книги {book_id}...")
    words_response = supabase.table("books").select(
        words_field).eq("id", book_id).single().execute()
    tasks_response = supabase.table("books").select(
        base_task_field).eq("id", book_id).single().execute()

    words_data = json.loads(words_response.data.get(words_field))
    tasks_data = json.loads(tasks_response.data.get(base_task_field))

    result = {"chapters": []}

    for ch_words, ch_tasks in zip(words_data["chapters"], tasks_data["chapters"]):
        print(f"\n📘 Глава {ch_words['chapter_number']}")
        updated_paragraphs = []

        for par_words, par_tasks in zip(ch_words["paragraphs"], ch_tasks["paragraphs"]):
            paragraph_number = par_words["paragraph_number"]
            print(f"  ✂️ Абзац {paragraph_number}")

            word_objects = []
            word_lookup = {}

            for sentence in par_words["sentences"]:
                sid = sentence["sentence_number"]
                for wid, word in enumerate(sentence.get("words", [])):
                    word_id = f"{ch_words['chapter_number']}_{par_words['paragraph_number']}_{sid}_{wid + 1}"

                    o = word["o"].strip()
                    o_t = word["o_t"].strip()

                    # ❌ Пропускаем слишком длинные слова
                    if len(o) > 22 or len(o_t) > 22:
                        continue

                    word_obj = {
                        "id": word_id,
                        "o": word["o"],
                        "o_t": word["o_t"]
                    }
                    word_objects.append(word_obj)
                    word_lookup[word_id] = word_obj

            if len(word_objects) < 3:
                print("    ⚠️ Недостаточно слов")
                par_tasks["how_to_translate"] = None
                updated_paragraphs.append(par_tasks)
                continue

            input_json = json.dumps(word_objects, ensure_ascii=False, indent=2)

            system_prompt = (
                "Ты — преподаватель иностранного языка.\n\n"
                "У тебя есть список слов с полями:\n"
                "- id — идентификатор слова\n"
                "- o — слово на изучаемом языке\n"
                "- o_t — его перевод на язык ученика\n\n"
                "Выбери одно менее частотное, специфичное для абзаца слово для проверки понимания учеником текста."
                "Верни:\n"
                "- correct_id — id этого слова\n"
                "- incorrect1_id и incorrect2_id — id других слов из списка, схожих по типу, но отличающихся по значению\n\n"
                "Верни строго JSON по схеме"
            )

            try:
                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": input_json[:3000]}
                    ],
                    response_format=HowToTranslateTask
                )
                result_obj = completion.choices[0].message.parsed

                try:
                    correct_word = word_lookup[result_obj.correct_id]
                    incorrect1 = word_lookup[result_obj.incorrect1_id]
                    incorrect2 = word_lookup[result_obj.incorrect2_id]
                except KeyError as e:
                    print(
                        f"    ⚠️ Один из ID не найден в словаре: {e}. Пропускаем абзац.")
                    par_tasks["how_to_translate"] = None
                    updated_paragraphs.append(par_tasks)
                    continue

                question_text = correct_word.get("o_t", "<?>")

                par_tasks["how_to_translate"] = {
                    "question": f"Как переводится '{question_text}'?",
                    "correct": correct_word.get("o", "—"),
                    "incorrect1": incorrect1.get("o", "—"),
                    "incorrect2": incorrect2.get("o", "—"),
                    "c": result_obj.correct_id,
                    "i1": result_obj.incorrect1_id,
                    "i2": result_obj.incorrect2_id
                }

                print(f"    ✅ Вопрос: {par_tasks['how_to_translate']['question']} → "
                      f"{par_tasks['how_to_translate']['correct']} | "
                      f"{par_tasks['how_to_translate']['incorrect1']} | "
                      f"{par_tasks['how_to_translate']['incorrect2']}")

            except Exception as e:
                print(f"    ❌ Ошибка GPT: {e}")
                par_tasks["how_to_translate"] = None

            updated_paragraphs.append(par_tasks)
            time.sleep(1)

        result["chapters"].append({
            "chapter_number": ch_tasks["chapter_number"],
            "paragraphs": updated_paragraphs
        })

    print(f"\n💾 Сохраняем {result_field}...")
    supabase.table("books").update({
        result_field: json.dumps(result, ensure_ascii=False, indent=2)
    }).eq("id", book_id).execute()
    print("✅ Вопросы 'how to translate' с ID и текстами сохранены.")


def add_two_words_tasks(book_id: int, words_field: str, base_task_field: str, result_field: str, target_lang: str):
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    print(
        f"📥 Загружаем {words_field} и {base_task_field} для книги {book_id}...")
    words_response = supabase.table("books").select(
        words_field).eq("id", book_id).single().execute()
    tasks_response = supabase.table("books").select(
        base_task_field).eq("id", book_id).single().execute()

    words_data = json.loads(words_response.data.get(words_field))
    tasks_data = json.loads(tasks_response.data.get(base_task_field))

    result = {"chapters": []}

    for ch_words, ch_tasks in zip(words_data["chapters"], tasks_data["chapters"]):
        print(f"\n📘 Глава {ch_words['chapter_number']}")
        updated_paragraphs = []

        for par_words, par_tasks in zip(ch_words["paragraphs"], ch_tasks["paragraphs"]):
            paragraph_number = par_words["paragraph_number"]
            print(f"  ✂️ Абзац {paragraph_number}")

            candidates = []
            word_lookup = {}

            for sentence in par_words["sentences"]:
                sid = sentence["sentence_number"]
                for wid, word in enumerate(sentence.get("words", [])):
                    word_id = f"{ch_words['chapter_number']}_{paragraph_number}_{sid}_{wid + 1}"
                    o_t = word.get("o_t", "").strip()
                    if len(o_t.split()) <= 2:
                        candidates.append({"id": word_id, "o_t": o_t})
                        word_lookup[word_id] = o_t

            if len(candidates) < 2:
                print("    ⚠️ Недостаточно подходящих слов")
                par_tasks["two_words"] = None
                updated_paragraphs.append(par_tasks)
                continue

            input_json = json.dumps(candidates, ensure_ascii=False, indent=2)

            system_prompt = (
                f"У тебя есть список слов из текста на {target_lang}.\n"
                f"Твоя задача:\n"
                f"1. Найди два слова, которые похожи по типу (например, оба — действия или предметы), но разные по значению.\n"
                f"2. Верни их id как id1 и id2.\n"
                f"3. Придумай третье слово на {target_lang}, похожее по типу, которое не подходит к теме текста.\n\n"
                f"Верни строго JSON: {{ id1, id2, invented }}"
            )

            try:
                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": input_json[:3000]}
                    ],
                    response_format=TwoWordsTask
                )
                task = completion.choices[0].message.parsed

                if task.id1 not in word_lookup or task.id2 not in word_lookup:
                    print(
                        f"    ❌ Ошибка: ID {task.id1} или {task.id2} не найдены. Пропускаем абзац.")
                    par_tasks["two_words"] = None
                    updated_paragraphs.append(par_tasks)
                    continue

                o1 = word_lookup[task.id1]
                o2 = word_lookup[task.id2]

                print(
                    f"    ✅ {task.id1}: {o1} | {task.id2}: {o2} → {task.invented}")

                par_tasks["two_words"] = {
                    "id1": task.id1,
                    "id2": task.id2,
                    "w1": o1,
                    "w2": o2,
                    "invented": task.invented
                }

            except Exception as e:
                print(f"    ❌ Ошибка GPT: {e}")
                par_tasks["two_words"] = None

            updated_paragraphs.append(par_tasks)
            time.sleep(1)

        result["chapters"].append({
            "chapter_number": ch_tasks["chapter_number"],
            "paragraphs": updated_paragraphs
        })

    print(f"\n💾 Сохраняем {result_field}...")
    supabase.table("books").update({
        result_field: json.dumps(result, ensure_ascii=False, indent=2)
    }).eq("id", book_id).execute()
    print("✅ Вопросы 'two words + invented' сохранены.")

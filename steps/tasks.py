from schemas.paragraph_translate import HowToTranslateTask
import os
import json
import time
import random
from openai import OpenAI
from pathlib import Path
from utils.supabase_client import get_supabase_client
from schemas.paragraph_tf import ParagraphTFItem, ParagraphTFQuestionOnly
from schemas.paragraph_translate import HowToTranslateTask
from schemas.paragraph_two_words import TwoWordsTask


def generate_paragraph_tasks(book_id: int, source_field: str, result_field: str, target_lang: str, source_lang: str):

    start_time = time.time()
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"log_tasks_book_{book_id}_{target_lang}.txt"

    def log(msg):
        print(msg)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    # Проверка: если результат уже есть — пропускаем
    existing = supabase.table("books_translations").select(result_field).eq(
        "book_id", book_id).eq("language", target_lang).single().execute()
    raw_result = existing.data.get(result_field)
    if raw_result and str(raw_result).strip() not in {"", "{}", "[]"}:
        log(f"⏭ Пропускаем: поле {result_field} уже заполнено для книги {book_id}, языка {target_lang}")
        return

    log(f"📥 Загружаем {source_field} из books_translations для книги {book_id} и языка {target_lang}...")
    response = supabase.table("books_translations").select(source_field).eq(
        "book_id", book_id).eq("language", target_lang).single().execute()
    text_data = response.data.get(source_field)

    if not text_data:
        log(
            f"❌ Нет текста для анализа (книга {book_id}, поле {source_field}, язык {target_lang}).")
        return

    try:
        data = json.loads(text_data)
    except Exception as e:
        log(f"❌ Ошибка при парсинге JSON: {e} (книга {book_id}, поле {source_field})")
        return

    chapters = data["chapters"]
    total_paragraphs = sum(len(ch["paragraphs"]) for ch in chapters)
    processed_paragraphs = 0
    result = {"chapters": []}

    lang_names_pr = {
        "en": "английском",
        "es": "испанском",
        "fr": "французском",
        "de": "немецком",
        "it": "итальянском",
        "ru": "русском",
        "zh": "китайском",
        "ja": "японском",
        "ko": "корейском",
    }
    readable_target_pr = lang_names_pr.get(target_lang, target_lang)

    for chapter in chapters:
        log_line = f"\n📘 Глава {chapter['chapter_number']} (книга {book_id}, язык {target_lang})"
        print(log_line)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")

        chapter_output = {
            "chapter_number": chapter["chapter_number"], "paragraphs": []}

        for paragraph in chapter["paragraphs"]:
            paragraph_text = " ".join(
                sentence["sentence_translation"] for sentence in paragraph["sentences"]).strip()
            if not paragraph_text:
                continue

            processed_paragraphs += 1
            percent = round((processed_paragraphs / total_paragraphs) * 100)
            log(f"  ✂️ Абзац {paragraph['paragraph_number']} — {percent}%")
            expected_answer = "true" if random.random() < 0.6 else "false"

            if expected_answer == "true":
                system_prompt = (
                    f"Ты — помощник по чтению книг. Сформулируй верное утверждение по содержанию абзаца.\n\n"
                    f"Утверждение должно:\n"
                    f"- быть на {readable_target_pr} языке;\n"
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
                    f"- быть на {readable_target_pr} языке;\n"
                    f"- отражать вымышленный факт относительно происходящего;\n"
                    f"- быть легко проверяемым по содержанию;\n"
                    f"- быть достаточно очевидным для вдумчивого читателя;\n"
                    f"- быть коротким, до 7 слов;\n"
                    f"- не содержать двусмысленностей.\n\n"
                    f"Верни объект строго по схеме: {{ question: '...' }}"
                )

            attempt = 0
            max_attempts = 2
            success = False
            paragraph_output = {
                "paragraph_number": paragraph["paragraph_number"],
                "true_or_false": None
            }

            while attempt < max_attempts and not success:
                attempt += 1
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

                    cleaned_question = q_obj.question.strip()
                    if cleaned_question.endswith("."):
                        cleaned_question = cleaned_question[:-1]

                    log(
                        f"    🏅 Вопрос: {cleaned_question} [{expected_answer}]")

                    paragraph_output["true_or_false"] = ParagraphTFItem(
                        question=cleaned_question,
                        answer=expected_answer
                    ).model_dump()
                    success = True
                except Exception as e:
                    log(
                        f"    ⚠️ Ошибка (попытка {attempt}): {e} (книга {book_id}, абзац {paragraph['paragraph_number']}, язык {target_lang})")
                    time.sleep(2)

            chapter_output["paragraphs"].append(paragraph_output)

        result["chapters"].append(chapter_output)

    log(f"\n💾 Сохраняем результат в {result_field} для книги {book_id} и языка {target_lang}...")
    supabase.table("books_translations").update({
        result_field: json.dumps(result, ensure_ascii=False, indent=2)
    }).eq("book_id", book_id).eq("language", target_lang).execute()
    log(f"✅ Вопросы по абзацам сохранены в {result_field}.")

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    summary_msg = f"⏱ Время генерации вопросов: {minutes} мин {seconds} сек (книга {book_id}, язык {target_lang}, поле {result_field})"
    print(summary_msg)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(summary_msg + "\n")


def add_how_to_translate_tasks(book_id: int, words_field: str, base_task_field: str, result_field: str, target_lang: str, source_lang: str):

    start_time = time.time()
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"log_translate_task_book_{book_id}_{target_lang}.txt"

    def log(msg):
        print(msg)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    existing = supabase.table("books_translations").select(result_field).eq(
        "book_id", book_id).eq("language", target_lang).single().execute()
    raw_result = existing.data.get(result_field)
    if raw_result and str(raw_result).strip() not in {"", "{}", "[]"}:
        log(f"⏭ Пропускаем: поле {result_field} уже заполнено для книги {book_id}, языка {target_lang}")
        return

    log(f"📥 Загружаем {words_field} и {base_task_field} для книги {book_id}, язык {target_lang}...")
    words_response = supabase.table("books_translations").select(words_field).eq(
        "book_id", book_id).eq("language", target_lang).single().execute()
    tasks_response = supabase.table("books_translations").select(base_task_field).eq(
        "book_id", book_id).eq("language", target_lang).single().execute()

    words_data = json.loads(words_response.data.get(words_field))
    tasks_data = json.loads(tasks_response.data.get(base_task_field))

    result = {"chapters": []}

    total_paragraphs = sum(len(ch["paragraphs"])
                           for ch in tasks_data["chapters"])
    processed_paragraphs = 0

    for ch_words, ch_tasks in zip(words_data["chapters"], tasks_data["chapters"]):
        log(f"\n📘 Глава {ch_words['chapter_number']} (книга {book_id}, язык {target_lang})")
        updated_paragraphs = []

        for par_words, par_tasks in zip(ch_words["paragraphs"], ch_tasks["paragraphs"]):
            processed_paragraphs += 1
            percent = round((processed_paragraphs / total_paragraphs) * 100)

            paragraph_number = par_words["paragraph_number"]
            log(f"  ✂️ Абзац {paragraph_number} — {percent}%")

            word_objects = []
            word_lookup = {}

            for sentence in par_words["sentences"]:
                sid = sentence["sentence_number"]
                for wid, word in enumerate(sentence.get("words", [])):
                    word_id = f"{ch_words['chapter_number']}_{par_words['paragraph_number']}_{sid}_{wid + 1}"

                    o = word["o"].strip()
                    o_t = word["o_t"].strip()

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
                log("    ⚠️ Недостаточно слов")
                updated_paragraphs.append({
                    "paragraph_number": paragraph_number,
                    "how_to_translate": None
                })
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

            attempt = 0
            max_attempts = 2
            success = False
            task_result = None

            while attempt < max_attempts and not success:
                attempt += 1
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
                        log(
                            f"    ⚠️ Один из ID не найден в словаре: {e}. Пропускаем абзац.")
                        break

                    task_result = {
                        "c": result_obj.correct_id,
                        "i1": result_obj.incorrect1_id,
                        "i2": result_obj.incorrect2_id
                    }

                    log(f"    ✅ Вопрос: Как переводится '{correct_word.get('o_t', '<???>')}' → {correct_word.get('o', '—')} | {incorrect1.get('o', '—')} | {incorrect2.get('o', '—')}")
                    success = True
                except Exception as e:
                    log(f"    ❌ Ошибка GPT (попытка {attempt}): {e}")
                    time.sleep(2)

            updated_paragraphs.append({
                "paragraph_number": paragraph_number,
                "how_to_translate": task_result
            })
            time.sleep(1)

        result["chapters"].append({
            "chapter_number": ch_tasks["chapter_number"],
            "paragraphs": updated_paragraphs
        })

    log(f"\n💾 Сохраняем результат в {result_field}...")
    supabase.table("books_translations").update({
        result_field: json.dumps(result, ensure_ascii=False, indent=2)
    }).eq("book_id", book_id).eq("language", target_lang).execute()
    log(f"✅ Вопросы 'how to translate' с ID сохранены в поле {result_field}.")

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    log(f"⏱ Время генерации: {minutes} мин {seconds} сек (книга {book_id}, язык {target_lang}, поле {result_field})")


def add_two_words_tasks(book_id: int, words_field: str, base_task_field: str, result_field: str, target_lang: str):

    start_time = time.time()
    supabase = get_supabase_client()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"log_two_words_book_{book_id}_{target_lang}.txt"

    def log(msg):
        print(msg)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    existing = supabase.table("books_translations").select(result_field).eq(
        "book_id", book_id).eq("language", target_lang).single().execute()
    raw_result = existing.data.get(result_field)
    if raw_result and str(raw_result).strip() not in {"", "{}", "[]"}:
        log(f"⏭ Пропускаем: поле {result_field} уже заполнено для книги {book_id}, языка {target_lang}")
        return

    log(f"📥 Загружаем {words_field} и {base_task_field} для книги {book_id}, язык {target_lang}...")
    words_response = supabase.table("books_translations").select(words_field).eq(
        "book_id", book_id).eq("language", target_lang).single().execute()
    tasks_response = supabase.table("books_translations").select(base_task_field).eq(
        "book_id", book_id).eq("language", target_lang).single().execute()

    words_data = json.loads(words_response.data.get(words_field))
    tasks_data = json.loads(tasks_response.data.get(base_task_field))

    result = {"chapters": []}

    total_paragraphs = sum(len(ch["paragraphs"])
                           for ch in tasks_data["chapters"])
    processed_paragraphs = 0

    lang_names_pr = {
        "en": "английском",
        "es": "испанском",
        "fr": "французском",
        "de": "немецком",
        "it": "итальянском",
        "ru": "русском",
        "zh": "китайском",
        "ja": "японском",
        "ko": "корейском",
    }
    readable_target_pr = lang_names_pr.get(target_lang, target_lang)

    for ch_words, ch_tasks in zip(words_data["chapters"], tasks_data["chapters"]):
        log(f"\n📘 Глава {ch_words['chapter_number']} (книга {book_id}, язык {target_lang})")
        updated_paragraphs = []

        for par_words, par_tasks in zip(ch_words["paragraphs"], ch_tasks["paragraphs"]):
            processed_paragraphs += 1
            percent = round((processed_paragraphs / total_paragraphs) * 100)

            paragraph_number = par_words["paragraph_number"]
            log(f"  ✂️ Абзац {paragraph_number} — {percent}%")

            candidates = []
            word_lookup = {}

            for sentence in par_words["sentences"]:
                sid = sentence["sentence_number"]
                for wid, word in enumerate(sentence.get("words", [])):
                    word_id = f"{ch_words['chapter_number']}_{paragraph_number}_{sid}_{wid + 1}"
                    o_t = word.get("o_t", "").strip()
                    if len(o_t.split()) <= 2 and len(o_t) < 15:
                        candidates.append({"id": word_id, "o_t": o_t})
                        word_lookup[word_id] = o_t

            if len(candidates) < 2:
                log("    ⚠️ Недостаточно подходящих слов")
                updated_paragraphs.append({
                    "paragraph_number": paragraph_number,
                    "two_words": None
                })
                continue

            input_json = json.dumps(candidates, ensure_ascii=False, indent=2)

            system_prompt = (
                f"У тебя есть список слов из текста на {readable_target_pr} языке.\n"
                f"Твоя задача:\n"
                f"1. Найди два слова, которые похожи по типу (например, оба — действия или предметы), но разные по значению.\n"
                f"2. Верни их id как id1 и id2.\n"
                f"3. Придумай третье слово на {readable_target_pr} языке, похожее по типу, которое не подходит к теме текста.\n\n"
                f"Верни строго JSON: {{ id1, id2, invented }}"
            )

            attempt = 0
            max_attempts = 2
            success = False
            task_result = None

            while attempt < max_attempts and not success:
                attempt += 1
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
                        log(
                            f"    ❌ Ошибка: ID {task.id1} или {task.id2} не найдены. Пропускаем абзац.")
                        break

                    o1 = word_lookup[task.id1]
                    o2 = word_lookup[task.id2]

                    task_result = {
                        "id1": task.id1,
                        "id2": task.id2,
                        "invented": task.invented
                    }

                    log(f"    ✅ {task.id1}: {o1} | {task.id2}: {o2} → {task.invented}")
                    success = True
                except Exception as e:
                    log(f"    ❌ Ошибка GPT (попытка {attempt}): {e}")
                    time.sleep(2)

            updated_paragraphs.append({
                "paragraph_number": paragraph_number,
                "two_words": task_result
            })
            time.sleep(1)

        result["chapters"].append({
            "chapter_number": ch_tasks["chapter_number"],
            "paragraphs": updated_paragraphs
        })

    log(f"\n💾 Сохраняем результат в {result_field}...")
    supabase.table("books_translations").update({
        result_field: json.dumps(result, ensure_ascii=False, indent=2)
    }).eq("book_id", book_id).eq("language", target_lang).execute()
    log(f"✅ Вопросы 'two words + invented' сохранены в поле {result_field}.")

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    log(f"⏱ Время генерации: {minutes} мин {seconds} сек (книга {book_id}, язык {target_lang}, поле {result_field})")

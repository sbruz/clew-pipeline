import os
import re
import time
import json
import spacy
from typing import Optional
from openai import OpenAI, OpenAIError, APIConnectionError, RateLimitError, AuthenticationError
from utils.sentence_splitter import split_into_sentences
from schemas.translation_schema import (
    ChapterParagraphSentence,
    Sentence,
    ChapterItemWithSentences,
    ChapterStructureWithSentences,
    WordItem,
    ParagraphWordAnalysis,
    SentenceOriginal,
    ChapterParagraphSentenceOriginal,
    ChapterParagraphSentenceTranslated,
    ChapterItemWithTranslatedSentences,
    ChapterStructureTranslatedSentences,
)
from schemas.chapter_schema import ChapterStructure
from schemas.paragraph_split import ParagraphParts


def format_text_with_openai(text, lang="en", max_chars=4000) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = (
        "Ты — помощник по редактированию текста. Приведи текст в порядок, не меняя его содержания:\n"
        "- Удали переносы строк внутри предложений и абзацев.\n"
        "- Удали лишние пробелы перед первой строкой абзаца и между предложениями.\n"
        "- Замени двойные и тройные тире на одинарные с пробелами вокруг.\n"
        "- Не изменяй текст, не переписывай предложения.\n"
        "- Разделяй абзацы двумя переводами строки.\n"
    )

    try:
        print("⏳ Отправка запроса в OpenAI...")
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                # <--- Используем лимит из конфига
                {"role": "user", "content": text[:max_chars]}
            ],
            temperature=0.2
        )
        print("✅ Ответ получен от OpenAI.")
        return response.choices[0].message.content

    except RateLimitError:
        print("⛔ Превышен лимит запросов к OpenAI. Подожди и попробуй позже.")
    except AuthenticationError:
        print("⛔ Ошибка авторизации. Проверь OPENAI_API_KEY.")
    except APIConnectionError:
        print("⛔ Проблема с соединением. Проверь интернет или API-доступ.")
    except OpenAIError as e:
        print(f"❌ Ошибка OpenAI: {str(e)}")
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {str(e)}")

    return ""


def run(text, lang, max_chars):
    print("📘 Форматирование текста...")
    start = time.time()
    formatted = format_text_with_openai(text, lang, max_chars)
    end = time.time()

    if not formatted:
        print("⚠️ Форматирование не выполнено. Проверь ошибки выше.")
        return ""

    print(f"✅ Форматирование завершено за {round(end - start, 2)} секунд.\n")
    print("📄 Отформатированный текст:")
    print(formatted[:1000])
    return formatted


def split_paragraphs_with_openai(text, lang="en", max_chars=4000) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = (
        "Ты — помощник по форматированию текста для языкового приложения.\n"
        "Твоя задача — разбить текст на короткие абзацы:\n"
        "- Делай абзацы до 150 символов.\n"
        "- Если абзац включает прямую речь, всё равно можешь разбить его."
        "- Абзац заканчивается только в конце предложения.\n"
        "- Отделяй каждый абзац двумя переносами строки.\n"
        "- Не меняй и не переформулируй текст.\n"
        "Верни только переработанный текст."
    )

    try:
        print("⏳ Отправка текста на разбивку в OpenAI...")
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:max_chars]}
            ],
            temperature=0.3
        )
        print("✅ Ответ получен от OpenAI.")
        return response.choices[0].message.content

    except RateLimitError:
        print("⛔ Превышен лимит запросов к OpenAI.")
    except AuthenticationError:
        print("⛔ Ошибка авторизации. Проверь API-ключ.")
    except APIConnectionError:
        print("⛔ Проблема с соединением.")
    except OpenAIError as e:
        print(f"❌ Ошибка OpenAI: {str(e)}")
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {str(e)}")

    return ""


def split_into_paragraphs(book_id, lang, max_chars):
    from utils.supabase_client import get_supabase_client
    supabase = get_supabase_client()

    print(f"📥 Загружаем splitted_text для книги {book_id}...")
    response = supabase.table("books").select(
        "splitted_text").eq("id", book_id).single().execute()
    text = response.data.get("splitted_text")
    if not text:
        print("❌ Нет текста для разбивки.")
        return

    result = split_paragraphs_with_openai(text, lang, max_chars)

    if not result:
        print("⚠️ Разбиение на абзацы не выполнено.")
        return

    print("📤 Сохраняем separated_text...")
    supabase.table("books").update(
        {"separated_text": result}).eq("id", book_id).execute()
    print("✅ Разбиение на абзацы завершено и сохранено.")


def group_into_chapters(book_id: int, lang: str, max_chars: int):
    from utils.supabase_client import get_supabase_client
    supabase = get_supabase_client()

    print(f"📥 Загружаем separated_text_verified для книги {book_id}...")
    response = supabase.table("books").select(
        "separated_text_verified").eq("id", book_id).single().execute()
    text: Optional[str] = response.data.get("separated_text_verified")

    if not text:
        print("❌ Текст для главы не найден.")
        return

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = (
        "Ты — помощник по структурированию текста в главы для языкового приложения.\n"
        "Разбей текст на главы по следующим правилам:\n"
        "- Новая глава начинается там, где начинается новая сцена или внимание читателя переключается на что-то другое.\n"
        "- Рекомендуемый размер главы: от 15 до 50 абзацев.\n"
        "- Приоритет — смысловое деление, а не длина.\n"
        "- Не изменяй текст абзацев.\n"
        "- Начинай нумерацию азбацев с 1 внутри каждой главы.\n"
        "- Верни результат строго в структуре JSON, соответствующей ожидаемому формату.\n"
    )

    try:
        print("⏳ Отправка текста в GPT для структурированной разбивки на главы...")

        completion = client.beta.chat.completions.parse(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:max_chars]}
            ],
            response_format=ChapterStructure,
        )

        chapter_data = completion.choices[0].message.parsed

        # Преобразуем в строку JSON для сохранения в Supabase
        json_text = chapter_data.model_dump_json(indent=2)

        supabase.table("books").update(
            {"text_by_chapters": json_text}).eq("id", book_id).execute()
        print("✅ Разметка глав завершена и сохранена.")

    except Exception as e:
        print(f"❌ Ошибка при разбивке на главы: {e}")


def simplify_text_for_beginners(book_id: int, lang: str, max_chars: int):
    from utils.supabase_client import get_supabase_client
    from schemas.chapter_schema import ChapterStructure, ChapterItem
    import json

    supabase = get_supabase_client()

    print(f"📥 Загружаем text_by_chapters для книги {book_id}...")
    response = supabase.table("books").select(
        "text_by_chapters").eq("id", book_id).single().execute()
    original_text = response.data.get("text_by_chapters")

    if not original_text:
        print("❌ Нет текстовой структуры для адаптации.")
        return

    original_structure = ChapterStructure.model_validate_json(original_text)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    lang_map = {
        "en": "английском",
        "es": "испанском",
        "fr": "французском",
        "de": "немецком"
    }

    # если язык неизвестен — обобщённо
    selected_lang = lang_map.get(lang, "изначальном")

    system_prompt = (
        "Ты — дружелюбный рассказчик, который помогает адаптировать главы книг для изучающих английский.\n"
        "Правила:\n"
        "- Перепиши текст простыми словами, используя короткие, лёгкие предложения (уровень A2–B1).\n"
        "- Сохраняй разбивку на абзацы — не объединяй и не пропускай абзацы.\n"
        f"- Пиши на {selected_lang} языке.\n"
        "- Пиши в тёплом, дружелюбном тоне — как будто рассказываешь историю другу.\n"
        "- Не используй длинных или сложных конструкций. Каждое предложение должно быть понятно само по себе.\n"
        "- Не пиши как учебник. Пиши как человек, который хорошо рассказывает.\n"
        "- Не упрощай до уровня робота — текст должен 'течь' живо, естественно, понятно.\n"
        "Верни только один объект главы по схеме ChapterItem. Без пояснений."
    )

    simplified_chapters = []

    total_chapters = len(original_structure.chapters)

    for idx, chapter in enumerate(original_structure.chapters, start=1):
        progress = round((idx / total_chapters) * 100)
        print(
            f"\n📘 Глава {chapter.chapter_number} — {len(chapter.paragraphs)} абзацев ({progress}%)")

        chapter_attempts = 0
        success = False

        while chapter_attempts < 3 and not success:
            chapter_attempts += 1
            print(f"  🔄 Попытка {chapter_attempts}...")

            try:
                chapter_json = chapter.model_dump_json(indent=2)

                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": chapter_json[:max_chars]}
                    ],
                    response_format=ChapterItem,
                )

                simplified = completion.choices[0].message.parsed

                original_count = len(chapter.paragraphs)
                simplified_count = len(simplified.paragraphs)

                if simplified_count != original_count:
                    print(
                        f"  ⚠️ Ошибка: ожидалось {original_count} абзацев, получено {simplified_count}")
                else:
                    print(f"  ✅ Успешно. Абзацев: {simplified_count}")
                    simplified_chapters.append(simplified)
                    success = True

            except Exception as e:
                print(f"  ❌ Ошибка GPT: {e}")

        if not success:
            print(
                f"⛔ Превышено количество попыток для главы {chapter.chapter_number}. Остановка.")
            return

    # Сборка результата
    final_structure = ChapterStructure(chapters=simplified_chapters)
    json_text = final_structure.model_dump_json(indent=2)

    supabase.table("books").update(
        {"text_by_chapters_simplified": json_text}).eq("id", book_id).execute()
    print("\n✅ Все главы адаптированы и сохранены.")


def translate_text_structure(
    book_id: int,
    source_field: str,
    result_field: str,
    source_lang: str,
    target_lang: str,
    max_chars: int
):
    from utils.supabase_client import get_supabase_client
    supabase = get_supabase_client()

    print(f"📥 Загружаем {source_field} для книги {book_id}...")
    response = supabase.table("books").select(
        source_field).eq("id", book_id).single().execute()
    text = response.data.get(source_field)

    if not text:
        print(f"❌ Нет текста в поле {source_field}.")
        return

    original_structure = ChapterStructure.model_validate_json(text)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    paragraphs_sentences_flat = []
    chapters_result = []

    total_paragraphs = sum(len(ch.paragraphs)
                           for ch in original_structure.chapters)
    translated_count = 0

    system_prompt_translate = (
        f"Переведи каждое предложение с {source_lang} на {target_lang}. "
        "Структуру JSON не меняй: добавь поле 'sentence_translation' рядом с 'sentence_original'. "
        "Не удаляй, не объединяй предложения. Перевод должен быть естественным."
    )

    for chapter in original_structure.chapters:
        print(f"\n📚 Глава {chapter.chapter_number}")
        translated_paragraphs = []

        for paragraph in chapter.paragraphs:
            print(f"  ✂️ Абзац {paragraph.paragraph_number}")

            raw_sentences = split_into_sentences(
                paragraph.paragraph_content, source_lang)
            para_struct_original = ChapterParagraphSentenceOriginal(
                paragraph_number=paragraph.paragraph_number,
                sentences=[
                    SentenceOriginal(
                        sentence_number=i + 1,
                        sentence_original=s.strip()
                    )
                    for i, s in enumerate(raw_sentences)
                ]
            )
            paragraphs_sentences_flat.append(para_struct_original)

            # Перевод
            attempt = 0
            success = False

            while attempt < 3 and not success:
                attempt += 1
                try:
                    print(f"    🌍 Перевод (попытка {attempt})...")
                    completion = client.beta.chat.completions.parse(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": system_prompt_translate},
                            {"role": "user", "content": para_struct_original.model_dump_json(indent=2)[
                                :max_chars]}
                        ],
                        response_format=ChapterParagraphSentenceTranslated
                    )
                    translated_para = completion.choices[0].message.parsed

                    if len(translated_para.sentences) != len(para_struct_original.sentences):
                        print(
                            f"    ⚠️ Несовпадение: {len(para_struct_original.sentences)} → {len(translated_para.sentences)}")
                    else:
                        translated_paragraphs.append(translated_para)
                        translated_count += 1
                        percent = round(
                            (translated_count / total_paragraphs) * 100)
                        print(
                            f"    ✅ Успешно. 📊 Прогресс: {translated_count}/{total_paragraphs} ({percent}%)")
                        success = True

                except Exception as e:
                    print(f"    ❌ Ошибка GPT: {e}")
                    time.sleep(2)

            if not success:
                print(
                    f"⛔ Не удалось перевести абзац {paragraph.paragraph_number}. Остановка.")
                return

        chapters_result.append(ChapterItemWithTranslatedSentences(
            chapter_number=chapter.chapter_number,
            paragraphs=translated_paragraphs
        ))

    # Сохраняем финальный результат (SentenceTranslated)
    print(f"💾 Сохраняем {result_field}...")
    full_structure = ChapterStructureTranslatedSentences(
        chapters=chapters_result)
    json_translated = full_structure.model_dump_json(indent=2)
    supabase.table("books").update(
        {result_field: json_translated}).eq("id", book_id).execute()

    print("\n✅ Перевод всех абзацев завершён.")


def enrich_sentences_with_words(
    book_id: int,
    source_field: str,
    result_field: str,
    source_lang: str,
    target_lang: str,
    max_chars: int
):
    from utils.supabase_client import get_supabase_client
    supabase = get_supabase_client()

    print(f"📥 Загружаем {source_field} для книги {book_id}...")
    response = supabase.table("books").select(
        source_field).eq("id", book_id).single().execute()
    text = response.data.get(source_field)

    if not text:
        print(f"❌ Нет текста в поле {source_field}.")
        return

    structure = ChapterStructureWithSentences.model_validate_json(text)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    total_sentences = sum(len(p.sentences)
                          for c in structure.chapters for p in c.paragraphs)
    enriched_count = 0

    system_prompt = (
        f"Ты — языковой помощник.\n"
        f"Очисти каждое предложение от знаков препинания и разбей на минимальные по длине смысловые группы, сохраняя вместе фразовые глаголы, идиомы.\n"
        f"Для каждой группы укажи:\n"
        f"- o: оригинал\n"
        f"- o_t: перевод\n"
        f"- l: лемма (если совпадает с o, оставь пустым)\n"
        f"- l_t: перевод леммы (если l пустое, оставь пустым)\n\n"
        f"Ответ строго по заданной структуре (response_format)."
    )

    for chapter in structure.chapters:
        print(f"\n📚 Глава {chapter.chapter_number}")

        for paragraph in chapter.paragraphs:
            print(
                f"  ✂️ Абзац {paragraph.paragraph_number} — {len(paragraph.sentences)} предложений")

            attempt = 0
            success = False

            while attempt < 3 and not success:
                attempt += 1
                try:
                    input_data = [
                        {
                            "sentence_number": s.sentence_number,
                            "sentence_original": s.sentence_original,
                            "sentence_translation": s.sentence_translation
                        }
                        for s in paragraph.sentences
                    ]

                    completion = client.beta.chat.completions.parse(
                        model="gpt-4.1",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": json.dumps(
                                input_data, ensure_ascii=False, indent=2)[:max_chars]}
                        ],
                        response_format=ParagraphWordAnalysis,
                    )

                    parsed_paragraph = completion.choices[0].message.parsed
                    parsed_sentences = parsed_paragraph.sentences

                    if len(parsed_sentences) != len(paragraph.sentences):
                        print(
                            f"    ⚠️ Несовпадение числа предложений: ожидалось {len(paragraph.sentences)}, получено {len(parsed_sentences)}")
                    else:
                        for sentence in paragraph.sentences:
                            match = next(
                                (s for s in parsed_sentences if s.sentence_number == sentence.sentence_number), None)
                            if not match:
                                raise ValueError(
                                    f"Предложение {sentence.sentence_number} не найдено")
                            sentence.words = match.words

                        enriched_count += len(paragraph.sentences)
                        percent = round(
                            (enriched_count / total_sentences) * 100)
                        print(
                            f"    ✅ Успешно — {len(paragraph.sentences)} предложений. 📊 Прогресс: {enriched_count}/{total_sentences} ({percent}%)")
                        success = True

                except Exception as e:
                    print(f"    ❌ Ошибка при анализе слов: {e}")

            if not success:
                print(
                    f"⛔ Не удалось обработать абзац {paragraph.paragraph_number}. Остановка.")
                return

    print(f"\n💾 Сохраняем {result_field}...")
    json_result = structure.model_dump_json(indent=2)
    supabase.table("books").update(
        {result_field: json_result}).eq("id", book_id).execute()

    print("✅ Разбор слов завершён и сохранён.")

# новый промежуточный шаг после форматирования - разбивка на короткие предложения


def split_into_sentences(book_id, lang="en", max_chars=4000):
    from utils.supabase_client import get_supabase_client

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    supabase = get_supabase_client()

    print(f"📥 Загружаем formated_text для книги {book_id}...")
    response = supabase.table("books").select(
        "formated_text").eq("id", book_id).single().execute()
    text = response.data.get("formated_text")
    if not text:
        print("❌ Нет текста для разбивки.")
        return

    system_prompt = (
        "Ты — помощник по форматированию текста для языкового приложения.\n"
        "Твоя задача — разбить длинные предложения на короткие, сохранив логическую и грамматическую корректность.\n"
        "- Оставь без изменений предложения, которые при разбивке могут потерять смысл.\n"
        "- Не изменяй порядок слов и не изменяй текст.\n"
        "- Если предложение включает прямую речь, всё равно можешь разбить её на несколько предложений, если это позволяет сохранить грамматическую и логическую корректность. Не бойся ставить точки даже внутри кавычек. Вставные конструкции с кавычками и запятыми — не повод избегать разбиения. Просто соблюдай смысл."
        "Верни только переработанный текст."
    )

    try:
        print("⏳ Отправка текста на разбивку предложений в OpenAI...")
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text[:max_chars]}
            ],
            temperature=0.3
        )
        print("✅ Ответ получен от OpenAI.")
        result = response.choices[0].message.content

    except RateLimitError:
        print("⛔ Превышен лимит запросов к OpenAI.")
        return
    except AuthenticationError:
        print("⛔ Ошибка авторизации. Проверь API-ключ.")
        return
    except APIConnectionError:
        print("⛔ Проблема с соединением.")
        return
    except OpenAIError as e:
        print(f"❌ Ошибка OpenAI: {str(e)}")
        return
    except Exception as e:
        print(f"❌ Неизвестная ошибка: {str(e)}")
        return

    if not result:
        print("⚠️ Разбиение не выполнено.")
        return

    print("📤 Сохраняем splitted_text...")
    supabase.table("books").update(
        {"splitted_text": result}).eq("id", book_id).execute()
    print("✅ Разбиение на предложения завершено и сохранено.")

# РУЧНАЯ РАЗБИВКА ТЕКСТА НА ПАРАГРАФЫ


def split_paragraph_manually(paragraph: str, spacy_nlp, max_length: int = 200, min_chunk_len: int = 30) -> list[str]:
    doc = spacy_nlp(paragraph)
    sentences = [sent.text.strip() for sent in doc.sents]

    new_paragraphs = []
    current = ""

    for i, sentence in enumerate(sentences):
        # Считаем, сколько символов осталось в абзаце, если бы мы НЕ добавили текущее предложение
        remaining_sentences = sentences[i:]
        remaining_length = sum(len(s) for s in remaining_sentences)

        # Всегда добавляем, если текущий накопленный текст слишком короткий
        if len(current) < min_chunk_len:
            current += (" " if current else "") + sentence
            continue

        # Не отделяем короткое предложение в хвост
        if remaining_length < min_chunk_len:
            current += (" " if current else "") + sentence
            continue

        # Если можем добавить предложение, не превышая лимит — добавим
        if len(current) + len(sentence) + 1 <= max_length:
            current += (" " if current else "") + sentence
        else:
            # Заканчиваем текущий абзац
            if current:
                new_paragraphs.append(current.strip())
            current = sentence

    if current:
        new_paragraphs.append(current.strip())

    return new_paragraphs


def verify_separated_text(book_id: int, lang_code: str, nlp):
    from utils.supabase_client import get_supabase_client
    supabase = get_supabase_client()

    print(f"📥 Загружаем separated_text для книги {book_id}...")
    response = supabase.table("books").select(
        "separated_text").eq("id", book_id).single().execute()
    text: Optional[str] = response.data.get("separated_text")

    if not text:
        print("❌ Текст не найден.")
        return

    end_punctuation = re.compile(r"[.!?…]")
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    long_paragraphs = [p for p in paragraphs if len(p) > 200]

    print(
        f"🔍 Всего абзацев: {len(paragraphs)} | Длинных: {len(long_paragraphs)}")

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    verified_paragraphs = []
    progress_log = []

    for idx, paragraph in enumerate(paragraphs, start=1):
        if len(paragraph) <= 200:
            verified_paragraphs.append(paragraph)
            continue

        status = "failed"
        if end_punctuation.search(paragraph):
            try:
                chunk_count = max(1, round(len(paragraph) / 150))
                system_prompt = (
                    f"Ты помощник по делению текста. Язык текста — {lang_code}. "
                    f"Раздели абзац на примерно равные части по длине, так, чтобы каждая часть заканчивалась полным предложением. "
                    f"Цель — разбить абзац на {chunk_count} частей. Не изменяй предложения и не добавляй ничего лишнего. "
                    "Ответ верни строго в JSON: {\"parts\": [\"часть 1\", \"часть 2\", ...]}"
                )

                completion = client.beta.chat.completions.parse(
                    model="gpt-4.1",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": paragraph}
                    ],
                    response_format=ParagraphParts
                )

                parts = completion.choices[0].message.parsed.parts
                all_good = True

                for part in parts:
                    if len(part) > 200 and end_punctuation.search(part):
                        manual_parts = split_paragraph_manually(part, nlp)
                        verified_paragraphs.extend(manual_parts)
                        if any(len(p) > 200 for p in manual_parts):
                            status = "failed"
                        else:
                            status = "manual OK"
                        all_good = False
                    else:
                        verified_paragraphs.append(part)

                if all_good:
                    status = "openai OK"

            except Exception as e:
                print(f"⚠️ Ошибка GPT: {e}. Пробуем вручную...")
                manual_parts = split_paragraph_manually(paragraph, nlp)
                verified_paragraphs.extend(manual_parts)
                if any(len(p) > 200 for p in manual_parts):
                    status = "failed"
                else:
                    status = "manual OK"
        else:
            verified_paragraphs.append(paragraph)
            status = "failed"

        if len(paragraph) > 200:
            log_index = len(progress_log) + 1
            print(
                f"🧩 Длинный абзац {log_index}/{len(long_paragraphs)} → {status}")
            progress_log.append((log_index, status))

    final_text = "\n\n".join(verified_paragraphs)
    supabase.table("books").update(
        {"separated_text_verified": final_text}
    ).eq("id", book_id).execute()

    print("📤 Сохранено в separated_text_verified.")

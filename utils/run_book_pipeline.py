def process_book_id(book_id: int):
    import os
    import yaml
    import spacy
    import subprocess
    import multiprocessing
    from dotenv import load_dotenv
    from utils.supabase_client import load_book_text, save_formatted_text, get_supabase_client
    from utils.supabase_client import check_supabase_connection
    from utils.elevenlabs_client import get_elevenlabs_voices
    from steps import preprocess, voice, export, goals, tasks, mems, pictures, characters, embeddings, chapters
    from utils.check_preparation import check_before_translate

    load_dotenv()

    pid = os.getpid()
    proc_name = multiprocessing.current_process().name
    print(f"🔧 [PID {pid}] [{proc_name}] Начинаем обработку книги ID {book_id}")

    # Загружаем конфиг
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    max_chars = config.get("limits", {}).get("max_chars_per_request", 5000)
    source_lang = config["source_lang"]
    target_langs = [lang.strip() for lang in config["target_lang"].split(",")]
    steps_enabled = config["steps"]
    max_paragraphs = config.get("options", {}).get("max_voiced_paragraphs", -1)

    def ensure_spacy_model(lang_code: str):
        lang_map = {
            "en": "en_core_web_sm",
            "es": "es_core_news_sm",
            "fr": "fr_core_news_sm",
            "de": "de_core_news_sm",
            "it": "it_core_news_sm",
        }
        model_name = lang_map.get(lang_code)
        if not model_name:
            raise ValueError(f"❌ Неизвестный язык: {lang_code}")

        try:
            return spacy.load(model_name)
        except OSError:
            print(f"📦 Модель {model_name} не найдена. Устанавливаем...")
            subprocess.run(
                ["python", "-m", "spacy", "download", model_name], check=True)
            return spacy.load(model_name)

    supabase = get_supabase_client()
    check_supabase_connection()

    nlp = ensure_spacy_model(source_lang)

    print(f"\n=== Обработка книги ID {book_id} ===")

    # Проверка наличия книги
    try:
        book_info_resp = supabase.table("books").select(
            "title", "author").eq("id", book_id).single().execute()
        book_info = book_info_resp.data
    except Exception as e:
        print(f"[{book_id}] ❌ Книга не найдена в базе. Пропускаем. Ошибка: {e}")
        return

    title = book_info.get("title", "Без названия")
    author = book_info.get("author", "Неизвестный автор")
    print(f"[{book_id}] ✅ Найдена книга: {title} — {author}")

    if steps_enabled.get("preprocess"):
        book_text = load_book_text(book_id)
        formatted = preprocess.run(book_text, source_lang, max_chars)
        save_formatted_text(book_id, formatted)

    if steps_enabled.get("sentence_split"):
        preprocess.split_into_sentences(book_id, source_lang, max_chars)

    if steps_enabled.get("paragraph_split"):
        preprocess.split_into_paragraphs(book_id, source_lang, max_chars)

    if steps_enabled.get("paragraph_split_manual"):
        preprocess.verify_separated_text(book_id, source_lang, nlp)

    if steps_enabled.get("chapter_split"):
        preprocess.group_into_chapters(book_id, source_lang, max_chars)

    if steps_enabled.get("simplify_text"):
        preprocess.simplify_text_for_beginners(book_id, source_lang, max_chars)

    if steps_enabled.get("check_preparation"):
        check_before_translate(book_id)
        return

    if steps_enabled.get("generate_mems"):
        mems.generate_memes_for_book(book_id, source_lang)
        return

    if steps_enabled.get("generate_pictures"):
        pictures.generate_object_pictures_for_book(book_id)
        return

    if steps_enabled.get("collect_characters"):
        characters.get_characters_appearance(book_id)
        return

    if steps_enabled.get("voice_narration"):
        # voices = get_elevenlabs_voices(source_lang)
        # voice_plan = voice.get_voice_plan_for_book(title, author, voices)
        voice.generate_audio_for_chapters(
            book_id=book_id,
            is_simplified=False,
            text_field="text_by_chapters",
            # voice_plan=voice_plan,
            output_dir=f"voice_book_{book_id}",
            # voices_list=voices,
            log_voice=config.get("options", {}).get("log_voice", False),
            max_paragraphs=max_paragraphs
        )
        if not steps_enabled.get("voice_narration_simplified"):
            return

    if steps_enabled.get("voice_narration_simplified"):
        # voices = get_elevenlabs_voices(source_lang)
        # voice_plan = voice.get_voice_plan_for_book(title, author, voices)
        voice.generate_audio_for_chapters(
            book_id=book_id,
            is_simplified=True,
            text_field="text_by_chapters_simplified",
            # voice_plan=voice_plan,
            output_dir=f"voice_book_{book_id}",
            # voices_list=voices,
            log_voice=config.get("options", {}).get("log_voice", False),
            max_paragraphs=max_paragraphs
        )
        return

    if steps_enabled.get("embeddings"):
        embeddings.generate_embedding(book_id=book_id)

    if steps_enabled.get("chapters_title"):
        chapters.generate_titles(
            book_id=book_id, book_title=title, book_author=author)

    if steps_enabled.get("chapters_icons"):
        chapters.generate_icons(
            book_id=book_id, title=title, author=author)

    for lang in target_langs:
        print(f"🌐 Переводим на язык: {lang}")

        if steps_enabled.get("translate_sentences"):
            preprocess.translate_text_structure(
                book_id=book_id,
                source_field="text_by_chapters",
                result_field="text_by_chapters_sentence_translation",
                source_lang=source_lang,
                target_lang=lang,
                max_chars=max_chars,
                spacy_nlp=nlp,
                chapter_number=-1
            )

        if steps_enabled.get("translate_sentences_simplified"):
            preprocess.translate_text_structure(
                book_id=book_id,
                source_field="text_by_chapters_simplified",
                result_field="text_by_chapters_simplified_sentence_translation",
                source_lang=source_lang,
                target_lang=lang,
                max_chars=max_chars,
                spacy_nlp=nlp,
                chapter_number=-1
            )

        if steps_enabled.get("translate_words"):
            preprocess.enrich_sentences_with_words(
                book_id=book_id,
                source_field="text_by_chapters_sentence_translation",
                result_field="text_by_chapters_sentence_translation_words",
                source_lang=source_lang,
                target_lang=lang,
                max_chars=max_chars,
                paras_number=-1
            )

        if steps_enabled.get("translate_words_simplified"):
            preprocess.enrich_sentences_with_words(
                book_id=book_id,
                source_field="text_by_chapters_simplified_sentence_translation",
                result_field="text_by_chapters_simplified_sentence_translation_words",
                source_lang=source_lang,
                target_lang=lang,
                max_chars=max_chars,
                paras_number=-1
            )

        if steps_enabled.get("tasks_true_or_false"):
            tasks.generate_paragraph_tasks(
                book_id,
                "text_by_chapters_sentence_translation",
                "tasks_true_or_false",
                lang,
                source_lang
            )

        if steps_enabled.get("tasks_true_or_false_simplified"):
            tasks.generate_paragraph_tasks(
                book_id,
                "text_by_chapters_simplified_sentence_translation",
                "tasks_true_or_false_simplified",
                lang,
                source_lang
            )

        if steps_enabled.get("tasks_how_to_translate"):
            tasks.add_how_to_translate_tasks(
                book_id=book_id,
                words_field="text_by_chapters_sentence_translation_words",
                base_task_field="tasks_true_or_false",
                result_field="tasks_truefalse_howto",
                target_lang=lang,
                source_lang=source_lang
            )

        if steps_enabled.get("tasks_how_to_translate_simplified"):
            tasks.add_how_to_translate_tasks(
                book_id=book_id,
                words_field="text_by_chapters_simplified_sentence_translation_words",
                base_task_field="tasks_true_or_false_simplified",
                result_field="tasks_truefalse_howto_simplified",
                target_lang=lang,
                source_lang=source_lang
            )

        if steps_enabled.get("tasks_two_words"):
            tasks.add_two_words_tasks(
                book_id=book_id,
                words_field="text_by_chapters_sentence_translation_words",
                base_task_field="tasks_truefalse_howto",
                result_field="tasks_truefalse_howto_words",
                target_lang=lang
            )

        if steps_enabled.get("tasks_two_words_simplified"):
            tasks.add_two_words_tasks(
                book_id=book_id,
                words_field="text_by_chapters_simplified_sentence_translation_words",
                base_task_field="tasks_truefalse_howto_simplified",
                result_field="tasks_truefalse_howto_words_simplified",
                target_lang=lang
            )

        if steps_enabled.get("chapters_title_translate"):
            chapters.translate_titles(
                book_id=book_id,
                source_field="chapters_titles",
                result_field="chapters_titles_translations",
                target_lang=lang,
                gemini_refine=False
            )

    print(
        f"🔧 [PID {pid}] [{proc_name}] ✅ Обработка книги ID {book_id} завершена")

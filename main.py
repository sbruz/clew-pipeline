from utils.supabase_client import load_book_text, save_formatted_text, check_supabase_connection
from utils.supabase_client import get_supabase_client
from utils.elevenlabs_client import get_elevenlabs_voices
from steps import preprocess, voice, export
import yaml

from dotenv import load_dotenv
load_dotenv()


# Загружаем конфиг
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

max_chars = config.get("limits", {}).get("max_chars_per_request", 5000)
book_id = config["book_id"]
source_lang = config["source_lang"]
target_lang = config["target_lang"]
steps_enabled = config["steps"]
max_paragraphs = config.get("options", {}).get("max_voiced_paragraphs", -1)


# отладка
check_supabase_connection()

# Этапы

if steps_enabled.get("preprocess"):
    book_text = load_book_text(book_id)
    formatted = preprocess.run(book_text, source_lang, max_chars)
    save_formatted_text(book_id, formatted)

if steps_enabled.get("paragraph_split"):
    preprocess.split_into_paragraphs(book_id, source_lang, max_chars)

if steps_enabled.get("chapter_split"):
    preprocess.group_into_chapters(book_id, source_lang, max_chars)

if steps_enabled.get("simplify_text"):
    preprocess.simplify_text_for_beginners(book_id, source_lang, max_chars)

if steps_enabled.get("translate_sentences"):
    preprocess.translate_text_structure(
        book_id=book_id,
        source_field="text_by_chapters",
        intermediate_field="text_by_chapters_sentence",
        result_field="text_by_chapters_sentence_translation",
        source_lang=source_lang,
        target_lang=target_lang,
        max_chars=max_chars
    )

if steps_enabled.get("translate_sentences_simplified"):
    preprocess.translate_text_structure(
        book_id=book_id,
        source_field="text_by_chapters_simplified",
        intermediate_field="text_by_chapters_simplified_sentence",
        result_field="text_by_chapters_simplified_sentence_translation",
        source_lang=source_lang,
        target_lang=target_lang,
        max_chars=max_chars
    )

if steps_enabled.get("translate_words"):
    preprocess.enrich_sentences_with_words(
        book_id=book_id,
        source_field="text_by_chapters_sentence_translation",
        result_field="text_by_chapters_sentence_translation_words",
        source_lang=source_lang,
        target_lang=target_lang,
        max_chars=max_chars
    )

if steps_enabled.get("translate_words_simplified"):
    preprocess.enrich_sentences_with_words(
        book_id=book_id,
        source_field="text_by_chapters_simplified_sentence_translation",
        result_field="text_by_chapters_simplified_sentence_translation_words",
        source_lang=source_lang,
        target_lang=target_lang,
        max_chars=max_chars
    )

if steps_enabled.get("voice_narration"):
    supabase = get_supabase_client()
    book_info = supabase.table("books").select(
        "title, author").eq("id", book_id).single().execute()
    title = book_info.data.get("title", "Без названия")
    author = book_info.data.get("author", "Неизвестный автор")

    voices = get_elevenlabs_voices()
    voice_plan = voice.get_voice_plan_for_book(title, author, voices)
    voice.generate_audio_for_chapters(
        book_id=book_id,
        is_simplified=False,
        text_field="text_by_chapters",
        voice_plan=voice_plan,
        output_dir=f"voice_book_{book_id}",
        voices_list=voices,
        log_voice=config.get("options", {}).get("log_voice", False),
        max_paragraphs=max_paragraphs
    )

if steps_enabled.get("voice_narration_simplified"):
    supabase = get_supabase_client()
    book_info = supabase.table("books").select(
        "title, author").eq("id", book_id).single().execute()
    title = book_info.data.get("title", "Без названия")
    author = book_info.data.get("author", "Неизвестный автор")

    voices = get_elevenlabs_voices()
    voice_plan = voice.get_voice_plan_for_book(title, author, voices)
    voice.generate_audio_for_chapters(
        book_id=book_id,
        is_simplified=True,
        text_field="text_by_chapters_simplified",
        voice_plan=voice_plan,
        output_dir=f"voice_book_{book_id}",
        voices_list=voices,
        log_voice=config.get("options", {}).get("log_voice", False),
        max_paragraphs=max_paragraphs
    )

if steps_enabled.get("export"):
    export.export_book_json(
        book_id, source_lang=source_lang, target_lang=target_lang)

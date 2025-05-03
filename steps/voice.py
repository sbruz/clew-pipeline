import os
import json
import base64
import requests
from pathlib import Path
from openai import OpenAI
from schemas.voice_schema import VoicePlan
from schemas.chapter_schema import ChapterStructure
from utils.supabase_client import get_supabase_client


def get_voice_plan_for_book(title: str, author: str, voices: list[dict]) -> VoicePlan:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = (
        "Ты — помощник по озвучке книг. Выбери один наиболее подходящий голос для рассказчика этой книги, основываясь на описаниях голосов с учетом жанра и сюжета произведения. "
        # "Выбирай из тех голосов, у которых американский акцент и желательно пометка warm. "
        "Дай четкие однозначные рекомендацию по интонации и стилю подачи на английском языке, не вдаваясь в подробности. "
        "Верни строго объект с полями voice_id, voice_name, voice_description и narration_style."
    )

    voices_text = json.dumps(voices, ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Название книги: {title}\nАвтор: {author}\nСписок голосов:\n{voices_text}"}
    ]

    completion = client.beta.chat.completions.parse(
        model="gpt-4.1",
        messages=messages,
        response_format=VoicePlan
    )

    return completion.choices[0].message.parsed


def generate_audio_for_chapters(
    book_id: int,
    is_simplified: bool,
    text_field: str,
    voice_plan: VoicePlan,
    output_dir: str,
    voices_list: list[dict],
    log_voice: bool,
    max_paragraphs: int
):
    supabase = get_supabase_client()

    print(f"📥 Загружаем {text_field} для книги {book_id}...")
    response = supabase.table("books").select(
        text_field).eq("id", book_id).single().execute()
    text = response.data.get(text_field)

    if not text:
        print(f"❌ Нет текста в поле {text_field}.")
        return

    structure = ChapterStructure.model_validate_json(text)
    api_key = os.getenv("ELEVENLABS_API_KEY")
    Path(f"export_book_{book_id}").mkdir(exist_ok=True)
    output_path = Path(f"export_book_{book_id}") / f"voice_book_{book_id}"
    output_path.mkdir(exist_ok=True)

    if log_voice:
        with open(output_path / "voices_log.json", "w", encoding="utf-8") as f:
            json.dump(voices_list, f, ensure_ascii=False, indent=2)
        with open(output_path / "voice_plan.json", "w", encoding="utf-8") as f:
            json.dump(voice_plan.model_dump(), f, ensure_ascii=False, indent=2)
        print(
            f"📝 Выбран голос: {voice_plan.voice_name} ({voice_plan.voice_id})")
        print(f"🧾 Интонация: {voice_plan.narration_style}")

    voice_settings = {
        "stability": 0.5,
        "similarity_boost": 0.7,
        "speed": 0.7 if is_simplified else 0.9
    }

    counter = 0

    for chapter in structure.chapters:
        paragraphs = chapter.paragraphs
        for idx, paragraph in enumerate(paragraphs):
            if max_paragraphs != -1 and counter >= max_paragraphs:
                print(
                    f"⏹️ Достигнут лимит в {max_paragraphs} абзацев. Остановка.")
                return

            counter += 1
            filename_base = f"{chapter.chapter_number}_{paragraph.paragraph_number}"
            if is_simplified:
                filename_base += "_s"

            filename_mp3 = filename_base + ".mp3"
            filename_json = filename_base + "_time.json"
            filename_txt = filename_base + ".txt"

            full_path_mp3 = output_path / filename_mp3
            full_path_json = output_path / filename_json
            full_path_txt = output_path / filename_txt

            text_to_speak = paragraph.paragraph_content
            instruction = voice_plan.narration_style
            if is_simplified:
                instruction += " Speak with longer pauses between words."
            instruction += " Speak clearly and pronounce all sounds."

            full_text = f"{instruction}\n{text_to_speak}"

            if log_voice:
                with open(full_path_txt, "w", encoding="utf-8") as f:
                    f.write(full_text)

            print(f"\n🎤 Генерируем аудио и тайминги: {filename_mp3}")

            previous_text = paragraphs[idx -
                                       1].paragraph_content if idx > 0 else ""
            next_text = paragraphs[idx +
                                   1].paragraph_content if idx < len(paragraphs) - 1 else ""

            response = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_plan.voice_id}/with-timestamps",
                headers={
                    "xi-api-key": api_key,
                    "accept": "application/json",
                    "Content-Type": "application/json"
                },
                json={
                    "text": text_to_speak,
                    "previous_text": previous_text,
                    "next_text": next_text,
                    "model_id": "eleven_multilingual_v2",  # "eleven_monolingual_v1",
                    "voice_settings": voice_settings,
                    "timestamp_format": ["word"]
                }
            )

            if response.status_code == 200:
                data = response.json()
                audio_base64 = data.get("audio_base64")
                alignment = data.get("alignment")

                if audio_base64:
                    with open(full_path_mp3, "wb") as f:
                        f.write(base64.b64decode(audio_base64))
                    print(f"✅ Аудио сохранено: {full_path_mp3}")
                else:
                    print(f"⚠️ Аудио не найдено в ответе.")

                if alignment:
                    with open(full_path_json, "w", encoding="utf-8") as f:
                        json.dump(alignment, f, ensure_ascii=False, indent=2)
                    print(f"🕒 Тайминги сохранены: {full_path_json}")
                else:
                    print(f"⚠️ Тайминги не найдены в ответе.")
            else:
                print(
                    f"❌ Ошибка запроса: {response.status_code} — {response.text}")

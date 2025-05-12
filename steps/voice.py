import os
import json
import time
import base64
import requests
from pathlib import Path
from openai import OpenAI
from typing import List
from schemas.voice_schema import VoicePlan
from schemas.chapter_schema import ChapterStructure
from utils.supabase_client import get_supabase_client


def generate_audio_for_chapters(
    book_id: int,
    is_simplified: bool,
    text_field: str,
    output_dir: str,
    log_voice: bool,
    max_paragraphs: int
):

    supabase = get_supabase_client()
    start_time = time.time()
    elevenlabs_requests = 0

    flag_field = "voiced_simp" if is_simplified else "voiced_orig"
    flag_check = supabase.table("books").select(
        flag_field).eq("id", book_id).single().execute()
    current_value = flag_check.data.get(flag_field)
    if current_value is not None:
        print(
            f"⏭ Пропуск озвучки для книги {book_id}, is_simplified={is_simplified}, так как {flag_field} уже установлено.")
        return

    # "занимаем" книгу — пишем False
    supabase.table("books").update(
        {flag_field: False}).eq("id", book_id).execute()

    print(f"📥 Загружаем {text_field} и голос для книги {book_id}...")
    book_response = supabase.table("books").select(
        "voice").eq("id", book_id).single().execute()
    voice_ref = book_response.data.get("voice")

    if not voice_ref:
        print(f"❌ У книги {book_id} не задан voice.")
        supabase.table("books").update(
            {flag_field: None}).eq("id", book_id).execute()
        return

    voice_response = supabase.table("elevenlabs_voices").select(
        "voice_id, name").eq("id", voice_ref).single().execute()
    voice_data = voice_response.data

    if not voice_data or not voice_data.get("voice_id"):
        print(
            f"❌ Не удалось найти voice_id в elevenlabs_voices для voice={voice_ref} (book_id={book_id})")
        supabase.table("books").update(
            {flag_field: None}).eq("id", book_id).execute()
        return

    voice_id = voice_data["voice_id"]
    voice_name = voice_data.get("name", "")

    response = supabase.table("books").select(
        text_field).eq("id", book_id).single().execute()
    text = response.data.get(text_field)

    if not text:
        print(f"❌ Нет текста в поле {text_field} для книги {book_id}.")
        supabase.table("books").update(
            {flag_field: None}).eq("id", book_id).execute()
        return

    structure = ChapterStructure.model_validate_json(text)
    api_key = os.getenv("ELEVENLABS_API_KEY")

    export_path = Path("export/voices")
    export_path.mkdir(parents=True, exist_ok=True)

    existing_files = {f.name for f in export_path.glob(
        f"book_{book_id}_*{'_s' if is_simplified else ''}.mp3")}

    if log_voice:
        with open(export_path / f"book_{book_id}_voice_meta.json", "w", encoding="utf-8") as f:
            json.dump(voice_data, f, ensure_ascii=False, indent=2)
        print(f"📝 Выбран голос: {voice_name} ({voice_id})")

    voice_settings = {
        "stability": 0.5,
        "similarity_boost": 0.7,
        "speed": 0.8 if is_simplified else 0.9
    }

    counter = 0
    skip_mode = True

    for chapter in structure.chapters:
        for paragraph in chapter.paragraphs:
            filename_base = f"book_{book_id}_{chapter.chapter_number}_{paragraph.paragraph_number}"
            suffix = "_s" if is_simplified else ""
            filename_mp3 = f"{filename_base}{suffix}.mp3"

            if filename_mp3 in existing_files:
                print(f"⏭ Пропуск {filename_mp3}, уже существует.")
                continue
            else:
                skip_mode = False

            if max_paragraphs != -1 and counter >= max_paragraphs:
                print(
                    f"⏹️ Достигнут лимит в {max_paragraphs} абзацев. Остановка.")
                supabase.table("books").update(
                    {flag_field: None}).eq("id", book_id).execute()
                return

            counter += 1

            full_path_mp3 = export_path / filename_mp3
            full_path_json = export_path / f"{filename_base}_time{suffix}.json"
            full_path_txt = export_path / f"{filename_base}{suffix}.txt"

            text_to_speak = paragraph.paragraph_content

            if log_voice:
                with open(full_path_txt, "w", encoding="utf-8") as f:
                    f.write(text_to_speak)

            print(f"\n🎤 Генерируем аудио и тайминги: {filename_mp3}")

            success = False
            for attempt in range(2):
                try:
                    response = requests.post(
                        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
                        headers={
                            "xi-api-key": api_key,
                            "accept": "application/json",
                            "Content-Type": "application/json"
                        },
                        json={
                            "text": text_to_speak,
                            "previous_text": "",
                            "next_text": "",
                            "model_id": "eleven_multilingual_v2",
                            "voice_settings": voice_settings,
                            "timestamp_format": ["word"]
                        }
                    )
                    elevenlabs_requests += 1

                    if response.status_code == 200:
                        data = response.json()
                        audio_base64 = data.get("audio_base64")
                        alignment = data.get("alignment")

                        if audio_base64:
                            with open(full_path_mp3, "wb") as f:
                                f.write(base64.b64decode(audio_base64))
                            print(f"✅ Аудио сохранено: {full_path_mp3}")
                        else:
                            print(
                                f"⚠️ [{book_id}:{chapter.chapter_number}:{paragraph.paragraph_number}] Аудио не найдено в ответе.")

                        if alignment:
                            with open(full_path_json, "w", encoding="utf-8") as f:
                                json.dump(alignment, f,
                                          ensure_ascii=False, indent=2)
                            print(f"🕒 Тайминги сохранены: {full_path_json}")
                        else:
                            print(
                                f"⚠️ [{book_id}:{chapter.chapter_number}:{paragraph.paragraph_number}] Тайминги не найдены в ответе.")

                        success = True
                        break
                    else:
                        print(
                            f"❌ Ошибка запроса к ElevenLabs (попытка {attempt + 1}) — {response.status_code}: {response.text}")
                except Exception as e:
                    print(
                        f"❌ Ошибка запроса (попытка {attempt + 1}) к ElevenLabs: {e}")
                time.sleep(2)

            if not success:
                print(
                    f"⛔ Ошибка генерации аудио. Завершаем процесс для книги {book_id}.")
                supabase.table("books").update(
                    {flag_field: None}).eq("id", book_id).execute()
                return

    supabase.table("books").update(
        {flag_field: True}).eq("id", book_id).execute()

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    avg_time = elapsed / elevenlabs_requests if elevenlabs_requests > 0 else 0
    print(
        f"\n📘 Завершена генерация аудио для книги {book_id} ({text_field}). Потрачено времени: {minutes} мин {seconds} сек. Запросов к ElevenLabs: {elevenlabs_requests}. Среднее время на запрос: {avg_time:.2f} сек")

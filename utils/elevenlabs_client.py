import os
import requests


import os
import requests


def get_elevenlabs_voices(source_lang: str):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    url = "https://api.elevenlabs.io/v1/voices"

    headers = {
        "accept": "application/json",
        "xi-api-key": api_key
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    voices = response.json()["voices"]

    voice_infos = []

    print(f"🎙 Получено всего голосов : {len(voices)}")
    # print(voices)

    for v in voices:

        # Условия фильтрации
        is_creator = "creator" in v.get("available_for_tiers", [])
        is_multilingual = "eleven_multilingual_v2" in v.get(
            "high_quality_base_model_ids", [])
        has_language = any(
            lang.get("language") == source_lang
            for lang in v.get("verified_languages", [])
        )

        info = {
            "voice_id": v["voice_id"],
            "voice_name": v["name"],
            "voice_description": v.get("labels", {}).get("description", ""),
            "accent": v.get("labels", {}).get("accent", ""),
            "gender": v.get("labels", {}).get("gender", "")
        }
        if is_multilingual:
            voice_infos.append(info)

    print(f"🎙 Найдено подходящих голосов: {len(voice_infos)}")
    return voice_infos

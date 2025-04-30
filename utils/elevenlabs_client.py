import requests
import os


def get_elevenlabs_voices():
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
    for v in voices:
        info = {
            "voice_id": v["voice_id"],
            "voice_name": v["name"],
            "voice_description": v.get("labels", {}).get("description", ""),
            "accent": v.get("labels", {}).get("accent", ""),
            "gender": v.get("labels", {}).get("gender", "")
        }
        voice_infos.append(info)

    return voice_infos

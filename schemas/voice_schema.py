from pydantic import BaseModel


class VoicePlan(BaseModel):
    voice_id: str
    voice_name: str
    voice_description: str
    narration_style: str  # рекомендации по интонации, скорости и т.п.

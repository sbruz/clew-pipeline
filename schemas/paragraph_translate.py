from pydantic import BaseModel


class HowToTranslateTask(BaseModel):
    correct_id: str
    incorrect1_id: str
    incorrect2_id: str

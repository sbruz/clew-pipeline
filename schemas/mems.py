from pydantic import BaseModel

class MemeIdea(BaseModel):
    paragraph_index: int  # начинается с 1
    meme_prompt: str
    hero_name: str
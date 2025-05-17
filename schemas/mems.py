from pydantic import BaseModel

class MemeIdea(BaseModel):
    paragraph_index: int  # начинается с 1
    picture_description: str
    picture_phrase: str
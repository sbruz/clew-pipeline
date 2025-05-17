from pydantic import BaseModel
from typing import List


class BookObject(BaseModel):
    paragraph_id: str
    object_description: str


class BookObjectsResponse(BaseModel):
    objects: List[BookObject]

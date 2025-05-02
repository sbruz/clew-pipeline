from pydantic import BaseModel
from typing import List


class WordGroup(BaseModel):
    label: str
    ids: List[str]  # должно быть ровно 5


class WordGroups(BaseModel):
    groups: List[WordGroup]

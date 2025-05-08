from pydantic import BaseModel
from typing import List


class ParagraphParts(BaseModel):
    parts: List[str]

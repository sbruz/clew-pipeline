from pydantic import BaseModel
from typing import List


class ChapterParagraph(BaseModel):
    paragraph_number: int
    paragraph_content: str


class ChapterItem(BaseModel):
    chapter_number: int
    paragraphs: List[ChapterParagraph]


class ChapterStructure(BaseModel):
    chapters: List[ChapterItem]

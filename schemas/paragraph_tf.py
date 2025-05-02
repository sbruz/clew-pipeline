from pydantic import BaseModel
from typing import List, Literal


class ParagraphTFItem(BaseModel):
    question: str
    answer: Literal["true", "false"]


class ParagraphTFList(BaseModel):
    questions: List[ParagraphTFItem]


class ParagraphTFQuestionOnly(BaseModel):
    question: str

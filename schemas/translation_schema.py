from pydantic import BaseModel
from typing import List, Optional


# --- Структура одного слова или словосочетания ---
class WordItem(BaseModel):
    o: str            # original
    o_t: str          # original translation
    l: Optional[str]  # lemma
    l_t: Optional[str]  # lemma translation


# --- Структура одного предложения для enrich ---
class Sentence(BaseModel):
    sentence_number: int
    sentence_original: str
    sentence_translation: str
    words: List[WordItem] = []


# --- Абзац, содержащий список предложений ---
class ChapterParagraphSentence(BaseModel):
    paragraph_number: int
    sentences: List[Sentence]


# --- Глава: номер + список абзацев с предложениями ---
class ChapterItemWithSentences(BaseModel):
    chapter_number: int
    paragraphs: List[ChapterParagraphSentence]


# --- Полная структура книги: главы → абзацы → предложения ---
class ChapterStructureWithSentences(BaseModel):
    chapters: List[ChapterItemWithSentences]


# --- Используется как ответ от OpenAI при разборе слов ---
class SentenceWordList(BaseModel):
    sentence_number: int
    words: List[WordItem]


class ParagraphWordAnalysis(BaseModel):
    sentences: List[SentenceWordList]


class SentenceOriginal(BaseModel):
    sentence_number: int
    sentence_original: str


class ChapterParagraphSentenceOriginal(BaseModel):
    paragraph_number: int
    sentences: List[SentenceOriginal]


# --- Структура одного предложения до enrich ---
class SentenceTranslated(BaseModel):
    sentence_number: int
    sentence_original: str
    sentence_translation: str


class ChapterParagraphSentenceTranslated(BaseModel):
    paragraph_number: int
    sentences: List[SentenceTranslated]


class ChapterItemWithTranslatedSentences(BaseModel):
    chapter_number: int
    paragraphs: List[ChapterParagraphSentenceTranslated]


class ChapterStructureTranslatedSentences(BaseModel):
    chapters: List[ChapterItemWithTranslatedSentences]

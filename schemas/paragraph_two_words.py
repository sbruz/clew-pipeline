from pydantic import BaseModel


class TwoWordsTask(BaseModel):
    id1: str        # ID первого слова
    id2: str        # ID второго слова
    invented: str   # новое слово (на target_lang)

from pydantic import BaseModel
from typing import List, Dict, Optional


class Names(BaseModel):
    """
    Структура для хранения имён персонажа:
    - main: основное имя, под которым чаще всего упоминается персонаж.
    - additional_names: список всех прозвищ, уменьшительно-ласкательных, других имён и способов обращения, встречающихся в тексте.

    Этот класс сериализуется целиком в поле name:text в базе.
    """
    main: str
    additional_names: List[str]


class Appearance(BaseModel):
    """
    Детализированное описание внешности персонажа:
    - basic: базовое, краткое впечатление или характеристика ("высокий и хитрый").
    - face: описание лица и его частей (форма, черты, мимика, особенности).
    - body: описание тела (телосложение, рост, вес, кожа, количество рук и т.д.).
    - hair: описание волос (цвет, длина, стиль, наличие/отсутствие).
    - clothes: описание одежды.

    В каждое поле заносится информация, если она появляется в тексте.
    """
    basic: Optional[str] = None
    face: Optional[str] = None
    body: Optional[str] = None
    hair: Optional[str] = None
    clothes: Optional[str] = None


class CharacterInParagraph(BaseModel):
    """
    Используется для хранения информации о персонаже, встреченном в конкретном абзаце.
    - id: числовой идентификатор персонажа (0 — если персонаж новый).
    - names: Names — актуальные имена персонажа на момент анализа абзаца.
    - appearance: Appearance — описание внешности, полученное из текущего абзаца.

    Эти данные возвращаются из OpenAI для каждого абзаца.
    """
    id: int
    names: Names
    appearance: Appearance


class CharactersInParagraph(BaseModel):
    """
    Используется для группировки всех персонажей, упомянутых в одном абзаце.
    - characters: список CharacterInParagraph — содержит объекты по каждому найденному персонажу.

    Эта структура возвращается из OpenAI при разборе каждого абзаца.
    """
    characters: List[CharacterInParagraph]


class AppearanceItem(BaseModel):
    paragraph: int
    appearance: Appearance


class CharacterAppearanceSummary(BaseModel):
    appearances: List[AppearanceItem]


class CharacterRoles(BaseModel):
    hero: Optional[int] = None
    ally: Optional[int] = None
    antagonist: Optional[int] = None
    trickster: Optional[int] = None
    victim: Optional[int] = None


class CharacterMention(BaseModel):
    id: int
    first_paragraph: int


class CharacterMentions(BaseModel):
    mentions: List[CharacterMention]


class ImageVerification(BaseModel):
    verification: int  # оценка 1-10
    comment: str       # короткий комментарий
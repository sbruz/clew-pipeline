from pydantic import BaseModel


class LocalizedMeta(BaseModel):
    localized_title: str
    localized_author: str

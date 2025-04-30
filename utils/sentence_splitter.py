import re


def split_into_sentences(text: str, lang: str) -> list[str]:
    if lang in {"zh", "ja", "ko"}:
        pattern = r'(?<=[。！？])'
    else:
        pattern = r'(?<=[.!?])\s+'

    return [s.strip() for s in re.split(pattern, text.strip()) if s.strip()]

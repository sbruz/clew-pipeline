import spacy
import subprocess


def split_old_into_sentences(text: str, lang: str, spacy_nlp) -> list[str]:
    if lang in {"zh", "ja", "ko"}:
        # Оставим старую регулярку для языков без пробелов
        import re
        pattern = r'(?<=[。！？])'
        return [s.strip() for s in re.split(pattern, text.strip()) if s.strip()]

    # Для остальных — SpaCy
    doc = spacy_nlp(text)
    return [sent.text.strip() for sent in doc.sents]

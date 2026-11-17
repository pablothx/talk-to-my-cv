"""Tiny Spanish/English detector, for replies written without the LLM (the refusal)."""

import re
from typing import Literal

Language = Literal["es", "en"]

SPANISH_MARKS = re.compile(r"[¿¡ñáéíóúü]", re.IGNORECASE)
# Short, frequent words that tell the two languages apart in a question.
_SPANISH = """
el la los las de del que qué en con por para es su sus un una y cuál cual cuánto
cuanto cómo como dónde donde tiene trabajó usó hizo sabe ella él
"""
_ENGLISH = """
the of and in with is are was did does do has have what which how where when who
her his she he a an to for on at much many
"""
SPANISH_WORDS = frozenset(_SPANISH.split())
ENGLISH_WORDS = frozenset(_ENGLISH.split())


def detect_language(text: str) -> Language | None:
    """`es`, `en`, or None when the evidence is too thin or tied."""
    words = re.findall(r"[a-záéíóúüñ]+", text.casefold())
    spanish = sum(w in SPANISH_WORDS for w in words) + 2 * len(SPANISH_MARKS.findall(text))
    english = sum(w in ENGLISH_WORDS for w in words)
    if spanish == english:
        return None
    return "es" if spanish > english else "en"

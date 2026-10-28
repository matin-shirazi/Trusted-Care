import re

_MAP = str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " ", "ة": "ه", "أ": "ا", "إ": "ا"})


def normalize(s: str) -> str:
    s = s.translate(_MAP)
    s = re.sub(r"[\u064B-\u0652]", "", s)  # diacritics
    s = re.sub(r"\s+", " ", s)
    return s.strip()

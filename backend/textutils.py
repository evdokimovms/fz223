import re

try:
    from nltk.stem.snowball import SnowballStemmer

    _stem = SnowballStemmer("russian").stem
except Exception: 
    def _stem(w: str) -> str:
        return w[:4] if len(w) > 4 else w


def normalize_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def cyr_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return 0.0
    cyr = sum(1 for c in letters if ("а" <= c.lower() <= "я") or c.lower() == "ё")
    return cyr / len(letters)


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[а-яёa-z0-9]+", text.lower())
    return [_stem(w) for w in words if len(w) > 2]


def windows(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    out, cur = [], ""
    for s in re.split(r"(?<=[.;])\s+", text):
        if cur and len(cur) + len(s) + 1 > max_chars:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    res = []
    for o in out:
        while len(o) > int(max_chars * 1.5):
            res.append(o[:max_chars])
            o = o[max_chars:]
        res.append(o)
    return res

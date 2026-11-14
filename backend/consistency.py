import logging
import os
import re

from judge import is_quote_valid
from llm_utils import ask_json
from textutils import norm

log = logging.getLogger("consistency")

WINDOW = int(os.getenv("CONSISTENCY_WINDOW_CHARS", "14000"))
OVERLAP_LINES = 12
MAX_ISSUES = 12

TYPES = {
    "contradiction": ("contradiction", "medium"),
    "title_mismatch": ("contradiction", "low"),
    "wrong_term": ("incorrect_term", "medium"),
    "bad_reference": ("reference", "low"),
    "spec_gap": ("completeness", "medium"),
}

PROMPT = (
    "Ты редактор технических заданий на закупку. Найди ВНУТРЕННИЕ несоответствия, "
    "которые видны только из самого текста:\n"
    "1. contradiction — один параметр/объект имеет разные значения в разных местах "
    "(тип, количество, размеры, мощность, сроки, коды, единицы).\n"
    "2. title_mismatch — название раздела/приложения не соответствует предмету закупки.\n"
    "3. wrong_term — условие применено к другому виду договора или объекту "
    "(например, для работ/услуг указано основание или документ, относящийся к купле-продаже товара).\n"
    "4. bad_reference — ссылки на стандарты/законы оформлены непоследовательно или с ошибкой "
    "(у однотипных документов одной серии разные обозначения).\n"
    "5. spec_gap — в предмете/составе работ есть поставка товара или работа, "
    "которой нет в спецификации (приложении) с кодом ОКПД 2.\n"
    "Правила: включай только то, что подтверждается ДОСЛОВНЫМИ цитатами из текста (до 200 символов, "
    "строка таблицы целиком); для contradiction нужны две цитаты с разными значениями. "
    "Не придумывай. «Или эквивалент», одинаковые значения и допустимые повторы — не ошибки. "
    "Сомневаешься — не включай.\n\n"
    "Текст (строки пронумерованы):\n<<TEXT>>\n\n"
    'JSON: {"issues":[{"type":"contradiction|title_mismatch|wrong_term|bad_reference|spec_gap",'
    '"lines":[номера строк],"quotes":["цитата A","цитата B"],'
    '"what":"в чём проблема, 1–2 предложения","fix":"что исправить"}]}'
)

VERIFY = (
    "Фрагменты технического задания:\n<<QUOTES>>\n\nЗамечание: <<WHAT>>\n"
    "Подтверждается ли замечание ТОЛЬКО этими фрагментами (без догадок)? "
    'JSON: {"confirmed":"yes|no|unclear"}'
)


def _windows(lines: list[str]) -> list[list[str]]:
    out, cur, size = [], [], 0
    for i, ln in enumerate(lines, 1):
        s = f"L{i}: {ln}"
        if cur and size + len(s) > WINDOW:
            out.append(cur)
            cur = cur[-OVERLAP_LINES:]
            size = sum(len(x) + 1 for x in cur)
        cur.append(s)
        size += len(s) + 1
    if cur:
        out.append(cur)
    return out


class ConsistencyChecker:
    def __init__(self, llm):
        self.llm = llm

    def _verify(self, issue: dict) -> str:
        data = ask_json(self.llm, VERIFY.replace("<<QUOTES>>", "\n".join(f"- {q}" for q in issue["quotes"]))
                        .replace("<<WHAT>>", issue["what"])) or {}
        v = str(data.get("confirmed", "")).lower()
        return v if v in ("yes", "no", "unclear") else "unclear"

    def check(self, text: str) -> list[dict]:
        if self.llm is None:
            return []
        lines = [ln for ln in text.split("\n") if ln.strip()]
        full_norm, seen, out = norm(text), set(), []
        for win in _windows(lines):
            data = ask_json(self.llm, PROMPT.replace("<<TEXT>>", "\n".join(win))) or {}
            for it in (data.get("issues") or [])[:MAX_ISSUES]:
                if not isinstance(it, dict) or it.get("type") not in TYPES:
                    continue
                quotes = [str(q).strip() for q in (it.get("quotes") or []) if str(q).strip()]
                quotes = [re.sub(r"^L\d+:\s*", "", q) for q in quotes]
                what = str(it.get("what") or "").strip()
                if not quotes or len(what) < 15 or not all(is_quote_valid(q, full_norm) for q in quotes):
                    continue  # цитаты обязаны быть в тексте
                if it["type"] == "contradiction" and len(quotes) < 2:
                    continue
                key = tuple(sorted(norm(q)[:80] for q in quotes))
                if key in seen:
                    continue
                seen.add(key)
                issue = {"type": it["type"], "quotes": quotes[:2], "what": what,
                         "fix": str(it.get("fix") or "").strip()}
                ok = self._verify(issue)
                if ok == "no":
                    continue
                out.append(self._finding(issue, "risk" if ok == "yes" else "check"))
        return out

    @staticmethod
    def _finding(issue: dict, verdict: str) -> dict:
        cat, sev = TYPES[issue["type"]]
        why = [issue["what"]]
        if len(issue["quotes"]) > 1:
            why.append(f"Второй фрагмент: «{issue['quotes'][1]}»")
        return {
            "status": "finding", "category": cat, "source": "consistency", "match": issue["what"][:80],
            "verdict": verdict, "severity": sev, "confidence": 0.8 if verdict == "risk" else 0.6,
            "rule_id": f"CONSIST:{issue['type']}", "quote": issue["quotes"][0][:400], "why": why,
            "mitigating": [], "extra_risk": [], "potential_violation": False, "llm_note": "",
            "recommendation": issue["fix"] or "Привести значения в документе к единому виду.",
            "law_basis": [], "history_refs": [], "signals": {},
            "quotes": issue["quotes"], 
            "_embed_text": " ".join(issue["quotes"]),
        }

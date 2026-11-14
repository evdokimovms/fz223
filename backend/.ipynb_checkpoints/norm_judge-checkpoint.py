
import logging
import re

from config import CFG
from llm_utils import ask_json, is_grounded
from roles import applicable

log = logging.getLogger("norm_judge")

VALID = {"violation", "risk", "ok"}

PROMPT = (
    "Ты эксперт по закупкам по 223-ФЗ. Определи, нарушает ли ФРАГМЕНТ ТЗ каждую из НОРМ.\n"
    "Контекст фрагмента: раздел «<<SECTION>>», роль фрагмента: <<ROLE>><<HEADER>>.\n\n"
    "Правила:\n"
    "1. Норма относится к фрагменту, только если регулирует то, о чём он по смыслу, "
    "а не просто содержит похожие слова. Иначе — ok.\n"
    "2. Если у нормы указано условие применимости, определи applies по тексту фрагмента: "
    "yes — условие явно выполнено, no — явно не выполнено, unknown — из фрагмента не видно.\n"
    "3. violation — только если фрагмент ПРЯМО противоречит норме; "
    "risk — реальная двусмысленность или возможное ограничение конкуренции; ok — не относится или не нарушает.\n"
    "4. reason — одно предложение со ссылкой на слова фрагмента; не добавляй фактов, которых в тексте нет.\n\n"
    "Фрагмент:\n<<FRAGMENT>>\n\nНормы:\n<<NORMS>>\n\n"
    'JSON: {"results":[{"id":"N1","applies":"yes|no|unknown","verdict":"violation|risk|ok","reason":"..."}]}'
)


def _cut(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= n:
        return s
    return s[:s.rfind(" ", 0, n)].rstrip(",;:") + "…"


class NormJudge:
    def __init__(self, evidence, llm):
        self.evidence, self.llm = evidence, llm
        self.llm_failed = 0  # сколько ответов LLM не удалось разобрать (audit.py выводит предупреждение)

    def _ask(self, clause, norms: dict, role: str):
        if not (CFG.use_llm_judge and self.llm is not None):
            return None
        block = "\n\n".join(
            f"[{k}] {m['norm']['ref']}: {m['norm']['requirement']}\n"
            f"Относится к: {', '.join(m['norm'].get('applies_to') or ['any'])}\n"
            f"Условие применимости: {(m['norm'].get('condition') or '').strip() or '—'}\n"
            f"Текст нормы: {m['norm']['text'][:600]}"
            for k, m in norms.items())
        header = f"; столбцы таблицы: {clause.table_header[:100]}" if getattr(clause, "table_header", "") else ""
        data = ask_json(self.llm, PROMPT
                        .replace("<<SECTION>>", getattr(clause, "section", "") or "не определён")
                        .replace("<<ROLE>>", role).replace("<<HEADER>>", header)
                        .replace("<<FRAGMENT>>", clause.text[:1200]).replace("<<NORMS>>", block))
        if not isinstance(data, dict):
            self.llm_failed += 1
            return None
        res = {}
        for r in data.get("results") or []:
            if isinstance(r, dict) and str(r.get("id")) in norms:
                v = str(r.get("verdict", "")).lower()
                if v in VALID:
                    a = str(r.get("applies", "")).lower()
                    res[str(r["id"])] = (v, str(r.get("reason") or "").strip(),
                                         a if a in ("yes", "no", "unknown") else "unknown")
        return res

    def judge_clause(self, clause, matches: list[dict], ctx, role: str = "other") -> list[dict]:
        cand = [m for m in matches if applicable(role, m["norm"].get("applies_to"))]
        norms = {f"N{i + 1}": m for i, m in enumerate(cand[: CFG.norm_top_per_clause])}
        if not norms:
            return []
        llm_res = self._ask(clause, norms, role)
        if llm_res is None: 
            return []
        quote = _cut(clause.text, 400)
        findings = []

        for k, m in norms.items():
            n = m["norm"]
            req = n.get("requirement") or ""
            ntext = n.get("text") or ""
            cond = (n.get("condition") or "").strip()
            v, reason, applies = llm_res.get(k, ("ok", "", "unknown"))
            if v == "ok" or applies == "no":
                continue

            final = v
            trusted = n.get("compiled_by") == "llm" or n.get("reviewed")
            if final == "violation" and (not trusted or n.get("strength", 0) < 0.6):
                final = "risk"
            needs_check = bool(cond) and applies != "yes"
            if needs_check:
                final = "check" 

            agree = 1.0 if v == final else 0.7
            match_part = min(1.0, max(0.0, (m["dense"] - CFG.norm_match_min_score) / 0.35))
            conf = round(n.get("strength", 0.6) * (0.55 + 0.25 * agree + 0.2 * match_part), 2)
            if conf < CFG.min_confidence: 
                continue

            note = reason if reason and is_grounded(reason, clause.text, req + " " + ntext) else ""
            why = [f"Норма: {req}"]
            rec = n.get("recommendation") or ""
            if needs_check:
                why.append(f"Применимость нормы по тексту ТЗ не подтверждена (условие: {cond}).")
                rec = f"Проверьте применимость нормы: {cond}. {rec}".strip()
            findings.append({
                "status": "finding", "source": "norm", "norm_id": n["norm_id"],
                "category": n["category"], "match": _cut(quote, 80), "verdict": final,
                "severity": n["severity"], "confidence": conf, "rule_id": f"NORM:{n['norm_id'][:8]}",
                "quote": quote, "why": why, "mitigating": [], "extra_risk": [],
                "potential_violation": False, "llm_note": note, "recommendation": rec,
                "role": role,
                "law_basis": [{
                    "id": n["norm_id"], "text": n["ref"], "source": n["doc_name"],
                    "source_type": n["source_type"], "excerpt": (n.get("source_quote") or ntext)[:350],
                }],
                "history_refs": [], "signals": {}, "_embed_text": quote,
            })

        if findings and self.evidence is not None:
            try:
                hist = self.evidence.search_history(clause.text[:300], ctx.tz_norm, ctx.job_id, limit=3)
            except Exception as e:
                log.warning("history search failed: %r", e)
                hist = []
            refs = [{"label": h.get("label"), "score": h["score"], "excerpt": h["text"][:240]} for h in hist]
            for f in findings:
                f["history_refs"] = refs
        return findings

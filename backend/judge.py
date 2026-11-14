import json
import logging
import re
from dataclasses import dataclass

from config import CFG
from llm_utils import ask_json, is_grounded  # noqa: F401
from textutils import norm

log = logging.getLogger("judge")


@dataclass
class DocContext:
    tz_norm: str
    job_id: str | None = None


JUDGE_PROMPT = (
    "Ты эксперт по 223-ФЗ. Проверь ОДИН фрагмент ТЗ.\n"
    "Категория: <<CATEGORY>>\nСигналы: <<SIGNALS>>\nФрагмент:\n<<FRAGMENT>>\n"
    "Нормы:\n<<LAW>>\nИстория:\n<<HISTORY>>\n"
    "violation только если очевидно; иначе risk; ok если законно. "
    "Не выдумывай факты вне фрагмента.\n"
    'JSON: {"verdict":"violation|risk|ok","law_ids":[],"reason":""}'
)


def is_quote_valid(quote: str, full_norm: str) -> bool:
    from rapidfuzz import fuzz

    q = norm(quote)
    if not q or len(q) < 15:
        return False
    if q in full_norm:
        return True
    try:
        aln = fuzz.partial_ratio_alignment(q, full_norm)
        if aln is None:
            return False
        return aln.score >= 90 and (aln.dest_end - aln.dest_start) >= len(q) * 0.7
    except Exception:
        return fuzz.partial_ratio(q, full_norm) >= 92


def pick_quote(frag: str, anchor: str, maxlen: int = 400) -> str:
    pos = frag.lower().find((anchor or "").lower()) if anchor else -1
    if pos < 0:
        pos = len(frag) // 2
    ls = frag.rfind("\n", 0, pos) + 1
    le = frag.find("\n", pos)
    le = len(frag) if le < 0 else le
    line = re.sub(r"\s+", " ", frag[ls:le]).strip()
    if len(line) < 40:
        line = re.sub(r"\s+", " ", frag[max(0, pos - 150): pos + 250]).strip()
    return line[:maxlen]


def format_law_refs(refs: list) -> list[dict]:
    out = []
    for r in refs or []:
        parts = [r.get("law") or "норма"]
        if r.get("article"):
            parts.append(f"статья {r['article']}")
        if r.get("part"):
            parts.append(f"часть {r['part']}")
        if r.get("point"):
            parts.append(f"пункт {r['point']}")
        out.append({"text": ", ".join(parts), "source": r.get("law", ""),
                    "ref": r, "excerpt": r.get("note") or ""})
    return out


def combine(rule: dict, llm_verdict):
    rv = rule["verdict"]
    if rule.get("potential_violation"):
        if llm_verdict == "violation" and rule["strength"] >= 0.85:
            return "violation"
        return "risk"
    if rv == "ok":
        return "ok"
    if rv == "violation":
        if rule["strength"] >= 0.9:
            return "violation"
        return "violation" if llm_verdict == "violation" else "risk"
    if llm_verdict == "ok" and rule["strength"] < 0.7:
        return "ok"
    return "risk"


def compute_confidence(rule, final, llm_v, law_rrf):
    if llm_v is None:
        agree = 0.55
    elif llm_v == final:
        agree = 1.0
    elif llm_v in ("risk", "violation") and final in ("risk", "violation"):
        agree = 0.6
    else:
        agree = 0.25
    law_part = min(1.0, law_rrf / (2.0 / (CFG.rrf_k + 1))) if law_rrf else 0.2
    return round(rule["strength"] * (0.6 + 0.25 * agree + 0.15 * law_part), 2)


class Judge:
    def __init__(self, engine, evidence, llm):
        self.engine, self.evidence, self.llm = engine, evidence, llm

    def judge(self, cand: dict, ctx: DocContext) -> dict:
        cat, signals = cand["category"], cand["signals"]
        base = {"category": cat, "match": cand["match"], "signals": signals}

        if signals.get("skip_rules"):
            return {"status": "ok", **base, "rule_id": None}
            
        if cat == "brand" and signals.get("standard_detected") and not signals.get("brands"):
            return {"status": "ok", **base, "rule_id": "ENTITY_STANDARD"}
        if cat == "brand" and signals.get("law_detected") and not signals.get("brands"):
            return {"status": "ok", **base, "rule_id": "ENTITY_LAW"}

        rule = self.engine.apply(signals)
        if rule["verdict"] == "ok" and rule.get("decisive"):
            return {"status": "ok", **base, "rule_id": rule.get("rule_id")}

        if (cat == "brand" and not signals.get("brands") and not signals.get("analogs_banned")
                and not signals.get("false_equivalent") and not signals.get("brand_detected")):
            return {"status": "ok", **base, "rule_id": rule.get("rule_id")}

        anchor = (signals.get("brands") or [None])[0] or cand["match"]
        quote = pick_quote(cand["fragment"], str(anchor))
        if not is_quote_valid(quote, ctx.tz_norm):
            return {"status": "dropped_quote", "quote": quote, **base}

        regs = self.evidence.retrieve_regulations(cat, cand["fragment"])
        need_hist = bool(
            signals.get("brands") or signals.get("analogs_banned") or signals.get("false_equivalent")
            or signals.get("exclusive_phrase") or signals.get("manufacturer_cert")
            or signals.get("territorial_experience") or cat in ("standards", "exclusive")
        )
        hist = (self.evidence.search_history(cand["match"] or cand["fragment"][:100],
                                             ctx.tz_norm, ctx.job_id, limit=4) if need_hist else [])
        ids_map = {f"L{i + 1}": it for i, it in enumerate(regs)}

        llm_v, llm_note, chosen = None, "", []
        if CFG.use_llm_judge and self.llm is not None:
            law_block = "\n\n".join(
                f"[{k}] {it['label']}\n{it['text'][:800]}" for k, it in ids_map.items()) or "(нет)"
            hist_block = "\n---\n".join(f"({h['score']}) {h['text']}" for h in hist) or "(нет)"
            sig_simple = {k: v for k, v in signals.items() if not isinstance(v, (list, dict))}
            prompt = (JUDGE_PROMPT
                      .replace("<<CATEGORY>>", cat)
                      .replace("<<SIGNALS>>", json.dumps(sig_simple, ensure_ascii=False))
                      .replace("<<FRAGMENT>>", cand["fragment"][:1200])
                      .replace("<<LAW>>", law_block)
                      .replace("<<HISTORY>>", hist_block))
            data = ask_json(self.llm, prompt) or {}
            v = str(data.get("verdict", "")).lower()
            llm_v = v if v in {"violation", "risk", "ok"} else None
            reason = str(data.get("reason") or "").strip()
            if reason and is_grounded(reason, cand["fragment"]):
                llm_note = reason
            chosen = [str(i) for i in (data.get("law_ids") or []) if str(i) in ids_map]

        verdict = combine(rule, llm_v)
        if verdict == "ok":
            return {"status": "ok", **base, "rule_id": rule.get("rule_id")}

        basis = []
        for lid in chosen:
            it = ids_map[lid]
            basis.append({"id": lid, "text": it["label"], "source": it["label"],
                          "source_type": it.get("source_type", "federal"),
                          "excerpt": it["text"][:350]})
        for ref in format_law_refs(rule.get("law_refs") or []):
            if ref["text"] not in {b["text"] for b in basis}:
                basis.append({**ref, "source_type": "federal", "id": "yaml"})
        if not any(b.get("excerpt") for b in basis) and regs:
            for it in regs[:2]:
                basis.append({"id": str(it["id"]), "text": it["label"], "source": it["label"],
                              "source_type": it.get("source_type"), "excerpt": it["text"][:350]})

        law_rrf = max([ids_map[i]["rrf"] for i in chosen],
                      default=(regs[0]["rrf"] * 0.5 if regs else 0.0))
        mitigating, extra = [], []
        if re.search(r"эквивалент|аналог", cand["fragment"], re.I):
            mitigating.append("В тексте есть формулировка про эквивалент/аналог.")
        if signals.get("false_equivalent"):
            extra.append("Эквивалент ограничен условиями, которые могут фактически исключать аналоги.")
        if signals.get("analogs_banned"):
            extra.append("Прямой запрет иных марок/аналогов.")

        return {
            "status": "finding", "category": cat, "match": cand["match"],
            "verdict": verdict, "severity": rule["severity"],
            "confidence": compute_confidence(rule, verdict, llm_v, law_rrf),
            "rule_id": rule.get("rule_id"), "quote": quote, "why": rule["why"],
            "mitigating": mitigating, "extra_risk": extra,
            "potential_violation": rule.get("potential_violation", False),
            "llm_note": llm_note, "recommendation": rule.get("recommendation") or "",
            "law_basis": basis,
            "history_refs": [{"label": h.get("label"), "score": h["score"], "excerpt": h["text"][:240]}
                             for h in hist[:3]],
            "signals": signals, "_embed_text": quote or cand["match"],
        }

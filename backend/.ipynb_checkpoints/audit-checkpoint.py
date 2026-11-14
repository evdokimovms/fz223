import time
import uuid
from collections import defaultdict
from typing import Callable, Optional

from clauses import split_clauses
from config import CFG
from evidence import Evidence
from consistency import ConsistencyChecker
from judge import DocContext, Judge
from layout import build_layout
from norm_judge import NormJudge
from okpd import OkpdChecker
from roles import classify_roles
from rule_engine import RuleEngine
from signals import find_candidates, missing_sections
from taxonomy import label
from textutils import norm, tokenize
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}
VERDICT_ORDER = {"violation": 0, "risk": 1, "check": 2}

Progress = Optional[Callable[[str, int], None]]


def compute_gate(rs: dict) -> tuple[str, str]:
    c = rs.get("counts") or {}
    n_viol, n_risk, n_check = c.get("violation", 0), c.get("risk", 0), c.get("check", 0)
    if n_viol > 0 or rs["level"] == "red":
        return "FAIL", (f"Обнаружено критических нарушений (violation): {n_viol}. "
                        "Публикация должна быть заблокирована до исправления.")
    if rs["level"] == "yellow" or n_risk > 0:
        return "REVIEW", (f"Критических нарушений нет. Рисков (risk): {n_risk}, "
                          f"проверок комплекта (check): {n_check}. "
                          "Рекомендуется human review перед публикацией.")
    return "PASS", ("Критических нарушений не обнаружено. "
                    + (f"Есть низкоприоритетные check: {n_check}." if n_check
                       else "Блокирующих рисков нет."))


class Auditor:
    def __init__(self, engine: RuleEngine, evidence: Evidence, encoder, llm, registry=None):
        self.engine, self.evidence, self.encoder, self.registry = engine, evidence, encoder, registry
        self.llm = llm
        self.consistency = ConsistencyChecker(llm) if CFG.use_consistency else None
        self.judge = Judge(engine, evidence, llm)
        self.norm_judge = NormJudge(evidence, llm) if registry is not None else None
        self.okpd = OkpdChecker(getattr(registry, "redis", None), getattr(CFG, "okpd_min_sim", 0.40))

    def semantic_merge(self, findings: list[dict]) -> list[dict]:
        if len(findings) <= 1:
            return findings
        texts = [f.get("_embed_text") or f.get("quote") or "" for f in findings]
        vecs = self.encoder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        used, merged = [False] * len(findings), []
        for i in range(len(findings)):
            if used[i]:
                continue
            group, used[i] = [findings[i]], True
            for j in range(i + 1, len(findings)):
                if used[j] or findings[i]["category"] != findings[j]["category"]:
                    continue
                if float(vecs[i] @ vecs[j]) >= CFG.semantic_dedup_threshold:
                    group.append(findings[j])
                    used[j] = True
            best = dict(max(group, key=lambda x: (
                VERDICT_ORDER.get(x["verdict"], 9), SEV_ORDER.get(x["severity"], 9), -x["confidence"])))
            if len(group) > 1:
                best["merged_count"] = len(group)
                whys = []
                for g in group:
                    for w in g.get("why") or []:
                        if w not in whys:
                            whys.append(w)
                best["why"] = whys
                bases = []
                for g in group:
                    for b in g.get("law_basis") or []:
                        if b.get("text") not in {x.get("text") for x in bases}:
                            bases.append(b)
                best["law_basis"] = bases
            merged.append(best)
        return merged

    @staticmethod
    def _history_stricter(current: str, past_texts: list[str]) -> str:
        marks = ["не допускается", "запрещ", "только", "исключительно",
                 "абсолютно идентич", "до миллиметр", "именн", "официальн"]
        cur = sum(1 for m in marks if m in current.lower())
        past = [sum(1 for m in marks if m in p.lower()) for p in past_texts]
        if not past:
            return "Недостаточно истории для сравнения строгости."
        avg = sum(past) / len(past)
        if cur >= avg + 1.5:
            return "Текущая формулировка выглядит строже типичных прошлых (больше запретов/ограничений)."
        if cur <= avg:
            return "По признакам строгости формулировка сопоставима с прошлыми закупками (не ужесточение)."
        return "Незначительное отличие от исторических формулировок; требуется экспертная оценка."

    def build_history_trend(self, findings: list[dict], ctx: DocContext) -> list[dict]:
        trends, seen = [], set()
        for f in findings:
            if f["verdict"] not in ("violation", "risk"):
                continue
            if f["severity"] == "low" and not f.get("potential_violation"):
                continue
            if f["category"] not in ("brand", "exclusive", "participants", "standards"):
                continue
            sig = f.get("signals") or {}
            if f["category"] == "brand" and not (
                    sig.get("brands") or sig.get("analogs_banned") or sig.get("false_equivalent")):
                continue
            q = (f.get("quote") or f.get("match") or "")[:100]
            if not q or q in seen:
                continue
            seen.add(q)
            hits = [h for h in self.evidence.search_history(q, ctx.tz_norm, ctx.job_id, limit=5)
                    if h["score"] >= CFG.history_compare_min_score]
            if not hits:
                continue
            trends.append({
                "category": f["category"],
                "current_quote": (f.get("quote") or "")[:240],
                "past": [{"score": h["score"], "label": h.get("label") or "ТЗ",
                          "excerpt": h["text"][:220]} for h in hits[:4]],
                "insight": self._history_stricter(f.get("quote") or "", [h["text"] for h in hits]),
            })
            if len(trends) >= 3:
                break
        return trends

    def audit(self, text: str, doc_name: str, job_id: str | None = None,
              progress: Progress = None) -> dict:
        def step(stage, pct):
            if progress:
                progress(stage, pct)

        t0 = time.time()
        ctx = DocContext(tz_norm=norm(text), job_id=job_id)
        layout = build_layout(text) 

        findings, dropped, ok_count, warnings = [], [], 0, []

        cands = []
        if CFG.use_yaml_rules:
            step("Поиск кандидатов (YAML-сигналы)", 20)
            cands = find_candidates(text)
            for i, c in enumerate(cands, 1):
                step(f"Judge: правило + RAG + LLM ({i}/{len(cands)})", 25 + int(25 * i / max(1, len(cands))))
                r = self.judge.judge(c, ctx)
                if r["status"] == "finding":
                    r.setdefault("source", "rule")
                    findings.append(r)
                elif r["status"] == "ok":
                    ok_count += 1
                else:
                    dropped.append({k: r.get(k) for k in ("status", "category", "match", "quote")})


        reg_version, norms_matched = None, 0
        if self.registry is not None:
            reg_version = self.registry.refresh()
            if not self.registry.stats()["active_norms"]:
                warnings.append("В реестре нет активных норм: загрузите закон/положение (POST /norms/upload).")
            step("Сопоставление пунктов ТЗ с нормами", 50)
            matches = self.registry.match(split_clauses(text, layout=layout))
            norms_matched = len(matches)
            by_clause = defaultdict(list)
            for m in matches:
                by_clause[m["clause"].idx].append(m)
            ordered = sorted(by_clause.values(), key=lambda ms: -max(m["score"] for m in ms))
            ordered = ordered[:CFG.max_llm_clauses]
            step("Определение роли пунктов", 55)
            roles = classify_roles(self.llm, [ms[0]["clause"] for ms in ordered])
            self.norm_judge.llm_failed = 0
            for j, ms in enumerate(ordered, 1):
                step(f"Judge по нормам ({j}/{len(ordered)})", 55 + int(20 * j / max(1, len(ordered))))
                clause = ms[0]["clause"]
                role = roles.get(clause.idx, "other")
                fs = self.norm_judge.judge_clause(clause, ms, ctx, role=role)
                for f in fs:
                    f["location"] = clause.loc 
                findings.extend(fs)
                if not fs:
                    ok_count += 1
            if self.norm_judge.llm_failed:
                warnings.append("LLM вернула некорректный ответ для части пунктов: проверка по нормам неполная.")

        step("Проверка кодов ОКПД 2", 78)
        findings.extend(self.okpd.check(text, self.encoder))

        if self.consistency is not None and CFG.use_llm_judge:
            step("Проверка согласованности документа", 79)
            findings.extend(self.consistency.check(text))

        for name in missing_sections(text):
            findings.append({
                "status": "finding", "category": "completeness", "match": name,
                "verdict": "check", "severity": "low", "confidence": 0.6,
                "rule_id": "COMPLETENESS", "quote": "",
                "why": [f"В тексте ТЗ не обнаружено: «{name}».",
                        "Возможно в извещении / документации о закупке / проекте договора."],
                "mitigating": [], "extra_risk": [], "potential_violation": False,
                "llm_note": "", "recommendation": "Проверьте полный комплект закупочной документации.",
                "law_basis": [], "history_refs": [], "signals": {}, "_embed_text": name,
            })

        step("Дедупликация и расчёт риска", 80)
        uniq, seen = [], set()
        for f in findings:
            key = (f["category"], " ".join(tokenize(f.get("match") or "")[:5]),
                   norm(f.get("quote") or "")[:100], f.get("norm_id"))
            if key not in seen:
                seen.add(key)
                uniq.append(f)
        uniq = self.semantic_merge(uniq)
        uniq.sort(key=lambda f: (VERDICT_ORDER.get(f["verdict"], 9),
                                 SEV_ORDER.get(f["severity"], 9), -f["confidence"]))
        shown = [f for f in uniq if f["confidence"] >= CFG.min_confidence]
        hidden = [f for f in uniq if f["confidence"] < CFG.min_confidence]

        risk = self.engine.score(shown)
        main = next((f for f in shown if f["verdict"] == "violation"
                     or (f["verdict"] == "risk" and f["severity"] == "high")),
                    shown[0] if shown else None)
        risk["main_risk"] = {
            "title": label(main["category"]),
            "quote": (main.get("quote") or "")[:200],
            "recommendation": main.get("recommendation"),
            "rule_id": main.get("rule_id"),
        } if main else None

        step("Сравнение с историей закупок", 90)
        trend = self.build_history_trend(shown, ctx)
        gate, gate_reason = compute_gate(risk)

        for f in shown + hidden:
            f.pop("_embed_text", None)
            quotes = f.get("quotes") or [f.get("quote") or f.get("match") or ""]
            if not f.get("location"):
                f["location"] = layout.locate(quotes[0])
            if len(quotes) > 1:
                f["locations"] = [layout.locate(q) for q in quotes]

        return {
            "run_id": str(uuid.uuid4()),
            "document": doc_name,
            "candidates_checked": len(cands),
            "ok_count": ok_count,
            "findings": shown,
            "hidden_low_confidence": hidden,
            "dropped": dropped,
            "history_trend": trend,
            "risk_summary": risk,
            "gate_decision": gate,
            "gate_reason": gate_reason,
            "elapsed_sec": round(time.time() - t0, 1),
            "sources_used": list(CFG.regulation_collections),
            "norm_sources": sorted({b.get("source") for f in shown for b in f.get("law_basis") or []
                                    if b.get("source") and f.get("source") == "norm"}),
            "registry_version": reg_version,
            "norms_matched": norms_matched,
            "warnings": warnings,
            "status": "pending_review",
        }

import logging
from pathlib import Path

import yaml

from config import CFG

log = logging.getLogger("rules")


class RuleEngine:
    def __init__(self, rules_dir):
        self.rules_dir = Path(rules_dir)
        self.rules: list = []
        self.weights: dict = {}
        self.reload()

    def reload(self):
        self.rules, self.weights = [], {}
        files = sorted(self.rules_dir.glob("*.yaml"))
        if not files:
            raise FileNotFoundError(f"Нет YAML-правил в {self.rules_dir}")
        for p in files:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if p.name == "risk_weights.yaml":
                self.weights = data
                continue
            for rule in data.get("rules") or []:
                rule["_file"] = p.name
                rule["_source"] = data.get("source", p.name)
                self.rules.append(rule)
        log.info("Rules loaded: %d from %s", len(self.rules), self.rules_dir)

    @staticmethod
    def _eval_trigger(trigger: dict, signals: dict) -> bool:
        if not trigger:
            return False

        def match_items(items, mode_all=True):
            if isinstance(items, dict):
                vals = [signals.get(k) == v for k, v in items.items()]
                return all(vals) if mode_all else any(vals)
            ok = [all(signals.get(k) == v for k, v in item.items())
                  for item in items if isinstance(item, dict)]
            return all(ok) if mode_all else any(ok)

        if "all" in trigger:
            return match_items(trigger["all"], True)
        if "any" in trigger:
            return match_items(trigger["any"], False)
        return all(signals.get(k) == v for k, v in trigger.items())

    def match(self, signals: dict) -> list:
        matched = [r for r in self.rules if self._eval_trigger(r.get("trigger") or {}, signals)]
        order_v = {"violation": 0, "risk": 1, "check": 2, "ok": 3}
        order_s = {"high": 0, "medium": 1, "low": 2}
        matched.sort(key=lambda r: (
            order_v.get(r.get("verdict", "risk"), 9),
            order_s.get(r.get("severity", "low"), 9),
            -float(r.get("strength", 0)),
        ))
        return matched

    def apply(self, signals: dict) -> dict:
        matched = self.match(signals)
        if not matched:
            return {
                "verdict": "risk", "strength": 0.5, "severity": "low",
                "why": ["Нет сработавшего YAML-правила — нужна ручная проверка."],
                "decisive": False, "rule_id": None, "signals": signals,
                "recommendation": "", "law_refs": [], "potential_violation": False,
            }
        for r in matched:
            if r.get("verdict") == "ok" and r.get("decisive"):
                return {
                    "verdict": "ok", "strength": float(r.get("strength", 0.8)),
                    "severity": r.get("severity", "low"), "why": [], "decisive": True,
                    "rule_id": r.get("id"), "recommendation": r.get("recommendation") or "",
                    "law_refs": r.get("law_refs") or [], "signals": signals,
                    "potential_violation": False,
                }
        for r in matched:
            if r.get("verdict") in ("violation", "risk", "check"):
                desc = r.get("description") or r.get("name") or r.get("id")
                return {
                    "verdict": r["verdict"], "strength": float(r.get("strength", 0.6)),
                    "severity": r.get("severity", "medium"), "why": [desc],
                    "decisive": bool(r.get("decisive")),
                    "potential_violation": bool(r.get("potential_violation")),
                    "rule_id": r.get("id"), "recommendation": r.get("recommendation") or "",
                    "law_refs": r.get("law_refs") or [], "signals": signals,
                }
        r = matched[0]
        return {
            "verdict": r.get("verdict", "ok"), "strength": float(r.get("strength", 0.8)),
            "severity": r.get("severity", "low"), "why": [], "decisive": bool(r.get("decisive")),
            "rule_id": r.get("id"), "recommendation": r.get("recommendation") or "",
            "law_refs": r.get("law_refs") or [], "signals": signals,
            "potential_violation": False,
        }

    def score(self, findings: list) -> dict:
        w = self.weights or {}
        vw = w.get("verdict_weight") or {"violation": 1.0, "risk": 0.65, "check": 0.25}
        sw = w.get("severity_weight") or {"high": 25, "medium": 12, "low": 5}
        bonus_map = w.get("signal_bonus") or {}
        thr = w.get("thresholds") or {"green_max": 29, "yellow_max": 69}
        min_c = float(w.get("min_confidence") or CFG.min_confidence)
        raw, counts = 0.0, {}
        for f in findings:
            if float(f.get("confidence") or 0) < min_c:
                continue
            v, s = f.get("verdict", "risk"), f.get("severity", "low")
            counts[v] = counts.get(v, 0) + 1
            counts[s] = counts.get(s, 0) + 1
            raw += sw.get(s, 5) * vw.get(v, 0.5) * (0.7 + 0.3 * float(f.get("confidence") or 0.5))
            sig = f.get("signals") or {}
            for k, b in bonus_map.items():
                if sig.get(k):
                    raw += b
        score = int(min(100, round(raw)))
        if score <= thr.get("green_max", 29):
            level, emoji = "green", "🟢"
        elif score <= thr.get("yellow_max", 69):
            level, emoji = "yellow", "🟠"
        else:
            level, emoji = "red", "🔴"
        return {"score": score, "level": level, "emoji": emoji, "counts": counts}

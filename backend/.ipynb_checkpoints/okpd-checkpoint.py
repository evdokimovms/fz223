
import logging
import re

from okpd_loader import KEY_NAMES, KEY_VERSION

log = logging.getLogger("okpd")

CODE_RX = re.compile(r"(?<![\d.])(\d{2}\.\d{1,2}(?:\.\d{1,2}(?:\.\d{3})?)?)(?!\.?\d)")
OKPD_RX = re.compile(r"ОКПД\s*-?\s*2?", re.I)
DATE_LIKE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
EMPTY_CELL = {"", "-", "—", "–", "н/д", "нет", "x", "х", "–", "—"}
FULL_LEN = 12


def _cosine(a, b) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


def _is_okpd_code(code: str) -> bool:
    if not code or DATE_LIKE.match(code):
        return False
    parts = code.split(".")
    if len(parts) < 2 or len(parts) > 4:
        return False
    if len(code) > 14:
        return False
    return True


class OkpdChecker:


    def __init__(self, redis_client=None, min_sim: float = 0.40):
        self.r, self.min_sim = redis_client, min_sim
        self.names: dict[str, str] = {}
        self.sections: set[str] = set()
        self._version = None

    def refresh(self):
        if self.r is None:
            return
        try:
            v = self.r.get(KEY_VERSION)
            if v == self._version:
                return
            self.names = self.r.hgetall(KEY_NAMES) if v else {}
            # Redis может вернуть bytes
            if self.names and isinstance(next(iter(self.names.keys()), None), bytes):
                self.names = {k.decode(): v.decode() for k, v in self.names.items()}
            self.sections = {c[:2] for c in self.names}
            self._version = v.decode() if isinstance(v, bytes) else v
            log.info("OKPD2: версия %s, кодов %d", self._version, len(self.names))
        except Exception as e:
            log.warning("OKPD2: redis недоступен (%r), используем то, что в памяти", e)

    @property
    def ready(self) -> bool:
        return bool(self.names)

    @staticmethod
    def _mentions(text: str):
        found, missing, seen = [], [], set()
        table_seen = False
        lines = text.split("\n")
        i = 0
        has_okpd_header = bool(OKPD_RX.search(text))

        while i < len(lines):
            line = lines[i]

            # --- путь 1: таблица с разделителем | (DOCX) ---
            if "|" in line and OKPD_RX.search(line):
                table_seen = True
                head = [c.strip() for c in line.split("|")]
                try:
                    idx = next(k for k, c in enumerate(head) if OKPD_RX.search(c))
                except StopIteration:
                    i += 1
                    continue
                j = i + 1
                while j < len(lines) and (not lines[j].strip() or "|" in lines[j]):
                    cells = [c.strip() for c in lines[j].split("|")]
                    if len(cells) >= len(head) - 1:  # допускаем небольшое расхождение
                        # выравниваем по min
                        n = min(len(cells), len(head))
                        cells = cells[:n]
                        ctx = " ".join(
                            c for k, c in enumerate(cells)
                            if k != idx and len(c) > 3 and not c.replace(",", "").replace(".", "").isdigit()
                        )
                        cell = cells[idx] if idx < len(cells) else ""
                        if cell.lower() in EMPTY_CELL:
                            if ctx:
                                missing.append(ctx)
                        else:
                            for code in CODE_RX.findall(cell):
                                if _is_okpd_code(code) and (code, ctx) not in seen:
                                    seen.add((code, ctx))
                                    found.append((code, ctx or cell))
                    j += 1
                i = j
                continue

        
            for m in OKPD_RX.finditer(line):
                for code in CODE_RX.findall(line[m.end(): m.end() + 100]):
                    if _is_okpd_code(code) and (code, line.strip()) not in seen:
                        seen.add((code, line.strip()))
                        found.append((code, line.strip()))

            i += 1

        
        if has_okpd_header and len(found) < 2:
            for idx, line in enumerate(lines):
                codes = [c for c in CODE_RX.findall(line) if _is_okpd_code(c)]
                if not codes:
                    continue
                # контекст: текущая + соседние строки без кодов
                ctx_parts = []
                for j in range(max(0, idx - 1), min(len(lines), idx + 2)):
                    if j == idx:
                        # убираем сам код из контекста
                        t = line
                        for c in codes:
                            t = t.replace(c, " ")
                        t = re.sub(r"\s+", " ", t).strip()
                        if len(t) > 3:
                            ctx_parts.append(t)
                    else:
                        if lines[j].strip() and not CODE_RX.search(lines[j]):
                            ctx_parts.append(lines[j].strip())
                ctx = " ".join(ctx_parts)[:300]
                for code in codes:
                    if (code, ctx) not in seen:
                        seen.add((code, ctx))
                        found.append((code, ctx or code))

  
        if has_okpd_header and not missing and not table_seen:
            for line in lines:
                if CODE_RX.search(line):
                    continue
                if OKPD_RX.search(line):
                    continue
                if re.search(r"^\s*\d+\s+", line) and len(line.strip()) > 15:
                    if found and not any(w in line.lower() for w in ("раздел", "итого", "всего", "№ п/п")):
                        missing.append(line.strip()[:200])

        return found, missing[:10]


    def _suggest(self, code: str) -> list[str]:
        p = code
        while len(p) > 2 and not any(c.startswith(p) for c in self.names):
            p = p[:-1]
        return [f"{c} {n}" for c, n in self.names.items() if c.startswith(p) and len(c) == FULL_LEN][:3]

    @staticmethod
    def _finding(match, quote, verdict, severity, conf, why, rec, rule):
        return {
            "status": "finding", "category": "okpd", "source": "okpd", "match": match,
            "verdict": verdict, "severity": severity, "confidence": conf, "rule_id": rule,
            "quote": quote[:240], "why": why, "mitigating": [], "extra_risk": [],
            "potential_violation": verdict == "violation", "llm_note": "",
            "recommendation": rec, "law_basis": [], "history_refs": [], "signals": {},
            "_embed_text": f"{match} {quote}",
        }

    def check(self, text: str, encoder=None) -> list[dict]:
        self.refresh()
        if not self.ready:
            log.warning("OKPD2: справочник пуст — проверка пропущена")
            return []
        found, missing = self._mentions(text)
        log.info("OKPD2: найдено кодов=%d, пустых=%d", len(found), len(missing))
        out, sem = [], []
        for code, ctx in found:
            name = self.names.get(code)
            if name is None:
                if code[:2] in self.sections:
                    hint = self._suggest(code)
                    out.append(self._finding(
                        code, ctx or code, "violation", "medium", 0.9,
                        [f"Код ОКПД 2 «{code}» отсутствует в справочнике."],
                        "Проверьте код по ОКПД 2 (ОК 034-2014)."
                        + (f" Ближайшие коды: {'; '.join(hint)}." if hint else ""),
                        "OKPD_UNKNOWN"))
                else:
                    out.append(self._finding(
                        code, ctx or code, "check", "low", 0.6,
                        [f"Код «{code}» не проверен: раздел {code[:2]} не загружен в справочник."],
                        "Загрузите полный справочник ОКПД 2 или проверьте код вручную.",
                        "OKPD_NOT_LOADED"))
                continue
            if len(code) < FULL_LEN:
                out.append(self._finding(
                    code, ctx or code, "check", "low", 0.65,
                    [f"Код «{code}» ({name}) указан укрупнённо — это группировка, а не конкретная позиция."],
                    "Уточните код до конечной позиции (xx.xx.xx.xxx).", "OKPD_COARSE"))
            if encoder is not None and ctx and len(ctx) > 10:
                sem.append((code, name, ctx))

        if sem:
            try:
                vecs = encoder.encode(
                    [n for _, n, _ in sem] + [c for _, _, c in sem],
                    normalize_embeddings=True, show_progress_bar=False,
                )
                k = len(sem)
                for (code, name, ctx), vn, vc in zip(sem, vecs[:k], vecs[k:]):
                    sim = _cosine(vn, vc)
                    if sim < self.min_sim:
                        out.append(self._finding(
                            code, ctx, "risk", "medium", 0.6,
                            [f"Код «{code}» — «{name}» — по смыслу плохо соответствует позиции (сходство {sim:.2f})."],
                            "Проверьте, что код ОКПД 2 соответствует предмету позиции.",
                            "OKPD_MISMATCH"))
            except Exception as e:
                log.warning("OKPD2 semantic check failed: %r", e)

        if missing:
            out.append(self._finding(
                "Код ОКПД 2", "; ".join(missing[:3]), "risk", "medium", 0.7,
                [f"В спецификации/таблице есть позиции без кода ОКПД 2: {len(missing)}."],
                "Заполните код ОКПД 2 для каждой позиции.", "OKPD_MISSING"))
        return out

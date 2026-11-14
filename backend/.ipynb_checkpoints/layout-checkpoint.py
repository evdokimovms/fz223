import bisect
import re
from dataclasses import dataclass

ROW_SEP = " | "
HEAD_WORD = re.compile(r"^(раздел|глава|статья|часть|приложение|section|chapter)\b", re.I)
HEAD_NUM = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}[.)]\s+\S")


@dataclass
class Line:
    no: int                       
    text: str
    section: str = ""
    page: int | None = None
    table_idx: int | None = None
    table_row: int | None = None  
    table_header: str = ""
    row_label: str = ""           


def is_heading(s: str) -> bool:
    s = (s or "").strip()
    if not s or len(s) > 120 or "|" in s:
        return False
    if HEAD_WORD.match(s) and "," not in s and len(s) <= 100:
        return True
    if HEAD_NUM.match(s) and "," not in s and ";" not in s and not s.endswith((":", ";")):
        return True
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 6 and len(s) <= 90 and sum(c.isupper() for c in letters) / len(letters) > 0.9


def _key(s: str) -> str:
    return re.sub(r"[\s|]+", " ", (s or "").lower()).strip()


def location_dict(first: Line, last: Line | None = None) -> dict:
    table = None
    if first.table_row is not None:
        table = {"index": first.table_idx, "row": first.table_row,
                 "label": first.row_label, "header": first.table_header}
    parts = []
    if first.section:
        parts.append(first.section[:90])
    if table:
        s = f"таблица {table['index']}, строка {table['row']}"
        if table["label"]:
            s += f" (№ {table['label']})"
        parts.append(s)
    else:
        parts.append(f"строка {first.no}")
    if first.page:
        parts.append(f"стр. {first.page}")
    return {"line": first.no,
            "end_line": last.no if last is not None and last.no != first.no else None,
            "section": first.section, "page": first.page, "table": table,
            "label": " · ".join(parts)}


class Layout:
    def __init__(self, lines: list[Line]):
        self.lines = lines
        self._hay: str | None = None
        self._starts: list[int] = []

    def __iter__(self):
        return iter(self.lines)

    def _index(self):
        if self._hay is None:
            parts, self._starts, pos = [], [], 0
            for ln in self.lines:
                k = _key(ln.text)
                self._starts.append(pos)
                parts.append(k)
                pos += len(k) + 1
            self._hay = " ".join(parts)
        return self._hay, self._starts

    def locate(self, quote: str) -> dict | None:
        
        q = _key(quote)
        if len(q) < 8 or not self.lines:
            return None
        hay, starts = self._index()
        full, p = False, -1
        for n in (len(q), 90, 60, 35):
            qq = q[:n]
            if len(qq) < 8:
                continue
            p = hay.find(qq)
            if p >= 0:
                full = n == len(q)
                break
        if p < 0:
            return None
        first = self.lines[bisect.bisect_right(starts, p) - 1]
        last = self.lines[bisect.bisect_right(starts, p + len(q) - 1) - 1] if full else None
        return location_dict(first, last)


def build_layout(text: str) -> Layout:
    raw = (text or "").split("\n")
    has_pages = "\f" in (text or "")
    lines, page = [], 1
    for no, r in enumerate(raw, 1):
        page += r.count("\f")
        lines.append(Line(no=no, text=r.replace("\f", "").strip(), page=page if has_pages else None))

    nonblank = [i for i, ln in enumerate(lines) if ln.text]
    is_row = {i: ROW_SEP in lines[i].text for i in nonblank}
    in_tbl = {}
    for k, i in enumerate(nonblank):
        if is_row[i]:
            in_tbl[i] = True
        else:  
            in_tbl[i] = (0 < k < len(nonblank) - 1 and is_row[nonblank[k - 1]]
                         and is_row[nonblank[k + 1]] and len(lines[i].text) < 60)

    section, tidx, trow, theader, prev_in = "", 0, 0, "", False
    for i in nonblank:
        ln = lines[i]
        if in_tbl[i]:
            if not prev_in:
                tidx, trow, theader = tidx + 1, 0, ""
            trow += 1
            if trow == 1:
                theader = ln.text[:140]
            ln.table_idx, ln.table_row, ln.table_header = tidx, trow, theader
            first = ln.text.split(ROW_SEP, 1)[0].strip()
            if ROW_SEP in ln.text and len(first) <= 6 and re.fullmatch(r"[\d.]+", first):
                ln.row_label = first
            prev_in = True
        else:
            prev_in = False
            if is_heading(ln.text):
                section = ln.text.strip()
        ln.section = section
    return Layout(lines)

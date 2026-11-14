from dataclasses import dataclass

from config import CFG
from layout import Layout, build_layout, location_dict
from textutils import norm, windows


@dataclass
class Clause:
    idx: int
    text: str
    line_no: int = 0
    end_line: int = 0
    section: str = ""
    table_header: str = ""     
    loc: dict | None = None    


def split_clauses(text: str, min_chars: int | None = None, max_chars: int | None = None,
                  layout: Layout | None = None) -> list[Clause]:
    min_chars = min_chars or CFG.clause_min_chars
    max_chars = max_chars or CFG.clause_max_chars
    layout = layout or build_layout(text)

    items = []  
    pend, pfirst = "", None
    for ln in layout.lines:
        line = ln.text
        if not line:
            continue
        if ln.table_row is not None:
            if len(pend) >= 15:
                items.append((pend, pfirst, pfirst))
            pend, pfirst = "", None
            if len(line) >= 15:
                for w in windows(line, max_chars):
                    items.append((w, ln, ln))
            continue
        if not pend:
            pfirst = ln
        buf = f"{pend} {line}".strip() if pend else line
        if len(buf) < min_chars:  
            pend = buf
            continue
        for w in windows(buf, max_chars):
            items.append((w, pfirst, ln))
        pend, pfirst = "", None
    if len(pend) >= 15:
        items.append((pend, pfirst, pfirst))

    clauses, seen = [], set()
    for t, first, last in items:
        k = norm(t)
        if k in seen:
            continue
        seen.add(k)
        clauses.append(Clause(
            idx=len(clauses), text=t, line_no=first.no, end_line=last.no, section=first.section,
            table_header=first.table_header if (first.table_row or 0) > 1 else "",
            loc=location_dict(first, last)))
    return clauses[:CFG.max_clauses]

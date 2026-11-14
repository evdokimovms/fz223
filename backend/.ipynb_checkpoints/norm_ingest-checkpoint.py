
import logging
import re
import sys
import uuid

from config import CFG
from llm_utils import ask_json
from registry import embed_text
from roles import ROLE_KEYS, ROLES_HELP
from taxonomy import CATEGORIES, classify, slug
from textutils import norm, windows

log = logging.getLogger("norm_ingest")

ART_RX = re.compile(r"(?m)^\s*Статья\s+(\d+(?:\.\d+)?)\.?\s*(.*)$")
PART_RX = re.compile(r"(?m)^\s*(\d{1,2}(?:\.\d+)?)\.\s+(?=\S)")
MODAL_RX = re.compile(
    r"не\s+вправе|не\s+допуска\w+|запрещ\w+|не\s+должн\w+|не\s+может|не\s+могут|"
    r"обязан\w*|должн\w+|вправе\s+установить|необходимо|подлежит", re.I)
PROHIB_RX = re.compile(r"не\s+вправе|не\s+допуска\w+|запрещ\w+|не\s+должн\w+|не\s+может|не\s+могут", re.I)
STRENGTH = {"high": 0.85, "medium": 0.75, "low": 0.6}

NORM_PROMPT = (
    "Ты юрист по закупкам (223-ФЗ). Из фрагмента нормативного акта выдели ПРОВЕРЯЕМЫЕ требования "
    "к документации о закупке и техническому заданию: что запрещено, что обязательно.\n"
    "Фрагмент (<<REF>>):\n<<TEXT>>\n"
    "Категории: <<CATS>> (можно предложить свою, латиницей).\n"
    "Роли для applies_to: <<ROLES_HELP>>.\n"
    'Верни JSON {"norms":[{"requirement":"краткая формулировка требования своими словами",'
    '"kind":"prohibition|obligation","category":"...","severity":"high|medium|low",'
    '"source_quote":"ДОСЛОВНАЯ цитата из фрагмента, от 25 символов",'
    '"violation_examples":["до 3 коротких примеров формулировок ТЗ, нарушающих норму"],'
    '"applies_to":["роли частей ТЗ/документации, к которым относится норма, или any"],'
    '"condition":"условие применимости нормы (тип закупки, порог НМЦ, вид заказчика и т.п.) или пустая строка",'
    '"recommendation":"как исправить"}]}\n'
    'Если проверяемых требований нет — {"norms":[]}. Не добавляй ничего, чего нет во фрагменте.'
)



def chunk_legal_text(text: str, max_chars: int | None = None) -> list[dict]:
    max_chars = max_chars or CFG.law_chunk_chars
    arts = list(ART_RX.finditer(text))
    spans = [] 
    if not arts:
        spans.append((None, "", text))
    else:
        if text[:arts[0].start()].strip():
            spans.append((None, "", text[:arts[0].start()]))
        for i, m in enumerate(arts):
            end = arts[i + 1].start() if i + 1 < len(arts) else len(text)
            spans.append((m.group(1), m.group(2).strip(), text[m.end():end]))

    chunks = []
    for art, head, body in spans:
        parts = list(PART_RX.finditer(body))
        pieces = []
        if not parts:
            pieces.append((None, body))
        else:
            if body[:parts[0].start()].strip():
                pieces.append((None, body[:parts[0].start()]))
            for j, p in enumerate(parts):
                end = parts[j + 1].start() if j + 1 < len(parts) else len(body)
                pieces.append((p.group(1), body[p.start():end]))
        for part, t in pieces:
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) < 30:
                continue
            for sub in windows(t, max_chars):
                chunks.append({"text": sub, "article": art, "part": part,
                               "heading": head, "idx": len(chunks)})
    return chunks


def ref_label(title: str, chunk: dict) -> str:
    parts = [title]
    if chunk.get("article"):
        parts.append(f"ст. {chunk['article']}")
    if chunk.get("part"):
        parts.append(f"ч. {chunk['part']}")
    return ", ".join(parts)


def heuristic_norms(chunk: dict) -> list[dict]:
    out = []
    for s in re.split(r"(?<=[.;])\s+", chunk["text"]):
        s = s.strip()
        if len(s) < 40 or not MODAL_RX.search(s):
            continue
        prohib = bool(PROHIB_RX.search(s))
        out.append({
            "requirement": s[:500], "kind": "prohibition" if prohib else "obligation",
            "category": classify(f"{chunk.get('heading', '')} {s}"),
            "severity": "medium" if prohib else "low", "source_quote": s[:300],
            "examples": [], "applies_to": ["any"], "condition": "",
            "recommendation": "Привести формулировку в соответствие с нормой.",
            "strength": 0.65 if prohib else 0.5,
        })
    return out


def llm_norms(llm, chunk: dict, ref: str) -> list[dict] | None:
    prompt = (NORM_PROMPT.replace("<<REF>>", ref).replace("<<TEXT>>", chunk["text"][:3000])
              .replace("<<CATS>>", ", ".join(CATEGORIES)).replace("<<ROLES_HELP>>", ROLES_HELP))
    data = ask_json(llm, prompt)
    if not isinstance(data, dict):
        return None
    chunk_norm, out = norm(chunk["text"]), []
    for it in data.get("norms") or []:
        if not isinstance(it, dict):
            continue
        req = str(it.get("requirement") or "").strip()
        quote = str(it.get("source_quote") or "").strip()

        if len(req) < 15 or len(quote) < 25 or norm(quote) not in chunk_norm:
            continue
        kind = str(it.get("kind") or "").lower()
        if kind not in ("prohibition", "obligation"):
            kind = "prohibition" if PROHIB_RX.search(req) else "obligation"
        cat = slug(str(it.get("category") or ""))
        if cat not in CATEGORIES and len(cat) < 3:
            cat = classify(req)
        sev = str(it.get("severity") or "").lower()
        sev = sev if sev in STRENGTH else "medium"
        ex = [str(e).strip()[:300] for e in (it.get("violation_examples") or []) if str(e).strip()][:3]
        at = [str(x).strip().lower() for x in (it.get("applies_to") or []) if str(x).strip()]
        at = [x for x in at if x in ROLE_KEYS or x == "any"] or ["any"]
        out.append({"requirement": req[:500], "kind": kind, "category": cat, "severity": sev,
                    "source_quote": quote[:400], "examples": ex, "strength": STRENGTH[sev],
                    "applies_to": at, "condition": str(it.get("condition") or "").strip()[:300],
                    "recommendation": str(it.get("recommendation") or "").strip()[:500]})
    return out


def compile_chunk(llm, chunk: dict, ref: str) -> tuple[list[dict], str]:
    if llm is not None:
        res = llm_norms(llm, chunk, ref)
        if res is not None:
            return res, "llm"
    return heuristic_norms(chunk), "heuristic"


def build_norm_payload(doc: dict, chunk: dict, n: dict, compiled_by: str, status: str) -> dict:
    ref = ref_label(doc["title"], chunk)
    norm_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc['doc_id']}:{chunk['idx']}:{norm(n['requirement'])[:120]}"))
    return {
        "norm_id": norm_id, "doc_id": doc["doc_id"], "doc_key": doc.get("doc_key"),
        "doc_name": doc["title"], "source_type": doc["source_type"],
        "article": chunk.get("article"), "part": chunk.get("part"), "ref": ref,
        "requirement": n["requirement"], "kind": n["kind"], "category": n["category"],
        "severity": n["severity"], "strength": n["strength"],
        "recommendation": n.get("recommendation") or "", "examples": n.get("examples", []),
        "applies_to": n.get("applies_to") or ["any"], "condition": n.get("condition") or "",
        "source_quote": n.get("source_quote", ""), "text": chunk["text"][:1500],
        "compiled_by": compiled_by, "reviewed": False, "status": status,
        "effective_from": doc.get("effective_from"), "effective_to": doc.get("effective_to"),
    }



class NormIngestor:
    def __init__(self, registry, llm):
        self.registry, self.llm, self.store = registry, llm, registry.store

    def ingest(self, doc: dict, text: str, progress=None) -> dict:
        """doc: doc_id, title, source_type (federal|internal), [doc_key, effective_from, effective_to]."""
        step = progress or (lambda *_: None)
        chunks = chunk_legal_text(text)
        if not chunks:
            raise ValueError("Не удалось выделить фрагменты нормативного акта")
        chunk_coll = CFG.law_collection if doc["source_type"] == "federal" else CFG.internal_collection
        status = "active" if CFG.norm_auto_activate else "draft"
        enc = self.registry.encoder()

        step("Индексация фрагментов акта", 20)
        self.store.ensure(chunk_coll, ("doc_id",))
        vecs = enc.encode([c["text"] for c in chunks], normalize_embeddings=True,
                          show_progress_bar=False, batch_size=16)
        self.store.upsert(chunk_coll, [
            (str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc['doc_id']}:chunk:{c['idx']}")), v.tolist(), {
                "text": c["text"], "doc_id": doc["doc_id"], "doc_key": doc.get("doc_key"),
                "doc_name": doc["title"], "law": doc["title"], "article": c["article"],
                "part": c["part"], "source_type": doc["source_type"], "status": status,
            }) for c, v in zip(chunks, vecs)])

        norms, by_count = {}, {"llm": 0, "heuristic": 0}
        for i, c in enumerate(chunks, 1):
            step(f"Извлечение норм ({i}/{len(chunks)})", 20 + int(60 * i / len(chunks)))
            items, by = compile_chunk(self.llm, c, ref_label(doc["title"], c))
            for n in items:
                p = build_norm_payload(doc, c, n, by, status)
                if p["norm_id"] not in norms:
                    norms[p["norm_id"]] = p
                    by_count[by] += 1

        step("Запись норм в реестр", 85)
        self.store.ensure(CFG.norm_collection, ("status", "doc_id", "doc_key", "category"))
        if norms:
            plist = list(norms.values())
            nvecs = enc.encode([embed_text(p) for p in plist], normalize_embeddings=True,
                               show_progress_bar=False, batch_size=16)
            self.store.upsert(CFG.norm_collection, [(p["norm_id"], v.tolist(), p) for p, v in zip(plist, nvecs)])

        superseded = self._supersede(doc)
        version = self.registry.bump()
        step("Реестр обновлён", 100)
        return {"doc_id": doc["doc_id"], "chunks": len(chunks), "norms": len(norms),
                "compiled_by": by_count, "status": status, "superseded": superseded,
                "registry_version": version}

    def _supersede(self, doc: dict) -> list[str]:
        key = doc.get("doc_key")
        if not key:
            return []
        old_ids = set()
        for coll in (CFG.norm_collection, CFG.law_collection, CFG.internal_collection):
            if self.store.exists(coll):
                old_ids |= {pl.get("doc_id") for _, pl in self.store.scroll(coll, {"doc_key": key})}
        old_ids -= {doc["doc_id"], None}
        for oid in old_ids:
            for coll in (CFG.norm_collection, CFG.law_collection, CFG.internal_collection):
                self.store.delete(coll, {"doc_id": oid})
        return sorted(old_ids)

    def reindex_existing(self, collection: str) -> dict:
        if not self.store.exists(collection):
            return {"collection": collection, "norms": 0}
        source_type = "internal" if collection == CFG.internal_collection else "federal"
        status = "active" if CFG.norm_auto_activate else "draft"
        enc, total = self.registry.encoder(), 0
        pts = [(pid, pl) for pid, pl in self.store.scroll(collection) if not pl.get("doc_id")]
        norms = {}
        for i, (pid, pl) in enumerate(pts):
            title = str(pl.get("doc_name") or pl.get("law") or pl.get("title") or "норма")
            doc = {"doc_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"legacy:{collection}:{title}")),
                   "doc_key": f"legacy:{title}", "title": title, "source_type": source_type}
            chunk = {"text": str(pl.get("text") or ""), "article": pl.get("article"),
                     "part": pl.get("part"), "heading": "", "idx": i}
            if len(chunk["text"]) < 40:
                continue
            items, by = compile_chunk(self.llm, chunk, ref_label(title, chunk))
            for n in items:
                p = build_norm_payload(doc, chunk, n, by, status)
                norms[p["norm_id"]] = p
        if norms:
            self.store.ensure(CFG.norm_collection, ("status", "doc_id", "doc_key", "category"))
            plist = list(norms.values())
            vecs = enc.encode([embed_text(p) for p in plist], normalize_embeddings=True,
                              show_progress_bar=False, batch_size=16)
            self.store.upsert(CFG.norm_collection, [(p["norm_id"], v.tolist(), p) for p, v in zip(plist, vecs)])
            self.registry.bump()
            total = len(plist)
        return {"collection": collection, "chunks": len(pts), "norms": total}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) >= 2 and sys.argv[1] == "reindex":
        from resources import get_llm, get_registry
        ing = NormIngestor(get_registry(), get_llm())
        for coll in sys.argv[2:] or [CFG.law_collection, CFG.internal_collection]:
            print(ing.reindex_existing(coll))
    else:
        print(__doc__)

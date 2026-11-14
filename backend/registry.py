
import logging
import math
from datetime import date

from config import CFG
from textutils import tokenize

log = logging.getLogger("registry")
VERSION_KEY = "norms:version"


class LexIndex:
    

    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs_tokens, k1, b
        self.n = len(docs_tokens)
        self.avgdl = (sum(len(d) for d in docs_tokens) / self.n) if self.n else 1.0
        self.df: dict[str, int] = {}
        for d in docs_tokens:
            for t in set(d):
                self.df[t] = self.df.get(t, 0) + 1

    def score(self, q_tokens: list[str], i: int) -> float:
        doc = self.docs[i]
        if not doc:
            return 0.0
        tf: dict[str, int] = {}
        for t in doc:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in set(q_tokens):
            f = tf.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
            s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(doc) / self.avgdl))
        return s


def active_on(payload: dict, today: str) -> bool:
    ef, et = payload.get("effective_from"), payload.get("effective_to")
    return (not ef or ef <= today) and (not et or today <= et)


def embed_text(n: dict) -> str:
    return "\n".join([n["requirement"], *n.get("examples", [])])


class NormRegistry:
    def __init__(self, store, get_encoder, redis_client=None):
        self.store, self._get_encoder, self.redis = store, get_encoder, redis_client
        self._local_version = 0
        self._loaded_version = None
        self._norms: dict[str, dict] = {}
        self._pos: dict[str, int] = {}
        self._lex: LexIndex | None = None

    def encoder(self):
        return self._get_encoder()

    def version(self) -> int:
        if self.redis is not None:
            try:
                return int(self.redis.get(VERSION_KEY) or 0)
            except Exception as e:
                log.warning("redis version read failed: %r", e)
        return self._local_version

    def bump(self) -> int:
        self._local_version += 1
        if self.redis is not None:
            try:
                return int(self.redis.incr(VERSION_KEY))
            except Exception as e:
                log.warning("redis version bump failed: %r", e)
        return self._local_version

    def refresh(self, force: bool = False) -> int:
        v = self.version()
        if not force and v == self._loaded_version:
            return v
        norms = {}
        if self.store.exists(CFG.norm_collection):
            for pid, pl in self.store.scroll(CFG.norm_collection, {"status": "active"}):
                norms[pid] = pl
        self._norms = norms
        ids = list(norms)
        self._pos = {pid: i for i, pid in enumerate(ids)}
        self._lex = LexIndex([tokenize(embed_text(norms[i])) for i in ids]) if ids else None
        self._loaded_version = v
        log.info("registry v%s: %d active norms", v, len(norms))
        return v

    def stats(self) -> dict:
        by_cat: dict[str, int] = {}
        for pl in self._norms.values():
            by_cat[pl.get("category", "general")] = by_cat.get(pl.get("category", "general"), 0) + 1
        return {"version": self._loaded_version, "active_norms": len(self._norms), "by_category": by_cat}

    def match(self, clauses: list, top_k: int | None = None, min_score: float | None = None,
              today: str | None = None) -> list[dict]:
        top_k = top_k or CFG.norm_top_per_clause
        min_score = CFG.norm_match_min_score if min_score is None else min_score
        today = today or date.today().isoformat()
        self.refresh()
        if not clauses or not self._norms or not self.store.exists(CFG.norm_collection):
            return []
        vecs = self.encoder().encode([c.text for c in clauses], normalize_embeddings=True,
                                     show_progress_bar=False, batch_size=16)
        out = []
        for c, v in zip(clauses, vecs):
            hits = self.store.search(CFG.norm_collection, v.tolist(), limit=top_k * 3,
                                     must={"status": "active"})
            qt = tokenize(c.text)
            scored = []
            for pid, dense, payload in hits:
                if dense < min_score or not active_on(payload, today):
                    continue
                lex, pos = 0.0, self._pos.get(pid)
                if pos is not None and self._lex:
                    raw = self._lex.score(qt, pos)
                    lex = raw / (raw + 4.0)
                scored.append({"clause": c, "norm": payload, "dense": dense, "lex": lex,
                               "score": dense + CFG.norm_lex_weight * lex})
            scored.sort(key=lambda s: s["score"], reverse=True)
            out.extend(scored[:top_k])
        return out

    def set_status(self, doc_id: str, status: str) -> int:
        if status not in ("active", "draft", "disabled"):
            raise ValueError(f"unknown status {status!r}")
        self.store.set_payload(CFG.norm_collection, {"status": status}, {"doc_id": doc_id})
        return self.bump()

    def delete_document(self, doc_id: str) -> int:
        for coll in (CFG.norm_collection, CFG.law_collection, CFG.internal_collection):
            self.store.delete(coll, {"doc_id": doc_id})
        return self.bump()

    def list_rules(self, doc_id: str) -> list[dict]:
        if not self.store.exists(CFG.norm_collection):
            return []
        keys = ("norm_id", "ref", "requirement", "kind", "category", "severity", "strength",
                "status", "compiled_by", "reviewed", "recommendation", "examples", "source_quote",
                "applies_to", "condition")
        return [{k: pl.get(k) for k in keys}
                for _, pl in self.store.scroll(CFG.norm_collection, {"doc_id": doc_id})]

"""Evidence RAG: dense (Qdrant) + BM25 по законам, RRF-слияние, поиск по истории ТЗ."""
import time
from collections import defaultdict

from config import CFG
from textutils import norm, tokenize

CATEGORY_LEGAL_QUERY = {
    "brand": "описание предмета закупки товарные знаки или эквивалент ограничение участников",
    "origin": "требования к стране происхождения товара ограничение участников",
    "standards": "документация о закупке стандарты ГОСТ ТУ ISO описание предмета",
    "exclusive": "необоснованное ограничение конкуренции равноправие",
    "participants": "требования к участникам закупки необоснованное ограничение конкуренции",
    "competition": "принципы закупки равноправие необоснованное ограничение конкуренции",
    "completeness": "документация о закупке характеристики предмета закупки",
}


def meta_label(payload: dict, limit: int = 160) -> str:
    for k in ("doc_name", "law", "title", "name", "filename", "file_name"):
        if payload.get(k):
            src = payload.get("source_type") or payload.get("doc_type") or ""
            prefix = "[внутр.] " if src in ("internal", "internal_regulation") else ""
            return (prefix + str(payload[k]))[:limit]
    return "норма"


class Evidence:
    def __init__(self, qdrant, encoder):
        self.qdrant = qdrant
        self.encoder = encoder
        self._bm25 = None
        self._law_ids: list = []
        self._law_docs: list[str] = []
        self._law_payload: dict = {}
        self._loaded_at = 0.0

    # ---------- BM25 по law_chunks (лениво, с TTL — база законов может пополняться) ----------
    def _ensure_bm25(self):
        if (time.time() - self._loaded_at) < CFG.bm25_ttl_sec:
            return
        self._loaded_at = time.time()
        from rank_bm25 import BM25Okapi

        if not self.qdrant.collection_exists(CFG.law_collection):
            self._bm25 = None
            return
        points, offset = [], None
        while True:
            batch, offset = self.qdrant.scroll(
                CFG.law_collection, limit=500, offset=offset, with_payload=True, with_vectors=False)
            points += batch
            if offset is None:
                break
        self._law_ids = [p.id for p in points]
        self._law_payload = {p.id: p.payload for p in points}
        self._law_docs = [(p.payload or {}).get("text", "") for p in points]
        self._bm25 = BM25Okapi([tokenize(t) for t in self._law_docs]) if self._law_docs else None

    def dense_search(self, query: str, collection: str, limit: int = 10) -> list[dict]:
        if not self.qdrant.collection_exists(collection):
            return []
        vec = self.encoder.encode(query, normalize_embeddings=True).tolist()
        res = self.qdrant.query_points(collection_name=collection, query=vec,
                                       limit=limit, with_payload=True)
        return [{"id": p.id, "text": (p.payload or {}).get("text", ""), "meta": p.payload or {},
                 "score": p.score, "collection": collection}
                for p in res.points if p.score >= CFG.dense_min_score]

    def bm25_search(self, query: str, limit: int = 10) -> list[dict]:
        self._ensure_bm25()
        if not self._bm25:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:limit]
        return [{"id": self._law_ids[i], "text": self._law_docs[i],
                 "meta": self._law_payload[self._law_ids[i]], "score": float(scores[i]),
                 "collection": CFG.law_collection} for i in order if scores[i] > 0]

    def hybrid_search_multi(self, query: str, k: int | None = None, pool: int | None = None):
        k, pool = k or CFG.retrieve_top, pool or CFG.retrieve_pool
        fused, items = defaultdict(float), {}
        for coll in CFG.regulation_collections:
            for rank, h in enumerate(self.dense_search(query, coll, pool)):
                key = f"{coll}:{h['id']}"
                fused[key] += 1.0 / (CFG.rrf_k + rank + 1) + (0.05 if coll == CFG.internal_collection else 0)
                items.setdefault(key, h)
        for rank, h in enumerate(self.bm25_search(query, pool)):
            key = f"{CFG.law_collection}:{h['id']}"
            fused[key] += 1.0 / (CFG.rrf_k + rank + 1)
            items.setdefault(key, h)
        out = []
        for key in sorted(fused, key=fused.get, reverse=True)[:k]:
            it = items[key]
            out.append({
                "id": it["id"], "text": it["text"], "label": meta_label(it["meta"]),
                "meta": it["meta"], "rrf": fused[key], "collection": it.get("collection", ""),
                "source_type": "internal" if it.get("collection") == CFG.internal_collection else "federal",
            })
        return out

    def retrieve_regulations(self, category: str, fragment: str) -> list[dict]:
        merged, seen = [], set()
        for q in [CATEGORY_LEGAL_QUERY.get(category, category), fragment[:350]]:
            for it in self.hybrid_search_multi(q, k=4):
                key = f"{it['collection']}:{it['id']}"
                if key not in seen:
                    seen.add(key)
                    merged.append(it)
        return merged[:CFG.retrieve_top]

    def search_history(self, query: str, tz_norm: str, job_id: str | None = None,
                       limit: int = 3) -> list[dict]:
        """Похожие формулировки из прошлых ТЗ (текущий документ исключается)."""
        if not self.qdrant.collection_exists(CFG.history_collection):
            return []
        result = []
        for h in self.dense_search(query, CFG.history_collection, limit * 5):
            if h["score"] < CFG.history_min_score:
                continue
            if job_id and str(h["meta"].get("job_id")) == str(job_id):
                continue
            if norm(h["text"])[:200] in tz_norm:
                continue
            result.append({"text": h["text"][:500], "score": round(h["score"], 3),
                           "label": meta_label(h["meta"]), "meta": h["meta"]})
            if len(result) >= limit:
                break
        return result

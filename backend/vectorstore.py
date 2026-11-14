import logging

log = logging.getLogger("vectorstore")


class QdrantStore:
    def __init__(self, client, size: int = 1024):
        self.c, self.size = client, size

    @staticmethod
    def _flt(must: dict | None):
        if not must:
            return None
        from qdrant_client import models
        return models.Filter(must=[
            models.FieldCondition(key=k, match=models.MatchValue(value=v)) for k, v in must.items()])

    def exists(self, name: str) -> bool:
        return self.c.collection_exists(name)

    def ensure(self, name: str, index_fields: tuple = ()):
        from qdrant_client import models
        if not self.c.collection_exists(name):
            self.c.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(size=self.size, distance=models.Distance.COSINE))
            log.info("created qdrant collection %s", name)
        for field in index_fields:
            try:
                self.c.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)
            except Exception as e: 
                log.debug("payload index %s.%s: %r", name, field, e)

    def upsert(self, name: str, items: list, batch: int = 128):
        from qdrant_client import models
        for i in range(0, len(items), batch):
            self.c.upsert(name, points=[
                models.PointStruct(id=pid, vector=vec, payload=pl) for pid, vec, pl in items[i:i + batch]])

    def search(self, name: str, vec: list, limit: int, must: dict | None = None) -> list:
        res = self.c.query_points(collection_name=name, query=vec, limit=limit,
                                  query_filter=self._flt(must), with_payload=True)
        return [(str(p.id), float(p.score), p.payload or {}) for p in res.points]

    def scroll(self, name: str, must: dict | None = None) -> list:
        out, offset = [], None
        while True:
            batch, offset = self.c.scroll(name, scroll_filter=self._flt(must), limit=500,
                                          offset=offset, with_payload=True, with_vectors=False)
            out += [(str(p.id), p.payload or {}) for p in batch]
            if offset is None:
                return out

    def delete(self, name: str, must: dict):
        from qdrant_client import models
        if self.c.collection_exists(name):
            self.c.delete(name, points_selector=models.FilterSelector(filter=self._flt(must)))

    def set_payload(self, name: str, payload: dict, must: dict):
        from qdrant_client import models
        if self.c.collection_exists(name):
            self.c.set_payload(name, payload=payload,
                               points=models.FilterSelector(filter=self._flt(must)))

import logging
from functools import lru_cache

from qdrant_client import QdrantClient

from config import CFG

log = logging.getLogger("resources")


@lru_cache(maxsize=1)
def get_qdrant() -> QdrantClient:
    return QdrantClient(url=CFG.qdrant_url)


@lru_cache(maxsize=1)
def get_encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(CFG.embed_model_name, device=CFG.embed_device)


@lru_cache(maxsize=1)
def get_llm():
    if not CFG.use_llm_judge:
        return None
    from langchain_ollama import ChatOllama

    base = dict(model=CFG.llm_model, temperature=CFG.llm_temperature, num_ctx=CFG.llm_num_ctx,
                num_predict=CFG.llm_num_predict, format="json", base_url=CFG.ollama_url)
    try:
        return ChatOllama(**base, reasoning=False)
    except Exception:
        return ChatOllama(**base)


@lru_cache(maxsize=1)
def get_store():
    from vectorstore import QdrantStore

    return QdrantStore(get_qdrant(), CFG.norm_vector_size)


@lru_cache(maxsize=1)
def get_redis():
    import redis

    return redis.Redis(host=CFG.redis_host, port=6379, decode_responses=True)


@lru_cache(maxsize=1)
def get_registry():
    from registry import NormRegistry

    return NormRegistry(get_store(), get_encoder, get_redis())


def ensure_collections():
    store = get_store()
    store.ensure(CFG.law_collection, ("doc_id", "doc_key"))
    store.ensure(CFG.internal_collection, ("doc_id", "doc_key"))
    store.ensure(CFG.history_collection)
    store.ensure(CFG.norm_collection, ("status", "doc_id", "doc_key", "category"))

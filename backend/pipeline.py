import logging
import uuid
from functools import lru_cache

from qdrant_client import models

import db
from audit import Auditor
from config import CFG
from document_loader import load_document_bytes
from evidence import Evidence
from norm_ingest import NormIngestor
from resources import ensure_collections, get_encoder, get_llm, get_qdrant, get_registry
from rule_engine import RuleEngine

log = logging.getLogger("pipeline")


@lru_cache(maxsize=1)
def get_auditor() -> Auditor:
    ensure_collections()
    encoder, qdrant = get_encoder(), get_qdrant()
    return Auditor(RuleEngine(CFG.rules_dir), Evidence(qdrant, encoder), encoder, get_llm(),
                   registry=get_registry())


def index_history(text: str, filename: str, job_id: str):
    size = CFG.history_chunk_chars
    chunks = [text[i:i + size] for i in range(0, len(text), size)][:CFG.history_max_chunks]
    chunks = [c for c in chunks if len(c.strip()) > 100]
    if not chunks:
        return
    enc = get_encoder()
    vecs = enc.encode(chunks, normalize_embeddings=True, show_progress_bar=False, batch_size=16)
    get_qdrant().upsert(CFG.history_collection, points=[
        models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{job_id}:{i}")), 
            vector=v.tolist(),
            payload={"text": c, "file_name": filename, "doc_name": filename,
                     "job_id": job_id, "chunk": i},
        ) for i, (c, v) in enumerate(zip(chunks, vecs))
    ])


def run_pipeline(job: dict, file_content: bytes, progress=None) -> dict:
    job_id, filename = job["job_id"], job["file"]
    if progress:
        progress("Извлечение текста", 15)
    text = load_document_bytes(file_content, filename)

    result = get_auditor().audit(text, doc_name=filename, job_id=job_id, progress=progress)

    if progress:
        progress("Сохранение результатов", 95)
    try:
        index_history(text, filename, job_id)  
    except Exception:
        log.exception("history indexing failed")
    try:
        db.save_result(job, len(file_content), result)
    except Exception:
        log.exception("postgres save failed")
    return result


def run_norm_ingest(job: dict, file_content: bytes, progress=None) -> dict:
    """Загрузка закона/положения: файл → нормы в реестре. Применяется сразу (версия реестра растёт)."""
    text = load_document_bytes(file_content, job["file"])
    doc = {"doc_id": job["doc_id"], "doc_key": job.get("doc_key"), "title": job["title"],
           "source_type": job.get("source_type", "federal"),
           "effective_from": job.get("effective_from"), "effective_to": job.get("effective_to")}
    summary = NormIngestor(get_registry(), get_llm()).ingest(doc, text, progress)
    try:
        db.finish_norm_document(job["doc_id"], summary)
    except Exception:
        log.exception("postgres norm_documents update failed")
    return summary

import logging
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

from config import CFG

log = logging.getLogger("db")


def connect():
    return psycopg2.connect(CFG.pg_dsn)


def save_result(job: dict, size: int, result: dict):
    rs = result["risk_summary"]
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO audit_jobs (job_id, file_name, file_size_bytes, s3_bucket, s3_key,
                       risk_score, risk_level, gate_decision, elapsed_sec, registry_version,
                       status, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DONE',CURRENT_TIMESTAMP)
                   ON CONFLICT (job_id) DO UPDATE SET
                       risk_score=EXCLUDED.risk_score, risk_level=EXCLUDED.risk_level,
                       gate_decision=EXCLUDED.gate_decision, elapsed_sec=EXCLUDED.elapsed_sec,
                       registry_version=EXCLUDED.registry_version,
                       status='DONE', updated_at=CURRENT_TIMESTAMP""",
                (job["job_id"], job["file"], size, job.get("bucket", CFG.s3_bucket),
                 job.get("s3_key", ""), rs["score"], rs["level"], result["gate_decision"],
                 result["elapsed_sec"], result.get("registry_version")),
            )
            cur.execute("DELETE FROM audit_findings WHERE job_id=%s", (job["job_id"],))  # идемпотентность
            for f in result["findings"]:
                cur.execute(
                    """INSERT INTO audit_findings (job_id, category, rule_id, verdict, severity,
                           confidence, quote, recommendation, why, law_basis, history_refs,
                           source, norm_id, location)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (job["job_id"], f["category"], f.get("rule_id"), f["verdict"], f["severity"],
                     f["confidence"], f.get("quote"), f.get("recommendation"),
                     Json(f.get("why")), Json(f.get("law_basis")), Json(f.get("history_refs")),
                     f.get("source"), f.get("norm_id"), Json(f.get("location"))),
                )
    finally:
        conn.close()


def mark_error(job_id: str):
    try:
        conn = connect()
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE audit_jobs SET status='ERROR', updated_at=CURRENT_TIMESTAMP WHERE job_id=%s",
                        (job_id,))
        conn.close()
    except Exception as e:
        log.warning("mark_error failed: %r", e)



def upsert_norm_document(doc: dict):
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO norm_documents (doc_id, doc_key, title, source_type, file_name, s3_bucket,
                       s3_key, status, effective_from, effective_to)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s,%s)
                   ON CONFLICT (doc_id) DO UPDATE SET status='QUEUED', updated_at=CURRENT_TIMESTAMP""",
                (doc["doc_id"], doc.get("doc_key"), doc["title"], doc["source_type"], doc.get("file"),
                 doc.get("bucket"), doc.get("s3_key"), doc.get("effective_from"), doc.get("effective_to")))
    finally:
        conn.close()


def finish_norm_document(doc_id: str, summary: dict):
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """UPDATE norm_documents SET status=%s, chunks_count=%s, norms_count=%s,
                       registry_version=%s, error=NULL, updated_at=CURRENT_TIMESTAMP WHERE doc_id=%s""",
                (summary["status"].upper(), summary["chunks"], summary["norms"],
                 summary["registry_version"], doc_id))
            if summary.get("superseded"):
                cur.execute("UPDATE norm_documents SET status='SUPERSEDED', updated_at=CURRENT_TIMESTAMP "
                            "WHERE doc_id = ANY(%s::uuid[])", (summary["superseded"],))
    finally:
        conn.close()


def set_norm_document_status(doc_id: str, status: str, error: str | None = None):
    try:
        conn = connect()
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE norm_documents SET status=%s, error=%s, updated_at=CURRENT_TIMESTAMP "
                        "WHERE doc_id=%s", (status.upper(), error, doc_id))
        conn.close()
    except Exception as e:
        log.warning("set_norm_document_status failed: %r", e)


def list_norm_documents() -> list[dict]:
    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute("""SELECT doc_id::text, doc_key, title, source_type, status, chunks_count, norms_count,
                                  registry_version, effective_from::text, effective_to::text, error,
                                  created_at::text, updated_at::text
                           FROM norm_documents ORDER BY created_at DESC""")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()

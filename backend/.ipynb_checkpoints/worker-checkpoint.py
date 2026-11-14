import json
import logging
import os
import traceback

import boto3
import redis
from kafka import KafkaConsumer

import db
from config import CFG
from okpd_loader import load_okpd
from pipeline import get_auditor, run_norm_ingest, run_pipeline

logging.basicConfig(level=logging.INFO)
redis_client = redis.Redis(host=CFG.redis_host, port=6379, decode_responses=True)
s3 = boto3.client("s3", endpoint_url=CFG.s3_endpoint,
                  aws_access_key_id=CFG.s3_key, aws_secret_access_key=CFG.s3_secret)

print(f"[OKPD] {load_okpd(redis_client, s3)}") 
get_auditor() 

TOPICS = [t.strip() for t in os.getenv("WORKER_TOPICS", "tz-check,norm-ingest").split(",") if t.strip()]

consumer = KafkaConsumer(
    *TOPICS,
    bootstrap_servers=[CFG.kafka_bootstrap],
    value_deserializer=lambda x: json.loads(x.decode()),
    group_id="tz-compliance-workers",
    auto_offset_reset="earliest",
    max_poll_interval_ms=30 * 60 * 1000,
    session_timeout_ms=60_000,
)

print(f"[INFRASTRUCTURE OK] Воркер запущен. Топики: {TOPICS}")


def handle_audit(job: dict):
    job_id = job["job_id"]
    key = f"job:{job_id}"
    print(f"[KAFKA INBOUND] Задача {job_id} взята в обработку.")

    def progress(stage: str, pct: int):
        redis_client.hset(key, mapping={"status": "RUNNING", "stage": stage, "progress": str(pct)})

    try:
        progress("Загрузка контента из S3 хранилища", 10)
        file_content = s3.get_object(Bucket=job["bucket"], Key=job["s3_key"])["Body"].read()

        result = run_pipeline(job, file_content, progress=progress)

        redis_client.hset(key, mapping={
            "status": "DONE", "stage": "Анализ завершен", "progress": "100",
            "gate": result["gate_decision"],
            "result": json.dumps(result, ensure_ascii=False, default=str),
        })
        print(f"[JOB COMPLETED] {job_id}: gate={result['gate_decision']}, "
              f"score={result['risk_summary']['score']}, registry=v{result.get('registry_version')}")
    except Exception as e:
        print(f"[WORKER ERROR] Ошибка при обработке задачи {job_id}")
        traceback.print_exc()
        redis_client.hset(key, mapping={"status": "ERROR", "stage": "Ошибка обработки",
                                        "error": str(e)})
        db.mark_error(job_id)


def handle_norm_ingest(job: dict):
    doc_id = job["doc_id"]
    key = f"normjob:{doc_id}"
    print(f"[NORM INGEST] Документ {doc_id} «{job.get('title')}» взят в обработку.")

    def progress(stage: str, pct: int):
        redis_client.hset(key, mapping={"status": "RUNNING", "stage": stage, "progress": str(pct)})

    try:
        progress("Загрузка акта из S3", 5)
        content = s3.get_object(Bucket=job["bucket"], Key=job["s3_key"])["Body"].read()
        summary = run_norm_ingest(job, content, progress=progress)
        redis_client.hset(key, mapping={
            "status": "DONE", "stage": "Нормы применены", "progress": "100",
            "summary": json.dumps(summary, ensure_ascii=False)})
        print(f"[NORM INGEST DONE] {doc_id}: norms={summary['norms']}, registry=v{summary['registry_version']}")
    except Exception as e:
        print(f"[NORM INGEST ERROR] {doc_id}")
        traceback.print_exc()
        redis_client.hset(key, mapping={"status": "ERROR", "stage": "Ошибка обработки", "error": str(e)})
        db.set_norm_document_status(doc_id, "ERROR", str(e))


for msg in consumer:
    if msg.topic == "norm-ingest":
        handle_norm_ingest(msg.value)
    else:
        handle_audit(msg.value)

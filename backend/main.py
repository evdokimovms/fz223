import uuid
import json
import boto3
import redis
import db
from config import CFG
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from kafka import KafkaProducer
from botocore.exceptions import ClientError

app = FastAPI(title="AI Проверка ТЗ 223-ФЗ — Phystech API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = redis.Redis(host=CFG.redis_host, port=6379, decode_responses=True)
producer = KafkaProducer(
    bootstrap_servers=[CFG.kafka_bootstrap],
    value_serializer=lambda x: json.dumps(x, ensure_ascii=False).encode("utf-8")
)
s3 = boto3.client("s3", endpoint_url=CFG.s3_endpoint, aws_access_key_id=CFG.s3_key, aws_secret_access_key=CFG.s3_secret)

BUCKET = CFG.s3_bucket

@app.on_event("startup")
def startup():
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=BUCKET)

    try:
        db.init_schema()
    except Exception as e:
        print(f"[INIT DB ERROR] {e}")

    try:
        from resources import ensure_collections
        ensure_collections()
    except Exception as e:
        print(f"[INIT QDRANT ERROR] {e}")


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    try:
        job_id = str(uuid.uuid4())
        content = await file.read()
        file_size = len(content)
        s3_key = f"history/{job_id}_{file.filename}"


        s3.put_object(Bucket=BUCKET, Key=s3_key, Body=content)

        redis_client.hset(
            f"job:{job_id}",
            mapping={
                "status": "QUEUED",
                "stage": "В очереди на обработку",
                "file": file.filename,
                "progress": "10"
            }
        )


        producer.send("tz-check", {
            "job_id": job_id,
            "file": file.filename,
            "size": file_size,
            "bucket": BUCKET,
            "s3_key": s3_key
        })
        producer.flush()

        return {"job_id": job_id, "status": "QUEUED"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return data


@app.get("/result/{job_id}")
def get_job_result(job_id: str):
    """Готовый отчёт (распарсенный JSON) + CI gate."""
    data = redis_client.hgetall(f"job:{job_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    if data.get("status") == "ERROR":
        raise HTTPException(status_code=422, detail=data.get("error", "Ошибка обработки"))
    if data.get("status") != "DONE":
        raise HTTPException(status_code=202, detail=data.get("stage", "В обработке"))
    return json.loads(data["result"])


@app.get("/health")
def health():
    return {"ok": True}



def _registry():
    from resources import get_registry
    return get_registry()


@app.post("/norms/upload")
async def upload_norm(file: UploadFile = File(...), title: str = Form(None), doc_key: str = Form(None),
                      source_type: str = Form("federal"), effective_from: str = Form(None),
                      effective_to: str = Form(None)):

    if source_type not in ("federal", "internal"):
        raise HTTPException(status_code=422, detail="source_type: federal | internal")
    try:
        doc_id = str(uuid.uuid4())
        content = await file.read()
        s3_key = f"norms/{doc_id}_{file.filename}"
        s3.put_object(Bucket=BUCKET, Key=s3_key, Body=content)
        job = {"doc_id": doc_id, "file": file.filename, "title": title or file.filename,
               "doc_key": doc_key, "source_type": source_type, "bucket": BUCKET, "s3_key": s3_key,
               "effective_from": effective_from or None, "effective_to": effective_to or None}
        db.upsert_norm_document(job)
        redis_client.hset(f"normjob:{doc_id}", mapping={
            "status": "QUEUED", "stage": "В очереди на обработку", "progress": "0", "title": job["title"]})
        producer.send("norm-ingest", job)
        producer.flush()
        return {"doc_id": doc_id, "status": "QUEUED"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/norms/jobs/{doc_id}")
def norm_job_status(doc_id: str):
    data = redis_client.hgetall(f"normjob:{doc_id}")
    if not data:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return data


@app.get("/norms")
def list_norms():
    return db.list_norm_documents()


@app.get("/norms/stats")
def norms_stats():
    reg = _registry()
    reg.refresh()
    return reg.stats()


@app.get("/norms/{doc_id}/rules")
def norm_rules(doc_id: str):
    return _registry().list_rules(doc_id)


class StatusBody(BaseModel):
    status: str  # active | draft | disabled


@app.post("/norms/{doc_id}/status")
def norm_set_status(doc_id: str, body: StatusBody):
    try:
        version = _registry().set_status(doc_id, body.status)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    db.set_norm_document_status(doc_id, "ACTIVE" if body.status == "active" else body.status)
    return {"doc_id": doc_id, "status": body.status, "registry_version": version}


@app.delete("/norms/{doc_id}")
def norm_delete(doc_id: str):
    version = _registry().delete_document(doc_id)
    db.set_norm_document_status(doc_id, "DELETED")
    return {"doc_id": doc_id, "registry_version": version}

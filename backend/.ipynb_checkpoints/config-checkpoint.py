import os
from dataclasses import dataclass
from pathlib import Path

_e = os.getenv


def _f(name, default):
    return float(_e(name, str(default)))


@dataclass
class Config:
    qdrant_url: str = _e("QDRANT_URL", "http://qdrant:6333")
    ollama_url: str = _e("OLLAMA_URL", "http://ollama:11434")
    pg_dsn: str = _e("PG_DSN", "host=postgres dbname=mlplatform user=admin password=password")
    redis_host: str = _e("REDIS_HOST", "redis")
    kafka_bootstrap: str = _e("KAFKA_BOOTSTRAP", "kafka:9092")
    s3_endpoint: str = _e("S3_ENDPOINT", "http://minio:9000")
    s3_key: str = _e("S3_ACCESS_KEY", "admin")
    s3_secret: str = _e("S3_SECRET_KEY", "adminpassword")
    s3_bucket: str = _e("S3_BUCKET", "tz-history")


    rules_dir: Path = Path(_e("RULES_DIR", str(Path(__file__).parent / "rules")))

    law_collection: str = "law_chunks"
    internal_collection: str = "internal_regs"
    history_collection: str = "tz_chunks"
    regulation_collections: tuple = ("internal_regs", "law_chunks")

    embed_model_name: str = _e("EMBED_MODEL", "BAAI/bge-m3")
    embed_device: str = _e("EMBED_DEVICE", "cpu")
    llm_model: str = _e("LLM_MODEL", "qwen3:8b")
    llm_temperature: float = 0.0
    llm_num_ctx: int = int(_e("LLM_NUM_CTX", "16384"))
    llm_num_predict: int = 1024
    use_llm_judge: bool = _e("USE_LLM_JUDGE", "1") == "1"

    dense_min_score: float = 0.38
    history_min_score: float = 0.50
    history_compare_min_score: float = 0.55
    rrf_k: int = 60
    retrieve_pool: int = 16
    retrieve_top: int = 6
    max_candidates_per_category: int = 8
    min_confidence: float = 0.55
    semantic_dedup_threshold: float = 0.85
    bm25_ttl_sec: int = 300

   
    norm_collection: str = "norm_rules"
    norm_vector_size: int = 1024
    norm_match_min_score: float = _f("NORM_MATCH_MIN_SCORE", 0.52)
    norm_top_per_clause: int = 3
    norm_lex_weight: float = 0.12
    norm_auto_activate: bool = _e("NORM_AUTO_ACTIVATE", "1") == "1"  
    use_yaml_rules: bool = _e("USE_YAML_RULES", "0") == "1"          # YAML-правила + regex-сигналы (по умолчанию выкл.)
    use_consistency: bool = _e("USE_CONSISTENCY", "1") == "1"        
    law_chunk_chars: int = 1200
    clause_min_chars: int = 40
    clause_max_chars: int = 700
    max_clauses: int = 400
    max_llm_clauses: int = int(_e("MAX_LLM_CLAUSES", "60"))

    history_chunk_chars: int = 1000
    history_max_chunks: int = 300

    okpd_min_sim: float = _f("OKPD_MIN_SIM", 0.40)


CFG = Config()

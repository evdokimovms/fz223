CREATE TABLE IF NOT EXISTS audit_jobs (
    job_id UUID PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    s3_bucket VARCHAR(64) NOT NULL,
    s3_key VARCHAR(512) NOT NULL,
    risk_score INT DEFAULT 0,
    risk_level VARCHAR(20) DEFAULT 'green',
    gate_decision VARCHAR(20) DEFAULT 'PASS',
    elapsed_sec REAL,
    status VARCHAR(50) DEFAULT 'QUEUED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_findings (
    id SERIAL PRIMARY KEY,
    job_id UUID REFERENCES audit_jobs(job_id) ON DELETE CASCADE,
    category VARCHAR(64) NOT NULL,
    rule_id VARCHAR(64),
    verdict VARCHAR(20) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    confidence REAL NOT NULL,
    quote TEXT,
    recommendation TEXT,
    why JSONB,
    law_basis JSONB,
    history_refs JSONB
);

CREATE INDEX IF NOT EXISTS idx_findings_job ON audit_findings(job_id);

ALTER TABLE audit_jobs ADD COLUMN IF NOT EXISTS registry_version BIGINT;
ALTER TABLE audit_findings ADD COLUMN IF NOT EXISTS source VARCHAR(16);
ALTER TABLE audit_findings ADD COLUMN IF NOT EXISTS norm_id VARCHAR(64);

CREATE TABLE IF NOT EXISTS norm_documents (
    doc_id UUID PRIMARY KEY,
    doc_key VARCHAR(255),
    title VARCHAR(512) NOT NULL,
    source_type VARCHAR(16) NOT NULL DEFAULT 'federal',
    file_name VARCHAR(255),
    s3_bucket VARCHAR(64),
    s3_key VARCHAR(512),
    status VARCHAR(20) DEFAULT 'QUEUED',
    chunks_count INT DEFAULT 0,
    norms_count INT DEFAULT 0,
    registry_version BIGINT,
    effective_from DATE,
    effective_to DATE,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_norm_docs_key ON norm_documents(doc_key);


ALTER TABLE audit_findings ADD COLUMN IF NOT EXISTS location JSONB;

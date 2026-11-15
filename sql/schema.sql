-- =============================================================================
-- Multi-Supplier Golden Product Catalog DDL Schema
-- Compatible with SQLite and DuckDB
-- =============================================================================

-- 1. Target Golden Product Catalog
CREATE TABLE IF NOT EXISTS golden_products (
    master_product_id    TEXT PRIMARY KEY,
    gtin                 TEXT,
    standard_title       TEXT NOT NULL,
    standard_category    TEXT NOT NULL,
    price_usd            TEXT NOT NULL,
    stock_quantity       INTEGER NOT NULL CHECK(stock_quantity >= 0),
    winning_supplier_id  TEXT NOT NULL,
    source_sku           TEXT NOT NULL,
    source_record_hash   TEXT NOT NULL,
    ingestion_run_id     TEXT NOT NULL,
    last_updated_at      TEXT NOT NULL,
    source_updated_at    TEXT NOT NULL,
    source_file          TEXT NOT NULL,
    source_batch_id      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_golden_gtin ON golden_products(gtin);
CREATE INDEX IF NOT EXISTS idx_golden_supplier ON golden_products(winning_supplier_id);
CREATE INDEX IF NOT EXISTS idx_golden_category ON golden_products(standard_category);

-- 2. Dead-Letter Quarantine Table
CREATE TABLE IF NOT EXISTS quarantine_products (
    rejection_id         TEXT PRIMARY KEY,
    supplier_id          TEXT NOT NULL,
    raw_record           TEXT NOT NULL,
    rejection_reason     TEXT NOT NULL,
    ingestion_run_id     TEXT NOT NULL,
    failed_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quarantine_run ON quarantine_products(ingestion_run_id);
CREATE INDEX IF NOT EXISTS idx_quarantine_reason ON quarantine_products(rejection_reason);

-- 3. Operational Audit & Run Log
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id               TEXT PRIMARY KEY,
    started_at           TEXT NOT NULL,
    completed_at         TEXT,
    status               TEXT NOT NULL CHECK(status IN ('SUCCESS', 'PARTIAL_SUCCESS', 'FAILED')),
    records_read_total   INTEGER NOT NULL,
    records_published    INTEGER NOT NULL,
    records_rejected     INTEGER NOT NULL,
    records_deduplicated INTEGER NOT NULL,
    records_unchanged    INTEGER NOT NULL,
    error_summary        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started ON pipeline_runs(started_at);

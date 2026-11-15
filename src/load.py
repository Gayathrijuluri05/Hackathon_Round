"""Target database loading: idempotent upserts, quarantine dead-letter, and audit logs."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from src.config import DEFAULT_SCHEMA_PATH


def initialize_database(conn: sqlite3.Connection, schema_path: Path | None = None) -> None:
    """Execute DDL script to create target tables and indexes."""
    path = schema_path or DEFAULT_SCHEMA_PATH
    conn.executescript(path.read_text(encoding='utf-8'))


def load_quarantine(conn: sqlite3.Connection, rejects: list[tuple]) -> None:
    """Batch-insert rejected records into quarantine_products."""
    if not rejects:
        return
    conn.executemany(
        '''INSERT INTO quarantine_products
           (rejection_id, supplier_id, raw_record, rejection_reason, ingestion_run_id, failed_at)
           VALUES (?, ?, ?, ?, ?, ?)''',
        rejects,
    )


def upsert_golden_products(
    conn: sqlite3.Connection,
    candidates: dict[str, dict],
    run_id: str,
    run_timestamp: str,
) -> tuple[int, int]:
    """Idempotently upsert winning candidate records into golden_products.
    
    Guards against older timestamps overwriting newer catalog entries.
    Identical records (matching timestamp and content hash) are skipped.
    
    Returns:
        (records_published, records_unchanged)
    """
    published = 0
    unchanged_or_stale = 0

    for row in candidates.values():
        old = conn.execute(
            'SELECT source_updated_at, source_record_hash FROM golden_products WHERE master_product_id = ?',
            (row['master_product_id'],),
        ).fetchone()

        if old:
            is_older = row['source_updated_at'] < old['source_updated_at']
            is_identical = (
                row['source_updated_at'] == old['source_updated_at']
                and row['source_record_hash'] == old['source_record_hash']
            )
            if is_older or is_identical:
                unchanged_or_stale += 1
                continue

        payload = {
            **row,
            'ingestion_run_id': run_id,
            'last_updated_at': run_timestamp,
        }

        conn.execute(
            '''INSERT INTO golden_products
               (master_product_id, gtin, standard_title, standard_category, price_usd, stock_quantity,
                winning_supplier_id, source_sku, source_record_hash, ingestion_run_id,
                last_updated_at, source_updated_at, source_file, source_batch_id)
               VALUES (:master_product_id, :gtin, :standard_title, :standard_category, :price_usd,
                       :stock_quantity, :winning_supplier_id, :source_sku, :source_record_hash, :ingestion_run_id,
                       :last_updated_at, :source_updated_at, :source_file, :source_batch_id)
               ON CONFLICT(master_product_id) DO UPDATE SET
               gtin = excluded.gtin,
               standard_title = excluded.standard_title,
               standard_category = excluded.standard_category,
               price_usd = excluded.price_usd,
               stock_quantity = excluded.stock_quantity,
               winning_supplier_id = excluded.winning_supplier_id,
               source_sku = excluded.source_sku,
               source_record_hash = excluded.source_record_hash,
               ingestion_run_id = excluded.ingestion_run_id,
               last_updated_at = excluded.last_updated_at,
               source_updated_at = excluded.source_updated_at,
               source_file = excluded.source_file,
               source_batch_id = excluded.source_batch_id''',
            payload,
        )
        published += 1

    return published, unchanged_or_stale


def record_pipeline_run(
    conn: sqlite3.Connection,
    run_id: str,
    started_at: str,
    completed_at: str,
    status: str,
    records_read_total: int,
    records_published: int,
    records_rejected: int,
    records_deduplicated: int,
    records_unchanged: int,
    error_summary: dict,
) -> None:
    """Record run metrics to the audit table pipeline_runs."""
    conn.execute(
        '''INSERT INTO pipeline_runs
           (run_id, started_at, completed_at, status, records_read_total, records_published,
            records_rejected, records_deduplicated, records_unchanged, error_summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            run_id,
            started_at,
            completed_at,
            status,
            records_read_total,
            records_published,
            records_rejected,
            records_deduplicated,
            records_unchanged,
            json.dumps(error_summary, sort_keys=True),
        ),
    )

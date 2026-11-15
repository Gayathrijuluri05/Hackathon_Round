"""Deterministic, locally runnable multi-supplier catalog pipeline orchestrator."""
from __future__ import annotations
import json
import logging
import sqlite3
import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import InvalidOperation
from pathlib import Path

from src.config import (
    ROOT,
    RATES,
    PRIORITY,
    SUPPLIER_FEEDS,
    DEFAULT_CATEGORIES_PATH,
)
from src.extract import iter_feed
from src.validate import gtin_valid
from src.transform import (
    canonical_hash,
    load_categories,
    normalize,
    winner_key,
)
from src.load import (
    initialize_database,
    load_quarantine,
    upsert_golden_products,
    record_pipeline_run,
)

LOG = logging.getLogger(__name__)


def now_utc() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def run_pipeline(
    input_dir: Path,
    db_path: Path,
    categories_path: Path | None = None,
) -> dict:
    """Execute end-to-end multi-supplier ingestion, validation, and catalog publishing.
    
    Args:
        input_dir: Directory containing supplier feed files.
        db_path: Path to target SQLite database file.
        categories_path: Optional path to category translation lookup CSV.
        
    Returns:
        dict: Execution summary containing run_id, counts, and reconciliation status.
    """
    input_dir, db_path = Path(input_dir), Path(db_path)
    categories = load_categories(categories_path or DEFAULT_CATEGORIES_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    run_id = str(uuid.uuid4())
    started_at = now_utc()
    read_count = 0
    rejects: list[tuple] = []
    dedup_count = 0
    candidates: dict[str, dict] = {}

    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        initialize_database(conn)

        try:
            # 1. Extraction, Validation & Conflict Resolution
            for supplier, filename in SUPPLIER_FEEDS:
                path = input_dir / filename
                if not path.exists():
                    raise FileNotFoundError(f'Missing input feed: {path}')

                for raw, parse_error in iter_feed(path, supplier):
                    read_count += 1
                    try:
                        if parse_error:
                            raise ValueError(parse_error)

                        row = normalize(supplier, raw, categories)
                        row['source_file'] = filename
                        row['source_batch_id'] = filename
                        key = row['master_product_id']

                        if key in candidates:
                            dedup_count += 1
                            if winner_key(row) < winner_key(candidates[key]):
                                candidates[key] = row
                        else:
                            candidates[key] = row

                    except (ValueError, TypeError, InvalidOperation) as exc:
                        rejects.append((
                            str(uuid.uuid4()),
                            supplier,
                            json.dumps(raw, default=str),
                            str(exc),
                            run_id,
                            now_utc(),
                        ))

            # 2. Persist Quarantined Records
            load_quarantine(conn, rejects)

            # 3. Idempotently Upsert Winning Golden Products
            published_count, unchanged_or_stale = upsert_golden_products(
                conn, candidates, run_id, now_utc()
            )

            # 4. Compile Audit Metrics & Reconcile
            breakdown = dict(Counter(x[3] for x in rejects))
            status = 'PARTIAL_SUCCESS' if rejects else 'SUCCESS'
            completed_at = now_utc()

            record_pipeline_run(
                conn=conn,
                run_id=run_id,
                started_at=started_at,
                completed_at=completed_at,
                status=status,
                records_read_total=read_count,
                records_published=published_count,
                records_rejected=len(rejects),
                records_deduplicated=dedup_count,
                records_unchanged=unchanged_or_stale,
                error_summary=breakdown,
            )

            conn.commit()

            catalog_total = conn.execute('SELECT COUNT(*) FROM golden_products').fetchone()[0]
            reconciled = (
                read_count == (published_count + len(rejects) + dedup_count + unchanged_or_stale)
            )

            result = {
                'run_id': run_id,
                'status': status,
                'records_read_total': read_count,
                'records_published': published_count,
                'records_rejected': len(rejects),
                'records_deduplicated': dedup_count,
                'records_unchanged': unchanged_or_stale,
                'catalog_rows': catalog_total,
                'reconciled': reconciled,
            }
            LOG.info('Pipeline finished: %s', json.dumps(result))
            return result

        except Exception as exc:
            conn.rollback()
            record_pipeline_run(
                conn=conn,
                run_id=run_id,
                started_at=started_at,
                completed_at=now_utc(),
                status='FAILED',
                records_read_total=read_count,
                records_published=0,
                records_rejected=0,
                records_deduplicated=0,
                records_unchanged=0,
                error_summary={'fatal_error': str(exc)},
            )
            conn.commit()
            LOG.exception('Pipeline failed: %s', exc)
            raise
    finally:
        conn.close()

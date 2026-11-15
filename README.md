# Multi-Supplier Golden Product Catalog | AI Data FDE Hackathon

A modular, tested, end-to-end Python + SQLite data engineering pipeline built for the multi-supplier catalog challenge. **No cloud services or API keys are needed.**

## Quick Start (Python 3.10+)

```bash
# 1. Install optional requirements (pipeline also runs with 0 external dependencies using stdlib)
python -m pip install -r requirements.txt

# 2. Run the pipeline on the sample supplier feeds (with automated reconciliation report)
python run_pipeline.py --input-dir data/sample --db output/catalog.db --report

# 3. Run the automated test suite (Zero-dependency, passes in 0.4s)
python tests/test_pipeline_unittest.py
# (Or using pytest if installed: python -m pytest -q)

# 4. Demonstrate Idempotency (re-run exact command: 0 republished, row count identical)
python run_pipeline.py --input-dir data/sample --db output/catalog.db --report

# 5. Run SQL analytics and reconciliation query
python -m src.reconcile --db output/catalog.db
```

To explore data using SQLite CLI (optional):
```bash
sqlite3 output/catalog.db < sql/analytics.sql
```

## Generate and Run 10,000–100,000 Records

```bash
# Benchmark with 10,000 records (~2.5 seconds)
python generate_data.py --count 10000 --out data/generated
python run_pipeline.py --input-dir data/generated --db output/generated.db --report

# Benchmark with 100,000 records
python generate_data.py --count 100000 --out data/generated_big
python run_pipeline.py --input-dir data/generated_big --db output/generated_big.db
```

`--count` specifies **total** records split across the three suppliers. Use `--seed` to reproduce synthetic data.

## Problem Solved

1. **Heterogeneous Formats**: Suppliers A, B, and C send incompatible schemas, key names, and formats (CSV, JSONL, TSV).
2. **Resilient Quarantine**: Dirty/malformed records (bad JSON, invalid barcodes, null prices) do not crash the pipeline; they are isolated in `quarantine_products` with explicit error codes.
3. **Canonical Normalization**: Standardizes categories via lookup dictionary, prices to USD via exact `Decimal` arithmetic, and stock availability to normalized integers.
4. **Deterministic Conflict Resolution**: When multiple suppliers offer the same product (matching GTIN), the winner is selected deterministically: Lowest Price USD $\rightarrow$ Stock $\rightarrow$ Supplier Hierarchy $\rightarrow$ Timestamp $\rightarrow$ Record Hash.
5. **Full Lineage & Traceability**: Every golden record tracks winning supplier, original SKU, raw payload hash, source file, batch ID, and pipeline run ID.
6. **Strict Idempotency**: Re-running the pipeline on identical inputs produces identical results without duplicating rows.
7. **Mathematical Reconciliation**: Every execution enforces:
   $$\text{Records Read} = \text{Published} + \text{Rejected} + \text{Deduplicated} + \text{Unchanged}$$

## Modular File Structure

```text
├── config/
│   └── lookup_categories.csv       # Category translation dictionary
├── src/
│   ├── __init__.py
│   ├── config.py                   # Exchange rates, supplier priorities, and feed definitions
│   ├── models.py                   # Pydantic data schemas for raw feeds, golden catalog, and audit
│   ├── extract.py                  # Streaming reader for CSV/TSV and JSONL with error trapping
│   ├── validate.py                 # GS1 GTIN check-digit validator, timestamp & price validation
│   ├── transform.py                # Canonical normalization and deterministic conflict arbiter
│   ├── load.py                     # Idempotent SQLite upserts, quarantine loading, and audit logging
│   ├── pipeline.py                 # End-to-end pipeline orchestrator
│   └── reconcile.py                # Terminal audit and reconciliation report generator
├── sql/
│   ├── schema.sql                  # DDL for golden_products, quarantine_products, pipeline_runs
│   └── analytics.sql               # 6 operational analytics and reconciliation queries
├── data/
│   └── sample/                     # Heterogeneous sample feeds with intentional dirty edge cases
├── tests/
│   ├── test_pipeline_unittest.py   # Comprehensive zero-dependency test suite (14 test cases)
│   └── test_pipeline.py            # Pytest test suite
├── docs/
│   ├── 3-TIER-ARCHITECTURE.md      # Detailed 3-tier architectural breakdown
│   ├── ARCHITECTURE.md             # Architecture design, Mermaid diagrams, and trade-offs
│   └── DATA_DICTIONARY.md          # Comprehensive table and field definitions
├── 3-TIER-ARCHITECTURE.md          # Dual 3-tier architectural specification
├── generate_data.py                # Scalable bulk synthetic data generator
├── run_pipeline.py                 # CLI runner script
└── requirements.txt                # Optional Python packages (pydantic, pytest)
```

## Demo Sequence for Judges

1. **Show Source Heterogeneity**: Inspect `data/sample/` to see Supplier A (`CSV`), Supplier B (`JSONL`), and Supplier C (`CSV`).
2. **Execute Ingestion**: Run `python run_pipeline.py --input-dir data/sample --db output/catalog.db --report`.
3. **Verify Conflict Resolution**: Show that *Laptop Pro* (GTIN `00036000291452`) was won by Supplier B ($850.00 USD) beating Supplier A ($899.00) and Supplier C ($875.00).
4. **Inspect Dead-Letter Quarantine**: Point to `quarantine_products` to review isolated records (`MALFORMED_JSON`, `MISSING_NAME`, `NULL_PRICE`, `INVALID_GTIN`).
5. **Prove Idempotency**: Run the exact command again. Show that `records_published = 0`, `records_unchanged = 5`, and total catalog rows remain at 5.
6. **Run Automated Tests**: Execute `python tests/test_pipeline_unittest.py` to show all 14 tests passing in $< 0.5$ seconds.
7. **Scale to 10k Records**: Run `generate_data.py` and benchmark 10,000 records processed in $\approx 2.5$ seconds.

## Scope & Production Roadmap

This is a working **local vertical slice** designed for 0–3 year FDE hackathons. For production enterprise deployments:
- **Historical Offer curves**: Implement an append-only `supplier_offers` bronze/silver table to retain historical price points per supplier.
- **Raw Object Archival**: Store original immutable feed files in AWS S3 or Google Cloud Storage with checksum manifests.
- **Vectorized Scaling**: For 100k+ to millions of rows, use DuckDB SQL staging or Polars for vectorized batch transformations.

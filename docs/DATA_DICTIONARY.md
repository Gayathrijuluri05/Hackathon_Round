# Data Dictionary

## `golden_products`
| Field | Meaning |
|---|---|
| master_product_id | Stable SHA-256 derived product identifier (32 hex characters) |
| gtin | Validated UPC/EAN/GTIN padded to 14 digits, nullable |
| standard_title | Whitespace-cleaned product name |
| standard_category | Mapped taxonomy or `Uncategorized` |
| price_usd | USD decimal money stored as TEXT for precise conversion |
| stock_quantity | Nonnegative integer; B and C represented as available 1/unavailable 0 |
| winning_supplier_id | A/B/C source that won the conflict rule |
| source_sku | Supplier's native SKU |
| source_record_hash | SHA-256 of canonical raw-record JSON |
| ingestion_run_id | Run that most recently inserted/updated the golden row |
| last_updated_at | UTC time of catalog write |
| source_updated_at | UTC time claimed by supplier source |
| source_file | Supplier feed filename |
| source_batch_id | Demonstration batch identifier, equal to filename |

## `quarantine_products`
| Field | Meaning |
|---|---|
| rejection_id | Unique rejected event UUID |
| supplier_id | Supplier identifier |
| raw_record | Original parsed record JSON or `_raw_line` on JSONL parse error |
| rejection_reason | Explicit validation or parsing error |
| ingestion_run_id | Run that encountered the invalid row |
| failed_at | UTC timestamp |

## `pipeline_runs`
| Field | Meaning |
|---|---|
| run_id | Unique execution UUID |
| started_at / completed_at | UTC execution timestamps |
| status | SUCCESS / PARTIAL_SUCCESS / FAILED |
| records_read_total | Nonblank records encountered across feeds |
| records_published | New/updated golden products in this run |
| records_rejected | Quarantined record events |
| records_deduplicated | Valid nonwinning offers/duplicates in current batch |
| records_unchanged | Accepted winners not written because unchanged or stale |
| error_summary | JSON reason-to-count mapping (or fatal error) |

-- =============================================================================
-- Operational Analytics & Data Quality Reconciliation Queries
-- =============================================================================

-- 1. Source-to-Target Reconciliation (Must balance to diff = 0 for every run)
SELECT run_id,
       status,
       records_read_total,
       records_published,
       records_rejected,
       records_deduplicated,
       records_unchanged,
       (records_read_total - records_published - records_rejected 
        - records_deduplicated - records_unchanged) AS diff_balance,
       CASE 
           WHEN (records_read_total - records_published - records_rejected 
                 - records_deduplicated - records_unchanged) = 0 THEN 'RECONCILED'
           ELSE 'DISCREPANCY'
       END AS reconciliation_verdict
FROM pipeline_runs
ORDER BY started_at DESC;

-- 2. Category Performance and Catalog Pricing Metrics
SELECT standard_category,
       COUNT(*) AS total_products,
       MIN(CAST(price_usd AS REAL)) AS min_price_usd,
       ROUND(AVG(CAST(price_usd AS REAL)), 2) AS avg_price_usd,
       MAX(CAST(price_usd AS REAL)) AS max_price_usd,
       SUM(stock_quantity) AS total_units_in_stock
FROM golden_products
GROUP BY standard_category
ORDER BY total_products DESC;

-- 3. Dead-Letter Quarantine Root Cause Breakdown
SELECT rejection_reason,
       COUNT(*) AS failure_count,
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM quarantine_products), 2) AS failure_percentage
FROM quarantine_products
GROUP BY rejection_reason
ORDER BY failure_count DESC;

-- 4. End-to-End Lineage & Provenance Verification
SELECT master_product_id,
       gtin,
       standard_title,
       winning_supplier_id,
       source_sku,
       source_file,
       source_record_hash,
       ingestion_run_id,
       source_updated_at,
       last_updated_at
FROM golden_products
ORDER BY master_product_id;

-- 5. Vendor Share of Published Catalog
SELECT winning_supplier_id,
       COUNT(*) AS winning_sku_count,
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM golden_products), 2) AS catalog_share_pct,
       ROUND(AVG(CAST(price_usd AS REAL)), 2) AS avg_offered_price
FROM golden_products
GROUP BY winning_supplier_id
ORDER BY winning_sku_count DESC;

-- 6. Inspect Sample Raw Quarantined Payloads
SELECT rejection_id,
       supplier_id,
       rejection_reason,
       raw_record,
       failed_at
FROM quarantine_products
ORDER BY failed_at DESC
LIMIT 5;

"""Source-to-target reconciliation and data quality auditing report generator."""
from __future__ import annotations
import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from src.config import DEFAULT_DB_PATH


def generate_reconciliation_report(db_path: Path) -> str:
    """Generate a formatted data reconciliation report from the target SQLite database."""
    if not db_path.exists():
        return f"Database file not found: {db_path}"

    lines: list[str] = []
    lines.append("=" * 80)
    lines.append(f"DATA RECONCILIATION & AUDIT REPORT: {db_path.name}")
    lines.append("=" * 80)

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        # 1. Pipeline Runs Reconciliation
        lines.append("\n[1] PIPELINE EXECUTION AUDIT & ROW RECONCILIATION")
        lines.append("-" * 80)
        runs = conn.execute(
            """SELECT run_id, status, started_at, completed_at,
                      records_read_total, records_published, records_rejected,
                      records_deduplicated, records_unchanged, error_summary,
                      records_read_total - records_published - records_rejected
                        - records_deduplicated - records_unchanged AS diff
               FROM pipeline_runs ORDER BY started_at DESC LIMIT 5"""
        ).fetchall()

        if not runs:
            lines.append("No pipeline runs recorded.")
        else:
            fmt_header = "{:<12} {:<15} {:<6} {:<9} {:<8} {:<8} {:<9} {:<6} {:<6}"
            lines.append(fmt_header.format(
                "Run Status", "Run ID[:8]", "Read", "Published", "Rejected", "Dedup", "Unchanged", "Diff", "Audit"
            ))
            lines.append("-" * 80)
            all_balanced = True
            for r in runs:
                diff = r["diff"]
                balanced = "PASS" if diff == 0 else "FAIL"
                if diff != 0:
                    all_balanced = False
                lines.append(fmt_header.format(
                    r["status"],
                    r["run_id"][:8] + "...",
                    r["records_read_total"],
                    r["records_published"],
                    r["records_rejected"],
                    r["records_deduplicated"],
                    r["records_unchanged"],
                    diff,
                    balanced,
                ))

            lines.append("-" * 80)
            if all_balanced:
                lines.append(">> BALANCE STATUS: PASS (Read = Published + Rejected + Dedup + Unchanged for all runs)")
            else:
                lines.append(">> BALANCE STATUS: FAIL (Discrepancy detected in row counts!)")

        # 2. Golden Catalog Summary
        lines.append("\n[2] GOLDEN PRODUCT CATALOG SUMMARY")
        lines.append("-" * 80)
        total_products = conn.execute("SELECT COUNT(*) FROM golden_products").fetchone()[0]
        lines.append(f"Total Unique Catalog Products: {total_products}")

        # Supplier distribution
        lines.append("\nWinning Supplier Contribution:")
        supplier_counts = conn.execute(
            """SELECT winning_supplier_id, COUNT(*) as cnt,
                      ROUND(AVG(CAST(price_usd AS REAL)), 2) as avg_price
               FROM golden_products GROUP BY winning_supplier_id ORDER BY cnt DESC"""
        ).fetchall()
        for sc in supplier_counts:
            lines.append(f"  - {sc['winning_supplier_id']:<15}: {sc['cnt']:>4} products (Avg Price: ${sc['avg_price']:.2f})")

        # Category distribution
        lines.append("\nCategory Distribution:")
        cat_counts = conn.execute(
            """SELECT standard_category, COUNT(*) as cnt,
                      ROUND(AVG(CAST(price_usd AS REAL)), 2) as avg_price
               FROM golden_products GROUP BY standard_category ORDER BY cnt DESC"""
        ).fetchall()
        for cc in cat_counts:
            lines.append(f"  - {cc['standard_category']:<26}: {cc['cnt']:>4} products (Avg Price: ${cc['avg_price']:.2f})")

        # 3. Quarantine Analysis
        lines.append("\n[3] DEAD-LETTER QUARANTINE ANALYSIS")
        lines.append("-" * 80)
        total_quarantined = conn.execute("SELECT COUNT(*) FROM quarantine_products").fetchone()[0]
        lines.append(f"Total Quarantined Rejections: {total_quarantined}")

        reasons = conn.execute(
            """SELECT rejection_reason, COUNT(*) as cnt
               FROM quarantine_products GROUP BY rejection_reason ORDER BY cnt DESC"""
        ).fetchall()
        for reason in reasons:
            lines.append(f"  - {reason['rejection_reason']:<25}: {reason['cnt']:>4} occurrences")

        # 4. Conflict Resolution Sample Demonstration
        lines.append("\n[4] CONFLICT RESOLUTION SAMPLE (Laptop Pro GTIN: 00036000291452)")
        lines.append("-" * 80)
        laptop = conn.execute(
            """SELECT master_product_id, gtin, standard_title, price_usd,
                      stock_quantity, winning_supplier_id, source_sku, source_file
               FROM golden_products WHERE gtin = '00036000291452'"""
        ).fetchone()
        if laptop:
            lines.append(f"  Title:            {laptop['standard_title']}")
            lines.append(f"  Master ID:        {laptop['master_product_id']}")
            lines.append(f"  Winning Supplier: {laptop['winning_supplier_id']} (Lowest price rule)")
            lines.append(f"  Published Price:  ${laptop['price_usd']} USD")
            lines.append(f"  Source SKU:       {laptop['source_sku']} from {laptop['source_file']}")
        else:
            lines.append("  Sample product not found in current catalog.")

        lines.append("=" * 80)

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate pipeline reconciliation report")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="Path to database")
    args = parser.parse_args()
    print(generate_reconciliation_report(args.db))

"""CLI: python run_pipeline.py --input-dir data/sample --db output/catalog.db [--report]"""
import argparse
import json
import logging
from pathlib import Path
from src.pipeline import run_pipeline
from src.reconcile import generate_reconciliation_report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Multi-Supplier Feed to Golden Catalog ETL Pipeline')
    parser.add_argument('--input-dir', type=Path, default=Path('data/sample'), help='Directory containing supplier feeds')
    parser.add_argument('--db', type=Path, default=Path('output/catalog.db'), help='Path to target SQLite catalog database')
    parser.add_argument('--categories', type=Path, default=None, help='Optional custom path to category mapping CSV')
    parser.add_argument('--report', action='store_true', help='Print detailed reconciliation and audit report after run')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    summary = run_pipeline(args.input_dir, args.db, args.categories)
    print(json.dumps(summary, indent=2))

    if args.report:
        print("\n" + generate_reconciliation_report(args.db))

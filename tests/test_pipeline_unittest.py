"""Comprehensive standard library unittest suite covering all modules."""
from __future__ import annotations
import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import RATES, PRIORITY
from src.models import (
    SupplierAFeedRow,
    SupplierBFeedRow,
    SupplierCFeedRow,
    NormalizedProduct,
    QuarantineRecord,
    PipelineRunSummary,
)
from src.validate import (
    gtin_valid,
    parse_timestamp,
    validate_numeric_price,
    validate_stock_quantity,
)
from src.extract import detect_delimiter, iter_feed
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
from src.pipeline import run_pipeline
from src.reconcile import generate_reconciliation_report
from generate_data import generate

CATEGORIES = load_categories(ROOT / 'config' / 'lookup_categories.csv')


class TestBarcodeValidation(unittest.TestCase):
    def test_barcode_check_digits(self):
        # Valid barcodes
        self.assertTrue(gtin_valid('036000291452'))  # UPC-12
        self.assertTrue(gtin_valid('042100005264'))  # UPC-12
        self.assertTrue(gtin_valid('9780201379624'))  # EAN-13
        self.assertTrue(gtin_valid('00036000291452'))  # GTIN-14
        self.assertTrue(gtin_valid('12345670'))  # GTIN-8
        
        # Invalid barcodes
        self.assertFalse(gtin_valid('036000291453'))  # Check digit wrong
        self.assertFalse(gtin_valid('abc'))
        self.assertFalse(gtin_valid(''))
        self.assertFalse(gtin_valid(None))
        self.assertFalse(gtin_valid('12345'))  # Invalid length


class TestPydanticModels(unittest.TestCase):
    def test_supplier_models(self):
        a = SupplierAFeedRow(
            supplier_sku='SKU-1',
            product_name='Widget',
            price='19.99',
            updated_at='2026-11-10T10:00:00Z',
        )
        self.assertEqual(a.supplier_sku, 'SKU-1')
        self.assertEqual(a.curr, 'USD')

        b = SupplierBFeedRow(
            item_id='B-1',
            title='Gadget',
            amount_cents=1999,
            feed_timestamp='2026-11-10T10:00:00Z',
        )
        self.assertEqual(b.amount_cents, 1999)
        self.assertFalse(b.in_stock)

        c = SupplierCFeedRow(
            vendor_ref='C-1',
            item_desc='Thing',
            wholesale_price='15.00',
            batch_date='2026-11-10T10:00:00Z',
        )
        self.assertEqual(c.availability_status, 'IN_STOCK')

    def test_normalized_product_model(self):
        prod = NormalizedProduct(
            master_product_id='a' * 32,
            gtin='00036000291452',
            standard_title='Clean Widget',
            standard_category='Electronics > Computers',
            price_usd='19.99',
            stock_quantity=10,
            winning_supplier_id='supplier_a',
            source_sku='SKU-1',
            source_record_hash='hash123',
            source_updated_at='2026-11-10T10:00:00+00:00',
            source_file='supplier_a_products.csv',
            source_batch_id='supplier_a_products.csv',
        )
        self.assertEqual(prod.price_usd, '19.99')
        self.assertEqual(prod.stock_quantity, 10)


class TestValidationAndNormalization(unittest.TestCase):
    def test_currency_and_category(self):
        row = {
            'vendor_ref': 'X',
            'barcode': '',
            'item_desc': '  USB   Hub ',
            'category_path': 'Nonexistent',
            'wholesale_price': '10',
            'currency': 'GBP',
            'availability_status': 'BACKORDER',
            'batch_date': '2026-01-01T00:00:00Z',
        }
        result = normalize('supplier_c', row, CATEGORIES)
        self.assertEqual(result['price_usd'], '12.70')  # 10 * 1.27
        self.assertEqual(result['standard_title'], 'USB Hub')
        self.assertEqual(result['standard_category'], 'Uncategorized')
        self.assertEqual(result['stock_quantity'], 0)
        self.assertEqual(len(result['master_product_id']), 32)

    def test_validation_errors(self):
        cases = [
            ('product_name', '', 'MISSING_NAME'),
            ('price', '', 'NULL_PRICE'),
            ('curr', 'CAD', 'UNSUPPORTED_CURRENCY'),
            ('upc_ean', '123456789013', 'INVALID_GTIN'),
            ('qty_on_hand', '-1', 'INVALID_STOCK'),
        ]
        for field, value, reason in cases:
            with self.subTest(field=field, value=value, reason=reason):
                rec = {
                    'supplier_sku': 'X',
                    'upc_ean': '036000291452',
                    'product_name': 'Laptop',
                    'category_code': 'CAT_402',
                    'price': '10',
                    'curr': 'USD',
                    'qty_on_hand': '1',
                    'updated_at': '2026-01-01T00:00:00Z',
                }
                rec[field] = value
                with self.assertRaises(ValueError) as ctx:
                    normalize('supplier_a', rec, CATEGORIES)
                self.assertIn(reason, str(ctx.exception))

    def test_timestamp_parsing(self):
        self.assertEqual(parse_timestamp('2026-11-10T10:00:00Z'), '2026-11-10T10:00:00+00:00')
        with self.assertRaises(ValueError):
            parse_timestamp('')
        with self.assertRaises(ValueError):
            parse_timestamp('not-a-timestamp')


class TestExtractAndDelimiters(unittest.TestCase):
    def test_detect_delimiter(self):
        self.assertEqual(detect_delimiter('col1,col2,col3'), ',')
        self.assertEqual(detect_delimiter('col1\tcol2\tcol3'), '\t')


class TestConflictResolution(unittest.TestCase):
    def test_winner_key_lowest_price(self):
        row_cheap = {
            'price_usd': '10.00',
            'stock_quantity': 5,
            'winning_supplier_id': 'supplier_c',
            'source_updated_at': '2026-01-01T00:00:00+00:00',
            'source_record_hash': 'h1',
        }
        row_expensive = {
            'price_usd': '12.00',
            'stock_quantity': 50,
            'winning_supplier_id': 'supplier_a',
            'source_updated_at': '2026-01-02T00:00:00+00:00',
            'source_record_hash': 'h2',
        }
        self.assertLess(winner_key(row_cheap), winner_key(row_expensive))

    def test_winner_key_tie_break_stock(self):
        row_more_stock = {
            'price_usd': '10.00',
            'stock_quantity': 20,
            'winning_supplier_id': 'supplier_c',
            'source_updated_at': '2026-01-01T00:00:00+00:00',
            'source_record_hash': 'h1',
        }
        row_less_stock = {
            'price_usd': '10.00',
            'stock_quantity': 5,
            'winning_supplier_id': 'supplier_a',
            'source_updated_at': '2026-01-01T00:00:00+00:00',
            'source_record_hash': 'h2',
        }
        self.assertLess(winner_key(row_more_stock), winner_key(row_less_stock))


class TestPipelineIntegration(unittest.TestCase):
    def test_end_to_end_and_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db = Path(tmp_dir) / 'catalog.db'
            a = run_pipeline(ROOT / 'data/sample', db)
            self.assertEqual(a['status'], 'PARTIAL_SUCCESS')
            self.assertEqual(a['records_read_total'], 13)
            self.assertEqual(a['records_rejected'], 4)
            self.assertEqual(a['records_deduplicated'], 4)
            self.assertEqual(a['records_published'], 5)
            self.assertTrue(a['reconciled'])

            with closing(sqlite3.connect(db)) as conn:
                laptop = conn.execute(
                    "SELECT price_usd, winning_supplier_id FROM golden_products WHERE gtin='00036000291452'"
                ).fetchone()
                self.assertEqual(laptop, ('850.00', 'supplier_b'))

                reasons = [r[0] for r in conn.execute('SELECT rejection_reason FROM quarantine_products')]
                self.assertIn('MALFORMED_JSON', reasons)
                self.assertIn('MISSING_NAME', reasons)
                self.assertIn('NULL_PRICE', reasons)
                self.assertIn('INVALID_GTIN', reasons)

            # Idempotent second run
            b = run_pipeline(ROOT / 'data/sample', db)
            self.assertEqual(b['catalog_rows'], a['catalog_rows'])
            self.assertEqual(b['records_published'], 0)
            self.assertEqual(b['records_unchanged'], 5)
            self.assertTrue(b['reconciled'])

            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0], 2)

            # Test reconciliation report generation
            report = generate_reconciliation_report(db)
            self.assertIn('BALANCE STATUS: PASS', report)
            self.assertIn('Laptop Pro', report)

    def test_empty_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            for name in ('supplier_a_products.csv', 'supplier_b_catalog.jsonl', 'supplier_c_feed.csv'):
                (tmp_path / name).write_text('')
            r = run_pipeline(tmp_path, tmp_path / 'db.sqlite')
            self.assertEqual(r['records_read_total'], 0)
            self.assertEqual(r['records_published'], 0)
            self.assertEqual(r['status'], 'SUCCESS')
            self.assertTrue(r['reconciled'])

    def test_late_arrival_and_schema_drift(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            generate(tmp_path, 3)
            db = tmp_path / 'db.sqlite'
            first = run_pipeline(tmp_path, db)
            self.assertEqual(first['records_published'], 3)

            # Modify file: add extra column and older timestamp
            path = tmp_path / 'supplier_a_products.csv'
            with path.open(newline='', encoding='utf-8') as f:
                rows = list(csv.DictReader(f))
            rows[0]['updated_at'] = '2020-01-01T00:00:00Z'
            rows[0]['price'] = '1'
            rows[0]['unexpected_extra'] = 'safe'
            with path.open('w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)

            second = run_pipeline(tmp_path, db)
            self.assertGreaterEqual(second['records_unchanged'], 1)
            self.assertEqual(second['catalog_rows'], 3)

    def test_missing_feed_logs_failure(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with self.assertRaises(FileNotFoundError):
                run_pipeline(tmp_path, tmp_path / 'db.sqlite')
            with closing(sqlite3.connect(tmp_path / 'db.sqlite')) as conn:
                self.assertEqual(conn.execute("SELECT status FROM pipeline_runs").fetchone()[0], 'FAILED')

    def test_bulk_generator(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            generate(tmp_path, 120)
            result = run_pipeline(tmp_path, tmp_path / 'db.sqlite')
            self.assertEqual(result['records_read_total'], 120)
            self.assertTrue(result['reconciled'])


if __name__ == '__main__':
    unittest.main()

import csv
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import pytest
from src.pipeline import ROOT, gtin_valid, normalize, load_categories, run_pipeline
from generate_data import generate

CATEGORIES = load_categories(ROOT / 'config/lookup_categories.csv')


def test_barcode_check_digit():
    assert gtin_valid('036000291452')
    assert gtin_valid('042100005264')
    assert not gtin_valid('036000291453')
    assert not gtin_valid('abc')


def test_currency_and_category():
    row = {'vendor_ref':'X','barcode':'','item_desc':'  USB   Hub ',
           'category_path':'Nonexistent', 'wholesale_price':'10', 'currency':'GBP',
           'availability_status':'BACKORDER','batch_date':'2026-01-01T00:00:00Z'}
    result = normalize('supplier_c', row, CATEGORIES)
    assert result['price_usd'] == '12.70'
    assert result['standard_title'] == 'USB Hub'
    assert result['standard_category'] == 'Uncategorized'
    assert result['stock_quantity'] == 0


@pytest.mark.parametrize('field,value,reason', [('product_name','','MISSING_NAME'),
    ('price','','NULL_PRICE'),('curr','CAD','UNSUPPORTED_CURRENCY'),
    ('upc_ean','123456789013','INVALID_GTIN'),('qty_on_hand','-1','INVALID_STOCK')])
def test_validation(field, value, reason):
    rec = {'supplier_sku':'X','upc_ean':'036000291452','product_name':'Laptop',
           'category_code':'CAT_402','price':'10','curr':'USD','qty_on_hand':'1',
           'updated_at':'2026-01-01T00:00:00Z'}
    rec[field] = value
    with pytest.raises(ValueError, match=reason):
        normalize('supplier_a', rec, CATEGORIES)


def test_end_to_end_and_idempotency(tmp_path):
    db = tmp_path / 'catalog.db'
    a = run_pipeline(ROOT / 'data/sample', db)
    assert a['status'] == 'PARTIAL_SUCCESS'
    assert a['records_read_total'] == 13
    assert a['records_rejected'] == 4
    assert a['records_deduplicated'] == 4
    assert a['records_published'] == 5
    assert a['reconciled']
    with closing(sqlite3.connect(db)) as conn:
        laptop = conn.execute("SELECT price_usd, winning_supplier_id FROM golden_products WHERE gtin='00036000291452'").fetchone()
        assert laptop == ('850.00', 'supplier_b')
        reasons = [r[0] for r in conn.execute('SELECT rejection_reason FROM quarantine_products')]
        assert 'MALFORMED_JSON' in reasons
        assert 'MISSING_NAME' in reasons
        assert 'NULL_PRICE' in reasons
        assert 'INVALID_GTIN' in reasons
    b = run_pipeline(ROOT / 'data/sample', db)
    assert b['catalog_rows'] == a['catalog_rows']
    assert b['records_published'] == 0
    assert b['reconciled']
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute('SELECT COUNT(*) FROM pipeline_runs').fetchone()[0] == 2


def test_empty_files(tmp_path):
    for name in ('supplier_a_products.csv','supplier_b_catalog.jsonl','supplier_c_feed.csv'):
        (tmp_path / name).write_text('')
    r = run_pipeline(tmp_path, tmp_path / 'db.sqlite')
    assert r['records_read_total'] == r['records_published'] == 0
    assert r['status'] == 'SUCCESS' and r['reconciled']


def test_late_arrival_and_schema_drift(tmp_path):
    generate(tmp_path, 3)
    db = tmp_path / 'db.sqlite'
    first = run_pipeline(tmp_path, db)
    assert first['records_published'] == 3
    path = tmp_path / 'supplier_a_products.csv'
    with path.open(newline='') as f:
        rows = list(csv.DictReader(f))
    rows[0]['updated_at'] = '2020-01-01T00:00:00Z'
    rows[0]['price'] = '1'
    rows[0]['unexpected_extra'] = 'safe'
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    second = run_pipeline(tmp_path, db)
    assert second['records_unchanged'] >= 1
    assert second['catalog_rows'] == 3


def test_missing_feed_logs_failure(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_pipeline(tmp_path, tmp_path / 'db.sqlite')
    with closing(sqlite3.connect(tmp_path / 'db.sqlite')) as conn:
        assert conn.execute("SELECT status FROM pipeline_runs").fetchone()[0] == 'FAILED'


def test_bulk_generator(tmp_path):
    generate(tmp_path, 120)
    result = run_pipeline(tmp_path, tmp_path / 'db.sqlite')
    assert result['records_read_total'] == 120
    assert result['reconciled']

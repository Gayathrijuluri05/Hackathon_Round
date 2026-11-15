"""Data transformation, standardization, and conflict resolution rules."""
from __future__ import annotations
import csv
import hashlib
import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from src.config import RATES, PRIORITY
from src.validate import (
    gtin_valid,
    parse_timestamp,
    validate_numeric_price,
    validate_stock_quantity,
)


def canonical_hash(record: dict) -> str:
    """Compute a deterministic SHA-256 hash of any arbitrary dictionary."""
    serialized = json.dumps(record, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


def load_categories(path: Path) -> dict[str, str]:
    """Load category translation lookup dictionary from CSV."""
    with path.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return {
            row['source_category'].strip().casefold(): row['standard_category'].strip()
            for row in reader
            if row.get('source_category') and row.get('standard_category')
        }


def normalize(supplier: str, record: dict, categories: dict[str, str]) -> dict:
    """Normalize supplier-specific raw records into a unified golden schema representation.
    
    Performs field extraction, data validation, currency conversion, taxonomy mapping,
    and stable ID generation. Raises ValueError with explicit codes on bad inputs.
    """
    if supplier == 'supplier_a':
        sku = record.get('supplier_sku')
        gtin = record.get('upc_ean')
        title = record.get('product_name')
        raw_price = record.get('price')
        currency = record.get('curr')
        category = record.get('category_code')
        raw_stock = record.get('qty_on_hand')
        raw_timestamp = record.get('updated_at')
    elif supplier == 'supplier_b':
        sku = record.get('item_id')
        gtin = record.get('gtin')
        title = record.get('title')
        cents = record.get('amount_cents')
        currency = record.get('currency_code')
        category = record.get('category')
        raw_price = (Decimal(str(cents)) / 100) if cents is not None and str(cents).strip() else None
        in_stock = str(record.get('in_stock', '')).strip().casefold() in ('true', '1', 'yes')
        raw_stock = 1 if in_stock else 0
        raw_timestamp = record.get('feed_timestamp')
    elif supplier == 'supplier_c':
        sku = record.get('vendor_ref')
        gtin = record.get('barcode')
        title = record.get('item_desc')
        raw_price = record.get('wholesale_price')
        currency = record.get('currency', 'USD')
        category = record.get('category_path')
        status = str(record.get('availability_status', '')).strip().upper()
        raw_stock = 1 if status == 'IN_STOCK' else 0
        raw_timestamp = record.get('batch_date')
    else:
        raise ValueError('UNKNOWN_SUPPLIER')

    # 1. Primary key checks
    if not sku or not str(sku).strip():
        raise ValueError('MISSING_SKU')
    if not title or not str(title).strip():
        raise ValueError('MISSING_NAME')

    # 2. Price and Currency normalization
    amount = validate_numeric_price(raw_price)
    code = str(currency or '').upper().strip()
    if code not in RATES:
        raise ValueError('UNSUPPORTED_CURRENCY')
    price_usd = (amount * RATES[code]).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    # 3. Barcode / GTIN validation
    gtin_str = str(gtin or '').strip()
    if gtin_str and not gtin_valid(gtin_str):
        raise ValueError('INVALID_GTIN')

    # 4. Stock validation
    stock_quantity = validate_stock_quantity(raw_stock)

    # 5. Timestamp validation
    timestamp_utc = parse_timestamp(raw_timestamp)

    # 6. Category mapping (falls back to Uncategorized)
    category_clean = str(category or '').strip().casefold()
    standard_category = categories.get(category_clean, 'Uncategorized')

    # 7. Identity resolution: GTIN taking precedence; fallback to SKU
    if gtin_str:
        canonical_gtin = gtin_str.zfill(14)
        entity_key = f'GTIN:{canonical_gtin}'
    else:
        canonical_gtin = None
        entity_key = f'SKU:{supplier}:{str(sku).strip()}'

    master_product_id = hashlib.sha256(entity_key.encode('utf-8')).hexdigest()[:32]

    return {
        'master_product_id': master_product_id,
        'gtin': canonical_gtin,
        'standard_title': ' '.join(str(title).split()),
        'standard_category': standard_category,
        'price_usd': str(price_usd),
        'stock_quantity': stock_quantity,
        'winning_supplier_id': supplier,
        'source_sku': str(sku).strip(),
        'source_record_hash': canonical_hash(record),
        'source_updated_at': timestamp_utc,
    }


def winner_key(row: dict) -> tuple:
    """Deterministic comparison key to rank competing records for the same physical product.
    
    Priority order:
    1. Lowest normalized USD price
    2. Higher available stock quantity
    3. Preferred supplier hierarchy (Supplier A > Supplier B > Supplier C)
    4. Most recent source update timestamp
    5. Deterministic record hash tie-breaker
    """
    return (
        Decimal(row['price_usd']),
        -row['stock_quantity'],
        PRIORITY.get(row['winning_supplier_id'], 999),
        -datetime.fromisoformat(row['source_updated_at']).timestamp(),
        row['source_record_hash'],
    )

"""Pipeline configuration constants, exchange rates, and supplier settings."""
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Static currency conversion rate card against USD base
RATES: dict[str, Decimal] = {
    'USD': Decimal('1.00'),
    'EUR': Decimal('1.08'),
    'GBP': Decimal('1.27'),
}

# Tie-breaking priority among suppliers (lower index = higher priority)
PRIORITY: dict[str, int] = {
    'supplier_a': 0,
    'supplier_b': 1,
    'supplier_c': 2,
}

# Expected supplier feed files within the input directory
SUPPLIER_FEEDS: list[tuple[str, str]] = [
    ('supplier_a', 'supplier_a_products.csv'),
    ('supplier_b', 'supplier_b_catalog.jsonl'),
    ('supplier_c', 'supplier_c_feed.csv'),
]

# Mandatory headers for CSV-based feeds
REQUIRED_HEADERS: dict[str, set[str]] = {
    'supplier_a': {'supplier_sku', 'product_name', 'price'},
    'supplier_c': {'vendor_ref', 'item_desc', 'wholesale_price'},
}

DEFAULT_CATEGORIES_PATH: Path = ROOT / 'config' / 'lookup_categories.csv'
DEFAULT_SCHEMA_PATH: Path = ROOT / 'sql' / 'schema.sql'
DEFAULT_DB_PATH: Path = ROOT / 'output' / 'catalog.db'
DEFAULT_INPUT_DIR: Path = ROOT / 'data' / 'sample'

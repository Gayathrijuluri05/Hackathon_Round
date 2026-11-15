"""Data validation functions: GTIN check-digits, nullability, types, and timestamps."""
from __future__ import annotations
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def gtin_valid(value: str) -> bool:
    """Validate GTIN-8, GTIN-12 (UPC-A), GTIN-13 (EAN-13), or GTIN-14 check digit using GS1 standard.
    
    The check digit calculation:
    Starting from the right (excluding the check digit):
    Multiply alternate digits by 3 and 1, sum the products,
    then check_digit = (10 - (sum % 10)) % 10.
    """
    if not value or not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped.isdigit() or len(stripped) not in (8, 12, 13, 14):
        return False
    digits = [int(x) for x in stripped]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    expected_check_digit = (10 - total % 10) % 10
    return expected_check_digit == digits[-1]


def parse_timestamp(value: object) -> str:
    """Validate and convert an arbitrary ISO timestamp into UTC ISO-8601 string.
    
    Raises:
        ValueError('MISSING_TIMESTAMP') if empty.
        ValueError('INVALID_TIMESTAMP') if unparseable.
    """
    if not value or not str(value).strip():
        raise ValueError('MISSING_TIMESTAMP')
    try:
        s = str(value).strip().replace('Z', '+00:00')
        parsed = datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        raise ValueError('INVALID_TIMESTAMP') from None


def validate_numeric_price(price: object) -> Decimal:
    """Ensure price is present, numeric, finite, and non-negative.
    
    Raises:
        ValueError('NULL_PRICE') if missing or empty.
        ValueError('INVALID_PRICE') if not a valid non-negative number.
    """
    if price is None or not str(price).strip():
        raise ValueError('NULL_PRICE')
    try:
        amount = Decimal(str(price).strip())
        if not amount.is_finite() or amount < 0:
            raise InvalidOperation
        return amount
    except (InvalidOperation, ValueError):
        raise ValueError('INVALID_PRICE') from None


def validate_stock_quantity(stock: object) -> int:
    """Ensure stock quantity is a non-negative integer.
    
    Raises:
        ValueError('INVALID_STOCK') if negative or unparseable.
    """
    try:
        quantity = int(stock)
        if quantity < 0:
            raise ValueError
        return quantity
    except (ValueError, TypeError):
        raise ValueError('INVALID_STOCK') from None

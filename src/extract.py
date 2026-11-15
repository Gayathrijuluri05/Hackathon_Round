
"""Feed extraction module: reads heterogeneous supplier formats streaming row-by-row."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Generator
from src.config import REQUIRED_HEADERS


def detect_delimiter(first_line: str) -> str:
    """Detect whether a line is tab-separated or comma-separated."""
    if '\t' in first_line and ',' not in first_line:
        return '\t'
    return ','


def iter_feed(path: Path, supplier: str) -> Generator[tuple[dict, str | None], None, None]:
    """Yield tuples of (raw_record, parse_error).
    
    Individual malformed rows/lines are trapped and yielded with an error tag
    so the caller can quarantine them without terminating the batch.
    """
    if supplier == 'supplier_b':
        with path.open(encoding='utf-8-sig') as f:
            for line_no, line in enumerate(f, start=1):
                raw_str = line.strip()
                if not raw_str:
                    continue
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError('JSON record must be an object')
                    yield value, None
                except (json.JSONDecodeError, ValueError):
                    yield {'_raw_line': line.rstrip('\n'), '_line_no': line_no}, 'MALFORMED_JSON'
    else:
        with path.open(newline='', encoding='utf-8-sig') as f:
            # Peek first non-empty line to detect delimiter (CSV vs TSV)
            sample = f.readline()
            if not sample.strip():
                return
            delimiter = detect_delimiter(sample)
            f.seek(0)

            reader = csv.DictReader(f, delimiter=delimiter)
            if not reader.fieldnames:
                return

            required = REQUIRED_HEADERS.get(supplier, set())
            missing = required - set(reader.fieldnames)

            while True:
                try:
                    row = next(reader)
                except StopIteration:
                    break
                except csv.Error as exc:
                    yield {'_raw_error': str(exc)}, 'MALFORMED_CSV'
                    continue

                if missing:
                    yield row, 'MISSING_COLUMNS: ' + ','.join(sorted(missing))
                elif None in row:
                    # DictReader puts extra fields under None key if line has more columns than header
                    yield row, 'MALFORMED_CSV'
                else:
                    yield row, None

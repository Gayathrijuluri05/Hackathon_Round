"""Generate reproducible three-supplier synthetic input files (10k–100k+ total rows)."""
import argparse
import csv
import json
import random
from pathlib import Path


def barcode(n: int) -> str:
    base = f'{n % 100000000000:011d}'
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(base)))
    return base + str((10 - total % 10) % 10)


def generate(output_dir: Path, count: int, seed: int = 42):
    if count < 0:
        raise ValueError('count must not be negative')
    random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / 'supplier_a_products.csv').open('w', newline='', encoding='utf-8') as fa, \
         (output_dir / 'supplier_b_catalog.jsonl').open('w', encoding='utf-8') as fb, \
         (output_dir / 'supplier_c_feed.csv').open('w', newline='', encoding='utf-8') as fc:
        wa = csv.DictWriter(fa, fieldnames=['supplier_sku','upc_ean','product_name','category_code','price','curr','qty_on_hand','updated_at'])
        wc = csv.DictWriter(fc, fieldnames=['vendor_ref','barcode','item_desc','category_path','wholesale_price','currency','availability_status','batch_date'])
        wa.writeheader(); wc.writeheader()
        for i in range(count):
            # Across suppliers, overlap on every third item; otherwise produce independent products.
            supplier = i % 3
            product_num = (i // 3) if i % 9 == 0 else i + 100000
            code = barcode(product_num)
            price = round(random.uniform(10, 1200), 2)
            title = f'Generated Product {product_num}'
            stamp = '2026-11-12T10:00:00Z'
            if supplier == 0:
                wa.writerow({'supplier_sku':f'A-{i}','upc_ean':code,'product_name':title,'category_code':'CAT_402', 'price':price, 'curr':'USD', 'qty_on_hand':random.randint(0,50),'updated_at':stamp})
            elif supplier == 1:
                fb.write(json.dumps({'item_id':f'B-{i}','gtin':code,'title':title,'category':'Laptops', 'amount_cents':int(round(price*100)), 'currency_code':'USD', 'in_stock':True,'feed_timestamp':stamp})+'\n')
            else:
                wc.writerow({'vendor_ref':f'C-{i}','barcode':code,'item_desc':title,'category_path':'Electronics > Computers', 'wholesale_price':price,'currency':'USD','availability_status':'IN_STOCK','batch_date':stamp})
    print(f'Generated {count} source records at {output_dir}')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--count', type=int, default=10000)
    p.add_argument('--out', type=Path, default=Path('data/generated'))
    p.add_argument('--seed', type=int, default=42)
    a = p.parse_args()
    generate(a.out, a.count, a.seed)

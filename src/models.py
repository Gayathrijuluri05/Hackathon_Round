"""Data models and schemas using Pydantic for validation and serialization."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class BaseFeedModel(BaseModel):
    """Base configuration for feed models."""
    model_config = ConfigDict(extra='allow', str_strip_whitespace=True)


class SupplierAFeedRow(BaseFeedModel):
    """Supplier A CSV raw row format."""
    supplier_sku: str
    upc_ean: Optional[str] = None
    product_name: str
    category_code: Optional[str] = None
    price: str
    curr: str = 'USD'
    qty_on_hand: Optional[int] = 0
    updated_at: str


class SupplierBFeedRow(BaseFeedModel):
    """Supplier B JSONL raw record format."""
    item_id: str
    gtin: Optional[str] = None
    title: str
    category: Optional[str] = None
    amount_cents: int
    currency_code: str = 'USD'
    in_stock: bool = False
    feed_timestamp: str


class SupplierCFeedRow(BaseFeedModel):
    """Supplier C CSV raw row format."""
    vendor_ref: str
    barcode: Optional[str] = None
    item_desc: str
    category_path: Optional[str] = None
    wholesale_price: str
    currency: str = 'USD'
    availability_status: str = 'IN_STOCK'
    batch_date: str


class NormalizedProduct(BaseModel):
    """Cleaned intermediate representation of a supplier product."""
    model_config = ConfigDict(extra='ignore')

    master_product_id: str = Field(description="SHA-256 derived 32-char hex product ID")
    gtin: Optional[str] = Field(default=None, description="Standardized 14-digit GTIN")
    standard_title: str = Field(description="Cleaned, normalized title")
    standard_category: str = Field(description="Canonical category or Uncategorized")
    price_usd: str = Field(description="Normalized USD price string with 2 decimals")
    stock_quantity: int = Field(ge=0, description="Normalized integer stock quantity")
    winning_supplier_id: str = Field(description="Supplier ID providing this record")
    source_sku: str = Field(description="Original supplier-assigned SKU")
    source_record_hash: str = Field(description="SHA-256 of the raw input record")
    source_updated_at: str = Field(description="ISO-8601 UTC timestamp from source")
    source_file: str = Field(description="Source file name")
    source_batch_id: str = Field(description="Batch identifier")


class GoldenProductRecord(NormalizedProduct):
    """Published target product catalog record."""
    ingestion_run_id: str = Field(description="UUID of the pipeline run that published/updated this row")
    last_updated_at: str = Field(description="ISO-8601 UTC timestamp of golden catalog write")


class QuarantineRecord(BaseModel):
    """Dead-letter quarantine record."""
    rejection_id: str
    supplier_id: str
    raw_record: str
    rejection_reason: str
    ingestion_run_id: str
    failed_at: str


class PipelineRunSummary(BaseModel):
    """Operational audit log for an ingestion run."""
    run_id: str
    started_at: str
    completed_at: Optional[str] = None
    status: str = Field(pattern="^(SUCCESS|PARTIAL_SUCCESS|FAILED)$")
    records_read_total: int = 0
    records_published: int = 0
    records_rejected: int = 0
    records_deduplicated: int = 0
    records_unchanged: int = 0
    error_summary: str = "{}"

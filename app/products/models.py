from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field

ProductCategory = Literal[
    "skincare",
    "color_makeup",
    "other",
    "unknown",
]

class ProductCandidate(BaseModel) :
    product_id: str
    source: str = "oliveyoung"
    brand_name: str | None = None
    product_name: str
    category: ProductCategory = "unknown"
    category_path: str | None = None
    product_url: str
    image_url: str | None = None
    original_price: int | None = None
    sale_price: int | None = None
    rank: int | None = None
    search_query: str | None = None

    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ProductSearchMetadata(BaseModel):
    provider: str
    result_count: int
    search_empty: bool
    cache_hit: bool = False


class ProductSearchResult(BaseModel):
    query: str
    products: list[ProductCandidate]=Field(
        default_factory=list
    )
    metadata: ProductSearchMetadata


class ProductIngredientResult(BaseModel):
    product_id: str
    product_url: str
    raw_ingredients: str
    ingredients: list[str] = Field(
        default_factory=list
    )
    extraction_method: str = "browser_dom"
    extraction_success: bool = False
    error_message: str | None = None
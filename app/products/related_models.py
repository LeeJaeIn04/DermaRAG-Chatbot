from typing import Literal

from pydantic import BaseModel, Field


CategoryMatchLevel = Literal[
    "same_category",
    "same_parent_path",
    "other_category",
]


class RelatedOptionMatch(BaseModel):
    option_id: str
    option_name: str | None = None
    matched_ingredients: list[str] = Field(default_factory=list)


class RelatedProductMatch(BaseModel):
    product_id: int
    source: str
    external_product_id: str
    product_name: str
    brand_name: str | None = None
    category: str
    category_path: str | None = None
    product_url: str
    image_url: str | None = None
    matched_ingredients: list[str] = Field(default_factory=list)
    matched_options: list[RelatedOptionMatch] = Field(default_factory=list)
    category_match_level: CategoryMatchLevel


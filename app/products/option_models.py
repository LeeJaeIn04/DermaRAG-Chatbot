from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


OptionMappingStatus = Literal[
    "matched",
    "unmatched",
    "ambiguous",
    "unsupported",
]


class ProductOption(BaseModel):
    internal_option_key: str
    source_option_id: str | None = None
    option_name: str
    raw_option_name: str
    normalized_name: str
    image_url: str | None = None
    mapping_status: OptionMappingStatus = "unmatched"
    mapping_confidence: float = 0.0
    source_option_names: list[str] = Field(
        default_factory=list,
        exclude=True,
    )
    source_option_ids: list[str] = Field(
        default_factory=list,
        exclude=True,
    )


class ProductIngredientRawDocument(BaseModel):
    source: str
    product_id: str
    raw_text: str
    fetched_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    parser_version: str


class NormalizedTextIndex(BaseModel):
    normalized_text: str
    original_indexes: list[int] = Field(default_factory=list)


class OptionIngredientSection(BaseModel):
    internal_option_key: str
    source_option_id: str | None = None
    option_name: str
    matched_header: str | None = None
    raw_ingredient_text: str = ""
    ingredients: list[str] = Field(default_factory=list)
    mapping_status: OptionMappingStatus
    mapping_method: str
    mapping_confidence: float
    duplicate_header_count: int = 0


OptionCollectionStatus = Literal[
    "collected",
    "no_options",
    "failed",
]


class ProductOptionExtractionResult(BaseModel):
    status: OptionCollectionStatus
    options: list[ProductOption] = Field(default_factory=list)
    option_count: int = 0
    raw_document: ProductIngredientRawDocument | None = None
    error_message: str | None = None


class OptionMappingDiagnostics(BaseModel):
    """옵션 매핑의 내부 진단용 집계값."""

    collected_option_count: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    ambiguous_count: int = 0
    unsupported_count: int = 0
    collected_raw_option_count: int = 0
    canonical_option_count: int = 0
    merged_duplicate_count: int = 0
    matched_canonical_count: int = 0
    unmatched_canonical_count: int = 0
    duplicate_header_count: int = 0


class ProductOptionPreparationResult(BaseModel):
    requires_option_selection: bool
    options: list[ProductOption] = Field(default_factory=list)
    can_analyze: bool
    status: Literal[
        "ready",
        "not_applicable",
        "mapping_failed",
        "extraction_failed",
    ]
    error_message: str | None = None
    mapping_diagnostics: OptionMappingDiagnostics | None = Field(
        default=None,
        exclude=True,
    )

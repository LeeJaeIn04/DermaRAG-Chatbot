from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


OptionMappingStatus = Literal[
    "matched",
    "unmatched",
    "ambiguous",
    "unsupported",
]

OptionAvailability = Literal[
    "available",
    "temporarily_sold_out",
    "unknown",
]

OptionMetadataMatchStatus = Literal[
    "not_applicable",
    "complete_match",
    "complete_match_reordered",
    "partial_metadata_enrichment",
    "mismatch",
]

OptionExtractionFailureStage = Literal[
    "option_button_not_found",
    "option_list_render_timeout",
    "option_dom_parse_failed",
    "flight_parse_failed",
    "option_dom_flight_mismatch",
    "ingredient_disclosure_failed",
    "ingredient_text_empty",
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
    # Step 4: 옵션 단위 분석 가능 여부. status는 Step 1
    # OptionParseStatus(ready/unmapped/empty/ambiguous/error)와 같은
    # 값을 쓴다. 기존 코드 경로는 이 필드를 모르므로 기본값(모름/
    # 분석 가능)으로 두고, API 응답을 만드는 지점에서만 명시적으로
    # 채운다.
    status: Literal[
        "ready",
        "unmapped",
        "empty",
        "ambiguous",
        "error",
    ] | None = Field(default=None)
    analysis_available: bool = Field(default=True)
    source_option_names: list[str] = Field(
        default_factory=list,
        exclude=True,
    )
    source_option_ids: list[str] = Field(
        default_factory=list,
        exclude=True,
    )
    # 상품 선택 UI 수집 진단과 캐시 재구성을 위한 metadata다.
    # 현재 사용자 API 계약에는 노출하지 않는다.
    product_id: str | None = Field(default=None, exclude=True)
    option_number: str | None = Field(default=None, exclude=True)
    standard_code: str | None = Field(default=None, exclude=True)
    normalized_option_name: str = Field(default="", exclude=True)
    availability: OptionAvailability = Field(
        default="unknown",
        exclude=True,
    )
    sold_out_flag: bool | None = Field(default=None, exclude=True)
    dom_disabled: bool | None = Field(default=None, exclude=True)
    sort_order: int | None = Field(default=None, exclude=True)
    representative: bool | None = Field(default=None, exclude=True)
    group_path: list[str] = Field(default_factory=list, exclude=True)
    combination_option_flag: bool | None = Field(
        default=None,
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
    metadata_match_status: OptionMetadataMatchStatus = Field(
        default="not_applicable",
        exclude=True,
    )
    failure_stage: OptionExtractionFailureStage | None = Field(
        default=None,
        exclude=True,
    )


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
    orphan_document_section_count: int = Field(default=0, exclude=True)
    malformed_header_count: int = Field(default=0, exclude=True)
    ambiguous_header_count: int = Field(default=0, exclude=True)
    document_format: Literal[
        "option_full_sections",
        "hierarchical_option_internal_sections",
        "needs_review",
    ] = Field(default="option_full_sections", exclude=True)
    structure_reason: str | None = Field(default=None, exclude=True)
    top_level_header_count: int = Field(default=0, exclude=True)
    nested_header_count: int = Field(default=0, exclude=True)


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
    # Step 4: Step 1 CollectionStatus(ready/partial/failed)를 그대로
    # 전달한다. 기존 status 필드의 의미(ready/not_applicable/
    # mapping_failed/extraction_failed)는 바꾸지 않는다 - 이 필드는
    # 추가 정보다.
    collection_status: Literal[
        "ready",
        "partial",
        "failed",
    ] | None = Field(default=None)
    mapping_diagnostics: OptionMappingDiagnostics | None = Field(
        default=None,
        exclude=True,
    )

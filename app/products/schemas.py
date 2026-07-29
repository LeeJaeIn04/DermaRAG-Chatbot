from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.schemas import UserSkinProfile
from app.skin_rule_schemas import (
    SkinCompatibilityNotice,
)


class ProductIngredientRequest(BaseModel):
    """
    선택한 상품의 전성분을 요청하는 모델.

    ProductIngredientCacheService는 상품 ID뿐 아니라
    source와 product_url도 필요하므로
    ProductCandidate 전체를 전달한다.

    색조 상품은 option_id와 option_name을
    함께 전달할 수 있다.
    """

    product: ProductCandidate
    option_id: str = ""
    internal_option_key: str | None = None
    option_name: str | None = None
    source_option_id: str | None = None


class ProductIngredientResponse(BaseModel):
    """
    전성분 결과와 캐시 처리 정보를 반환한다.
    """

    result: ProductIngredientResult
    cache_hit: bool
    cache_expired: bool
    extraction_performed: bool


class ProductAnalysisRequest(BaseModel):
    """
    선택한 상품의 전성분을 확보하고
    기존 식약처 성분 RAG로 분석하기 위한 요청 모델.
    """

    product: ProductCandidate

    # 사용자가 궁금한 내용이나
    # 제품 사용 후 나타난 피부 반응
    question: str

    # 사용자 피부 정보
    skin_type: str | None = None
    skin_profile: UserSkinProfile | None = None
    current_routine: str | None = None

    # 색조 상품 옵션
    option_id: str = ""
    internal_option_key: str | None = None
    option_name: str | None = None
    source_option_id: str | None = None


class ProductRegulationSource(BaseModel):
    """
    제품 전성분과 일치한 식약처 규제 정보.

    내부 Repository 모델 전체를 노출하지 않고,
    API 응답에 필요한 값만 반환한다.
    """

    query_ingredient: str
    matched_name: str

    match_type: Literal[
        "ingredient_kor_name",
        "chemical_name",
        "cas_no",
    ]

    regulation_type: Literal[
        "prohibited",
        "restricted",
    ]

    category: Literal[
        "prohibited",
        "preservative",
        "uv_filter",
        "hair_dye",
        "restricted_other",
    ]

    cas_no: str = ""
    chemical_name: str | None = None

    max_concentration: str | None = None
    product_scope: str | None = None
    use_conditions: str | None = None
    warning_text: str | None = None

    source_authority: str
    source_document: str
    notice_number: str
    notice_date: str
    source_section: str

class ProductFragranceAllergenSource(BaseModel):
    """
    제품 전성분과 일치한 식약처 향료 알레르기
    유발성분 표시 대상 정보.

    이 모델은 법적 표시 대상 정보를 나타내며,
    특정 사용자에게 실제 알레르기 반응을
    일으킨다는 의미는 아니다.
    """

    query_ingredient: str
    matched_name: str

    match_type: Literal[
        "ingredient_kor_name",
        "ingredient_eng_name",
        "inci_name",
        "alias",
        "cas_no",
    ]

    ingredient_kor_name: str
    ingredient_eng_name: str | None = None
    inci_name: str | None = None

    cas_numbers: list[str] = Field(
        default_factory=list
    )
    aliases: list[str] = Field(
        default_factory=list
    )

    allergen_type: str
    legal_status: str
    jurisdiction: str
    evidence_scope: str

    rinse_off_threshold: str | None = None
    leave_on_threshold: str | None = None

    source_authority: str
    source_document: str
    source_document_version: str | None = None
    source_document_date: str | None = None
    source_section: str | None = None
    source_page: int | None = None
    source_row: int


class ProductAnalysisResponse(BaseModel):
    """
    상품 RAG 분석 결과와 식약처 규제 정보,
    전성분 캐시 처리 상태를 반환한다.
    """

    product: ProductCandidate

    answer: str

    # 현재 LangGraph의 sources와 metadata 구조가
    # 완전히 고정되지 않았으므로 우선 범용 타입을 사용한다.
    sources: list[Any] = Field(
        default_factory=list
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    ingredient_count: int
    skin_compatibility: list[
        SkinCompatibilityNotice
    ] = Field(default_factory=list)
    selected_option_key: str | None = None
    selected_option_name: str | None = None
    option_specific_ingredients: bool = False

    regulation_count: int = 0
    regulations: list[
        ProductRegulationSource
    ] = Field(
        default_factory=list
    )
    allergen_count: int = 0

    allergens: list[
        ProductFragranceAllergenSource
    ] = Field(
        default_factory=list
    )

    cache_hit: bool
    cache_expired: bool
    extraction_performed: bool

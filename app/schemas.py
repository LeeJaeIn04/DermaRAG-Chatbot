from pydantic import BaseModel, Field
from app.products.models import (
    ProductCandidate,
    ProductSearchMetadata,
)

class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        description="사용자의 질문 또는 피부 반응 설명",
        examples=["쿠션을 바꾼 뒤, 볼에 좁쌀이 올라오고 따가워요."],
    )
    skin_type: str | None = Field(
        default=None,
        description="사용자가 알고 있는 피부 타입",
        examples=["건성, 지성, 복합성, 수부지, 민감성"],
    )
    ingredient_list: str | None = Field(
        default=None,
        description="제품 전성분표",
        examples=["정제수, 티타늄디옥사이드, 글리세린, 나이아신아마이드, 향료"],
    )
    current_routine: str | None = Field(
        default=None,
        description="현재 스킨케어 루틴",
        examples=["BHA 토너를 주 3회 사용 중"],
    )

class Source(BaseModel):
    source: str
    content: str

    ingredient_kor_name: str | None = None
    ingredient_eng_name: str | None = None
    cas_no: str | None = None

    retrieval_type: str | None = None
    match_score: float | None = None

class ChatMetadata(BaseModel):
    route: str | None = None
    warnings: list[str] = Field(default_factory=list)

    ingredient_count: int | None = None
    retrieved_doc_count: int | None = None
    exact_match_count: int | None = None
    vector_fallback_count: int | None = None

    context_char_count: int | None = None
    context_empty: bool | None = None
    used_rag_context: bool | None = None

class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]=Field(default_factory=list)
    metadata: ChatMetadata = Field(default_factory=ChatMetadata)


class ProductSearchRequest(BaseModel):
    query: str = Field(
        min_length=1,
        description="검색할 상품명 또는 검색어",
    )

    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="반환할 최대 상품 수",
    )


class ProductSearchResponse(BaseModel):
    query: str

    products: list[ProductCandidate] = Field(
        default_factory=list
    )

    metadata: ProductSearchMetadata


class ProductSelectionRequest(BaseModel):
    product_id: str
    products: list[ProductCandidate]


class ProductSelectionResponse(BaseModel):
    selected_product: ProductCandidate
    next_action: str
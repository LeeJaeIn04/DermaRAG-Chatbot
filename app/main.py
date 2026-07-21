from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from app.schemas import ChatRequest, ChatResponse
from app.config import settings
from app.services.langsmith_trace import invoke_derma_rag
from app.products.providers.mock import (
    MockProductSearchProvider,
)
from app.products.service import ProductSearchService
from app.schemas import (
    ProductSearchRequest,
    ProductSearchResponse,
    ProductSelectionRequest,
    ProductSelectionResponse,
)
from app.products.classifier import (
    get_next_action,
)

from app.products.ingredient_extractors import (
    OliveYoungIngredientExtractor,
)
from app.products.models import (
    ProductIngredientResult,
)

app = FastAPI(
    title="DermaRAG API",
    description="성분 기반 피부 반응 원인 후보 분석 챗봇 API",
    version="1.0.0",
)

product_search_service = ProductSearchService(
    provider=MockProductSearchProvider(),

    ingredient_extractor=(
        OliveYoungIngredientExtractor(
            headless=False,
        )
    ),
)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "project": settings.langsmith_project,
    }

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    final_state = invoke_derma_rag(request)
    
    return ChatResponse (
        answer = final_state.get("answer", ""),
        sources = final_state.get("sources", []),
        metadata=final_state.get("metadata", {}),
    )


@app.post(
    "/products/search",
    response_model=ProductSearchResponse,
)
def search_products(
    request: ProductSearchRequest,
) -> ProductSearchResponse:
    try:
        result = product_search_service.search(
            query=request.query,
            limit=request.limit,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    return ProductSearchResponse(
        query=result.query,
        products=result.products,
        metadata=result.metadata,
    )


@app.post(
    "/products/select",
    response_model=ProductSelectionResponse,
)
def select_product(
    request: ProductSelectionRequest,
) -> ProductSelectionResponse:
    selected_product = product_search_service.find_product(
        product_id=request.product_id,
        products=request.products,
    )

    if selected_product is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "선택한 상품이 상품 후보 목록에 없습니다."
            ),
        )

    next_action = get_next_action(
        selected_product.category
    )

    return ProductSelectionResponse(
        selected_product=selected_product,
        next_action=next_action,
    )

class ProductIngredientRequest(BaseModel):
    """
    전성분을 추출할 상품 선택 요청.

    /products/search에서 반환된 product_id를 전달한다.
    """

    product_id: str

@app.post(
    "/products/extract-ingredients",
    response_model=ProductIngredientResult,
)
def extract_product_ingredients(
    request: ProductIngredientRequest,
) -> ProductIngredientResult:
    """
    직전 상품 검색 결과에서 선택한 상품의
    상세 페이지를 열어 전성분을 추출한다.

    실행 순서:
    1. product_id로 상품 후보 조회
    2. 상품 URL 확인
    3. Playwright 추출기 실행
    4. 전성분 결과 반환
    """

    try:
        result = (
            product_search_service
            .extract_product_ingredients(
                product_id=request.product_id
            )
        )

    except ValueError as error:
        # 후보에 없는 상품, URL 없음 등의 요청 문제
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    if not result.extraction_success:
        # 상품은 정상적으로 선택됐지만
        # 외부 페이지에서 전성분을 읽지 못한 경우
        raise HTTPException(
            status_code=502,
            detail=(
                result.error_message
                or "전성분 추출에 실패했습니다."
            ),
        )

    return result
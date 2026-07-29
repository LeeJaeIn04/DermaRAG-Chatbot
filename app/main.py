from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import (
    SessionLocal,
    create_database_tables,
)
from app.products.schemas import ProductAnalysisRequest, ProductAnalysisResponse
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ProductIngredientRequest,
    ProductIngredientResponse,
    ProductSearchRequest,
    ProductSearchResponse,
    ProductSelectionRequest,
    ProductSelectionResponse,
)
from app.services.langsmith_trace import (
    invoke_derma_rag,
)
from app.rag_chain import resolve_ingredients

from app.products.classifier import (
    get_next_action,
)
from app.products.ingredient_cache_service import (
    ProductIngredientCacheService,
)
from app.products.ingredient_extractors import (
    OliveYoungIngredientExtractor,
    OliveYoungProductOptionExtractor,
)
from app.products.providers import (
    OliveYoungProductSearchProvider,
)
from app.products.providers.base import (
    ProductSearchProviderError,
)
from app.products.repositories import (
    SQLiteProductIngredientRepository,
)
from app.products.service import (
    ProductSearchService,
)
from app.products.option_service import (
    ProductOptionService,
)
from app.products.regulation_mapper import (
    build_product_regulations,
    build_regulation_context,
)
from app.safety.mfds_repository import (
    get_mfds_regulation_repository,
)
from app.allergens.mfds_repository import (
    get_mfds_fragrance_allergen_repository,
)
from app.products.allergen_mapper import (
    build_allergen_context,
    build_product_allergens,
)


app = FastAPI(
    title="DermaRAG API",
    description=(
        "성분 기반 피부 반응 원인 후보 분석 "
        "챗봇 API"
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# SQLAlchemy 모델에 정의된 테이블을
# 실제 SQLite 데이터베이스에 생성한다.
#
# 이미 테이블이 있으면 다시 만들지 않는다.
create_database_tables()


# 상품 검색과 상품 선택을 담당한다.
product_search_service = ProductSearchService(
    provider=OliveYoungProductSearchProvider(
        headless=False,
    ),
)


# 상품과 전성분의 DB 조회·저장을 담당한다.
#
# SQLiteProductIngredientRepository는
# Session 자체가 아니라 Session을 생성하는
# SessionLocal을 전달받는다.
ingredient_repository = (
    SQLiteProductIngredientRepository(
        session_factory=SessionLocal,
    )
)


# 올리브영 상품 페이지에서
# 실제 전성분을 가져오는 추출기다.
#
# headless=False:
# 올리브영은 headless Chrome 세션을 Cloudflare 봇 차단으로
# 막아 "잠시만 기다려 주세요" 안내 페이지만 반환한다(실제
# 상품 페이지에 도달하지 못해 상품정보 제공고시 영역을
# 영원히 찾지 못하고 타임아웃한다). CAPTCHA 우회나 stealth
# 플러그인 같은 회피 기법은 쓰지 않기로 했으므로, 실제
# 사용자가 보는 화면을 그대로 띄우는 headless=False가
# 현재 유일하게 검증된 실행 방식이다. 따라서 이 서버를
# 띄우는 환경에는 화면 출력이 가능해야 한다(원격 서버라면
# Xvfb 같은 가상 디스플레이가 필요하다).
ingredient_extractor = (
    OliveYoungIngredientExtractor(
        headless=False,
    )
)


# 전성분 캐시 조회와 추출 실행을 조정한다.
#
# 유효한 DB 캐시가 있으면 Extractor를 실행하지 않고,
# 캐시가 없거나 만료됐을 때만 Playwright를 실행한다.
ingredient_cache_service = (
    ProductIngredientCacheService(
        repository=ingredient_repository,
        extractor=ingredient_extractor,
        ttl_days=90,
    )
)

product_option_extractor = (
    OliveYoungProductOptionExtractor(
        ingredient_extractor=ingredient_extractor,
        headless=False,
    )
)

product_option_service = ProductOptionService(
    extractor=product_option_extractor,
    cache_service=ingredient_cache_service,
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """
    서버가 정상 실행 중인지 확인한다.
    """

    return {
        "status": "ok",
        "project": settings.langsmith_project,
    }


@app.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    request: ChatRequest,
) -> ChatResponse:
    """
    기존 DermaRAG LangGraph를 실행한다.
    """

    final_state = invoke_derma_rag(request)

    return ChatResponse(
        answer=final_state.get(
            "answer",
            "",
        ),
        sources=final_state.get(
            "sources",
            [],
        ),
        metadata=final_state.get(
            "metadata",
            {},
        ),
        skin_compatibility=final_state.get(
            "skin_compatibility",
            [],
        ),
    )


@app.post(
    "/products/search",
    response_model=ProductSearchResponse,
)
def search_products(
    request: ProductSearchRequest,
) -> ProductSearchResponse:
    """
    사용자 검색어로 상품 후보를 검색한다.
    """

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
    except ProductSearchProviderError as error:
        raise HTTPException(
            status_code=502,
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
    """
    상품 후보 목록에서 사용자가 선택한 상품을 찾는다.
    """

    selected_product = (
        product_search_service.find_product(
            product_id=request.product_id,
            products=request.products,
        )
    )

    if selected_product is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "선택한 상품이 상품 후보 "
                "목록에 없습니다."
            ),
        )

    next_action = get_next_action(
        selected_product.category
    )

    try:
        option_preparation = (
            product_option_service.prepare_product(
                selected_product
            )
        )
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "상품 옵션과 전성분을 준비하지 "
                f"못했습니다: {error}"
            ),
        ) from error

    return ProductSelectionResponse(
        selected_product=selected_product,
        next_action=next_action,
        requires_option_selection=(
            option_preparation.requires_option_selection
        ),
        options=option_preparation.options,
        can_analyze=option_preparation.can_analyze,
        option_status=option_preparation.status,
        option_error=option_preparation.error_message,
    )


@app.post(
    "/products/extract-ingredients",
    response_model=ProductIngredientResponse,
)
def extract_product_ingredients(
    request: ProductIngredientRequest,
) -> ProductIngredientResponse:
    """
    선택한 상품의 전성분을 확보한다.

    실행 순서:
    1. 상품과 옵션 기준으로 DB 캐시 조회
    2. 유효한 캐시가 있으면 DB 결과 사용
    3. 캐시가 없거나 만료됐으면 Playwright 실행
    4. 추출 성공 결과를 SQLite에 저장
    5. 전성분과 캐시 처리 정보 반환
    """

    try:
        selected_option_key = (
            request.internal_option_key or request.option_id
        ).strip()
        if selected_option_key:
            resolution = (
                ingredient_cache_service.get_cached_option(
                    product=request.product,
                    internal_option_key=selected_option_key,
                )
            )
        else:
            resolution = (
                ingredient_cache_service.get_or_extract(
                    product=request.product,
                    option_id="",
                    option_name=None,
                )
            )

    except ValueError as error:
        # 잘못된 상품 정보나 옵션 값 등
        # 요청 데이터에서 발생한 오류
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        # DB 연결이나 Playwright 실행 등
        # 서버 내부 처리에서 발생한 예외
        raise HTTPException(
            status_code=500,
            detail=(
                "전성분 처리 중 서버 오류가 "
                f"발생했습니다: {error}"
            ),
        ) from error

    if not resolution.result.extraction_success:
        # 상품 정보는 정상이지만 외부 페이지에서
        # 전성분을 읽지 못한 경우
        raise HTTPException(
            status_code=502,
            detail=(
                resolution.result.error_message
                or "전성분 추출에 실패했습니다."
            ),
        )

    return ProductIngredientResponse(
        result=resolution.result,
        cache_hit=resolution.cache_hit,
        cache_expired=(
            resolution.cache_expired
        ),
        extraction_performed=(
            resolution.extraction_performed
        ),
    )

@app.post(
    "/products/analyze",
    response_model=ProductAnalysisResponse,
)
def analyze_product(
    request: ProductAnalysisRequest,
) -> ProductAnalysisResponse:
    """
    선택한 상품의 전성분을 확보한 뒤
    기존 식약처 성분 RAG를 실행한다.

    실행 순서:
    1. DB 전성분 캐시 조회
    2. 캐시가 없거나 만료됐으면 Playwright 추출
    3. 구조화된 성분 목록으로 ChatRequest 생성
    4. 기존 LangGraph RAG 실행
    5. 상품 분석 결과와 캐시 정보 반환
    """

    selected_option_key = (
        request.internal_option_key or request.option_id
    ).strip()
    if (
        request.internal_option_key
        and request.option_id
        and request.internal_option_key.strip()
        != request.option_id.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "internal_option_key와 option_id가 "
                "서로 일치하지 않습니다."
            ),
        )

    # 1. 상품 전성분을 캐시 또는 Extractor로 확보한다.
    try:
        if selected_option_key:
            resolution = (
                ingredient_cache_service.get_cached_option(
                    product=request.product,
                    internal_option_key=selected_option_key,
                )
            )
        else:
            resolution = (
                ingredient_cache_service.get_or_extract(
                    product=request.product,
                    option_id="",
                    option_name=None,
                )
            )

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "상품 전성분 처리 중 오류가 "
                f"발생했습니다: {error}"
            ),
        ) from error

    # 2. 전성분 확보에 실패한 경우에는
    # 식약처 RAG를 실행할 수 없다.
    if not resolution.result.extraction_success:
        raise HTTPException(
            status_code=502,
            detail=(
                resolution.result.error_message
                or "상품 전성분 확보에 실패했습니다."
            ),
        )

    # 3. 성분 목록이 비어 있으면 RAG를 진행할 수 없다.
    if not resolution.result.ingredients:
        raise HTTPException(
            status_code=502,
            detail=(
                "상품의 전성분 목록이 비어 있어 "
                "성분 분석을 진행할 수 없습니다."
            ),
        )

    # 4. 구조화된 성분 목록을 그대로 ChatRequest에 전달한다.
    # 문자열로 합쳤다가 다시 split하면 성분명 내부의 쉼표/슬래시가
    # 구분자로 잘못 처리될 수 있으므로 list[str]을 유지한다.
    # LangGraph 쪽 metadata.ingredient_count도 동일한
    # resolve_ingredients() 결과를 사용하므로 여기서 미리 계산해
    # 응답의 ingredient_count와 항상 일치시킨다.
    resolved_ingredients = resolve_ingredients(
        ingredients=list(resolution.result.ingredients),
        ingredient_list=None,
    )

    # 5. 확보한 전성분을 식약처 규제 데이터와
    # exact match로 비교한다.
    try:
        regulation_repository = (
            get_mfds_regulation_repository()
        )

        regulation_matches = (
            regulation_repository
            .find_for_ingredients(
                resolved_ingredients
            )
        )

        regulations = build_product_regulations(
            regulation_matches
        )

        regulation_context = (
            build_regulation_context(
                regulations
            )
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "식약처 규제 데이터 조회 중 "
                f"오류가 발생했습니다: {error}"
            ),
        ) from error

    # 6. 확보한 전성분을 식약처 향료 알레르기
    # 표시 대상 목록과 exact match로 비교한다.
    try:
        allergen_repository = (
            get_mfds_fragrance_allergen_repository()
        )

        allergen_matches = (
            allergen_repository
            .find_for_ingredients(
                resolved_ingredients
            )
        )

        allergens = build_product_allergens(
            allergen_matches
        )

        allergen_context = (
            build_allergen_context(
                allergens
            )
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "식약처 향료 알레르겐 데이터 조회 중 "
                f"오류가 발생했습니다: {error}"
            ),
        ) from error

    rag_request = ChatRequest(
        question=request.question,
        skin_type=request.skin_type,
        skin_profile=request.skin_profile,
        ingredients=resolved_ingredients,
        current_routine=request.current_routine,
        regulation_context=regulation_context,
        allergen_context=allergen_context,
    )

    # 7. 기존 LangGraph와 LangSmith tracing 흐름을
    # 그대로 재사용한다.
    try:
        final_state = invoke_derma_rag(
            rag_request,
            api_endpoint="/products/analyze",
        )

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "식약처 성분 RAG 분석 중 오류가 "
                f"발생했습니다: {error}"
            ),
        ) from error

    # 8. 최종 RAG 결과와 캐시 상태를 함께 반환한다.
    return ProductAnalysisResponse(
        product=request.product,
        answer=final_state.get(
            "answer",
            "",
        ),
        sources=final_state.get(
            "sources",
            [],
        ),
        metadata=final_state.get(
            "metadata",
            {},
        ),
        ingredient_count=len(
            resolved_ingredients
        ),
        skin_compatibility=final_state.get(
            "skin_compatibility",
            [],
        ),
        selected_option_key=(
            selected_option_key or None
        ),
        selected_option_name=(
            request.option_name
            if selected_option_key
            else None
        ),
        option_specific_ingredients=bool(
            selected_option_key
        ),
        regulation_count=len(
            regulations
        ),
        regulations=regulations,
        allergen_count=len(
            allergens
        ),
        allergens=allergens,
        cache_hit=resolution.cache_hit,
        cache_expired=(
            resolution.cache_expired
        ),
        extraction_performed=(
            resolution.extraction_performed
        ),
    )

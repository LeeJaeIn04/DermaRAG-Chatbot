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
from app.products.errors import (
    ProductCollectionRetryLaterError,
    ProductDataUnavailableError,
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
from app.products.parser_debug import (
    ParserDebugResponse,
    ParserDebugUnavailableError,
    build_parser_debug_response,
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
    allow_methods=["*"],
    allow_headers=["*"],
)


# SQLAlchemy 모델에 정의된 테이블을
# 실제 SQLite 데이터베이스에 생성한다.
#
# 이미 테이블이 있으면 다시 만들지 않는다.
create_database_tables()


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


# 검색어 캐시 HIT는 DB에서 반환하고, MISS일 때만 설정에 따라
# 상품 검색 provider를 한 번 실행해 기본 정보와 검색 관계를 저장한다.
product_search_service = ProductSearchService(
    provider=OliveYoungProductSearchProvider(
        headless=settings.playwright_headless,
        timeout_ms=settings.product_playwright_timeout_ms,
        deadline_ms=settings.product_playwright_deadline_ms,
        max_attempts=settings.product_playwright_max_attempts,
    ),
    repository=ingredient_repository,
    search_cache_ttl_minutes=settings.product_search_cache_ttl_minutes,
    cache_only_mode=settings.product_cache_only_mode,
    live_collection_enabled=settings.product_live_collection_enabled,
)


# 올리브영 상품 페이지에서
# 실제 전성분을 가져오는 추출기다.
#
# 운영에서는 smoke test 확인 후 PLAYWRIGHT_HEADLESS=true로
# 실행한다. 실패 시 자동으로 headed 모드로 전환하지 않는다.
ingredient_extractor = (
    OliveYoungIngredientExtractor(
        headless=settings.playwright_headless,
        timeout_ms=settings.product_playwright_timeout_ms,
        deadline_ms=settings.product_playwright_deadline_ms,
        max_attempts=settings.product_playwright_max_attempts,
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
        ttl_days=settings.product_ingredient_ttl_days,
        cache_only_mode=settings.product_cache_only_mode,
        live_collection_enabled=settings.product_live_collection_enabled,
        option_level_cache_enabled=(
            settings.product_option_level_cache_enabled
        ),
    )
)

product_option_extractor = (
    OliveYoungProductOptionExtractor(
        ingredient_extractor=ingredient_extractor,
        headless=settings.playwright_headless,
        timeout_ms=settings.product_playwright_timeout_ms,
        deadline_ms=settings.product_playwright_deadline_ms,
        max_attempts=settings.product_playwright_max_attempts,
    )
)

product_option_service = ProductOptionService(
    extractor=product_option_extractor,
    cache_service=ingredient_cache_service,
    retry_base_seconds=settings.product_collection_retry_base_seconds,
    retry_max_seconds=settings.product_collection_retry_max_seconds,
    shadow_observation_enabled=(
        settings.product_shadow_observation_enabled
    ),
    selected_parser_result_enabled=(
        settings.product_selected_parser_result_enabled
    ),
)


PRODUCT_OPTION_UNAVAILABLE_MESSAGE = (
    "현재 이 상품의 옵션별 전성분 정보를 정확히 확인할 수 없습니다. "
    "다른 상품을 선택해 주세요."
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

    try:
        option_preparation = (
            product_option_service.prepare_product(
                selected_product
            )
        )
    except (
        ProductDataUnavailableError,
        ProductCollectionRetryLaterError,
    ) as error:
        raise HTTPException(
            status_code=409,
            detail={"code": error.code, "message": error.public_message},
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "상품 옵션과 전성분을 준비하지 못했습니다."
            ),
        ) from error

    if option_preparation.can_analyze:
        next_action = get_next_action(selected_product.category)
        # option_preparation.status는 내부 값(ready/not_applicable/
        # mapping_failed)이라 그대로 API의 option_status Literal에
        # 못 들어가는 경우가 있다(partial일 때 status는 여전히
        # "mapping_failed"다) - collection_status가 partial이면
        # option_status도 partial로 노출한다.
        if option_preparation.collection_status == "partial":
            public_option_status = "partial"
        else:
            public_option_status = option_preparation.status
        public_options = option_preparation.options
        public_option_error = None
    else:
        next_action = "product_data_unavailable"
        public_option_status = "unavailable"
        public_options = []
        public_option_error = PRODUCT_OPTION_UNAVAILABLE_MESSAGE

    return ProductSelectionResponse(
        selected_product=selected_product,
        next_action=next_action,
        requires_option_selection=(
            option_preparation.requires_option_selection
        ),
        options=public_options,
        can_analyze=option_preparation.can_analyze,
        option_status=public_option_status,
        option_error=public_option_error,
        collection_status=option_preparation.collection_status,
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

    except ProductDataUnavailableError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": error.code, "message": error.public_message},
        ) from error
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
            detail="전성분 처리 중 서버 오류가 발생했습니다.",
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

    except ProductDataUnavailableError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": error.code, "message": error.public_message},
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail="상품 전성분 처리 중 오류가 발생했습니다.",
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


@app.get(
    "/products/{product_id}/parser-debug",
    response_model=ParserDebugResponse,
    summary="[dev-only] production/shadow option parser 비교 진단",
)
def get_parser_debug(
    product_id: str,
) -> ParserDebugResponse:
    """
    production parser(parse_option_full_sections)와 shadow
    parser(shadow_parse_option_ingredient_sections)의 구조
    판정·매핑 결과를 나란히 비교하는 읽기 전용 진단 endpoint다.

    ENVIRONMENT=development일 때만 동작한다. DB 캐시나 수집
    상태(ready 판정, parser_version, collection queue 등)는
    절대 변경하지 않으며, 전성분 원문이나 전체 성분 목록도
    반환하지 않는다.
    """

    if settings.environment != "development":
        raise HTTPException(
            status_code=404,
            detail="Not Found",
        )

    try:
        return build_parser_debug_response(
            product_id,
            repository=ingredient_repository,
            option_extractor=product_option_extractor,
        )
    except ParserDebugUnavailableError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

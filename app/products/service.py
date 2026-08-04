from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from app.products.models import (
    ProductCandidate,
    ProductSearchMetadata,
    ProductSearchResult,
    ProductIngredientResult,
)
from app.products.providers.base import (
    ProductSearchProvider,
)
from app.products.classifier import (
    classify_product_category,
)

from app.products.ingredient_extractors import (
    IngredientExtractor,
)
from app.products.concurrency import KeyedLockPool
from app.products.repositories import ProductIngredientRepository
from app.products.product_name_normalization import normalize_product_name


def normalize_product_search_query(value: str) -> str:
    return normalize_product_name(value)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

class ProductSearchService:
    def __init__(
        self,
        provider: ProductSearchProvider,
        ingredient_extractor: (
            IngredientExtractor | None
        ) = None,
        repository: ProductIngredientRepository | None = None,
        search_cache_ttl_minutes: int = 1_440,
        cache_only_mode: bool = False,
        live_collection_enabled: bool = True,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if search_cache_ttl_minutes <= 0:
            raise ValueError("search_cache_ttl_minutes는 1 이상이어야 합니다.")
        self.provider = provider
        self.ingredient_extractor = ingredient_extractor
        self.repository = repository
        self.search_cache_ttl_minutes = search_cache_ttl_minutes
        self.cache_only_mode = cache_only_mode
        self.live_collection_enabled = live_collection_enabled
        self.clock = clock or utc_now
        self._search_locks = KeyedLockPool()
        self._last_candidates: list[ProductCandidate] = []

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> ProductSearchResult:          
        display_query = query.strip()
        normalized_query = normalize_product_search_query(query)

        if not normalized_query:
            raise ValueError(
                "상품 검색어는 비어 있을 수 없습니다."
            )

        normalized_limit = max(
            1,
            min(limit, 10),
        )

        if self.repository is not None:
            cached = self.repository.get_cached_search(
                normalized_query,
                now=self.clock(),
            )
            if cached is not None:
                return self._search_result(
                    display_query,
                    list(cached.products)[:normalized_limit],
                    provider="sqlite_search_cache",
                    cache_hit=True,
                )
            search_stored = getattr(
                self.repository, "search_products_by_text", None
            )
            stored_products = (
                search_stored(
                    display_query,
                    now=self.clock(),
                    limit=10,
                )
                if search_stored is not None
                else []
            )
            if stored_products:
                now = self.clock()
                saved = self.repository.save_search_results(
                    normalized_query,
                    stored_products,
                    searched_at=now,
                    expires_at=now
                    + timedelta(minutes=self.search_cache_ttl_minutes),
                )
                return self._search_result(
                    display_query,
                    list(saved.products)[:normalized_limit],
                    provider="sqlite_product_cache",
                    cache_hit=True,
                )
            if self.cache_only_mode or not self.live_collection_enabled:
                return self._search_result(
                    display_query,
                    [],
                    provider="sqlite_search_cache",
                    cache_hit=False,
                )

            with self._search_locks.acquire(normalized_query):
                cached = self.repository.get_cached_search(
                    normalized_query,
                    now=self.clock(),
                )
                if cached is not None:
                    return self._search_result(
                        display_query,
                        list(cached.products)[:normalized_limit],
                        provider="sqlite_search_cache",
                        cache_hit=True,
                    )
                stored_products = (
                    search_stored(
                        display_query,
                        now=self.clock(),
                        limit=10,
                    )
                    if search_stored is not None
                    else []
                )
                if stored_products:
                    now = self.clock()
                    saved = self.repository.save_search_results(
                        normalized_query,
                        stored_products,
                        searched_at=now,
                        expires_at=now
                        + timedelta(minutes=self.search_cache_ttl_minutes),
                    )
                    return self._search_result(
                        display_query,
                        list(saved.products)[:normalized_limit],
                        provider="sqlite_product_cache",
                        cache_hit=True,
                    )
                products = self.provider.search_products(
                    query=display_query,
                    limit=10,
                )
                products = self._classify_products(products)
                now = self.clock()
                saved = self.repository.save_search_results(
                    normalized_query,
                    products,
                    searched_at=now,
                    expires_at=now
                    + timedelta(minutes=self.search_cache_ttl_minutes),
                )
                return self._search_result(
                    display_query,
                    list(saved.products)[:normalized_limit],
                    provider=self.provider.provider_name,
                    cache_hit=False,
                )

        products = self.provider.search_products(
            query=display_query,
            limit=normalized_limit,
        )
        products = self._classify_products(products)
        return self._search_result(
            display_query,
            products,
            provider=self.provider.provider_name,
            cache_hit=False,
        )

    @staticmethod
    def _classify_products(
        products: list[ProductCandidate],
    ) -> list[ProductCandidate]:

        classified_products: list[ProductCandidate] = []

        for product in products:
            # Provider가 이미 신뢰할 수 있는 category를 넣었다면
            # 그 값을 그대로 유지한다.
            if product.category != "unknown":
                classified_products.append(product)
                continue

            # category가 unknown일 때만 공통 분류기를 적용한다.
            classified_category = classify_product_category(
                product_name=product.product_name,
                category_path=product.category_path,
            )

            # Pydantic 모델을 직접 변경하지 않고
            # category만 갱신한 복사본을 만든다.
            classified_product = product.model_copy(
                update={
                    "category": classified_category,
                }
            )

            classified_products.append(classified_product)

        return classified_products

    def _search_result(
        self,
        query: str,
        products: list[ProductCandidate],
        *,
        provider: str,
        cache_hit: bool,
    ) -> ProductSearchResult:

        # extract_product_ingredients()가 product_id만으로
        # 상품 URL을 찾을 수 있도록 직전 검색 결과를 기억해둔다.
        self._last_candidates = products

        return ProductSearchResult(
            query=query,
            products=products,
            metadata=ProductSearchMetadata(
                provider=provider,
                result_count=len(products),
                search_empty=not bool(products),
                cache_hit=cache_hit,
            ),
        )

    def find_product(
        self,
        product_id: str,
        products: list[ProductCandidate],
    ) -> ProductCandidate | None:

        normalized_product_id = product_id.strip()

        for product in products:
            if product.product_id.strip() == normalized_product_id:
                return product

        return None
    
    def extract_product_ingredients(
        self,
        product_id: str,
    ) -> ProductIngredientResult:
        """
        직전 검색 결과에서 상품을 찾고,
        해당 상품 URL을 이용해 전성분을 추출한다.

        Raises
        ------
        ValueError:
            상품이 후보 목록에 없거나,
            URL 또는 추출기가 준비되지 않은 경우.
        """

        # 직전 검색 결과에서 선택한 상품을 찾는다.
        product = self.find_product(
            product_id=product_id,
            products=self._last_candidates,
        )

        if product is None:
            raise ValueError(
                "선택한 상품이 상품 후보 목록에 없습니다."
            )

        if not product.product_url:
            raise ValueError(
                "선택한 상품에 상세 페이지 URL이 없습니다."
            )

        if self.ingredient_extractor is None:
            raise ValueError(
                "전성분 추출기가 설정되지 않았습니다."
            )

        # 정식 Playwright 추출기에 상품 ID와 URL을 전달한다.
        return self.ingredient_extractor.extract(
            product_id=product.product_id,
            product_url=product.product_url,
        )

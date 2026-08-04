from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence

from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.products.related_models import RelatedProductMatch


@dataclass(frozen=True)
class CachedProductOption:
    option_id: str
    option_name: str
    source_option_id: str | None = None
    raw_option_name: str | None = None
    normalized_name: str | None = None
    image_url: str | None = None
    source_option_names: tuple[str, ...] = ()
    source_option_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CachedProductPreparation:
    status: str
    options: tuple[CachedProductOption, ...] = ()


@dataclass(frozen=True)
class CachedProductSearch:
    products: tuple[ProductCandidate, ...]
    searched_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class ProductCollectionQueueItem:
    product: ProductCandidate
    status: str
    attempt_count: int
    last_attempt_at: datetime | None
    next_retry_at: datetime | None
    attempt_started: bool = False


@dataclass(frozen=True)
class ProductCollectionEntry:
    result: ProductIngredientResult
    option_id: str = ""
    option_name: str | None = None


@dataclass(frozen=True)
class CachedProductIngredients:
    """
    DB에서 조회한 상품 전성분 캐시.

    ProductIngredientResult 외에도 캐시 만료 판단에 필요한
    시간 정보를 함께 가진다.
    """

    product_id: str
    source: str
    product_url: str

    raw_ingredients: str
    ingredients: tuple[str, ...]

    extraction_method: str
    ingredient_hash: str

    extracted_at: datetime
    last_checked_at: datetime
    expires_at: datetime

    option_id: str = ""
    option_name: str | None = None

    def is_expired(
        self,
        now: datetime,
    ) -> bool:
        """
        현재 시각을 기준으로 캐시가 만료됐는지 판단한다.

        DB 내부 시각은 UTC naive datetime으로 통일한다.
        """

        return self.expires_at <= now

    def to_result(
        self,
    ) -> ProductIngredientResult:
        """
        DB 캐시를 기존 API 응답 모델로 변환한다.
        """

        return ProductIngredientResult(
            product_id=self.product_id,
            product_url=self.product_url,
            raw_ingredients=self.raw_ingredients,
            ingredients=list(self.ingredients),
            extraction_method=self.extraction_method,
            extraction_success=True,
            error_message=None,
        )


class ProductIngredientRepository(Protocol):
    """
    상품과 전성분 데이터를 저장하고 조회하는 인터페이스.

    Cache Service는 SQLite 구현에 직접 의존하지 않고
    이 인터페이스만 사용한다.
    """

    def get_cached_ingredients(
        self,
        source: str,
        external_product_id: str,
        option_id: str = "",
    ) -> CachedProductIngredients | None:
        """
        상품과 옵션에 해당하는 전성분 캐시를 조회한다.

        데이터가 없으면 None을 반환한다.
        """
        ...

    def save_ingredients(
        self,
        product: ProductCandidate,
        result: ProductIngredientResult,
        expires_at: datetime,
        option_id: str = "",
        option_name: str | None = None,
    ) -> CachedProductIngredients:
        """
        상품 정보와 전성분 추출 결과를 저장한다.

        같은 상품·옵션의 데이터가 이미 있으면 갱신한다.
        """

        ...

    def get_cached_preparation(
        self,
        source: str,
        external_product_id: str,
        now: datetime,
    ) -> CachedProductPreparation | None:
        """완전하고 유효한 상품 선택 캐시를 반환한다."""
        ...

    def mark_collection_complete(
        self,
        product: ProductCandidate,
        *,
        status: str,
        option_ids: list[str],
        options: list[dict[str, object]],
        expires_at: datetime,
        parser_version: str,
    ) -> None:
        """모든 옵션 저장이 끝난 뒤 완전성 상태를 기록한다."""
        ...

    def save_collection(
        self,
        product: ProductCandidate,
        *,
        entries: Sequence[ProductCollectionEntry],
        status: str,
        options: list[dict[str, object]],
        expires_at: datetime,
        parser_version: str,
    ) -> None:
        """상품의 전체 옵션과 완료 상태를 한 transaction으로 저장한다."""
        ...

    def find_products_by_ingredient(
        self,
        ingredient_name: str,
        limit: int = 10,
    ) -> list[ProductCandidate]:
        """
        특정 성분을 포함한 저장 상품을 조회한다.
        """

        ...

    def find_related_products_by_ingredients(
        self,
        normalized_ingredient_names: Sequence[str],
        *,
        exclude_product_id: int | None = None,
        exclude_source: str | None = None,
        exclude_external_product_id: str | None = None,
        category: str | None = None,
        category_path: str | None = None,
        limit: int = 5,
        include_legacy: bool = False,
    ) -> list[RelatedProductMatch]:
        """완전 수집 상품에서 exact 성분 매칭 결과를 조회한다."""
        ...

    def get_product_candidate(
        self,
        source: str,
        external_product_id: str,
    ) -> ProductCandidate | None:
        """저장된 상품 기본 정보를 조회한다."""
        ...

    def search_complete_products(
        self,
        query: str,
        *,
        now: datetime,
        limit: int = 5,
    ) -> list[ProductCandidate]:
        """캐시 전용 검색을 위해 완전 수집 상품만 조회한다."""
        ...

    def search_products_by_text(
        self,
        query: str,
        *,
        now: datetime,
        limit: int = 10,
    ) -> list[ProductCandidate]:
        """저장된 상품 기본 정보를 이름/브랜드로 검색한다."""
        ...

    def get_cached_search(
        self,
        normalized_query: str,
        *,
        now: datetime,
    ) -> CachedProductSearch | None:
        """유효한 검색어 캐시를 조회한다. 빈 결과 캐시도 구분한다."""
        ...

    def save_search_results(
        self,
        normalized_query: str,
        products: Sequence[ProductCandidate],
        *,
        searched_at: datetime,
        expires_at: datetime,
    ) -> CachedProductSearch:
        """상품 기본 정보와 검색어-상품 관계만 저장한다."""
        ...

    def start_collection_attempt(
        self,
        product: ProductCandidate,
        *,
        now: datetime,
        force: bool = False,
        collecting_lease_timeout_seconds: int = 90,
    ) -> ProductCollectionQueueItem:
        """claim 가능한 항목 또는 stale collecting을 원자적으로 claim한다."""
        ...

    def finish_collection_attempt(
        self,
        product: ProductCandidate,
        *,
        success: bool,
        now: datetime,
        retry_base_seconds: int,
        retry_max_seconds: int,
    ) -> ProductCollectionQueueItem:
        """상세 수집을 complete 또는 backoff가 있는 failed로 종료한다."""
        ...

    def list_collection_queue(
        self,
        *,
        now: datetime,
        limit: int,
        collecting_lease_timeout_seconds: int = 90,
    ) -> list[ProductCollectionQueueItem]:
        """worker가 처리할 pending/failed/stale collecting을 조회한다."""
        ...

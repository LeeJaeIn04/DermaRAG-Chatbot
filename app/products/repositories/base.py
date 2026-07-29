from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)


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

    def find_products_by_ingredient(
        self,
        ingredient_name: str,
        limit: int = 10,
    ) -> list[ProductCandidate]:
        """
        특정 성분을 포함한 저장 상품을 조회한다.
        """

        ...
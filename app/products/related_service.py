from collections.abc import Sequence

from app.products.normalization import normalize_ingredient_name
from app.products.related_models import RelatedProductMatch
from app.products.repositories import ProductIngredientRepository


class RelatedProductService:
    """같은 성분이 포함된 비교 상품 조회 입력을 정규화한다."""

    def __init__(self, repository: ProductIngredientRepository) -> None:
        self.repository = repository

    def find_related_products(
        self,
        ingredient_names: Sequence[str],
        *,
        exclude_product_id: int | None = None,
        exclude_source: str | None = None,
        exclude_external_product_id: str | None = None,
        category: str | None = None,
        category_path: str | None = None,
        limit: int = 5,
        include_legacy: bool = False,
    ) -> list[RelatedProductMatch]:
        if limit <= 0 or limit > 50:
            raise ValueError("limit은 1 이상 50 이하여야 합니다.")

        normalized_names = tuple(
            dict.fromkeys(
                normalized
                for value in ingredient_names
                if (normalized := normalize_ingredient_name(value))
            )
        )
        if not normalized_names:
            return []

        return self.repository.find_related_products_by_ingredients(
            normalized_names,
            exclude_product_id=exclude_product_id,
            exclude_source=exclude_source,
            exclude_external_product_id=exclude_external_product_id,
            category=category,
            category_path=category_path,
            limit=limit,
            include_legacy=include_legacy,
        )

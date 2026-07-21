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

class ProductSearchService:
    def __init__(
        self,
        provider: ProductSearchProvider,
        ingredient_extractor: (
            IngredientExtractor | None
        ) = None,
    ) -> None:
        self.provider = provider
        self.ingredient_extractor = ingredient_extractor
        self._last_candidates: list[ProductCandidate] = []

    def search(
        self,
        query: str,
        limit: int = 5,
    ) -> ProductSearchResult:          
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError(
                "상품 검색어는 비어 있을 수 없습니다."
            )

        normalized_limit = max(
            1,
            min(limit, 10),
        )

        products = self.provider.search_products(
            query=normalized_query,
            limit=normalized_limit,
        )

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

        products = classified_products

        # extract_product_ingredients()가 product_id만으로
        # 상품 URL을 찾을 수 있도록 직전 검색 결과를 기억해둔다.
        self._last_candidates = products

        return ProductSearchResult(
            query=normalized_query,
            products=products,
            metadata=ProductSearchMetadata(
                provider=self.provider.provider_name,
                result_count=len(products),
                search_empty=not bool(products),
                cache_hit=False,
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
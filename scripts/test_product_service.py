import pytest

from app.products.models import ProductIngredientResult
from app.products.providers.mock import (
    MockProductSearchProvider,
)
from app.products.service import ProductSearchService


# MockProductSearchProvider가 반환하는 상품 ID.
# 순수 Mock 상품 2개 + 전성분 추출 검증용 실제 올리브영 상품 1개.
MOCK_SKINCARE_PRODUCT_ID = "MOCK-SKIN-001"
MOCK_COLOR_PRODUCT_ID = "MOCK-COLOR-001"
OLIVEYOUNG_VERIFIED_PRODUCT_ID = "A000000149135"
OLIVEYOUNG_VERIFIED_PRODUCT_URL = (
    "https://www.oliveyoung.co.kr/store/goods/"
    "getGoodsDetail.do?goodsNo=A000000149135"
)

ALL_MOCK_PROVIDER_PRODUCT_IDS = {
    MOCK_SKINCARE_PRODUCT_ID,
    MOCK_COLOR_PRODUCT_ID,
    OLIVEYOUNG_VERIFIED_PRODUCT_ID,
}


class FakeIngredientExtractor:
    """
    실제 Playwright/Chrome을 실행하지 않는 테스트용 추출기.

    호출 인자를 기록해두어, 서비스가 올바른
    product_id/product_url로 추출기를 호출했는지 검증할 수 있다.
    """

    def __init__(
        self,
        result: ProductIngredientResult | None = None,
    ) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def extract(
        self,
        product_id: str,
        product_url: str,
    ) -> ProductIngredientResult:
        self.calls.append((product_id, product_url))

        if self.result is not None:
            return self.result

        return ProductIngredientResult(
            product_id=product_id,
            product_url=product_url,
            raw_ingredients="정제수, 글리세린",
            ingredients=["정제수", "글리세린"],
            extraction_method="fake",
            extraction_success=True,
            error_message=None,
        )


def test_product_search_returns_candidates() -> None:
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
    )

    result = service.search(
        query="라운드랩 선크림",
        limit=5,
    )

    # 검색어가 결과에 그대로 보존되는지 확인한다.
    assert result.query == "라운드랩 선크림"

    # 상품 개수 자체보다 어떤 상품이 반환됐는지를 검증한다.
    # provider에 상품이 추가/삭제돼도 ID 집합만 갱신하면 되도록 한다.
    product_ids = {
        product.product_id for product in result.products
    }
    assert product_ids == ALL_MOCK_PROVIDER_PRODUCT_IDS

    assert len(result.products) == 3
    assert result.metadata.result_count == len(result.products)
    assert result.metadata.search_empty is False


def test_product_search_respects_limit() -> None:
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
    )

    result = service.search(
        query="선크림",
        limit=1,
    )

    assert len(result.products) == 1
    assert result.metadata.result_count == 1


def test_find_product_returns_selected_product() -> None:
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
    )

    result = service.search(
        query="선크림",
        limit=5,
    )

    selected = service.find_product(
        product_id=MOCK_SKINCARE_PRODUCT_ID,
        products=result.products,
    )

    assert selected is not None
    assert selected.category == "skincare"


def test_find_product_returns_none_for_unknown_id() -> None:
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
    )

    result = service.search(
        query="선크림",
        limit=5,
    )

    selected = service.find_product(
        product_id="NOT-FOUND",
        products=result.products,
    )

    assert selected is None


def test_find_product_strips_surrounding_whitespace() -> None:
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
    )

    result = service.search(
        query="선크림",
        limit=5,
    )

    selected = service.find_product(
        product_id=f"  {MOCK_SKINCARE_PRODUCT_ID}  ",
        products=result.products,
    )

    assert selected is not None
    assert selected.product_id == MOCK_SKINCARE_PRODUCT_ID


def test_service_classifies_mock_products() -> None:
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
    )

    result = service.search(
        query="화장품",
        limit=5,
    )

    products_by_id = {
        product.product_id: product
        for product in result.products
    }

    assert products_by_id.keys() == ALL_MOCK_PROVIDER_PRODUCT_IDS

    assert (
        products_by_id[MOCK_SKINCARE_PRODUCT_ID].category
        == "skincare"
    )
    assert (
        products_by_id[MOCK_COLOR_PRODUCT_ID].category
        == "color_makeup"
    )

    # 실제 올리브영 전성분 추출 검증에 쓰이는 상품이므로
    # skincare로 분류되는지 별도로 확인한다.
    assert (
        products_by_id[OLIVEYOUNG_VERIFIED_PRODUCT_ID].category
        == "skincare"
    )


def test_extract_product_ingredients_uses_last_search_candidates() -> None:
    fake_extractor = FakeIngredientExtractor()

    service = ProductSearchService(
        provider=MockProductSearchProvider(),
        ingredient_extractor=fake_extractor,
    )

    # /products/search에 해당하는 호출.
    # 이 검색 결과가 서비스 내부에 직전 후보 목록으로 저장돼야 한다.
    service.search(
        query="라운드랩 선크림",
        limit=5,
    )

    # /products/extract-ingredients에 해당하는 호출.
    # product_id만으로 URL을 찾아 추출기를 호출해야 한다.
    result = service.extract_product_ingredients(
        product_id=OLIVEYOUNG_VERIFIED_PRODUCT_ID,
    )

    assert result.extraction_success is True
    assert result.product_id == OLIVEYOUNG_VERIFIED_PRODUCT_ID
    assert result.ingredients

    assert fake_extractor.calls == [
        (
            OLIVEYOUNG_VERIFIED_PRODUCT_ID,
            OLIVEYOUNG_VERIFIED_PRODUCT_URL,
        )
    ]


def test_extract_product_ingredients_raises_for_unknown_product() -> None:
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
        ingredient_extractor=FakeIngredientExtractor(),
    )

    service.search(
        query="선크림",
        limit=5,
    )

    with pytest.raises(ValueError):
        service.extract_product_ingredients(
            product_id="NOT-FOUND",
        )


def test_extract_product_ingredients_raises_without_prior_search() -> None:
    # search()를 한 번도 호출하지 않으면 직전 후보 목록이 비어 있으므로
    # 알려진 product_id라도 상품을 찾을 수 없어야 한다.
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
        ingredient_extractor=FakeIngredientExtractor(),
    )

    with pytest.raises(ValueError):
        service.extract_product_ingredients(
            product_id=OLIVEYOUNG_VERIFIED_PRODUCT_ID,
        )


def test_extract_product_ingredients_raises_when_extractor_missing() -> None:
    # ingredient_extractor를 넘기지 않으면
    # 상품은 찾더라도 추출을 시도하지 않고 실패해야 한다.
    service = ProductSearchService(
        provider=MockProductSearchProvider(),
    )

    service.search(
        query="선크림",
        limit=5,
    )

    with pytest.raises(ValueError):
        service.extract_product_ingredients(
            product_id=OLIVEYOUNG_VERIFIED_PRODUCT_ID,
        )
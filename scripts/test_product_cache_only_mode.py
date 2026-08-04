import pytest
from datetime import datetime
from fastapi import HTTPException

from app import main
from app.products.errors import ProductDataUnavailableError
from app.products.models import ProductCandidate
from app.products.repositories import CachedProductSearch
from app.schemas import ProductSearchRequest, ProductSelectionRequest
from app.products.option_models import ProductOptionPreparationResult


def product() -> ProductCandidate:
    return ProductCandidate(
        product_id="CACHE-1",
        product_name="합성 캐시 상품",
        category="skincare",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=CACHE-1"
        ),
    )


def test_cache_only_search_uses_sqlite_without_live_provider(monkeypatch) -> None:
    calls = []

    def cached_search(query, *, now):
        calls.append(query)
        return CachedProductSearch(
            products=(product(),),
            searched_at=datetime(2026, 8, 4),
            expires_at=datetime(2026, 8, 5),
        )

    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_search",
        cached_search,
    )
    monkeypatch.setattr(main.product_search_service, "cache_only_mode", True)
    monkeypatch.setattr(
        main.product_search_service, "live_collection_enabled", False
    )
    response = main.search_products(ProductSearchRequest(query="합성", limit=5))
    assert response.metadata.provider == "sqlite_search_cache"
    assert response.metadata.cache_hit is True
    assert calls == ["합성"]


def test_cache_only_select_miss_returns_public_domain_error(monkeypatch) -> None:
    def unavailable(_product):
        raise ProductDataUnavailableError()

    monkeypatch.setattr(
        main.product_option_service, "prepare_product", unavailable
    )
    with pytest.raises(HTTPException) as captured:
        main.select_product(
            ProductSelectionRequest(
                product_id="CACHE-1", products=[product()]
            )
        )
    assert captured.value.status_code == 409
    assert captured.value.detail["code"] == "PRODUCT_NOT_PREFETCHED"
    public_text = captured.value.detail["message"].lower()
    assert "playwright" not in public_text
    assert "headless" not in public_text
    assert "browser" not in public_text


def test_select_collects_only_the_chosen_product(monkeypatch) -> None:
    products = [
        product(),
        product().model_copy(
            update={"product_id": "CACHE-2", "product_name": "두 번째 합성 상품"}
        ),
    ]
    calls = []

    def prepare(selected):
        calls.append(selected.product_id)
        return ProductOptionPreparationResult(
            requires_option_selection=False,
            can_analyze=True,
            status="not_applicable",
        )

    monkeypatch.setattr(main.product_option_service, "prepare_product", prepare)
    response = main.select_product(
        ProductSelectionRequest(product_id="CACHE-2", products=products)
    )
    assert response.selected_product.product_id == "CACHE-2"
    assert calls == ["CACHE-2"]

from datetime import datetime, timedelta
from threading import Event, Thread

from app.products.models import ProductCandidate
from app.products.repositories import CachedProductSearch
from app.products.service import ProductSearchService


NOW = datetime(2026, 8, 4, 12, 0)


def product() -> ProductCandidate:
    return ProductCandidate(
        product_id="SEARCH-1",
        product_name="합성 검색 상품",
        category="skincare",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=SEARCH-1"
        ),
    )


class FakeSearchRepository:
    def __init__(self, cached=None) -> None:
        self.cached = cached
        self.get_calls = 0
        self.save_calls = 0

    def get_cached_search(self, normalized_query, *, now):
        self.get_calls += 1
        return self.cached

    def save_search_results(
        self, normalized_query, products, *, searched_at, expires_at
    ):
        self.save_calls += 1
        self.cached = CachedProductSearch(
            products=tuple(products),
            searched_at=searched_at,
            expires_at=expires_at,
        )
        return self.cached


class FakeProvider:
    provider_name = "fake_live"

    def __init__(self) -> None:
        self.calls = 0

    def search_products(self, query, limit):
        self.calls += 1
        return [product()]


def cached() -> CachedProductSearch:
    return CachedProductSearch(
        products=(product(),),
        searched_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )


def test_search_db_hit_never_calls_provider() -> None:
    repository = FakeSearchRepository(cached())
    provider = FakeProvider()
    result = ProductSearchService(
        provider,
        repository=repository,
        clock=lambda: NOW,
    ).search("  합성   검색  ")
    assert result.metadata.cache_hit is True
    assert result.metadata.provider == "sqlite_search_cache"
    assert provider.calls == 0


def test_stored_product_text_hit_builds_query_cache_without_provider() -> None:
    class StoredProductRepository(FakeSearchRepository):
        def search_products_by_text(
            self, query, *, now, limit
        ):
            return [product()]

    repository = StoredProductRepository()
    provider = FakeProvider()
    result = ProductSearchService(
        provider, repository=repository, clock=lambda: NOW
    ).search("합성 검색")
    assert result.metadata.provider == "sqlite_product_cache"
    assert result.metadata.cache_hit is True
    assert provider.calls == 0
    assert repository.save_calls == 1


def test_search_miss_calls_provider_once_and_next_request_uses_db() -> None:
    repository = FakeSearchRepository()
    provider = FakeProvider()
    service = ProductSearchService(
        provider,
        repository=repository,
        clock=lambda: NOW,
    )
    first = service.search("합성 검색")
    second = service.search("합성   검색")
    assert first.metadata.cache_hit is False
    assert second.metadata.cache_hit is True
    assert provider.calls == 1
    assert repository.save_calls == 1


def test_cache_only_or_live_disabled_miss_never_calls_provider() -> None:
    for cache_only, live_enabled in ((True, True), (False, False)):
        provider = FakeProvider()
        result = ProductSearchService(
            provider,
            repository=FakeSearchRepository(),
            cache_only_mode=cache_only,
            live_collection_enabled=live_enabled,
            clock=lambda: NOW,
        ).search("없는 검색")
        assert result.products == []
        assert provider.calls == 0


def test_search_never_calls_detail_extractor() -> None:
    class FailingDetailExtractor:
        def extract(self, **kwargs):
            raise AssertionError("검색 단계에서 상세 추출을 호출하면 안 됩니다.")

    service = ProductSearchService(
        FakeProvider(),
        ingredient_extractor=FailingDetailExtractor(),
        repository=FakeSearchRepository(),
        clock=lambda: NOW,
    )
    assert service.search("합성").products


def test_concurrent_search_miss_is_single_flight() -> None:
    entered = Event()
    release = Event()

    class BlockingProvider(FakeProvider):
        def search_products(self, query, limit):
            self.calls += 1
            entered.set()
            assert release.wait(timeout=2)
            return [product()]

    repository = FakeSearchRepository()
    provider = BlockingProvider()
    service = ProductSearchService(
        provider, repository=repository, clock=lambda: NOW
    )
    results = []

    first = Thread(target=lambda: results.append(service.search("동시 검색")))
    second = Thread(target=lambda: results.append(service.search("동시   검색")))
    first.start()
    assert entered.wait(timeout=2)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert len(results) == 2
    assert provider.calls == 1
    assert sum(result.metadata.cache_hit for result in results) == 1

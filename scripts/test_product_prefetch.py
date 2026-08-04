import pytest
from pydantic import ValidationError

from app.products.models import ProductCandidate
from app.products.option_models import ProductOptionPreparationResult
from app.products.prefetch import (
    PrefetchProductEntry,
    ProductPrefetchService,
    validate_manifest_entries,
)


URL = (
    "https://www.oliveyoung.co.kr/store/goods/"
    "getGoodsDetail.do?goodsNo=A000000000001"
)


def entry(product_id: str = "A000000000001") -> PrefetchProductEntry:
    return PrefetchProductEntry(
        external_product_id=product_id,
        product_url=URL.replace("A000000000001", product_id),
        label="합성 테스트 상품",
        category="skincare",
    )


class FakeRepository:
    def get_product_candidate(self, source, external_product_id):
        return None


class FakeCache:
    def __init__(self, cached=None) -> None:
        self.cached = cached
        self.get_calls = 0

    def get_cached_preparation(self, product):
        self.get_calls += 1
        return self.cached


class FakeOptionService:
    def __init__(self, cached=None, *, fail=False) -> None:
        self.cache_service = FakeCache(cached)
        self.calls = []
        self.fail = fail

    def prepare_product(self, product, *, force_refresh=False):
        self.calls.append((product, force_refresh))
        if self.fail:
            raise RuntimeError("collection failed")
        return ProductOptionPreparationResult(
            requires_option_selection=False,
            can_analyze=True,
            status="not_applicable",
        )


def cached_result() -> ProductOptionPreparationResult:
    return ProductOptionPreparationResult(
        requires_option_selection=False,
        can_analyze=True,
        status="not_applicable",
    )


def test_complete_cache_hit_skips_collection() -> None:
    option_service = FakeOptionService(cached_result())
    summary = ProductPrefetchService(
        FakeRepository(), option_service
    ).prefetch([entry()])
    assert summary.cache_hit == 1
    assert option_service.calls == []


def test_cache_miss_collects_once() -> None:
    option_service = FakeOptionService()
    summary = ProductPrefetchService(
        FakeRepository(), option_service
    ).prefetch([entry()])
    assert summary.collected == 1
    assert len(option_service.calls) == 1


def test_force_refresh_bypasses_valid_cache() -> None:
    option_service = FakeOptionService(cached_result())
    summary = ProductPrefetchService(
        FakeRepository(), option_service
    ).prefetch([entry()], force_refresh=True)
    assert summary.collected == 1
    assert option_service.calls[0][1] is True


def test_dry_run_never_collects() -> None:
    option_service = FakeOptionService()
    summary = ProductPrefetchService(
        FakeRepository(), option_service
    ).prefetch([entry()], dry_run=True)
    assert summary.skipped == 1
    assert option_service.calls == []


def test_continue_on_error_processes_next_product() -> None:
    option_service = FakeOptionService(fail=True)
    summary = ProductPrefetchService(
        FakeRepository(), option_service
    ).prefetch(
        [entry(), entry("A000000000002")],
        continue_on_error=True,
    )
    assert summary.failed == 2
    assert len(option_service.calls) == 2


def test_manifest_rejects_invalid_source_and_url() -> None:
    with pytest.raises(ValidationError):
        PrefetchProductEntry(
            source="other",
            external_product_id="A000000000001",
            product_url=URL,
            label="합성 테스트 상품",
        )
    with pytest.raises(ValidationError):
        PrefetchProductEntry(
            external_product_id="A000000000001",
            product_url="https://example.com/product",
            label="합성 테스트 상품",
        )


def test_manifest_rejects_empty_and_duplicate_entries() -> None:
    with pytest.raises(ValueError, match="비어"):
        validate_manifest_entries([])
    with pytest.raises(ValueError, match="중복"):
        validate_manifest_entries([entry(), entry()])

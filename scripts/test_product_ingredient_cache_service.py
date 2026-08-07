from datetime import datetime, timedelta
from threading import Event, Thread

from app.products.ingredient_cache_service import (
    ProductIngredientCacheService,
)
from app.products.models import ProductCandidate
from app.products.repositories import (
    CachedProductIngredients,
    CachedProductOption,
    CachedProductPreparation,
    ProductCollectionEntry,
)
from app.products.option_parser import (
    PARSER_VERSION,
    canonicalize_product_options,
    make_product_option,
)
from app.products.models import (
    ProductIngredientResult,
)
from app.products.errors import ProductDataUnavailableError


FIXED_NOW = datetime(
    2026,
    7,
    23,
    12,
    0,
)


def make_product() -> ProductCandidate:
    return ProductCandidate(
        product_id="A000000149135",
        source="oliveyoung",
        brand_name="라운드랩",
        product_name=(
            "자작나무 수분 선크림 50ml"
        ),
        category="skincare",
        category_path=(
            "스킨케어 > 선케어 > 선크림"
        ),
        product_url=(
            "https://www.oliveyoung.co.kr/"
            "store/goods/getGoodsDetail.do"
            "?goodsNo=A000000149135"
        ),
    )


def make_success_result() -> (
    ProductIngredientResult
):
    return ProductIngredientResult(
        product_id="A000000149135",
        product_url=(
            "https://www.oliveyoung.co.kr/"
            "store/goods/getGoodsDetail.do"
            "?goodsNo=A000000149135"
        ),
        raw_ingredients=(
            "정제수, 다이부틸아디페이트, "
            "프로판다이올"
        ),
        ingredients=[
            "정제수",
            "다이부틸아디페이트",
            "프로판다이올",
        ],
        extraction_method="browser_dom",
        extraction_success=True,
        error_message=None,
    )


def make_failure_result() -> (
    ProductIngredientResult
):
    return ProductIngredientResult(
        product_id="A000000149135",
        product_url=(
            "https://www.oliveyoung.co.kr/"
            "store/goods/getGoodsDetail.do"
            "?goodsNo=A000000149135"
        ),
        raw_ingredients="",
        ingredients=[],
        extraction_method="browser_dom",
        extraction_success=False,
        error_message=(
            "전성분 영역을 찾지 못했습니다."
        ),
    )


def make_cached_result(
    expires_at: datetime,
    option_id: str = "",
) -> CachedProductIngredients:
    return CachedProductIngredients(
        product_id="A000000149135",
        source="oliveyoung",
        product_url=(
            "https://www.oliveyoung.co.kr/"
            "store/goods/getGoodsDetail.do"
            "?goodsNo=A000000149135"
        ),
        raw_ingredients=(
            "정제수, 다이부틸아디페이트, "
            "프로판다이올"
        ),
        ingredients=(
            "정제수",
            "다이부틸아디페이트",
            "프로판다이올",
        ),
        extraction_method="browser_dom",
        ingredient_hash="test-hash",
        extracted_at=FIXED_NOW,
        last_checked_at=FIXED_NOW,
        expires_at=expires_at,
        option_id=option_id,
        option_name=None,
    )


class FakeRepository:
    """
    DB를 사용하지 않는 캐시 서비스 테스트용 Repository.
    """

    def __init__(
        self,
        cached: CachedProductIngredients | None = None,
    ) -> None:
        self.cached = cached
        self.get_calls = 0
        self.save_calls = 0
        self.saved_arguments: dict | None = None

    def get_cached_ingredients(
        self,
        source: str,
        external_product_id: str,
        option_id: str = "",
    ) -> CachedProductIngredients | None:
        """
        실제 ProductIngredientRepository와 동일한 이름과
        매개변수 구조를 사용하는 테스트용 조회 메서드.
        """

        self.get_calls += 1
        return self.cached

    def save_ingredients(
        self,
        **kwargs,
    ) -> CachedProductIngredients:
        """
        실제 Repository의 저장 메서드 이름에 맞춘
        테스트용 저장 메서드.
        """

        self.save_calls += 1
        self.saved_arguments = kwargs

        product = kwargs["product"]
        result = kwargs["result"]

        self.cached = CachedProductIngredients(
            product_id=product.product_id,
            source=product.source,
            product_url=product.product_url,
            raw_ingredients=result.raw_ingredients,
            ingredients=tuple(result.ingredients),
            extraction_method=(
                result.extraction_method
            ),
            ingredient_hash="saved-hash",
            extracted_at=FIXED_NOW,
            last_checked_at=FIXED_NOW,
            expires_at=kwargs["expires_at"],
            option_id=kwargs["option_id"],
            option_name=kwargs["option_name"],
        )

        return self.cached


class FakeExtractor:
    """
    실제 Playwright를 실행하지 않는 테스트용 추출기.
    """

    def __init__(
        self,
        result: ProductIngredientResult,
    ) -> None:
        self.result = result
        self.call_count = 0

    def extract(
        self,
        product_id: str,
        product_url: str,
    ) -> ProductIngredientResult:
        self.call_count += 1
        return self.result


def test_extracts_and_saves_when_cache_missing() -> None:
    repository = FakeRepository()
    extractor = FakeExtractor(
        make_success_result()
    )

    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        ttl_days=90,
        clock=lambda: FIXED_NOW,
    )

    resolution = service.get_or_extract(
        product=make_product()
    )

    assert resolution.cache_hit is False
    assert resolution.cache_expired is False
    assert (
        resolution.extraction_performed
        is True
    )
    assert (
        resolution.result.extraction_success
        is True
    )

    assert extractor.call_count == 1
    assert repository.save_calls == 1

    assert (
        repository.saved_arguments[
            "expires_at"
        ]
        == FIXED_NOW + timedelta(days=90)
    )


def test_uses_valid_cache_without_extracting() -> None:
    repository = FakeRepository(
        cached=make_cached_result(
            expires_at=(
                FIXED_NOW
                + timedelta(days=1)
            )
        )
    )

    extractor = FakeExtractor(
        make_success_result()
    )

    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        clock=lambda: FIXED_NOW,
    )

    resolution = service.get_or_extract(
        product=make_product()
    )

    assert resolution.cache_hit is True
    assert resolution.cache_expired is False
    assert (
        resolution.extraction_performed
        is False
    )

    assert extractor.call_count == 0
    assert repository.save_calls == 0

    assert resolution.result.ingredients == [
        "정제수",
        "다이부틸아디페이트",
        "프로판다이올",
    ]


def test_reextracts_when_cache_expired() -> None:
    repository = FakeRepository(
        cached=make_cached_result(
            expires_at=(
                FIXED_NOW
                - timedelta(seconds=1)
            )
        )
    )

    extractor = FakeExtractor(
        make_success_result()
    )

    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        clock=lambda: FIXED_NOW,
    )

    resolution = service.get_or_extract(
        product=make_product()
    )

    assert resolution.cache_hit is False
    assert resolution.cache_expired is True
    assert (
        resolution.extraction_performed
        is True
    )

    assert extractor.call_count == 1
    assert repository.save_calls == 1


def test_does_not_save_failed_extraction() -> None:
    repository = FakeRepository()
    extractor = FakeExtractor(
        make_failure_result()
    )

    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        clock=lambda: FIXED_NOW,
    )

    resolution = service.get_or_extract(
        product=make_product()
    )

    assert (
        resolution.result.extraction_success
        is False
    )
    assert resolution.cache_hit is False
    assert resolution.cache_expired is False
    assert (
        resolution.extraction_performed
        is True
    )

    assert extractor.call_count == 1
    assert repository.save_calls == 0


def test_keeps_expired_cache_when_reextraction_fails() -> None:
    expired_cache = make_cached_result(
        expires_at=(
            FIXED_NOW - timedelta(days=1)
        )
    )

    repository = FakeRepository(
        cached=expired_cache
    )

    extractor = FakeExtractor(
        make_failure_result()
    )

    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        clock=lambda: FIXED_NOW,
    )

    resolution = service.get_or_extract(
        product=make_product()
    )

    assert resolution.cache_expired is True
    assert (
        resolution.result.extraction_success
        is False
    )

    assert repository.save_calls == 0

    # 기존 만료 데이터가 삭제되지 않았는지 확인
    assert repository.cached is expired_cache


def test_separates_cache_by_option_id() -> None:
    repository = FakeRepository()
    extractor = FakeExtractor(
        make_success_result()
    )

    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        clock=lambda: FIXED_NOW,
    )

    resolution = service.get_or_extract(
        product=make_product(),
        option_id="COLOR-01",
        option_name="01 누드 베이지",
    )

    assert (
        resolution.extraction_performed
        is True
    )

    assert (
        repository.saved_arguments[
            "option_id"
        ]
        == "COLOR-01"
    )

    assert (
        repository.saved_arguments[
            "option_name"
        ]
        == "01 누드 베이지"
    )


def test_collection_storage_keeps_canonical_source_options_internal() -> None:
    class CollectionRepository(FakeRepository):
        def save_collection(self, product, **kwargs):
            self.saved_arguments = {"product": product, **kwargs}

    repository = CollectionRepository()
    service = ProductIngredientCacheService(
        repository=repository,
        extractor=FakeExtractor(make_success_result()),
        clock=lambda: FIXED_NOW,
    )
    canonical = canonicalize_product_options(
        [
            make_product_option(
                "[기획] 23호 누카다미아", source_option_id="plan"
            ),
            make_product_option(
                "단품/23 누카다미아", source_option_id="single"
            ),
        ]
    )[0]
    service.store_collection(
        make_product(),
        entries=[
            ProductCollectionEntry(
                result=make_success_result(),
                option_id=canonical.internal_option_key,
                option_name=canonical.option_name,
            )
        ],
        status="ready",
        options=[canonical],
        parser_version="test-canonical",
    )

    assert repository.saved_arguments is not None
    stored_option = repository.saved_arguments["options"][0]
    assert stored_option["option_name"] == "23 누카다미아"
    assert stored_option["source_option_names"] == [
        "[기획] 23호 누카다미아",
        "단품/23 누카다미아",
    ]
    assert stored_option["source_option_ids"] == ["plan", "single"]


def test_legacy_duplicate_option_cache_is_not_reused_as_complete() -> None:
    class LegacyPreparationRepository(FakeRepository):
        def get_cached_preparation(self, **kwargs):
            return CachedProductPreparation(
                status="ready",
                options=(
                    CachedProductOption(
                        option_id="legacy-plan",
                        option_name="[기획] 23호 누카다미아",
                        raw_option_name="[기획] 23호 누카다미아",
                    ),
                    CachedProductOption(
                        option_id="legacy-single",
                        option_name="단품/23 누카다미아",
                        raw_option_name="단품/23 누카다미아",
                    ),
                ),
            )

    service = ProductIngredientCacheService(
        repository=LegacyPreparationRepository(),
        extractor=FakeExtractor(make_success_result()),
        clock=lambda: FIXED_NOW,
    )
    assert service.get_cached_preparation(make_product()) is None


def test_false_ready_previous_parser_version_cache_is_not_reused() -> None:
    for stale_version in (
        "option-sections-v2-header-first",
        "option-sections-v3-structure-guard",
    ):
        class PreviousParserRepository(FakeRepository):
            def get_cached_preparation(self, **kwargs):
                return CachedProductPreparation(
                    status="ready",
                    options=(
                        CachedProductOption(
                            option_id="old-parser-option",
                            option_name="19호",
                            raw_option_name="19호",
                        ),
                    ),
                    parser_version=stale_version,
                )

        service = ProductIngredientCacheService(
            repository=PreviousParserRepository(),
            extractor=FakeExtractor(make_success_result()),
            clock=lambda: FIXED_NOW,
        )

        assert service.get_cached_preparation(make_product()) is None


def test_optionless_cache_is_reused_across_option_parser_versions() -> None:
    class OptionlessRepository(FakeRepository):
        def get_cached_preparation(self, **kwargs):
            return CachedProductPreparation(
                status="not_applicable",
                parser_version="option-sections-v1",
            )

    service = ProductIngredientCacheService(
        repository=OptionlessRepository(),
        extractor=FakeExtractor(make_success_result()),
        clock=lambda: FIXED_NOW,
    )

    cached = service.get_cached_preparation(make_product())
    assert cached is not None
    assert cached.status == "not_applicable"


def test_selected_option_reads_only_its_cache() -> None:
    repository = FakeRepository(
        cached=make_cached_result(
            expires_at=FIXED_NOW + timedelta(days=1),
            option_id="option-key-19",
        )
    )
    extractor = FakeExtractor(make_success_result())
    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        clock=lambda: FIXED_NOW,
    )

    resolution = service.get_cached_option(
        product=make_product(),
        internal_option_key="option-key-19",
    )

    assert resolution.cache_hit is True
    assert resolution.extraction_performed is False
    assert extractor.call_count == 0


def test_missing_selected_option_never_extracts_common_ingredients() -> None:
    repository = FakeRepository()
    extractor = FakeExtractor(make_success_result())
    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        clock=lambda: FIXED_NOW,
    )

    try:
        service.get_cached_option(
            product=make_product(),
            internal_option_key="missing-option",
        )
    except ValueError as error:
        assert "캐시가 없습니다" in str(error)
    else:
        raise AssertionError("ValueError가 발생해야 합니다.")

    assert extractor.call_count == 0
    assert repository.save_calls == 0


def test_stale_false_ready_option_cache_cannot_be_analyzed_directly() -> None:
    for stale_version in (
        "option-sections-v2-header-first",
        "option-sections-v3-structure-guard",
    ):
        class StaleOptionRepository(FakeRepository):
            def get_cached_preparation(self, **kwargs):
                return CachedProductPreparation(
                    status="ready",
                    parser_version=stale_version,
                    options=(
                        CachedProductOption(
                            option_id="stale-option",
                            option_name="코스모스",
                            raw_option_name="코스모스",
                        ),
                    ),
                )

        repository = StaleOptionRepository(
            cached=make_cached_result(
                expires_at=FIXED_NOW + timedelta(days=1),
                option_id="stale-option",
            )
        )
        service = ProductIngredientCacheService(
            repository=repository,
            extractor=FakeExtractor(make_success_result()),
            clock=lambda: FIXED_NOW,
        )

        try:
            service.get_cached_option(make_product(), "stale-option")
        except ValueError as error:
            assert "현재 parser cache가 유효하지 않습니다" in str(error)
        else:
            raise AssertionError("stale option cache를 차단해야 합니다.")


def test_current_ready_option_cache_can_be_analyzed() -> None:
    class CurrentOptionRepository(FakeRepository):
        def get_cached_preparation(self, **kwargs):
            return CachedProductPreparation(
                status="ready",
                parser_version=PARSER_VERSION,
                options=(
                    CachedProductOption(
                        option_id="current-option",
                        option_name="3C 웨딩피치",
                        raw_option_name="3C 웨딩피치",
                    ),
                ),
            )

    repository = CurrentOptionRepository(
        cached=make_cached_result(
            expires_at=FIXED_NOW + timedelta(days=1),
            option_id="current-option",
        )
    )
    service = ProductIngredientCacheService(
        repository=repository,
        extractor=FakeExtractor(make_success_result()),
        clock=lambda: FIXED_NOW,
    )

    resolution = service.get_cached_option(
        make_product(),
        "current-option",
    )

    assert resolution.cache_hit is True
    assert resolution.result.ingredients


def test_rejects_invalid_ttl() -> None:
    repository = FakeRepository()
    extractor = FakeExtractor(
        make_success_result()
    )

    try:
        ProductIngredientCacheService(
            repository=repository,
            extractor=extractor,
            ttl_days=0,
        )
    except ValueError as error:
        assert "ttl_days" in str(error)
    else:
        raise AssertionError(
            "ValueError가 발생해야 합니다."
        )


def test_concurrent_misses_run_extractor_once() -> None:
    repository = FakeRepository()
    started = Event()
    release = Event()

    class BlockingExtractor(FakeExtractor):
        def extract(self, product_id: str, product_url: str):
            self.call_count += 1
            started.set()
            assert release.wait(timeout=2)
            return self.result

    extractor = BlockingExtractor(make_success_result())
    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        clock=lambda: FIXED_NOW,
    )
    results = []

    def resolve() -> None:
        results.append(service.get_or_extract(make_product()))

    first = Thread(target=resolve)
    second = Thread(target=resolve)
    first.start()
    assert started.wait(timeout=2)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert len(results) == 2
    assert extractor.call_count == 1
    assert sum(result.extraction_performed for result in results) == 1


def test_cache_only_miss_never_runs_extractor() -> None:
    repository = FakeRepository()
    extractor = FakeExtractor(make_success_result())
    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        cache_only_mode=True,
        live_collection_enabled=False,
        clock=lambda: FIXED_NOW,
    )
    try:
        service.get_or_extract(make_product())
    except ProductDataUnavailableError as error:
        assert error.code == "PRODUCT_NOT_PREFETCHED"
    else:
        raise AssertionError("ProductDataUnavailableError가 필요합니다.")
    assert extractor.call_count == 0


def test_cache_only_hit_still_returns_without_extractor() -> None:
    repository = FakeRepository(
        cached=make_cached_result(FIXED_NOW + timedelta(days=1))
    )
    extractor = FakeExtractor(make_success_result())
    service = ProductIngredientCacheService(
        repository=repository,
        extractor=extractor,
        cache_only_mode=True,
        live_collection_enabled=False,
        clock=lambda: FIXED_NOW,
    )
    assert service.get_or_extract(make_product()).cache_hit is True
    assert extractor.call_count == 0

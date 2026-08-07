import json
import logging
from pathlib import Path
from threading import Event, Thread

from app.products.models import ProductCandidate
from app.products.option_models import (
    ProductIngredientRawDocument,
    ProductOptionExtractionResult,
    ProductOptionPreparationResult,
)
from app.products.option_parser import (
    PARSER_VERSION,
    make_product_option,
)
from app.products.option_service import ProductOptionService
from app.products.errors import ProductCollectionRetryLaterError
from app.products.repositories import ProductCollectionQueueItem


TARGET_FIXTURE_PATH = Path(__file__).parent / "fixtures" / (
    "product_option_mapping_A000000241210.json"
)


def _product() -> ProductCandidate:
    return ProductCandidate(
        product_id="A000000000001",
        source="oliveyoung",
        product_name="옵션 테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000000001"
        ),
    )


class FakeOptionExtractor:
    def __init__(self, result: ProductOptionExtractionResult) -> None:
        self.result = result
        self.call_count = 0

    def extract(self, product_id: str, product_url: str):
        self.call_count += 1
        return self.result


class FakeCacheService:
    def __init__(self, cached=None) -> None:
        self.saved: list[dict] = []
        self.cached = cached
        self.completed: list[dict] = []
        self.option_cache_snapshots: list[dict] = []

    def get_cached_preparation(self, product):
        return self.cached

    def ensure_live_collection_allowed(self):
        return None

    def store_extracted(self, product, result, **kwargs):
        self.saved.append(
            {
                "product": product,
                "result": result,
                **kwargs,
            }
        )

    def mark_collection_complete(self, product, **kwargs):
        self.completed.append({"product": product, **kwargs})

    def store_collection(self, product, *, entries, **kwargs):
        for entry in entries:
            self.saved.append(
                {
                    "product": product,
                    "result": entry.result,
                    "option_id": entry.option_id,
                    "option_name": entry.option_name,
                }
            )
        self.completed.append({"product": product, **kwargs})

    def store_option_cache_snapshot(self, product, **kwargs):
        self.option_cache_snapshots.append(
            {"product": product, **kwargs}
        )


def _raw_document(raw_text: str) -> ProductIngredientRawDocument:
    return ProductIngredientRawDocument(
        source="oliveyoung",
        product_id="A000000000001",
        raw_text=raw_text,
        parser_version=PARSER_VERSION,
    )


def test_optionless_product_keeps_common_ingredient_flow() -> None:
    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="no_options",
                raw_document=_raw_document(
                    "정제수, 글리세린, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.status == "not_applicable"
    assert result.requires_option_selection is False
    assert result.can_analyze is True
    assert cache.saved[0].get("option_id", "") == ""


def test_romand_no_option_product_keeps_common_ingredient_flow() -> None:
    """롬앤 등 옵션 필터가 없는 상품은 기존 공통 전성분 흐름을 유지해야 한다."""

    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="no_options",
                raw_document=_raw_document(
                    "정제수, 다이메티콘, 글리세린, 나이아신아마이드, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.status == "not_applicable"
    assert result.requires_option_selection is False
    assert result.can_analyze is True
    assert cache.saved[0].get("option_id", "") == ""
    assert cache.saved[0]["result"].ingredients == [
        "정제수",
        "다이메티콘",
        "글리세린",
        "나이아신아마이드",
        "향료",
    ]


def test_partial_option_mapping_is_not_marked_complete(caplog) -> None:
    caplog.set_level(logging.WARNING)
    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[
                    make_product_option("19호"),
                    make_product_option("21호"),
                ],
                raw_document=_raw_document(
                    "[19호] 정제수, 글리세린, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    # Step 4: partial(19호만 ready)이라 status는 여전히
    # "mapping_failed"지만, collection_status=partial이면 ready 옵션은
    # 분석 가능해야 하므로 can_analyze는 True로 바뀐다. legacy 저장
    # (cache.saved/completed)은 이전과 동일하게 여전히 비어 있다 -
    # 100% matched가 아니면 legacy cache에는 절대 쓰지 않는다는 기존
    # 정책은 그대로다.
    assert result.status == "mapping_failed"
    assert result.collection_status == "partial"
    assert result.can_analyze is True
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.model_dump() == {
        "collected_option_count": 2,
        "matched_count": 1,
        "unmatched_count": 1,
        "ambiguous_count": 0,
        "unsupported_count": 0,
        "collected_raw_option_count": 2,
        "canonical_option_count": 2,
        "merged_duplicate_count": 0,
        "matched_canonical_count": 1,
        "unmatched_canonical_count": 1,
        "duplicate_header_count": 0,
    }
    assert "mapping_diagnostics" not in result.model_dump()
    assert cache.saved == []
    assert cache.completed == []
    assert "raw=2" in caplog.text
    assert "canonical=2" in caplog.text
    assert "matched=1" in caplog.text
    assert "정제수" not in caplog.text

    options_by_name = {option.option_name: option for option in result.options}
    assert options_by_name["19"].status == "ready"
    assert options_by_name["19"].analysis_available is True
    assert options_by_name["21"].status == "unmapped"
    assert options_by_name["21"].analysis_available is False


def test_partial_repeated_full_labels_never_store_ready_entries() -> None:
    cache = FakeCacheService()
    body = "정제수, 글리세린, 다이메티콘, 실리카, 토코페롤"
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[
                    make_product_option(name)
                    for name in (
                        "01 로즈",
                        "02 피치",
                        "03 베이지",
                        "04 코랄",
                    )
                ],
                raw_document=_raw_document(
                    " ".join(
                        (
                            f"01 로즈 {body}",
                            f"02 피치 {body}",
                            f"03 베이지 {body}",
                        )
                    )
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    # Step 4: 3/4 옵션이 ready인 partial이므로 can_analyze는 True고
    # 4개 옵션 모두(ready 3 + non-ready 1) 응답에 남는다. legacy
    # cache 저장(엄격히 100% matched만 허용)은 여전히 일어나지 않는다
    # - 이름 그대로 "ready entries를 저장하지 않는다."
    assert result.status == "mapping_failed"
    assert result.collection_status == "partial"
    assert result.can_analyze is True
    assert len(result.options) == 4
    ready_names = {
        option.option_name
        for option in result.options
        if option.analysis_available
    }
    assert ready_names == {"01 로즈", "02 피치", "03 베이지"}
    non_ready = [
        option for option in result.options if not option.analysis_available
    ]
    assert len(non_ready) == 1
    assert non_ready[0].option_name == "04 코랄"
    assert non_ready[0].status != "ready"
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.matched_count == 3
    assert result.mapping_diagnostics.unmatched_count == 1
    assert cache.saved == []
    assert cache.completed == []


def test_all_mapping_failures_block_analysis() -> None:
    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[make_product_option("21호")],
                raw_document=_raw_document(
                    "[19호] 정제수, 글리세린, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.status == "mapping_failed"
    assert result.can_analyze is False
    assert result.options == []
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.matched_count == 0
    assert result.mapping_diagnostics.unmatched_count == 1
    assert cache.saved == []


def test_failed_collection_status_blocks_analysis_for_every_option() -> None:
    """Step 4: collection_status가 "failed"(ready 옵션 0개)면
    can_analyze는 False이고, 응답에 담긴 옵션이 있다면 그 전부
    analysis_available도 False여야 한다."""

    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[
                    make_product_option("19호"),
                    make_product_option("21호"),
                ],
                raw_document=_raw_document(
                    "[22호] 정제수, 글리세린, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.collection_status == "failed"
    assert result.can_analyze is False
    assert result.options == []
    assert all(not option.analysis_available for option in result.options)


def test_target_fixture_reports_mapping_diagnostic_counts() -> None:
    fixture = json.loads(TARGET_FIXTURE_PATH.read_text(encoding="utf-8"))
    result = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[
                    make_product_option(name)
                    for name in fixture["options"]
                ],
                raw_document=_raw_document(
                    "\n".join(fixture["raw_sections"])
                ),
            )
        ),
        cache_service=FakeCacheService(),
    ).prepare_product(_product())

    assert result.status == "mapping_failed"
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.model_dump() == {
        "collected_option_count": 4,
        "matched_count": 2,
        "unmatched_count": 1,
        "ambiguous_count": 0,
        "unsupported_count": 0,
        "collected_raw_option_count": 4,
        "canonical_option_count": 3,
        "merged_duplicate_count": 1,
        "matched_canonical_count": 2,
        "unmatched_canonical_count": 1,
        "duplicate_header_count": 0,
    }


def test_duplicate_raw_options_are_saved_as_one_canonical_option() -> None:
    cache = FakeCacheService()
    raw_options = [
        make_product_option(
            "[기획] 23호 누카다미아", source_option_id="plan"
        ),
        make_product_option(
            "단품/23 누카다미아", source_option_id="single"
        ),
        make_product_option(
            "23호 누카다미아", source_option_id="plain"
        ),
    ]
    result = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=raw_options,
                raw_document=_raw_document(
                    "[23 누카다미아] 정제수, 글리세린"
                ),
            )
        ),
        cache_service=cache,
    ).prepare_product(_product())

    assert result.status == "ready"
    assert result.can_analyze is True
    assert len(result.options) == len(cache.saved) == 1
    canonical = result.options[0]
    assert canonical.option_name == "23 누카다미아"
    assert canonical.source_option_names == [
        option.raw_option_name for option in raw_options
    ]
    assert canonical.source_option_ids == ["plan", "single", "plain"]
    assert "source_option_names" not in canonical.model_dump(mode="json")
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.canonical_option_count == 1
    assert result.mapping_diagnostics.merged_duplicate_count == 2


def test_duplicate_headers_are_ambiguous_and_block_analysis() -> None:
    result = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[make_product_option("23호 누카다미아")],
                raw_document=_raw_document(
                    "[23 누카다미아] 정제수, 글리세린\n"
                    "[23호 누카다미아] 향료, 판테놀"
                ),
            )
        ),
        cache_service=FakeCacheService(),
    ).prepare_product(_product())

    assert result.status == "mapping_failed"
    assert result.options == []
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.ambiguous_count == 1
    assert result.mapping_diagnostics.duplicate_header_count == 1
    assert result.mapping_diagnostics.ambiguous_header_count == 2


def test_orphan_document_section_is_diagnosed_without_blocking_matches() -> None:
    cache = FakeCacheService()
    result = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[make_product_option("[AD][단품] 3C 웨딩피치")],
                raw_document=_raw_document(
                    "[3C 웨딩피치] 정제수, 글리세린, 적색산화철 "
                    "[기존 21호 아이보리] 정제수, 글리세린, 흑색산화철"
                ),
            )
        ),
        cache_service=cache,
    ).prepare_product(_product())

    assert result.status == "ready"
    assert len(result.options) == len(cache.saved) == 1
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.orphan_document_section_count == 1
    assert "흑색산화철" not in cache.saved[0]["result"].ingredients


def test_hierarchical_document_is_unsupported_and_never_cached() -> None:
    cache = FakeCacheService()
    result = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[
                    make_product_option("코스모스"),
                    make_product_option("새턴 베이지"),
                ],
                raw_document=_raw_document(
                    "[코스모스] "
                    "소프트 레이 Soft Ray 마이카, 실리카, 적색산화철 "
                    "라일락 플래시 Lilac Flash 마이카, 실리카, 황색산화철 "
                    "[새턴 베이지] "
                    "문 샌드 Moon Sand 마이카, 실리카, 적색산화철 "
                    "바닐라 샌드 Vanilla Sand 마이카, 실리카, 황색산화철"
                ),
            )
        ),
        cache_service=cache,
    ).prepare_product(_product())

    assert result.status == "mapping_failed"
    assert result.can_analyze is False
    assert result.options == []
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.document_format == (
        "hierarchical_option_internal_sections"
    )
    assert result.mapping_diagnostics.unsupported_count == 2
    assert result.mapping_diagnostics.matched_count == 0
    assert result.mapping_diagnostics.nested_header_count == 4
    assert cache.saved == []
    assert cache.completed == []


def test_malformed_header_is_diagnosed_and_blocks_that_option() -> None:
    result = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[make_product_option("401호 누디스트")],
                raw_document=_raw_document(
                    "[누디스트) 오일, 왁스, 적색산화철"
                ),
            )
        ),
        cache_service=FakeCacheService(),
    ).prepare_product(_product())

    assert result.status == "mapping_failed"
    assert result.mapping_diagnostics is not None
    assert result.mapping_diagnostics.unmatched_count == 1
    assert result.mapping_diagnostics.malformed_header_count == 1


def test_failed_option_log_is_count_and_length_limited(caplog) -> None:
    caplog.set_level(logging.WARNING)
    options = [
        make_product_option(f"{index}호 " + "긴옵션명" * 30)
        for index in range(1, 8)
    ]
    result = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=options,
                raw_document=_raw_document("99 다른색상 정제수, 글리세린"),
            )
        ),
        cache_service=FakeCacheService(),
    ).prepare_product(_product())

    assert result.status == "mapping_failed"
    warning = next(
        record
        for record in caplog.records
        if "mapping incomplete" in record.getMessage()
    )
    failed_names = warning.args[-1]
    assert len(failed_names) == 5
    assert all(len(name) <= 80 for name in failed_names)


def test_all_matched_options_are_saved_as_one_collection() -> None:
    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[
                    make_product_option("19호"),
                    make_product_option("21호"),
                ],
                raw_document=_raw_document(
                    "[19호] 정제수, 글리세린\n[21호] 정제수, 판테놀"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.status == "ready"
    assert len(result.options) == 2
    assert len(cache.saved) == 2
    assert len(cache.completed) == 1


def test_complete_cache_skips_option_extractor() -> None:
    cached = ProductOptionPreparationResult(
        requires_option_selection=False,
        can_analyze=True,
        status="not_applicable",
    )
    cache = FakeCacheService(cached=cached)
    class QueueMustRemainUntouched:
        def start_collection_attempt(self, *args, **kwargs):
            raise AssertionError("complete cache HIT에서 queue claim 금지")

        def finish_collection_attempt(self, *args, **kwargs):
            raise AssertionError("complete cache HIT에서 queue 갱신 금지")

    cache.repository = QueueMustRemainUntouched()
    extractor = FakeOptionExtractor(
        ProductOptionExtractionResult(status="failed")
    )
    service = ProductOptionService(extractor=extractor, cache_service=cache)

    assert service.prepare_product(_product()) == cached
    assert extractor.call_count == 0


def test_concurrent_select_misses_collect_once() -> None:
    started = Event()
    release = Event()

    class BlockingExtractor(FakeOptionExtractor):
        def extract(self, product_id: str, product_url: str):
            self.call_count += 1
            started.set()
            assert release.wait(timeout=2)
            return self.result

    class CompletingCache(FakeCacheService):
        def store_collection(self, product, *, entries, **kwargs):
            super().store_collection(
                product, entries=entries, **kwargs
            )
            self.cached = ProductOptionPreparationResult(
                requires_option_selection=False,
                can_analyze=True,
                status="not_applicable",
            )

    extractor = BlockingExtractor(
        ProductOptionExtractionResult(
            status="no_options",
            raw_document=_raw_document("정제수, 글리세린"),
        )
    )
    cache = CompletingCache()
    service = ProductOptionService(extractor=extractor, cache_service=cache)
    results = []

    def prepare() -> None:
        results.append(service.prepare_product(_product()))

    first = Thread(target=prepare)
    second = Thread(target=prepare)
    first.start()
    assert started.wait(timeout=2)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert len(results) == 2
    assert extractor.call_count == 1


def test_collection_backoff_prevents_immediate_detail_retry() -> None:
    class BackoffRepository:
        def start_collection_attempt(
            self,
            product,
            *,
            now,
            force=False,
            collecting_lease_timeout_seconds,
        ):
            return ProductCollectionQueueItem(
                product=product,
                status="failed",
                attempt_count=1,
                last_attempt_at=now,
                next_retry_at=now,
                attempt_started=False,
            )

    cache = FakeCacheService()
    cache.repository = BackoffRepository()
    cache.current_time = lambda: _raw_document("x").fetched_at.replace(
        tzinfo=None
    )
    extractor = FakeOptionExtractor(
        ProductOptionExtractionResult(status="failed")
    )
    service = ProductOptionService(extractor=extractor, cache_service=cache)

    try:
        service.prepare_product(_product())
    except ProductCollectionRetryLaterError:
        pass
    else:
        raise AssertionError("backoff 중에는 재수집하면 안 됩니다.")
    assert extractor.call_count == 0


def test_valid_collecting_lease_keeps_retry_later_response() -> None:
    class CollectingRepository:
        def start_collection_attempt(
            self,
            product,
            *,
            now,
            force=False,
            collecting_lease_timeout_seconds,
        ):
            assert collecting_lease_timeout_seconds == 90
            return ProductCollectionQueueItem(
                product=product,
                status="collecting",
                attempt_count=1,
                last_attempt_at=now,
                next_retry_at=None,
                attempt_started=False,
            )

    cache = FakeCacheService()
    cache.repository = CollectingRepository()
    cache.current_time = lambda: _raw_document("x").fetched_at.replace(
        tzinfo=None
    )
    extractor = FakeOptionExtractor(
        ProductOptionExtractionResult(status="failed")
    )
    service = ProductOptionService(extractor=extractor, cache_service=cache)

    try:
        service.prepare_product(_product())
    except ProductCollectionRetryLaterError:
        pass
    else:
        raise AssertionError("유효한 collecting lease는 409여야 합니다.")
    assert extractor.call_count == 0

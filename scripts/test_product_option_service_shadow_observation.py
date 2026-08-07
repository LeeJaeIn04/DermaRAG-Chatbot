"""Step 2 selector 관찰 모드 wiring 테스트.

이 모듈은 ProductOptionService._collect_product 안에서 새로 추가된
관찰 전용 경로(shadow 실행 게이팅, production/shadow ParserResult
변환, select_safe_parser_result 호출, 로그 기록)만 검증한다.
실제 shadow 파싱 정확도는 test_shadow_option_parser.py가 이미
검증하므로, 여기서는 대부분 shadow_parse_option_ingredient_sections를
monkeypatch로 대체해 wiring 자체에 집중한다.
"""

import logging

import app.products.option_service as option_service_module
from app.products.models import ProductCandidate
from app.products.option_models import (
    ProductIngredientRawDocument,
    ProductOptionExtractionResult,
)
from app.products.option_parser import (
    PARSER_VERSION,
    IngredientSection,
    OptionSectionMapping,
    ShadowParseResult,
    canonicalize_product_options,
    make_product_option,
)
from app.products.option_service import ProductOptionService


def _product() -> ProductCandidate:
    return ProductCandidate(
        product_id="A000000000002",
        source="oliveyoung",
        product_name="셀렉터 관찰 모드 테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000000002"
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

    def get_cached_preparation(self, product):
        return self.cached

    def ensure_live_collection_allowed(self):
        return None

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
        pass


def _raw_document(raw_text: str) -> ProductIngredientRawDocument:
    return ProductIngredientRawDocument(
        source="oliveyoung",
        product_id="A000000000002",
        raw_text=raw_text,
        parser_version=PARSER_VERSION,
    )


def _partial_extraction() -> ProductOptionExtractionResult:
    """production이 partial(1개 matched, 1개 unmatched)로 끝나는 입력.

    "21호" 헤더가 원문에 전혀 없어 production이 그 옵션을 인식하지
    못하지만, "19호" 성분에는 어떤 오염도 없다."""

    return ProductOptionExtractionResult(
        status="collected",
        options=[
            make_product_option("19호"),
            make_product_option("21호"),
        ],
        raw_document=_raw_document(
            "[19호] 정제수, 글리세린, 향료"
        ),
    )


def _ready_extraction() -> ProductOptionExtractionResult:
    return ProductOptionExtractionResult(
        status="collected",
        options=[make_product_option("19호")],
        raw_document=_raw_document(
            "[19호] 정제수, 글리세린, 다이메티콘, 나이아신아마이드"
        ),
    )


def _fake_shadow_result(
    canonical_options,
    ingredients_by_option_name: dict[str, list[str]],
) -> ShadowParseResult:
    """canonical_options와 동일한 internal_option_key를 쓰는 최소
    ShadowParseResult를 만든다(같은 canonical_options을 순회하므로
    option_id 정책은 production과 항상 같다)."""

    sections = []
    mappings = []
    for index, option in enumerate(canonical_options):
        ingredients = tuple(
            ingredients_by_option_name.get(option.option_name, [])
        )
        sections.append(
            IngredientSection(
                raw_header=f"[{option.option_name}]",
                header_start_index=0,
                header_end_index=0,
                body_start_index=0,
                body_end_index=0,
                raw_ingredient_text=", ".join(ingredients),
                ingredients=ingredients,
            )
        )
        mappings.append(
            OptionSectionMapping(
                internal_option_key=option.internal_option_key,
                option_name=option.option_name,
                section_index=index,
                mapping_status="matched" if ingredients else "unmatched",
                mapping_method="fake_shadow_for_test",
                mapping_confidence=1.0,
            )
        )
    matched_count = sum(
        1 for mapping in mappings if mapping.mapping_status == "matched"
    )
    return ShadowParseResult(
        sections=tuple(sections),
        boundary_candidates=(),
        document_format="option_full_sections",
        structure_reason=None,
        mappings=tuple(mappings),
        orphan_section_count=0,
        matched_count=matched_count,
        unmatched_count=len(mappings) - matched_count,
        ambiguous_count=0,
        unsupported_count=0,
    )


# ---------------------------------------------------------------------------
# 1) flag=false면 shadow/selector 미실행
# ---------------------------------------------------------------------------


def test_flag_disabled_by_default_skips_shadow_and_selector(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError(
            "flag가 false인데 shadow parser가 호출되었습니다."
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _must_not_be_called,
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=FakeCacheService(),
    )
    assert service.shadow_observation_enabled is False

    result = service.prepare_product(_product())

    assert result.status == "mapping_failed"
    assert "Shadow selector observation" not in caplog.text


def test_flag_explicit_false_skips_shadow_and_selector(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError(
            "flag가 false인데 shadow parser가 호출되었습니다."
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _must_not_be_called,
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=FakeCacheService(),
        shadow_observation_enabled=False,
    )

    result = service.prepare_product(_product())

    assert result.status == "mapping_failed"
    assert "Shadow selector observation" not in caplog.text


# ---------------------------------------------------------------------------
# 2) production ready면 shadow 미실행 / 3) partial·failed면 실행
# ---------------------------------------------------------------------------


def test_shadow_not_executed_when_production_is_ready(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError(
            "production이 ready인데 shadow parser가 호출되었습니다."
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _must_not_be_called,
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_ready_extraction()),
        cache_service=FakeCacheService(),
        shadow_observation_enabled=True,
    )

    result = service.prepare_product(_product())

    assert result.status == "ready"
    assert "Shadow selector observation" not in caplog.text


def test_shadow_executed_when_production_is_partial(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)
    call_count = 0

    def _spy_shadow(raw_text, canonical_options):
        nonlocal call_count
        call_count += 1
        return _fake_shadow_result(
            canonical_options,
            {"19": ["정제수", "글리세린", "향료"], "21": []},
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _spy_shadow,
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=FakeCacheService(),
        shadow_observation_enabled=True,
    )

    result = service.prepare_product(_product())

    assert result.status == "mapping_failed"
    assert call_count == 1
    assert "Shadow selector observation" in caplog.text
    assert "selected=production" in caplog.text
    assert "reason=no_safe_improvement_detected" in caplog.text


# ---------------------------------------------------------------------------
# 4) selector가 shadow를 선택해도 저장 인자/응답은 production
# ---------------------------------------------------------------------------


def test_selector_picking_shadow_does_not_change_cache_or_response(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)

    def _shadow_confirms_both_options(raw_text, canonical_options):
        return _fake_shadow_result(
            canonical_options,
            {
                "19": ["정제수", "글리세린", "향료"],
                "21": ["정제수", "글리세린", "폴리부텐", "탤크"],
            },
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_confirms_both_options,
    )

    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=cache,
        shadow_observation_enabled=True,
    )

    result = service.prepare_product(_product())

    # selector는 shadow가 ready 옵션 수를 늘렸다고 판단해 shadow를
    # 고르지만, 그 판단은 로그에만 남고 실제 저장/응답에는 아무
    # 영향도 주지 않는다 - production은 여전히 21호를 인식하지
    # 못했으므로(19호만 ready인 partial) 매핑 실패 상태 그대로다.
    # Step 4에서 partial은 ready 옵션(19호)만 분석 가능하게 응답에
    # 남기지만, 그 성분 내용은 production 값이지 shadow 값이 아니다.
    assert "selected=shadow" in caplog.text
    assert (
        "reason=shadow_increases_ready_option_count_without_regression"
        in caplog.text
    )
    assert result.status == "mapping_failed"
    assert result.collection_status == "partial"
    assert result.can_analyze is True
    options_by_name = {option.option_name: option for option in result.options}
    assert options_by_name["19"].analysis_available is True
    assert options_by_name["21"].analysis_available is False
    assert cache.saved == []
    assert cache.completed == []


def test_observe_shadow_selection_never_calls_cache_service() -> None:
    """selector 판단 자체가 cache_service를 절대 호출하지 않음을
    직접 확인한다(간접적으로만 보장하지 않기 위한 단위 테스트)."""

    from app.products.parser_state import (
        build_option_level_result,
        build_parser_result,
    )
    from app.products.option_parser import OptionFullSectionParseResult

    class ExplodingCacheService:
        def __getattr__(self, name):
            raise AssertionError(
                f"observation 경로에서 cache_service.{name}이 호출되었습니다."
            )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=ExplodingCacheService(),
        shadow_observation_enabled=True,
    )

    canonical_options = canonicalize_product_options(
        [make_product_option("19호"), make_product_option("21호")]
    )
    production_parser_result = build_parser_result(
        "production",
        [
            build_option_level_result(
                option_id=canonical_options[0].internal_option_key,
                option_name="19호",
                mapping_status="matched",
                ingredients=["정제수", "글리세린", "향료"],
            ),
            build_option_level_result(
                option_id=canonical_options[1].internal_option_key,
                option_name="21호",
                mapping_status="unmatched",
                ingredients=[],
            ),
        ],
    )
    parse_result = OptionFullSectionParseResult(
        sections=(),
        headers=(),
        orphan_document_sections=(),
    )

    def _shadow_confirms_both(raw_text, canonical_options):
        return _fake_shadow_result(
            canonical_options,
            {
                "19": ["정제수", "글리세린", "향료"],
                "21": ["정제수", "글리세린", "폴리부텐", "탤크"],
            },
        )

    import app.products.option_service as service_module

    original = service_module.shadow_parse_option_ingredient_sections
    service_module.shadow_parse_option_ingredient_sections = (
        _shadow_confirms_both
    )
    try:
        service._observe_shadow_selection(
            _product(),
            "[19호] 정제수, 글리세린, 향료",
            canonical_options,
            parse_result,
            {"matched": 1, "unmatched": 1, "ambiguous": 0, "unsupported": 0},
            production_parser_result,
        )
    finally:
        service_module.shadow_parse_option_ingredient_sections = original


# ---------------------------------------------------------------------------
# 5) production/shadow 동일 옵션의 option_id 일치
# ---------------------------------------------------------------------------


def test_production_and_shadow_use_identical_option_id_for_same_option() -> (
    None
):
    canonical_options = canonicalize_product_options(
        [make_product_option("19호"), make_product_option("21호")]
    )

    from app.products.option_parser import parse_option_full_sections

    raw_text = "[19호] 정제수, 글리세린, 향료"
    parse_result = parse_option_full_sections(raw_text, canonical_options)
    sections_by_key = {
        section.internal_option_key: section
        for section in parse_result.sections
    }

    shadow_result = _fake_shadow_result(
        canonical_options,
        {"19": ["정제수", "글리세린", "향료"], "21": []},
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=FakeCacheService(),
    )
    production_result = service._build_production_parser_result(
        canonical_options, sections_by_key
    )
    shadow_parser_result = service._build_shadow_parser_result(
        canonical_options, shadow_result
    )

    production_ids = [option.option_id for option in production_result.options]
    shadow_ids = [option.option_id for option in shadow_parser_result.options]
    expected_ids = [option.internal_option_key for option in canonical_options]

    assert production_ids == expected_ids
    assert shadow_ids == expected_ids


# ---------------------------------------------------------------------------
# 6) shadow 예외 / selector 예외가 production 요청을 실패시키지 않음
# ---------------------------------------------------------------------------


def test_shadow_exception_does_not_fail_production_request(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.WARNING)

    def _raise(raw_text, canonical_options):
        raise RuntimeError("shadow parser boom")

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _raise,
    )

    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=cache,
        shadow_observation_enabled=True,
    )

    result = service.prepare_product(_product())

    assert result.status == "mapping_failed"
    assert cache.saved == []
    assert "Shadow option parser failed" in caplog.text


def test_selector_exception_does_not_fail_production_request(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.WARNING)

    def _shadow_ok(raw_text, canonical_options):
        return _fake_shadow_result(
            canonical_options,
            {"19": ["정제수", "글리세린", "향료"], "21": []},
        )

    def _raise_selector(*args, **kwargs):
        raise RuntimeError("selector boom")

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_ok,
    )
    monkeypatch.setattr(
        option_service_module,
        "select_safe_parser_result",
        _raise_selector,
    )

    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=cache,
        shadow_observation_enabled=True,
    )

    result = service.prepare_product(_product())

    assert result.status == "mapping_failed"
    assert cache.saved == []
    assert "Shadow selector observation failed" in caplog.text


# ---------------------------------------------------------------------------
# 7) 관찰 모드 로그는 성분/원문을 남기지 않는다
# ---------------------------------------------------------------------------


def test_observation_log_does_not_leak_ingredient_lists(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)

    def _shadow_ok(raw_text, canonical_options):
        return _fake_shadow_result(
            canonical_options,
            {
                "19": ["정제수", "글리세린", "향료"],
                "21": ["정제수", "글리세린", "폴리부텐", "탤크"],
            },
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_ok,
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=FakeCacheService(),
        shadow_observation_enabled=True,
    )

    service.prepare_product(_product())

    assert "폴리부텐" not in caplog.text
    assert "탤크" not in caplog.text


# ---------------------------------------------------------------------------
# 8) selector 관찰 INFO 로그는 상품당 최대 1건 / 옵션별 상세는 DEBUG
# ---------------------------------------------------------------------------


def test_selector_observation_emits_at_most_one_info_log(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.INFO)

    def _shadow_ok(raw_text, canonical_options):
        return _fake_shadow_result(
            canonical_options,
            {
                "19": ["정제수", "글리세린", "향료"],
                "21": ["정제수", "글리세린", "폴리부텐", "탤크"],
            },
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_ok,
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=FakeCacheService(),
        shadow_observation_enabled=True,
    )

    service.prepare_product(_product())

    info_records = [
        record for record in caplog.records if record.levelno == logging.INFO
    ]
    selector_info_records = [
        record
        for record in info_records
        if "Shadow selector observation" in record.getMessage()
    ]
    assert len(selector_info_records) == 1
    message = selector_info_records[0].getMessage()
    assert "production_status=" in message
    assert "production_ready=" in message
    assert "shadow_status=" in message
    assert "shadow_ready=" in message
    assert "selected=" in message
    assert "reason=" in message


def test_no_info_log_when_shadow_not_executed(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("production이 ready인데 shadow가 호출됨")

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _must_not_be_called,
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_ready_extraction()),
        cache_service=FakeCacheService(),
        shadow_observation_enabled=True,
    )

    service.prepare_product(_product())

    shadow_related_info = [
        record
        for record in caplog.records
        if record.levelno == logging.INFO
        and (
            "Shadow selector observation" in record.getMessage()
            or "Shadow option parser diagnostics" in record.getMessage()
        )
    ]
    assert shadow_related_info == []


def test_per_option_detail_logged_at_debug_without_names_or_ingredients(
    monkeypatch, caplog
) -> None:
    caplog.set_level(logging.DEBUG)

    def _shadow_ok(raw_text, canonical_options):
        return _fake_shadow_result(
            canonical_options,
            {
                "19": ["정제수", "글리세린", "향료"],
                "21": ["정제수", "글리세린", "폴리부텐", "탤크"],
            },
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_ok,
    )

    canonical_options = canonicalize_product_options(
        [make_product_option("19호"), make_product_option("21호")]
    )
    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=FakeCacheService(),
        shadow_observation_enabled=True,
    )

    service.prepare_product(_product())

    detail_records = [
        record
        for record in caplog.records
        if record.levelno == logging.DEBUG
        and "Shadow selector observation detail" in record.getMessage()
    ]
    assert len(detail_records) == 1
    message = detail_records[0].getMessage()

    for option in canonical_options:
        assert option.internal_option_key in message
    # 옵션명·성분·원문은 절대 남기지 않는다.
    assert "19호" not in message
    assert "21호" not in message
    assert "정제수" not in message
    assert "폴리부텐" not in message
    assert "탤크" not in message


def test_shadow_comparison_diagnostics_downgraded_to_debug(
    monkeypatch, caplog
) -> None:
    """기존 format/status_counts 진단 로그는 더 이상 INFO가 아니라
    DEBUG다 - INFO 레벨에서는 selector 요약 로그 1건만 보여야
    한다."""

    caplog.set_level(logging.DEBUG)

    def _shadow_ok(raw_text, canonical_options):
        return _fake_shadow_result(
            canonical_options,
            {"19": ["정제수", "글리세린", "향료"], "21": []},
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_ok,
    )

    service = ProductOptionService(
        extractor=FakeOptionExtractor(_partial_extraction()),
        cache_service=FakeCacheService(),
        shadow_observation_enabled=True,
    )

    service.prepare_product(_product())

    diagnostics_records = [
        record
        for record in caplog.records
        if "Shadow option parser diagnostics" in record.getMessage()
    ]
    assert len(diagnostics_records) == 1
    assert diagnostics_records[0].levelno == logging.DEBUG

    info_records = [
        record for record in caplog.records if record.levelno == logging.INFO
    ]
    assert len(info_records) == 1
    assert "Shadow selector observation" in info_records[0].getMessage()

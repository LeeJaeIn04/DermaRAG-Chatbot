"""Step 6: PRODUCT_SELECTED_PARSER_RESULT_ENABLED (production 전환).

flag=false면 지금까지와 완전히 동일하게 production 결과만 쓴다.
flag=true면 Step 1 selector가 고른 결과(production 또는 shadow)를
effective result로 API 응답/cache 저장에 그대로 반영한다. selector
정책 자체나 parser 재계산은 절대 건드리지 않는다 - Step 2에서 이미
계산한 selection을 그대로 재사용하는지만 검증한다.
"""

from datetime import timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.products.db_models import utc_now
from app.products.ingredient_cache_service import (
    ProductIngredientCacheService,
)
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
    make_product_option,
)
from app.products.option_service import ProductOptionService
from app.products.repositories.sqlite import (
    SQLiteProductIngredientRepository,
)
import app.products.option_service as option_service_module


def _repository() -> SQLiteProductIngredientRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )
    return SQLiteProductIngredientRepository(session_factory=session_factory)


def _product(product_id: str) -> ProductCandidate:
    return ProductCandidate(
        product_id=product_id,
        source="oliveyoung",
        product_name="Step 6 테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=" + product_id
        ),
    )


class _FakeExtractor:
    def __init__(self, result: ProductOptionExtractionResult) -> None:
        self.result = result
        self.calls = 0

    def extract(self, product_id: str, product_url: str):
        self.calls += 1
        return self.result


def _partial_extraction(product_id: str) -> ProductOptionExtractionResult:
    """production이 partial(19호만 matched)로 끝나는 입력. shadow가
    matched=[19호] 성분을 production과 동일하게 재현하면 회귀 없이
    ready 수만 늘릴 수 있다(selector가 shadow를 고를 수 있는
    조건)."""

    return ProductOptionExtractionResult(
        status="collected",
        options=[
            make_product_option("19호"),
            make_product_option("21호"),
        ],
        raw_document=ProductIngredientRawDocument(
            source="oliveyoung",
            product_id=product_id,
            raw_text="[19호] 정제수, 글리세린, 향료",
            parser_version=PARSER_VERSION,
        ),
    )


def _shadow_confirms_both_matching_production(raw_text, canonical_options):
    """production의 19호 성분(정제수, 글리세린, 향료)을 그대로 재현하고
    21호까지 새로 matched로 만든다 - selector가 회귀 없이 shadow의
    ready 수 증가를 인정할 수 있는 유일한 조건."""

    ingredients_by_name = {
        "19": ("정제수", "글리세린", "향료"),
        "21": ("정제수", "탤크", "마이카"),
    }
    sections = []
    mappings = []
    for index, option in enumerate(canonical_options):
        ingredients = ingredients_by_name[option.option_name]
        sections.append(
            IngredientSection(
                raw_header=f"[{option.option_name}호]",
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
                mapping_status="matched",
                mapping_method="fake_shadow_for_test",
                mapping_confidence=1.0,
            )
        )
    return ShadowParseResult(
        sections=tuple(sections),
        boundary_candidates=(),
        document_format="option_full_sections",
        structure_reason=None,
        mappings=tuple(mappings),
        orphan_section_count=0,
        matched_count=len(mappings),
        unmatched_count=0,
        ambiguous_count=0,
        unsupported_count=0,
    )


def _shadow_matches_only_existing(raw_text, canonical_options):
    """production과 완전히 동일한 결과만 재현한다(개선 없음) - selector가
    production을 그대로 고르는 경우를 만든다."""

    sections = []
    mappings = []
    for index, option in enumerate(canonical_options):
        if option.option_name == "19":
            ingredients = ("정제수", "글리세린", "향료")
            status = "matched"
        else:
            ingredients = ()
            status = "unmatched"
        sections.append(
            IngredientSection(
                raw_header=f"[{option.option_name}호]",
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
                mapping_status=status,
                mapping_method="fake_shadow_for_test",
                mapping_confidence=1.0,
            )
        )
    return ShadowParseResult(
        sections=tuple(sections),
        boundary_candidates=(),
        document_format="option_full_sections",
        structure_reason=None,
        mappings=tuple(mappings),
        orphan_section_count=0,
        matched_count=1,
        unmatched_count=1,
        ambiguous_count=0,
        unsupported_count=0,
    )


def _make_service(
    product_id: str,
    *,
    shadow_observation_enabled: bool = False,
    selected_parser_result_enabled: bool = False,
    option_level_cache_enabled: bool = True,
):
    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=option_level_cache_enabled,
    )
    extractor = _FakeExtractor(_partial_extraction(product_id))
    service = ProductOptionService(
        extractor=extractor,
        cache_service=cache_service,
        shadow_observation_enabled=shadow_observation_enabled,
        selected_parser_result_enabled=selected_parser_result_enabled,
    )
    return service, extractor, repository


# ---------------------------------------------------------------------------
# 1) flag off 회귀: shadow가 더 나은 결과를 줘도 절대 쓰지 않는다
# ---------------------------------------------------------------------------


def test_flag_off_ignores_shadow_even_if_it_would_improve(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_confirms_both_matching_production,
    )
    service, extractor, repository = _make_service(
        "A000000000101",
        shadow_observation_enabled=False,
        selected_parser_result_enabled=False,
    )

    result = service.prepare_product(_product("A000000000101"))

    assert result.collection_status == "partial"
    options_by_name = {o.option_name: o for o in result.options}
    assert options_by_name["19"].analysis_available is True
    assert options_by_name["21"].analysis_available is False
    # Step 3 option-level cache(partial snapshot)는 계속 저장되지만,
    # flag가 꺼져 있으므로 저장된 값은 production 그대로다 - shadow가
    # 21호를 ready로 봤어도 21호는 여전히 unmapped로 저장된다.
    with repository.session_factory() as session:
        option_cache_status_by_name = {
            row[0]: row[1]
            for row in session.execute(
                text(
                    "SELECT r.option_name, r.option_cache_status "
                    "FROM product_ingredient_records r "
                    "JOIN products p ON p.id = r.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": "A000000000101"},
            )
        }
    assert option_cache_status_by_name == {"19": "ready", "21": "unmapped"}


# ---------------------------------------------------------------------------
# 2) flag on, selector가 production을 선택
# ---------------------------------------------------------------------------


def test_flag_on_selector_picks_production_when_shadow_does_not_improve(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_matches_only_existing,
    )
    service, extractor, repository = _make_service(
        "A000000000102",
        selected_parser_result_enabled=True,
    )

    result = service.prepare_product(_product("A000000000102"))

    assert result.collection_status == "partial"
    options_by_name = {o.option_name: o for o in result.options}
    assert options_by_name["19"].analysis_available is True
    assert options_by_name["21"].analysis_available is False


# ---------------------------------------------------------------------------
# 3) flag on, selector가 shadow를 선택
# ---------------------------------------------------------------------------


def test_flag_on_selector_picks_shadow_and_it_becomes_effective_result(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_confirms_both_matching_production,
    )
    service, extractor, repository = _make_service(
        "A000000000103",
        selected_parser_result_enabled=True,
    )

    result = service.prepare_product(_product("A000000000103"))

    # shadow가 21호까지 ready로 만들었으므로 effective result는 이제
    # ready(collection_status="ready")다 - production 단독으로는
    # partial이었던 것과 다르다.
    assert result.collection_status == "ready"
    assert result.can_analyze is True
    options_by_name = {o.option_name: o for o in result.options}
    assert options_by_name["19"].analysis_available is True
    assert options_by_name["21"].analysis_available is True

    with repository.session_factory() as session:
        rows = {
            row[0]: row[1]
            for row in session.execute(
                text(
                    "SELECT r.option_name, r.raw_ingredients "
                    "FROM product_ingredient_records r "
                    "JOIN products p ON p.id = r.product_id "
                    "WHERE p.external_product_id = :pid"
                ),
                {"pid": "A000000000103"},
            )
        }
    # 21호의 성분은 production에는 없던 shadow 값이 그대로 저장됐다.
    assert rows["21"] == "정제수, 탤크, 마이카"
    assert rows["19"] == "정제수, 글리세린, 향료"


# ---------------------------------------------------------------------------
# 4) shadow 실패/없음 → production fallback
# ---------------------------------------------------------------------------


def test_shadow_failure_falls_back_to_production_even_with_flag_on(
    monkeypatch,
) -> None:
    def _raise(raw_text, canonical_options):
        raise RuntimeError("shadow boom")

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _raise,
    )
    service, extractor, repository = _make_service(
        "A000000000104",
        selected_parser_result_enabled=True,
    )

    result = service.prepare_product(_product("A000000000104"))

    assert result.collection_status == "partial"
    options_by_name = {o.option_name: o for o in result.options}
    assert options_by_name["19"].analysis_available is True
    assert options_by_name["21"].analysis_available is False


# ---------------------------------------------------------------------------
# 5) observation off + selected on: shadow는 여전히 실행된다
# ---------------------------------------------------------------------------


def test_shadow_runs_when_only_selected_flag_is_enabled(monkeypatch) -> None:
    calls = {"count": 0}

    def _spy(raw_text, canonical_options):
        calls["count"] += 1
        return _shadow_confirms_both_matching_production(
            raw_text, canonical_options
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _spy,
    )
    service, extractor, repository = _make_service(
        "A000000000105",
        shadow_observation_enabled=False,
        selected_parser_result_enabled=True,
    )

    result = service.prepare_product(_product("A000000000105"))

    assert calls["count"] == 1
    assert result.collection_status == "ready"


# ---------------------------------------------------------------------------
# 6) selected shadow cache 재조회 시 재수집 없음
# ---------------------------------------------------------------------------


def test_selected_shadow_cache_hit_avoids_recollection(monkeypatch) -> None:
    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_confirms_both_matching_production,
    )
    service, extractor, repository = _make_service(
        "A000000000106",
        selected_parser_result_enabled=True,
    )

    first = service.prepare_product(_product("A000000000106"))
    assert first.collection_status == "ready"
    assert extractor.calls == 1

    second = service.prepare_product(_product("A000000000106"))
    assert extractor.calls == 1
    assert second.collection_status == "ready"
    options_by_name = {o.option_name: o for o in second.options}
    assert options_by_name["21"].analysis_available is True


# ---------------------------------------------------------------------------
# 7) provenance 보존: selected shadow는 relabel 없이 source="shadow"로
# 저장 경로까지 그대로 전달된다
# ---------------------------------------------------------------------------


def test_selected_shadow_preserves_source_through_ready_storage_path(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_confirms_both_matching_production,
    )
    service, extractor, repository = _make_service(
        "A000000000107",
        selected_parser_result_enabled=True,
    )

    captured = {}
    original_save_collection = repository.save_collection

    def _spy_save_collection(product, **kwargs):
        captured["production_parser_result"] = kwargs[
            "production_parser_result"
        ]
        return original_save_collection(product, **kwargs)

    repository.save_collection = _spy_save_collection

    result = service.prepare_product(_product("A000000000107"))

    assert result.collection_status == "ready"
    assert captured["production_parser_result"].source == "shadow"


def test_selected_shadow_preserves_source_through_partial_snapshot_path(
    monkeypatch,
) -> None:
    """production 2/3 옵션이 여전히 partial이고 shadow가 회귀 없이
    ready 수만 늘려(1/3 -> 2/3, 여전히 partial) 선택되는 경우에도,
    partial 저장 경로(store_option_cache_snapshot)에 전달되는
    ParserResult의 source가 "shadow"로 보존된다."""

    product_id = "A000000000108"
    extraction = ProductOptionExtractionResult(
        status="collected",
        options=[
            make_product_option("19호"),
            make_product_option("21호"),
            make_product_option("23호"),
        ],
        raw_document=ProductIngredientRawDocument(
            source="oliveyoung",
            product_id=product_id,
            raw_text="[19호] 정제수, 글리세린, 향료",
            parser_version=PARSER_VERSION,
        ),
    )

    def _shadow_confirms_two_of_three(raw_text, canonical_options):
        ingredients_by_name = {
            "19": ("정제수", "글리세린", "향료"),
            "21": ("정제수", "탤크", "마이카"),
            "23": (),
        }
        sections = []
        mappings = []
        for index, option in enumerate(canonical_options):
            ingredients = ingredients_by_name[option.option_name]
            status = "matched" if ingredients else "unmatched"
            sections.append(
                IngredientSection(
                    raw_header=f"[{option.option_name}호]",
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
                    mapping_status=status,
                    mapping_method="fake_shadow_for_test",
                    mapping_confidence=1.0,
                )
            )
        return ShadowParseResult(
            sections=tuple(sections),
            boundary_candidates=(),
            document_format="option_full_sections",
            structure_reason=None,
            mappings=tuple(mappings),
            orphan_section_count=0,
            matched_count=2,
            unmatched_count=1,
            ambiguous_count=0,
            unsupported_count=0,
        )

    monkeypatch.setattr(
        option_service_module,
        "shadow_parse_option_ingredient_sections",
        _shadow_confirms_two_of_three,
    )
    repository = _repository()
    cache_service = ProductIngredientCacheService(
        repository=repository,
        extractor=None,
        clock=utc_now,
        option_level_cache_enabled=True,
    )
    service = ProductOptionService(
        extractor=_FakeExtractor(extraction),
        cache_service=cache_service,
        selected_parser_result_enabled=True,
    )

    captured = {}
    original_snapshot = repository.save_option_cache_snapshot

    def _spy_snapshot(product, **kwargs):
        captured["parser_result"] = kwargs["parser_result"]
        return original_snapshot(product, **kwargs)

    repository.save_option_cache_snapshot = _spy_snapshot

    result = service.prepare_product(_product(product_id))

    # production은 19호만 ready(1/3), shadow는 19호+21호 ready(2/3) -
    # 여전히 partial이지만 회귀 없이 ready 수가 늘어 selector가
    # shadow를 고른다.
    assert result.collection_status == "partial"
    options_by_name = {o.option_name: o for o in result.options}
    assert options_by_name["21"].analysis_available is True
    assert options_by_name["23"].analysis_available is False
    assert captured["parser_result"].source == "shadow"

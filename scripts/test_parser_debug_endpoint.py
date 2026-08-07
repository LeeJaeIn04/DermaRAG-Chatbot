import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import app.main as main
from app.products.models import ProductCandidate
from app.products.option_models import (
    ProductOptionExtractionResult,
)
from app.products.option_parser import make_product_option
from app.products.parser_debug import PARSER_VERSION, SHADOW_PARSER_VERSION
from app.products.repositories.base import CachedProductIngredients


FIXTURES_DIR = Path(__file__).parent / "fixtures"
WAKEMAKE_FIXTURE_PATH = (
    FIXTURES_DIR
    / "shadow_wakemake_lip_mixed_bracket_typo_A000000226241.json"
)
STRING_FORMULA_FIXTURE_PATH = (
    FIXTURES_DIR
    / "shadow_string_formula_prefix_candidates_A000000258200.json"
)
TRAILING_DESCRIPTION_FIXTURE_PATH = (
    FIXTURES_DIR
    / "shadow_wakemake_lip_trailing_description_A000000226241.json"
)
TRAILING_BRACKET_SUFFIX_FIXTURE_PATH = (
    FIXTURES_DIR
    / "shadow_wakemake_lip_trailing_bracket_suffix_A000000226241.json"
)


def _load_fixture(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _product(product_id: str = "A000000226241") -> ProductCandidate:
    return ProductCandidate(
        product_id=product_id,
        source="oliveyoung",
        product_name="테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=" + product_id
        ),
    )


def _extraction_result(fixture: dict) -> ProductOptionExtractionResult:
    from app.products.option_models import ProductIngredientRawDocument

    options = [
        make_product_option(name) for name in fixture["options"]
    ]
    raw_document = ProductIngredientRawDocument(
        source="oliveyoung",
        product_id=fixture.get("product_id", "A000000226241"),
        raw_text=fixture["raw_text"],
        parser_version=PARSER_VERSION,
    )
    return ProductOptionExtractionResult(
        status="collected",
        options=options,
        option_count=len(options),
        raw_document=raw_document,
    )


def test_parser_debug_returns_404_outside_development_environment(
    monkeypatch,
) -> None:
    monkeypatch.setattr(main.settings, "environment", "production")
    response = TestClient(main.app).get(
        "/products/A000000226241/parser-debug"
    )
    assert response.status_code == 404


def test_parser_debug_returns_404_when_product_not_found(
    monkeypatch,
) -> None:
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: None,
    )
    response = TestClient(main.app).get(
        "/products/A000000000000/parser-debug"
    )
    assert response.status_code == 404


def test_parser_debug_compares_production_and_shadow_for_real_case(
    monkeypatch,
) -> None:
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )

    response = TestClient(main.app).get(
        "/products/A000000226241/parser-debug"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["product_id"] == "A000000226241"
    assert body["production_parser_version"] == PARSER_VERSION
    assert body["shadow_parser_version"] == SHADOW_PARSER_VERSION
    assert body["canonical_option_count"] == 3
    assert body["production_document_format"] == "option_full_sections"
    assert body["shadow_document_format"] == "option_full_sections"
    assert body["shadow_section_count"] == 3
    assert body["shadow_status_counts"]["matched"] == 3
    assert body["shadow_orphan_count"] == 0
    assert body["format_diff"] is False

    # production은 '{옵션명]' 오타 header 문법을 지원하지 않으므로
    # 실제로 2개 옵션(19호/21호)을 unmatched로 남긴다. shadow는 이
    # 오타를 인식해 3개 모두 matched로 처리한다 - 이 endpoint가
    # 드러내야 하는 정확히 그 격차다.
    assert body["production_status_counts"]["matched"] == 1
    assert body["production_status_counts"]["unmatched"] == 2
    assert body["status_diff"] == {"matched": -2, "unmatched": 2}
    assert len(body["shadow_sections"]) == 3
    for section in body["shadow_sections"]:
        assert section["mapping_status"] == "matched"
        assert section["mapped_option_name"] is not None
        assert len(section["first_ingredients"]) <= 3
        assert len(section["last_ingredients"]) <= 2
        assert section["nested_formula_count"] == 0


def test_parser_debug_response_never_includes_full_raw_text_or_ingredients(
    monkeypatch,
) -> None:
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )

    response = TestClient(main.app).get(
        "/products/A000000226241/parser-debug"
    )

    assert response.status_code == 200
    raw_response_text = response.text
    # 원문 전체(멀티라인 raw_text)는 어떤 필드에도 그대로 나타나면
    # 안 된다. first/last_ingredients 미리보기에 일부 성분명이
    # 등장하는 것은 허용된다.
    assert fixture["raw_text"] not in raw_response_text
    body = response.json()
    for section in body["shadow_sections"]:
        assert "raw_ingredient_text" not in section
        assert "ingredients" not in section
        assert len(section["first_ingredients"]) <= 3
        assert len(section["last_ingredients"]) <= 2


def test_parser_debug_does_not_call_extractor_when_common_cache_exists(
    monkeypatch,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )

    def fake_get_cached_ingredients(source, external_product_id, option_id=""):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return CachedProductIngredients(
            product_id=external_product_id,
            source=source,
            product_url="https://example.com",
            raw_ingredients="정제수, 글리세린, 향료",
            ingredients=("정제수", "글리세린", "향료"),
            extraction_method="browser_dom:test",
            ingredient_hash="hash",
            extracted_at=now,
            last_checked_at=now,
            expires_at=now + timedelta(days=90),
        )

    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        fake_get_cached_ingredients,
    )

    def fail_if_called(product_id, product_url):
        calls.append(product_id)
        raise AssertionError(
            "no_options 캐시가 있으면 추출기를 다시 호출하면 안 된다."
        )

    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        fail_if_called,
    )

    response = TestClient(main.app).get(
        "/products/A000000000001/parser-debug"
    )

    assert response.status_code == 200
    assert calls == []
    body = response.json()
    assert body["production_document_format"] == "not_applicable"
    assert body["shadow_document_format"] == "not_applicable"
    assert body["canonical_option_count"] == 0


def test_parser_debug_never_writes_to_cache_or_collection_state(
    monkeypatch,
) -> None:
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )

    mutating_methods = [
        "save_ingredients",
        "save_collection",
        "mark_collection_complete",
        "start_collection_attempt",
        "finish_collection_attempt",
    ]

    def _forbidden(*args, **kwargs):
        raise AssertionError(
            "parser-debug 진단 endpoint는 캐시/수집 상태를 "
            "변경하면 안 된다."
        )

    for method_name in mutating_methods:
        monkeypatch.setattr(
            main.ingredient_repository, method_name, _forbidden
        )

    response = TestClient(main.app).get(
        "/products/A000000226241/parser-debug"
    )

    assert response.status_code == 200


def test_parser_debug_route_is_registered_for_swagger() -> None:
    schema = TestClient(main.app).get("/openapi.json").json()
    assert "/products/{product_id}/parser-debug" in schema["paths"]
    assert "get" in schema["paths"]["/products/{product_id}/parser-debug"]


# ---------------------------------------------------------------------------
# A000000258200 - 문자열형 내부 formula 구조 진단 후보
# ---------------------------------------------------------------------------


def test_parser_debug_reports_confirmed_string_formula_structure(
    monkeypatch,
) -> None:
    """dictionary exact match 규칙으로 문자열형 내부 formula가 최소
    조건(유일한 분할 후보 2개 이상, formula body exact-known 성분
    4개 이상)을 만족하면 shadow parser가 hierarchical로 확정한다
    (더 이상 parser-debug의 후보 목록에만 남지 않는다).
    """

    fixture = _load_fixture(STRING_FORMULA_FIXTURE_PATH)
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )

    response = TestClient(main.app).get(
        "/products/A000000258200/parser-debug"
    )

    assert response.status_code == 200
    body = response.json()

    assert body["shadow_document_format"] == (
        "hierarchical_option_internal_sections"
    )
    assert body["shadow_section_count"] == 1
    assert body["shadow_sections"][0]["nested_formula_count"] == 3
    # hierarchical로 확정되면 판매 옵션 매핑은 시도하지 않는다
    # (unsupported로만 남고 ready로 새지 않는다).
    assert body["shadow_status_counts"]["matched"] == 0
    assert body["shadow_status_counts"]["unsupported"] == 1

    # production parser는 이 문자열형 구조를 전혀 인식하지 못해
    # flat 단일 section으로만 남는다 - production 코드는 이번 턴에
    # 손대지 않았으므로 그대로다.
    assert body["production_document_format"] == "option_full_sections"

    assert fixture["raw_text"] not in response.text


def test_string_formula_fixture_is_confirmed_as_hierarchical() -> None:
    from app.products.option_parser import (
        canonicalize_product_options as _canon,
    )
    from app.products.option_parser import (
        shadow_parse_option_ingredient_sections as _shadow_parse,
    )

    fixture = _load_fixture(STRING_FORMULA_FIXTURE_PATH)
    options = [make_product_option(name) for name in fixture["options"]]
    canonical = _canon(options)
    result = _shadow_parse(fixture["raw_text"], canonical)

    assert result.document_format == "hierarchical_option_internal_sections"
    assert len(result.sections) == 1
    top_section = result.sections[0]
    assert top_section.ingredients == ()
    assert len(top_section.subsections) == 3

    labels = [subsection.label for subsection in top_section.subsections]
    assert labels == ["", "코랄글로우", "피치쉬머"]

    for subsection in top_section.subsections:
        assert len(subsection.ingredients) >= 4

    # 판매 옵션 매핑은 시도하지 않는다(unsupported).
    assert result.matched_count == 0
    assert result.unsupported_count == 1
    assert result.mappings[0].mapping_status == "unsupported"
    assert result.mappings[0].section_index is None


# ---------------------------------------------------------------------------
# A000000226241 - 후행 상품 설명 구조 진단 후보
# ---------------------------------------------------------------------------


def test_parser_debug_reports_trailing_description_candidates(
    monkeypatch,
) -> None:
    fixture = _load_fixture(TRAILING_DESCRIPTION_FIXTURE_PATH)
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )

    response = TestClient(main.app).get(
        "/products/A000000226241/parser-debug"
    )

    assert response.status_code == 200
    body = response.json()

    candidates = body["trailing_description_candidates"]
    assert len(candidates) == 2

    section_end_only = next(
        c for c in candidates if c["boundary_type"] == "section_end_only"
    )
    document_end = next(
        c for c in candidates if c["boundary_type"] == "document_end"
    )

    assert section_end_only["section_raw_header"] == "[19호 쉘 피치]"
    assert section_end_only["preceding_ingredient"] == "향료"
    assert (
        section_end_only["trailing_text"]
        == "[본품 이미지와 실제 색상 차이가 있을 수 있습니다]"
    )
    assert section_end_only["has_additional_ingredient_body_after"] is True

    assert document_end["section_raw_header"] == "[20호 플레저]"
    assert document_end["preceding_ingredient"] == "향료"
    assert document_end["trailing_text"] == "[실제 색상과 다를 수 있습니다]"
    assert document_end["has_additional_ingredient_body_after"] is False

    for candidate in candidates:
        assert set(candidate.keys()) == {
            "section_raw_header",
            "preceding_ingredient",
            "trailing_text",
            "has_additional_ingredient_body_after",
            "boundary_type",
        }
    assert fixture["raw_text"] not in response.text


def test_parser_debug_does_not_remove_trailing_description_annotations() -> (
    None
):
    from app.products.option_parser import (
        canonicalize_product_options as _canon,
    )
    from app.products.option_parser import (
        shadow_parse_option_ingredient_sections as _shadow_parse,
    )

    fixture = _load_fixture(TRAILING_DESCRIPTION_FIXTURE_PATH)
    options = [make_product_option(name) for name in fixture["options"]]
    canonical = _canon(options)
    result = _shadow_parse(fixture["raw_text"], canonical)

    # 진단 로직이 shadow parser가 실제로 만든 section 목록(트레일링
    # bracket이 자체 section으로 남아 있는 상태)을 그대로 두고
    # annotation을 지우거나 병합하지 않는다.
    raw_headers = [section.raw_header for section in result.sections]
    assert "[본품 이미지와 실제 색상 차이가 있을 수 있습니다]" in raw_headers
    assert "[실제 색상과 다를 수 있습니다]" in raw_headers
    assert len(result.sections) == 4
    assert result.document_format == "option_full_sections"


# ---------------------------------------------------------------------------
# parser-debug 보강: section_kind / formula_boundary_candidates /
# ambiguous_boundaries / ambiguous_annotation_candidates / component_group
# ---------------------------------------------------------------------------


def test_parser_debug_exposes_formula_boundary_candidates_for_real_chunks(
    monkeypatch,
) -> None:
    """A000000258200에서 후보 0개로 보이던 문제가 고정됐는지
    parser-debug 응답으로 직접 확인한다."""

    raw_text = (
        "[01 팔레트] "
        "소프트 레이 Soft Ray 탤크, 실리카, "
        "흑색산화철 아이시 알로이 Icy Alloy 탤크, 실리카, "
        "문 샌드 Moon Sand 탤크, 실리카, "
        "핑크 페탈 Pink Petal 탤크, 실리카, "
        "피치 솔라 Peach Solar 마이카, 실리카"
    )
    fixture = {
        "product_id": "A000000258200",
        "options": ["01 팔레트"],
        "raw_text": raw_text,
    }
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )

    response = TestClient(main.app).get(
        "/products/A000000258200/parser-debug"
    )

    assert response.status_code == 200
    body = response.json()
    section = body["shadow_sections"][0]
    assert section["section_kind"] == "ingredient_section"
    candidates = section["formula_boundary_candidates"]
    assert len(candidates) == 5
    right_ingredients = {c["right_ingredient"] for c in candidates}
    assert right_ingredients == {"탤크", "마이카"}
    assert section["ambiguous_boundaries"] == []
    # body마다 성분이 2개뿐(탤크/마이카 + 실리카)이라 hierarchical로
    # 확정되지 않는다 - 기준 완화 없이 needs_review로 남는다.
    assert body["shadow_document_format"] == "needs_review"


def test_parser_debug_exposes_ambiguous_annotation_candidates(
    monkeypatch,
) -> None:
    fixture = _load_fixture(TRAILING_BRACKET_SUFFIX_FIXTURE_PATH)
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )

    response = TestClient(main.app).get(
        "/products/A000000226241/parser-debug"
    )

    assert response.status_code == 200
    body = response.json()

    section_by_header = {
        section["raw_header"]: section for section in body["shadow_sections"]
    }
    plain_section = section_by_header["[19호 쉘 피치]"]
    assert plain_section["ambiguous_annotation_candidates"] == []

    annotated_section = section_by_header["[20호 플레저]"]
    assert len(annotated_section["ambiguous_annotation_candidates"]) == 1
    annotation = annotated_section["ambiguous_annotation_candidates"][0]
    assert annotation["text"] == "[헬시 글로우 밤 스틱 기획(2024.10)]"
    assert (
        fixture["raw_text"][
            annotation["start_index"]:annotation["end_index"]
        ]
        == annotation["text"]
    )
    # 다른 정상 option section의 매핑은 막히지 않는다.
    assert body["shadow_status_counts"]["matched"] == 2


def test_parser_debug_exposes_component_group_summary(monkeypatch) -> None:
    raw_text = (
        "[19호 쉘 피치] 정제수, 글리세린, 마이카(CI 77019), 향료, "
        "[증정], 정제수, 글리세린, 탤크, 디메치콘"
    )
    fixture = {
        "product_id": "A000000226241",
        "options": ["19호 쉘 피치"],
        "raw_text": raw_text,
    }
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )

    response = TestClient(main.app).get(
        "/products/A000000226241/parser-debug"
    )

    assert response.status_code == 200
    body = response.json()

    assert body["component_group_sections"] == [
        {"raw_header": "[증정]", "ingredient_count": 4}
    ]
    section_by_header = {
        section["raw_header"]: section for section in body["shadow_sections"]
    }
    assert section_by_header["[증정]"]["section_kind"] == "component_group"
    # component_group은 canonical mapping에서 제외되어 다른 정상
    # section 매핑을 막지 않는다.
    assert body["shadow_status_counts"]["matched"] == 1
    assert body["shadow_orphan_count"] == 0


# ---------------------------------------------------------------------------
# parser-debug 보강: hierarchical section 진단 정보 보존 (재스캔 금지)
# ---------------------------------------------------------------------------


def _hierarchical_multi_section_fixture() -> dict:
    def build_section_text(index: int) -> str:
        return (
            f"[{index:02d}호 컬러{index}] "
            f"정제수, 글리세린, 폴리부텐, 탤크 "
            f"이름{index}A 정제수, 글리세린, 폴리부텐, 탤크 "
            f"이름{index}B 정제수, 글리세린, 폴리부텐, 탤크"
        )

    raw_text = "\n".join(build_section_text(index) for index in range(1, 4))
    return {
        "product_id": "A000000258200",
        "options": [f"{index:02d}호 컬러{index}" for index in range(1, 4)],
        "raw_text": raw_text,
    }


def _get_parser_debug(monkeypatch, fixture: dict, product_id: str) -> dict:
    monkeypatch.setattr(main.settings, "environment", "development")
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_product_candidate",
        lambda source, external_product_id: _product(external_product_id),
    )
    monkeypatch.setattr(
        main.ingredient_repository,
        "get_cached_ingredients",
        lambda source, external_product_id, option_id="": None,
    )
    monkeypatch.setattr(
        main.product_option_extractor,
        "extract",
        lambda product_id, product_url: _extraction_result(fixture),
    )
    response = TestClient(main.app).get(f"/products/{product_id}/parser-debug")
    assert response.status_code == 200
    return response.json()


def test_hierarchical_section_keeps_formula_boundary_candidates_after_confirmation(
    monkeypatch,
) -> None:
    """hierarchical로 확정된 section은 raw_ingredient_text가 비어
    재스캔으로는 후보를 재현할 수 없다. 확정 당시 보존된 진단
    정보(FormulaBoundaryDiagnostic)가 formula_boundary_candidates로
    그대로 노출되어야 한다 - 더 이상 []가 아니다."""

    fixture = _hierarchical_multi_section_fixture()
    body = _get_parser_debug(monkeypatch, fixture, "A000000258200")

    assert body["shadow_document_format"] == (
        "hierarchical_option_internal_sections"
    )
    sections_by_header = {
        section["raw_header"]: section for section in body["shadow_sections"]
    }
    for index in range(1, 4):
        section = sections_by_header[f"[{index:02d}호 컬러{index}]"]
        assert section["nested_formula_count"] == 3
        candidates = section["formula_boundary_candidates"]
        # 첫 body(어떤 boundary도 열지 않은 section 시작 구간) 1개 +
        # 두 개의 경계("이름NA", "이름NB")가 body마다 보존된다.
        assert len(candidates) == 3
        for candidate in candidates:
            assert candidate["decision"] == "confirmed"
            assert candidate["body_ingredient_count"] >= 4
            assert candidate["body_exact_known_count"] >= 4
        boundary_texts = {
            c["boundary_text"] for c in candidates if c["boundary_text"]
        }
        assert boundary_texts == {f"이름{index}A", f"이름{index}B"}
        opened_boundaries = [c for c in candidates if c["chunk_index"] != -1]
        for candidate in opened_boundaries:
            assert candidate["right_ingredient"] == "정제수"
        assert section["ambiguous_boundaries"] == []


def test_hierarchical_section_not_reported_as_trailing_description_candidate(
    monkeypatch,
) -> None:
    """hierarchical section은 ingredients가 비어 있는 게 정상 구조다
    (성분이 nested formula로 옮겨감). '성분 body 없는 header'처럼
    trailing_description_candidates에 잘못 나타나지 않아야 한다."""

    fixture = _hierarchical_multi_section_fixture()
    body = _get_parser_debug(monkeypatch, fixture, "A000000258200")

    assert body["shadow_document_format"] == (
        "hierarchical_option_internal_sections"
    )
    assert body["trailing_description_candidates"] == []


def test_hierarchical_diagnostics_fix_does_not_change_parsing_result(
    monkeypatch,
) -> None:
    """진단 정보 보존/노출 방식 변경이 실제 parsing 결과(구조 판정,
    canonical mapping status)에는 아무 영향을 주지 않는다 - 여전히
    3개 section 전부 unsupported로 남는다."""

    fixture = _hierarchical_multi_section_fixture()
    body = _get_parser_debug(monkeypatch, fixture, "A000000258200")

    assert body["shadow_status_counts"] == {
        "matched": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "unsupported": 3,
    }
    for section in body["shadow_sections"]:
        assert section["mapping_status"] == "unsupported"
        assert section["mapped_option_name"] is None
    assert body["shadow_orphan_count"] == 0

    # A000000226241 flat 구조 회귀: annotation/component_group 동작은
    # 변경되지 않는다.
    wakemake_fixture = _load_fixture(TRAILING_DESCRIPTION_FIXTURE_PATH)
    wakemake_body = _get_parser_debug(
        monkeypatch, wakemake_fixture, "A000000226241"
    )
    assert wakemake_body["shadow_document_format"] == "option_full_sections"
    assert len(wakemake_body["trailing_description_candidates"]) == 2
    assert wakemake_body["shadow_status_counts"]["matched"] == 2

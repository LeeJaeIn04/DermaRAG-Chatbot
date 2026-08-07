import json
from pathlib import Path

from app.products.option_parser import (
    _find_formula_boundary_splits,
    build_ingredient_sections,
    canonicalize_product_options,
    extract_boundary_candidates,
    make_product_option,
    shadow_parse_option_ingredient_sections,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
WAKEMAKE_FIXTURE_PATH = (
    FIXTURES_DIR
    / "shadow_wakemake_lip_mixed_bracket_typo_A000000226241.json"
)
PALETTE_FIXTURE_PATH = (
    FIXTURES_DIR / "shadow_palette_hierarchical_numbered_formula.json"
)
TRAILING_DESCRIPTION_FIXTURE_PATH = (
    FIXTURES_DIR
    / "shadow_wakemake_lip_trailing_description_A000000226241.json"
)


def _load_fixture(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _shadow_parse(fixture: dict):
    options = [make_product_option(name) for name in fixture["options"]]
    return shadow_parse_option_ingredient_sections(
        fixture["raw_text"], options
    )


# ---------------------------------------------------------------------------
# Fixture 1: 웨이크메이크 립 - '[옵션명]'/'{옵션명]' 혼재 flat 문서
# ---------------------------------------------------------------------------


def test_wakemake_fixture_product_id_matches_real_case() -> None:
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    assert fixture["product_id"] == "A000000226241"


def test_wakemake_fixture_shadow_document_format_is_flat() -> None:
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    assert result.document_format == "option_full_sections"


def test_wakemake_fixture_headers_extracted_as_separate_sections() -> None:
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    assert len(result.sections) >= 3
    for section in result.sections:
        assert len(section.ingredients) >= 3


def test_wakemake_fixture_malformed_curly_bracket_preserved_verbatim() -> (
    None
):
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    raw_headers = [section.raw_header for section in result.sections]
    assert "{19호 쉘 피치]" in raw_headers
    assert "{21호 그레이스]" in raw_headers
    assert "[20호 플레저]" in raw_headers


def test_wakemake_fixture_first_and_last_section_boundary_ingredients() -> (
    None
):
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    first_section = result.sections[0]
    last_section = result.sections[-1]
    assert first_section.ingredients[0] == "다이아이소스테아릴말레이트"
    assert last_section.ingredients[-1] == "향료"


def test_wakemake_fixture_no_nested_subsections() -> None:
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    for section in result.sections:
        assert section.subsections == ()


def test_wakemake_fixture_maps_uniquely_with_no_ambiguous() -> None:
    fixture = _load_fixture(WAKEMAKE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    assert result.matched_count == 3
    assert result.ambiguous_count == 0
    assert result.unmatched_count == 0
    assert result.unsupported_count == 0
    for mapping in result.mappings:
        assert mapping.mapping_status == "matched"
        assert mapping.mapping_method == "shadow_exact_normalized_label"


# ---------------------------------------------------------------------------
# Fixture 2: 섀도우 팔레트 - 단일 top-level + '1.'~'9.' 계층형 문서
# ---------------------------------------------------------------------------


def test_palette_fixture_shadow_document_format_is_hierarchical() -> None:
    fixture = _load_fixture(PALETTE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    assert result.document_format == "hierarchical_option_internal_sections"


def test_palette_fixture_single_top_level_with_nine_subsections() -> None:
    fixture = _load_fixture(PALETTE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    assert len(result.sections) == 1
    top_section = result.sections[0]
    assert top_section.raw_header == "[01 데이지]"
    assert len(top_section.subsections) == 9


def test_palette_fixture_subsections_are_not_merged() -> None:
    fixture = _load_fixture(PALETTE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    subsections = result.sections[0].subsections
    assert [subsection.label for subsection in subsections] == [
        f"{number}." for number in range(1, 10)
    ]
    # 각 formula만의 고유 성분(마이카/탤크/디메치콘/향료 외 안료)이
    # 서로 다른 subsection에만 존재해야 하나의 ingredient list로
    # 병합되지 않았음을 확인할 수 있다.
    assert "적색산화철(CI 77491)" in subsections[1].ingredients
    assert "적색산화철(CI 77491)" not in subsections[0].ingredients
    assert "적색202호" in subsections[8].ingredients
    assert "적색202호" not in subsections[0].ingredients
    for subsection in subsections:
        assert len(subsection.ingredients) >= 4


def test_palette_fixture_ci_notation_preserved_in_subsections() -> None:
    fixture = _load_fixture(PALETTE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    first_subsection = result.sections[0].subsections[0]
    assert "마이카(CI 77019)" in first_subsection.ingredients


def test_palette_fixture_canonical_option_is_unsupported_not_ready() -> None:
    fixture = _load_fixture(PALETTE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    assert result.matched_count == 0
    assert len(result.mappings) == 1
    mapping = result.mappings[0]
    assert mapping.mapping_status == "unsupported"
    assert mapping.section_index is None


# ---------------------------------------------------------------------------
# 추가 검증
# ---------------------------------------------------------------------------


def test_mica_with_space_before_ci_notation_preserved_as_one_ingredient() -> (
    None
):
    sections = build_ingredient_sections(
        "정제수, 마이카 (CI 77019), 탤크"
    )
    assert len(sections) == 1
    assert "마이카 (CI 77019)" in sections[0].ingredients


def test_alphanumeric_style_header_boundary_preserved_as_single_text() -> (
    None
):
    candidates = extract_boundary_candidates(
        "정제수, 02 플레저, 글리세린"
    )
    text_candidates = [
        candidate
        for candidate in candidates
        if candidate.boundary_text == "02 플레저"
    ]
    assert len(text_candidates) == 1
    assert text_candidates[0].kind == "text"


def test_single_numbered_dot_boundary_does_not_confirm_nested_formula() -> (
    None
):
    raw_text = (
        "[단일옵션] 정제수, 글리세린, 2. 다이머티콘처럼 보이는 표기, 향료"
    )
    options = [make_product_option("단일옵션")]
    canonical = canonicalize_product_options(options)
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert result.document_format == "option_full_sections"
    assert len(result.sections) == 1
    assert result.sections[0].subsections == ()


def test_unknown_ingredient_token_is_not_misread_as_header() -> None:
    sections = build_ingredient_sections(
        "정제수, 언노운신물질XYZ123, 글리세린"
    )
    assert len(sections) == 1
    assert sections[0].raw_header == ""
    assert "언노운신물질XYZ123" in sections[0].ingredients


def test_duplicate_adjacent_header_blocks_matched_mapping_as_ambiguous() -> (
    None
):
    raw_text = (
        "[19호] 정제수, 글리세린, 향료\n"
        "[19호] 정제수, 다이머틸실록세인, 향료"
    )
    options = [make_product_option("19호")]
    canonical = canonicalize_product_options(options)
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert result.document_format == "option_full_sections"
    assert result.matched_count == 0
    assert result.ambiguous_count == 1
    assert result.mappings[0].mapping_status == "ambiguous"
    assert (
        result.mappings[0].mapping_method
        == "shadow_duplicate_or_colliding_header"
    )


def test_orphan_unmatched_ambiguous_counts_are_tallied_correctly() -> None:
    raw_text = (
        "[아이템A] 정제수, 글리세린, 향료\n"
        "[아이템A] 정제수, 다이머틸실록세인, 향료\n"
        "[미확인헤더] 정제수, 글리세린, 향료"
    )
    options = [
        make_product_option("아이템A"),
        make_product_option("아이템B"),
    ]
    canonical = canonicalize_product_options(options)
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert result.document_format == "option_full_sections"
    assert result.matched_count == 0
    assert result.ambiguous_count == 1
    assert result.unmatched_count == 1
    assert result.orphan_section_count == 1

    statuses_by_option = {
        mapping.option_name: mapping.mapping_status
        for mapping in result.mappings
    }
    assert statuses_by_option["아이템A"] == "ambiguous"
    assert statuses_by_option["아이템B"] == "unmatched"


# ---------------------------------------------------------------------------
# 규칙 1: 문자열형 내부 formula (ingredient dictionary exact match)
# ---------------------------------------------------------------------------


def test_general_chunk_needs_exact_known_left_and_right_ingredients() -> (
    None
):
    """일반 chunk는 [왼쪽 성분][중간 문자열][오른쪽 성분] exact match만
    허용한다. 유일한 분할 하나만 나오면 그게 BoundaryCandidate다."""

    splits = _find_formula_boundary_splits(
        ["향료", "코랄글로우", "정제수"],
        has_left_ingredient=True,
    )
    assert splits == [(1, 2)]


def test_ambiguous_multi_way_split_is_not_a_boundary_candidate() -> None:
    """같은 chunk에서 복수 분할이 나오면 ambiguous로 남고 유일한
    후보로 확정하지 않는다."""

    splits = _find_formula_boundary_splits(
        ["정제수", "미확인단어", "글리세린", "향료"],
        has_left_ingredient=True,
    )
    assert len(splits) >= 2


def test_ambiguous_boundary_forces_needs_review_not_flat() -> None:
    """chunk 하나가 ambiguous하면 document를 flat으로 강제하지 않고
    needs_review로 남긴다."""

    raw_text = (
        "[01 테스트] 정제수, 글리세린, 폴리부텐, "
        "향료 이름1 정제수, "
        "정제수 미확인단어 글리세린 향료, "
        "트라이에틸헥사노인, 적색201호"
    )
    canonical = canonicalize_product_options(
        [make_product_option("01 테스트")]
    )
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert result.document_format == "needs_review"
    assert result.mappings[0].mapping_status == "unsupported"


def test_single_boundary_candidate_does_not_confirm_nested_formula() -> (
    None
):
    """같은 top-level section에서 후보가 1개뿐이면(최소 2개 미만)
    nested formula로 확정하지 않고 flat으로 남는다."""

    raw_text = (
        "[01 테스트] 정제수, 글리세린, 폴리부텐, "
        "향료 이름1 정제수, 글리세린, "
        "트라이에틸헥사노인, 적색201호"
    )
    canonical = canonicalize_product_options(
        [make_product_option("01 테스트")]
    )
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert result.document_format == "option_full_sections"
    assert result.sections[0].subsections == ()


def test_formula_body_under_four_known_ingredients_forces_needs_review() -> (
    None
):
    """유일한 분할 후보가 2개 이상이어도 formula body의 exact-known
    성분이 4개 미만이면 hierarchical로 확정하지 않고 needs_review로
    남긴다."""

    raw_text = (
        "[01 테스트] 정제수, "
        "향료 이름1 정제수, 글리세린, "
        "폴리부텐 이름2 정제수, 글리세린, "
        "트라이에틸헥사노인, 적색201호"
    )
    canonical = canonicalize_product_options(
        [make_product_option("01 테스트")]
    )
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert result.document_format == "needs_review"
    # needs_review로 남은 문자열형 formula는 판매 옵션 ready로
    # 매핑되지 않는다.
    assert result.matched_count == 0
    assert result.mappings[0].mapping_status == "unsupported"


def test_formula_body_boundary_three_fails_four_confirms() -> None:
    """exact-known 성분이 정확히 3개면 확정하지 않고, 정확히 4개면
    확정한다(hierarchical 최소 성분 수 경계값 검증)."""

    raw_three = (
        "[01 테스트] 정제수, 글리세린, 폴리부텐, "
        "향료 이름1 정제수, 글리세린, 폴리부텐 이름2 정제수, "
        "글리세린, 트라이에틸헥사노인, 적색201호"
    )
    canonical = canonicalize_product_options(
        [make_product_option("01 테스트")]
    )
    result_three = shadow_parse_option_ingredient_sections(
        raw_three, canonical
    )
    assert result_three.document_format == "needs_review"

    raw_four = (
        "[01 테스트] 정제수, 글리세린, 폴리부텐, 탤크, "
        "향료 이름1 정제수, 글리세린, 폴리부텐, "
        "탤크 이름2 정제수, 글리세린, 트라이에틸헥사노인, 적색201호"
    )
    result_four = shadow_parse_option_ingredient_sections(
        raw_four, canonical
    )
    assert (
        result_four.document_format
        == "hierarchical_option_internal_sections"
    )
    subsections = result_four.sections[0].subsections
    assert len(subsections) == 3
    assert len(subsections[1].ingredients) == 4
    assert len(subsections[2].ingredients) == 4


def test_dictionary_match_rejects_partial_and_number_only_strings() -> None:
    """ingredient dictionary는 exact match만 허용한다: 부분 문자열,
    접두어/접미어만 같은 문자열, 숫자만으로는 성분으로 인정하지
    않는다."""

    from app.products.ingredient_dictionary import is_known_ingredient

    assert is_known_ingredient("정제수") is True
    assert is_known_ingredient("정제수엑기스") is False
    assert is_known_ingredient("고정제수") is False
    assert is_known_ingredient("17") is False
    assert is_known_ingredient("") is False

    # 왼쪽 성분 자리에 숫자만 있으면 그 숫자는 성분으로 인정되지
    # 않으므로, 숫자를 "왼쪽 성분"으로 쓰는 분할은 나오지 않는다.
    # 이 chunk에는 콤마로 이미 분리된(왼쪽 성분이 없는) 해석만
    # 남고, 그 해석의 middle text에 "17"이 포함될 뿐 "17" 자체가
    # 성분으로 매칭되는 것은 아니다.
    splits = _find_formula_boundary_splits(
        ["17", "이름", "정제수"], has_left_ingredient=True
    )
    assert splits == [(0, 2)]
    assert is_known_ingredient(
        " ".join(["17", "이름", "정제수"][: splits[0][1]])
    ) is False


def test_numbered_dot_fallback_still_works_without_dictionary_support() -> (
    None
):
    """문자열형 formula 규칙(사전 exact match)이 적용되지 않는
    성분명(사전에 없음)이어도, 기존 '1.'~'N.' 번호 규칙은 그대로
    hierarchical을 확정한다(기존 규칙 회귀 없음)."""

    raw_text = (
        "[01 테스트]\n"
        "1. 가상성분에이, 가상성분비, 가상성분씨\n"
        "2. 가상성분에이, 가상성분디, 가상성분씨\n"
        "3. 가상성분에이, 가상성분이, 가상성분씨"
    )
    canonical = canonicalize_product_options(
        [make_product_option("01 테스트")]
    )
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert (
        result.document_format == "hierarchical_option_internal_sections"
    )
    assert result.structure_reason == "shadow_numbered_dot_formula_sequence"
    assert len(result.sections[0].subsections) == 3


def test_component_group_excluded_from_canonical_mapping_even_with_matching_name() -> (  # noqa: E501
    None
):
    """canonical 옵션 이름이 우연히 [증정]/[본품]/[리필]과 같아도
    component_group section은 매핑 대상도, orphan 집계 대상도
    되지 않는다."""

    raw_text = (
        "[19호 쉘 피치] 정제수, 글리세린, 마이카(CI 77019), 향료, "
        "[증정], 정제수, 글리세린, 탤크, 디메치콘"
    )
    canonical = canonicalize_product_options(
        [make_product_option("19호 쉘 피치"), make_product_option("증정")]
    )
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)

    statuses_by_option = {
        mapping.option_name: mapping.mapping_status
        for mapping in result.mappings
    }
    assert statuses_by_option["19 쉘 피치"] == "matched"
    # "증정" canonical 옵션은 component_group section이 매핑 후보에서
    # 빠지므로 대응하는 section이 없어 unmatched로 남는다(잘못
    # matched되지 않는다).
    assert statuses_by_option["증정"] == "unmatched"
    assert result.orphan_section_count == 0


def test_confirmed_string_formula_boundaries_do_not_overlap() -> None:
    """확정된 각 formula body의 시작/끝 구간이 서로 겹치지 않는다."""

    fixture = _load_fixture(
        FIXTURES_DIR
        / "shadow_string_formula_prefix_candidates_A000000258200.json"
    )
    canonical = canonicalize_product_options(
        [make_product_option(name) for name in fixture["options"]]
    )
    result = shadow_parse_option_ingredient_sections(
        fixture["raw_text"], canonical
    )
    assert result.document_format == "hierarchical_option_internal_sections"
    subsections = result.sections[0].subsections
    spans = [(sub.start_index, sub.end_index) for sub in subsections]
    for previous, current in zip(spans, spans[1:]):
        assert previous[1] <= current[0]


# ---------------------------------------------------------------------------
# 규칙 2: bracket section 분류 (ingredient_section / component_group /
# ambiguous_annotation_candidate)
# ---------------------------------------------------------------------------


def test_bracket_header_with_enough_known_ingredients_is_ingredient_section() -> (  # noqa: E501
    None
):
    raw_text = (
        "[19호 쉘 피치] 정제수, 글리세린, 마이카(CI 77019), 향료"
    )
    canonical = canonicalize_product_options(
        [make_product_option("19호 쉘 피치")]
    )
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert result.sections[0].section_kind == "ingredient_section"
    assert result.matched_count == 1


def test_gift_and_component_labels_become_component_group_and_unmapped() -> (
    None
):
    """[증정]/[본품]/[리필] 뒤 성분이 4개 이상이면 component_group으로
    분류하고 판매 옵션과 매핑하지 않는다."""

    raw_text = (
        "[19호 쉘 피치] 정제수, 글리세린, 마이카(CI 77019), 향료, "
        "[증정], 정제수, 글리세린, 탤크, 디메치콘"
    )
    canonical = canonicalize_product_options(
        [make_product_option("19호 쉘 피치")]
    )
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    assert result.document_format == "option_full_sections"

    kinds_by_header = {
        section.raw_header: section.section_kind
        for section in result.sections
    }
    assert kinds_by_header["[19호 쉘 피치]"] == "ingredient_section"
    assert kinds_by_header["[증정]"] == "component_group"

    # component_group은 판매 옵션과 매핑되지 않고, 다른 안전한
    # section의 매핑도 막지 않는다.
    assert result.matched_count == 1
    assert result.mappings[0].mapping_status == "matched"
    assert result.orphan_section_count == 0


def test_trailing_bracket_with_no_body_at_document_end_is_annotation_candidate() -> (  # noqa: E501
    None
):
    fixture = _load_fixture(TRAILING_DESCRIPTION_FIXTURE_PATH)
    canonical = canonicalize_product_options(
        [make_product_option(name) for name in fixture["options"]]
    )
    result = shadow_parse_option_ingredient_sections(
        fixture["raw_text"], canonical
    )

    kinds_by_header = {
        section.raw_header: section.section_kind
        for section in result.sections
    }
    assert (
        kinds_by_header["[실제 색상과 다를 수 있습니다]"]
        == "ambiguous_annotation_candidate"
    )
    # annotation 후보는 삭제되지 않고 section 목록에 그대로 보존된다.
    assert len(result.sections) == 4


def test_annotation_candidate_is_excluded_from_ingredient_mapping() -> None:
    fixture = _load_fixture(TRAILING_DESCRIPTION_FIXTURE_PATH)
    canonical = canonicalize_product_options(
        [make_product_option(name) for name in fixture["options"]]
    )
    result = shadow_parse_option_ingredient_sections(
        fixture["raw_text"], canonical
    )

    # 후보 문구 자체는 어떤 section의 ingredients 목록에도 나타나지
    # 않는다.
    for section in result.sections:
        assert "[실제 색상과 다를 수 있습니다]" not in section.ingredients


def test_annotation_candidate_does_not_block_other_safe_sections() -> None:
    """후보 하나(annotation) 때문에 다른 안전한 section이 orphan으로
    밀리거나 매핑이 막히지 않는다."""

    fixture = _load_fixture(TRAILING_DESCRIPTION_FIXTURE_PATH)
    canonical = canonicalize_product_options(
        [make_product_option(name) for name in fixture["options"]]
    )
    result = shadow_parse_option_ingredient_sections(
        fixture["raw_text"], canonical
    )

    assert result.matched_count == 2
    assert result.document_format == "option_full_sections"
    for mapping in result.mappings:
        assert mapping.mapping_status == "matched"


# ---------------------------------------------------------------------------
# 실상품 A000000258200 디버그: 문자열형 formula 후보 0개 버그 진단·고정
# ---------------------------------------------------------------------------


REAL_PRODUCT_CHUNKS = [
    "소프트 레이 Soft Ray 탤크",
    "흑색산화철 아이시 알로이 Icy Alloy 탤크",
    "문 샌드 Moon Sand 탤크",
    "핑크 페탈 Pink Petal 탤크",
    "피치 솔라 Peach Solar 마이카",
]


def test_dictionary_exact_match_for_real_product_terms() -> None:
    from app.products.ingredient_dictionary import is_known_ingredient

    assert is_known_ingredient("탤크") is True
    assert is_known_ingredient("마이카") is True
    assert is_known_ingredient("흑색산화철") is True
    assert is_known_ingredient("C20-24알킬다이메티콘") is True


def test_real_product_chunks_each_produce_exactly_one_boundary_candidate() -> (  # noqa: E501
    None
):
    """A000000258200 실상품 debug에서 후보 0개로 나온 원인 진단.

    각 chunk는 오른쪽 성분(탤크/마이카)은 exact match로 확인되지만,
    콤마가 이미 이전 formula와 깨끗이 분리해 둔 chunk("소프트 레이
    Soft Ray 탤크" 등)에는 "왼쪽 성분"이 존재하지 않는다. 예전
    구현은 첫 chunk가 아니면 왼쪽 성분이 반드시 있어야 한다고
    강제해 이런 chunk를 전부 탈락시켰다(후보 0개). 수정 후에는
    왼쪽 성분이 있는 분할이 하나도 없을 때만 왼쪽 없는
    [middle][right] 분할을 대신 채택하므로, 다섯 chunk 모두
    유일한 후보를 만든다.
    """

    expected = {
        "소프트 레이 Soft Ray 탤크": (0, 4),
        "흑색산화철 아이시 알로이 Icy Alloy 탤크": (1, 5),
        "문 샌드 Moon Sand 탤크": (0, 4),
        "핑크 페탈 Pink Petal 탤크": (0, 4),
        "피치 솔라 Peach Solar 마이카": (0, 4),
    }
    for chunk, expected_split in expected.items():
        splits = _find_formula_boundary_splits(
            chunk.split(), has_left_ingredient=True
        )
        assert splits == [expected_split], chunk


def test_real_product_chunk_without_left_ingredient_has_no_left_boundary() -> (  # noqa: E501
    None
):
    """왼쪽에 exact-known 성분이 전혀 없는 chunk는 왼쪽 없는 분할만
    쓴다 - '소프트 레이 Soft Ray'라는 색상명이 왼쪽 성분으로
    잘못 인정되는 일은 없다(기준 완화 아님)."""

    from app.products.ingredient_dictionary import is_known_ingredient

    words = "소프트 레이 Soft Ray 탤크".split()
    left_end, right_start = _find_formula_boundary_splits(
        words, has_left_ingredient=True
    )[0]
    assert left_end == 0
    assert is_known_ingredient(" ".join(words[:right_start])) is False
    assert is_known_ingredient(" ".join(words[right_start:])) is True


def test_real_product_chunk_with_left_ingredient_prefers_with_left_split() -> (  # noqa: E501
    None
):
    """왼쪽에 exact-known 성분("흑색산화철")이 있으면 그 분할을
    우선 채택하고, 왼쪽 없는 해석과 섞여 ambiguous가 되지
    않는다."""

    words = "흑색산화철 아이시 알로이 Icy Alloy 탤크".split()
    splits = _find_formula_boundary_splits(words, has_left_ingredient=True)
    assert splits == [(1, 5)]


def test_body_under_four_known_ingredients_is_needs_review_not_hierarchical() -> (  # noqa: E501
    None
):
    """후보가 잡혀도(2개 이상) 각 formula body의 exact-known 성분이
    4개 미만이면 hierarchical으로 확정하지 않고 needs_review로
    남긴다 - 기준을 완화해 억지로 hierarchical을 만들지 않는다."""

    raw_text = (
        "[01 팔레트] "
        + ", ".join(REAL_PRODUCT_CHUNKS[:2])
    )
    canonical = canonicalize_product_options(
        [make_product_option("01 팔레트")]
    )
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)
    # formula body 성분이 1~2개뿐이므로(4개 미만) 확정하지 않는다.
    assert result.document_format != "hierarchical_option_internal_sections"


# ---------------------------------------------------------------------------
# 실상품 A000000226241 디버그: 마지막 성분에 붙은 trailing bracket 분리
# ---------------------------------------------------------------------------


TRAILING_BRACKET_SUFFIX_FIXTURE_PATH = (
    FIXTURES_DIR
    / "shadow_wakemake_lip_trailing_bracket_suffix_A000000226241.json"
)


def test_trailing_bracket_suffix_is_split_from_last_ingredient() -> None:
    fixture = _load_fixture(TRAILING_BRACKET_SUFFIX_FIXTURE_PATH)
    canonical = canonicalize_product_options(
        [make_product_option(name) for name in fixture["options"]]
    )
    result = shadow_parse_option_ingredient_sections(
        fixture["raw_text"], canonical
    )

    section = next(
        section
        for section in result.sections
        if section.raw_header == "[20호 플레저]"
    )
    assert section.ingredients[-1] == "글리세릴카프릴레이트"
    assert "[헬시 글로우 밤 스틱 기획(2024.10)]" not in section.ingredients

    assert len(section.annotation_candidates) == 1
    candidate = section.annotation_candidates[0]
    assert candidate.text == "[헬시 글로우 밤 스틱 기획(2024.10)]"
    # 원문 위치가 정확히 보존된다.
    assert (
        fixture["raw_text"][candidate.start_index:candidate.end_index]
        == candidate.text
    )


def test_trailing_bracket_suffix_does_not_block_other_option_sections() -> (
    None
):
    fixture = _load_fixture(TRAILING_BRACKET_SUFFIX_FIXTURE_PATH)
    canonical = canonicalize_product_options(
        [make_product_option(name) for name in fixture["options"]]
    )
    result = shadow_parse_option_ingredient_sections(
        fixture["raw_text"], canonical
    )

    assert result.document_format == "option_full_sections"
    assert result.matched_count == 2
    for mapping in result.mappings:
        assert mapping.mapping_status == "matched"


# ---------------------------------------------------------------------------
# 실상품 A000000258200 재검증: 여러 top-level section 각각의 문자열형
# 내부 formula가 독립적으로 평가되는지 진단·고정
# ---------------------------------------------------------------------------


def _multi_section_string_formula_raw_text(count: int = 3) -> str:
    def build_section_text(index: int) -> str:
        return (
            f"[{index:02d}호 컬러{index}] "
            f"정제수, 글리세린, 폴리부텐, 탤크 "
            f"이름{index}A 정제수, 글리세린, 폴리부텐, 탤크 "
            f"이름{index}B 정제수, 글리세린, 폴리부텐, 탤크"
        )

    return "\n".join(
        build_section_text(index) for index in range(1, count + 1)
    )


def test_each_top_level_section_is_evaluated_independently_for_string_formula() -> (  # noqa: E501
    None
):
    """이전 버전은 top-level section이 하나일 때만
    _evaluate_string_formula_structure를 호출했다. 실상품처럼
    top-level section이 여러 개(여러 색상 옵션)이고 각각 내부에
    formula 반복 구조가 있으면, 예전에는 평가 자체가 스킵되어
    unmatched로만 남았다(nested_formula_count=0, document_format
    변화 없음). 이 테스트는 각 section이 실제로 독립 평가되고
    후보/body/exact-known 개수가 올바르게 계산됨을 고정한다.
    """

    from app.products.ingredient_dictionary import is_known_ingredient
    from app.products.option_parser import _evaluate_string_formula_structure

    raw_text = _multi_section_string_formula_raw_text(3)
    raw_sections = build_ingredient_sections(raw_text)
    assert len(raw_sections) == 3

    for section_index, section in enumerate(raw_sections, start=1):
        evaluation = _evaluate_string_formula_structure(section, raw_text)
        assert evaluation.outcome == "hierarchical"

        labels = [sub.label for sub in evaluation.subsections]
        assert labels == ["", f"이름{section_index}A", f"이름{section_index}B"]

        for subsection in evaluation.subsections:
            # 각 후보의 body 시작/끝 index가 실제 원문 구간과 일치한다.
            assert (
                raw_text[
                    subsection.start_index:subsection.end_index
                ].strip()
                == subsection.raw_text
            )
            # body exact-known ingredient 개수가 정책 최소치(4) 이상이다.
            known_count = sum(
                1
                for ingredient in subsection.ingredients
                if is_known_ingredient(ingredient)
            )
            assert known_count >= 4


def test_multi_section_document_confirms_hierarchical_for_all_qualifying_sections() -> (  # noqa: E501
    None
):
    """최종 structure decision: 여러 top-level section이 모두
    조건을 만족하면 문서 전체가 hierarchical로 확정되고, 각
    section이 자신의 subsections를 갖는다(서로 병합되지 않는다).
    canonical mapping은 unsupported로 남는다."""

    raw_text = _multi_section_string_formula_raw_text(3)
    options = [
        make_product_option(f"{index:02d}호 컬러{index}")
        for index in range(1, 4)
    ]
    canonical = canonicalize_product_options(options)
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)

    assert result.document_format == "hierarchical_option_internal_sections"
    assert len(result.sections) == 3
    for section in result.sections:
        assert len(section.subsections) == 3
        assert section.ingredients == ()

    assert result.matched_count == 0
    for mapping in result.mappings:
        assert mapping.mapping_status == "unsupported"


def test_one_section_needs_review_forces_whole_document_needs_review() -> (
    None
):
    """탈락 이유 고정: 두 번째 section은 formula body 성분이 2개뿐
    (exact-known 4개 미만)이라 needs_review로 평가된다. 첫 번째
    section은 조건을 만족하더라도, 다른 section이 애매하면 문서
    전체를 hierarchical로 확정하지 않고 needs_review로 남긴다
    (기준 완화 금지)."""

    from app.products.option_parser import _evaluate_string_formula_structure

    raw_text = (
        "[01호 컬러1] 정제수, 글리세린, 폴리부텐, 탤크 "
        "이름1A 정제수, 글리세린, 폴리부텐, 탤크 "
        "이름1B 정제수, 글리세린, 폴리부텐, 탤크\n"
        "[02호 컬러2] 정제수, 글리세린, "
        "이름2A 정제수, 글리세린, "
        "이름2B 정제수, 글리세린"
    )
    raw_sections = build_ingredient_sections(raw_text)
    assert len(raw_sections) == 2

    # 진단: section별 최종 평가와 탈락 이유
    first_evaluation = _evaluate_string_formula_structure(
        raw_sections[0], raw_text
    )
    second_evaluation = _evaluate_string_formula_structure(
        raw_sections[1], raw_text
    )
    assert first_evaluation.outcome == "hierarchical"
    # 두 번째 section은 formula body exact-known 성분이 2개뿐이라
    # (정제수, 글리세린) 최소 기준(4개) 미달로 needs_review다.
    assert second_evaluation.outcome == "needs_review"

    options = [
        make_product_option("01호 컬러1"),
        make_product_option("02호 컬러2"),
    ]
    canonical = canonicalize_product_options(options)
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)

    # 최종 structure decision: 부분 확정이 아니라 문서 전체가
    # needs_review로 남는다.
    assert result.document_format == "needs_review"
    assert result.matched_count == 0
    for mapping in result.mappings:
        assert mapping.mapping_status == "unsupported"


# ---------------------------------------------------------------------------
# 전체 회귀 검증: 기존 fixture 재사용 + A000000258200(6 section × 6
# nested formula) / A000000226241(matched 16 + component_group 3 +
# trailing annotation) 실상품 규모 재현
# ---------------------------------------------------------------------------


def test_hierarchical_top_level_ingredient_count_zero_means_moved_to_nested() -> (  # noqa: E501
    None
):
    """hierarchical로 확정된 section의 top-level ingredient_count=0은
    성분이 사라진 게 아니라 nested formula(subsections)로 옮겨간
    정상 구조임을 고정한다 - 팔레트 fixture 재사용."""

    fixture = _load_fixture(PALETTE_FIXTURE_PATH)
    result = _shadow_parse(fixture)
    top_section = result.sections[0]
    assert top_section.ingredients == ()
    total_nested_ingredients = sum(
        len(subsection.ingredients) for subsection in top_section.subsections
    )
    assert total_nested_ingredients > 0


def _many_sections_string_formula_raw_text(
    section_count: int, formula_count: int
) -> str:
    def build_section_text(section_index: int) -> str:
        def build_formula(formula_index: int) -> str:
            prefix = (
                "" if formula_index == 0 else f"이름{section_index}_{formula_index} "
            )
            return f"{prefix}정제수, 글리세린, 폴리부텐, 탤크"

        formulas = " ".join(
            build_formula(formula_index)
            for formula_index in range(formula_count)
        )
        return f"[{section_index:02d}호 컬러{section_index}] {formulas}"

    return "\n".join(
        build_section_text(section_index)
        for section_index in range(1, section_count + 1)
    )


def test_a000000258200_scale_six_sections_six_nested_formulas_each() -> None:
    """실상품 A000000258200 재검증 규모(6 section × nested formula 6개)를
    재현한다 - 모든 section이 독립적으로 hierarchical 확정되고, canonical
    매핑은 6개 전부 unsupported로 남는다(ready로 잘못 매핑되지 않는다)."""

    from app.products.ingredient_dictionary import is_known_ingredient

    raw_text = _many_sections_string_formula_raw_text(
        section_count=6, formula_count=6
    )
    options = [
        make_product_option(f"{index:02d}호 컬러{index}")
        for index in range(1, 7)
    ]
    canonical = canonicalize_product_options(options)
    result = shadow_parse_option_ingredient_sections(raw_text, canonical)

    assert result.document_format == "hierarchical_option_internal_sections"
    assert len(result.sections) == 6
    for section in result.sections:
        assert len(section.subsections) == 6
        assert section.ingredients == ()
        for subsection in section.subsections:
            known_count = sum(
                1
                for ingredient in subsection.ingredients
                if is_known_ingredient(ingredient)
            )
            assert known_count >= 4

    assert result.matched_count == 0
    assert len(result.mappings) == 6
    for mapping in result.mappings:
        assert mapping.mapping_status == "unsupported"


WAKEMAKE_FULL_REGRESSION_FIXTURE_PATH = (
    FIXTURES_DIR
    / "shadow_wakemake_lip_full_regression_A000000226241.json"
)


def test_a000000226241_scale_matched_16_component_group_3_trailing_annotation() -> (  # noqa: E501
    None
):
    """실상품 A000000226241 재검증 규모(matched 16 유지, component_group
    3개 제외, trailing annotation 분리)를 재현한다."""

    fixture = _load_fixture(WAKEMAKE_FULL_REGRESSION_FIXTURE_PATH)
    result = _shadow_parse(fixture)

    assert result.document_format == "option_full_sections"

    kinds = [section.section_kind for section in result.sections]
    assert kinds.count("component_group") == 3
    assert kinds.count("ambiguous_annotation_candidate") == 1
    assert kinds.count("ingredient_section") == 16

    # matched 16 유지 - component_group/annotation은 판매 옵션 매핑
    # 대상도, orphan 집계 대상도 아니다.
    assert result.matched_count == 16
    assert result.ambiguous_count == 0
    assert result.unmatched_count == 0
    assert result.orphan_section_count == 0
    for mapping in result.mappings:
        assert mapping.mapping_status == "matched"

    # trailing annotation 문구는 어떤 section의 ingredients에도
    # 섞여 들어가지 않는다(annotation candidate ingredient 혼입 0).
    annotation_text = "[실제 색상과 다를 수 있습니다]"
    for section in result.sections:
        assert annotation_text not in section.ingredients

    # component_group section의 성분도 다른 section과 병합되지 않는다
    # (formula body 병합 0) - 각자 자신의 4개 성분만 갖는다.
    for section in result.sections:
        if section.section_kind == "component_group":
            assert len(section.ingredients) == 4

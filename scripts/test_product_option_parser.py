from app.products.option_parser import (
    make_internal_option_key,
    make_product_option,
    normalize_option_label,
    normalize_text_with_indexes,
    split_option_ingredient_sections,
)


def _split(raw_text: str, names: list[str]):
    return split_option_ingredient_sections(
        raw_text,
        [make_product_option(name) for name in names],
    )


def test_splits_bracketed_shade_numbers() -> None:
    sections = _split(
        (
            "[19호] 정제수, 글리세린, 향료\n"
            "[21호] 정제수, 나이아신아마이드, 티타늄디옥사이드"
        ),
        ["19호", "21호"],
    )

    assert [section.mapping_status for section in sections] == [
        "matched",
        "matched",
    ]
    assert sections[0].ingredients == ["정제수", "글리세린", "향료"]
    assert sections[1].ingredients == [
        "정제수",
        "나이아신아마이드",
        "티타늄디옥사이드",
    ]


def test_splits_code_and_color_names_with_product_prefix() -> None:
    sections = _split(
        (
            "퍼펙트립스쇼킹립N01루비쇼킹 정제수, 황색4호, 향료\n"
            "퍼펙트립스쇼킹립N02토마토쇼킹 정제수, 적색104호, 향료"
        ),
        ["N01 루비쇼킹", "N02 토마토쇼킹"],
    )

    assert all(
        section.mapping_status == "matched"
        for section in sections
    )
    assert "적색104호" not in sections[0].ingredients
    assert "황색4호" not in sections[1].ingredients


def test_normalizes_spaces_brackets_hyphens_slashes_and_dots() -> None:
    expected = "21n아이보리"
    for value in (
        "21 N 아이보리",
        "[21N 아이보리]",
        "21-N/아이보리.",
    ):
        assert normalize_option_label(value) == expected


def test_normalized_index_maps_back_to_original_text() -> None:
    original = "[N01 루비-쇼킹]"
    indexed = normalize_text_with_indexes(original)
    start = indexed.normalized_text.index("n01루비쇼킹")
    original_start = indexed.original_indexes[start]
    original_end = indexed.original_indexes[
        start + len("n01루비쇼킹") - 1
    ]

    assert original[original_start:original_end + 1] == "N01 루비-쇼킹"


def test_preserves_parenthesized_ci_numbers() -> None:
    sections = _split(
        (
            "[19호] 황색4호 (CI 19140), "
            "적색104호의(1) (CI 45410), 정제수"
        ),
        ["19호"],
    )

    assert sections[0].ingredients == [
        "황색4호 (CI 19140)",
        "적색104호의(1) (CI 45410)",
        "정제수",
    ]


def test_bracket_configuration_phrase_is_ignored_for_header_matching() -> None:
    """대괄호 구성 문구는 헤더 후보 생성에서만 제거되고 원본은 보존된다."""

    sections = _split(
        (
            "#17N 정제수, 글리세린, 향료\n"
            "#21P 정제수, 나이아신아마이드, 티타늄디옥사이드"
        ),
        ["[본품+리필+파우치] 17N", "[본품+리필] 21P"],
    )

    assert [section.mapping_status for section in sections] == [
        "matched",
        "matched",
    ]
    assert sections[0].ingredients == ["정제수", "글리세린", "향료"]
    assert sections[1].ingredients == [
        "정제수",
        "나이아신아마이드",
        "티타늄디옥사이드",
    ]
    # 원본 option_name은 그대로 유지된다.
    assert sections[0].option_name == "[본품+리필+파우치] 17N"
    assert sections[1].option_name == "[본품+리필] 21P"


def test_stable_option_keys_are_distinct() -> None:
    first = make_internal_option_key(
        normalize_option_label("19호")
    )
    same = make_internal_option_key(
        normalize_option_label("[19호]")
    )
    second = make_internal_option_key(
        normalize_option_label("21호")
    )

    assert first == same
    assert first != second


def test_unmatched_option_is_not_marked_as_analyzable() -> None:
    sections = _split(
        "[19호] 정제수, 글리세린, 향료",
        ["19호", "21호"],
    )

    assert sections[0].mapping_status == "matched"
    assert sections[1].mapping_status == "unmatched"
    assert sections[1].ingredients == []


def test_repeated_header_is_ambiguous() -> None:
    sections = _split(
        (
            "[19호] 정제수, 글리세린\n"
            "[19호] 향료, 티타늄디옥사이드"
        ),
        ["19호"],
    )

    assert sections[0].mapping_status == "ambiguous"
    assert sections[0].ingredients == []


def test_identical_span_options_share_the_same_section() -> None:
    """같은 색상 코드를 가리키는 패키지 구성 옵션들은 헤더를 공유한다."""

    sections = _split(
        "17N 정제수, 글리세린, 향료",
        ["[본품+리필+파우치] 17N", "[본품+리필] 17N"],
    )

    assert [section.mapping_status for section in sections] == [
        "matched",
        "matched",
    ]
    assert sections[0].matched_header == sections[1].matched_header == "17N"
    assert (
        sections[0].ingredients
        == sections[1].ingredients
        == ["정제수", "글리세린", "향료"]
    )


def test_partial_overlap_between_different_options_is_ambiguous() -> None:
    """구간 경계가 서로 다르게 겹치면 여전히 ambiguous로 남는다."""

    sections = _split(
        "머리말, 21N아이보리 정제수, 글리세린, 향료",
        ["21N 아이보리", "N 아이보리"],
    )

    assert all(
        section.mapping_status == "ambiguous"
        for section in sections
    )


def test_naming_cushion_five_shade_headers_are_split_independently() -> None:
    names = ["17Y 내추럴", "19N 내추럴", "21Y 내추럴", "21P 내추럴", "23Y 내추럴"]
    sections = _split(
        (
            "17Y 내추럴 정제수, 사이클로펜타실록세인, 티타늄디옥사이드\n"
            "19N 내추럴 정제수, 나이아신아마이드, 마이카\n"
            "21Y 내추럴 정제수, 글리세린, 알루미나\n"
            "21P 내추럴 정제수, 다이메티콘, 실리카\n"
            "23Y 내추럴 정제수, 향료, 산화철"
        ),
        names,
    )

    assert [section.mapping_status for section in sections] == [
        "matched"
    ] * 5
    assert sections[0].ingredients == [
        "정제수",
        "사이클로펜타실록세인",
        "티타늄디옥사이드",
    ]
    assert sections[1].ingredients == [
        "정제수",
        "나이아신아마이드",
        "마이카",
    ]
    assert sections[2].ingredients == [
        "정제수",
        "글리세린",
        "알루미나",
    ]
    assert sections[3].ingredients == [
        "정제수",
        "다이메티콘",
        "실리카",
    ]
    assert sections[4].ingredients == [
        "정제수",
        "향료",
        "산화철",
    ]
    keys = {section.internal_option_key for section in sections}
    assert len(keys) == 5

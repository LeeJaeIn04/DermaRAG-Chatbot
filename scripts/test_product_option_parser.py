import json
from pathlib import Path

from app.products.option_parser import (
    canonicalize_product_options,
    make_internal_option_key,
    make_product_option,
    normalize_option_label,
    normalize_option_mapping_key,
    normalize_text_with_indexes,
    split_option_ingredient_sections,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / (
    "product_option_mapping_A000000241210.json"
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


def test_mapping_key_normalizes_shade_ho_and_spacing() -> None:
    expected = "23누카다미아"
    assert normalize_option_mapping_key("23호 누카다미아") == expected
    assert normalize_option_mapping_key("23 호 누카다미아") == expected
    assert normalize_option_mapping_key("23호") == "23"


def test_mapping_key_removes_only_verified_promotion_prefixes() -> None:
    expected = "23누카다미아"
    assert normalize_option_mapping_key("[기획] 23호 누카다미아") == expected
    assert normalize_option_mapping_key("단품/23호 누카다미아") == expected
    assert normalize_option_mapping_key("[NEW] 23호 누카다미아") == expected


def test_mapping_key_removes_verified_package_and_promotion_tokens() -> None:
    assert normalize_option_mapping_key("[본품+리필] 17N") == "17n"
    assert normalize_option_mapping_key("[마블컬렉션] 10호 베어로맨스") == (
        "10베어로맨스"
    )
    assert normalize_option_mapping_key("421호 로즐린 단품") == "421로즐린"
    # 실제 shade label을 담은 대괄호는 package token으로 지우지 않는다.
    assert normalize_option_mapping_key("[3C 웨딩피치]") == "3c웨딩피치"


def test_package_variants_share_one_canonical_option() -> None:
    canonical = canonicalize_product_options(
        [
            make_product_option("[본품+리필+파우치] 17N"),
            make_product_option("[본품] 17N"),
            make_product_option("[기획] 17N"),
        ]
    )

    assert len(canonical) == 1
    assert canonical[0].option_name == "17N"
    assert canonical[0].source_option_names == [
        "[본품+리필+파우치] 17N",
        "[본품] 17N",
        "[기획] 17N",
    ]


def test_mapping_key_preserves_ho_inside_general_words() -> None:
    assert normalize_option_mapping_key("호호바오일") == "호호바오일"


def test_mapping_matches_safe_shade_name_variants() -> None:
    for option_name, raw_header in (
        ("23호 누카다미아", "23 누카다미아"),
        ("23 호 누카다미아", "23호 누카다미아"),
        ("[기획] 23호 누카다미아", "23 누카다미아"),
        ("단품/23호 누카다미아", "23 누카다미아"),
    ):
        section = _split(
            f"{raw_header} 정제수, 글리세린",
            [option_name],
        )[0]
        assert section.mapping_status == "matched"


def test_numeric_code_does_not_match_a_different_color_name() -> None:
    section = _split(
        "23 피치 피치 미 정제수, 글리세린",
        ["23호 누카다미아"],
    )[0]
    assert section.mapping_status == "unmatched"


def test_duplicate_mapping_keys_merge_into_one_canonical_option() -> None:
    options = [
        make_product_option(name, source_option_id=str(index))
        for index, name in enumerate(
            [
                "[기획] 23호 누카다미아",
                "단품/23 누카다미아",
                "23호 누카다미아",
            ]
        )
    ]
    canonical = canonicalize_product_options(options)
    assert len(canonical) == 1
    assert canonical[0].option_name == "23 누카다미아"
    assert canonical[0].raw_option_name == "[기획] 23호 누카다미아"
    assert canonical[0].source_option_names == [
        "[기획] 23호 누카다미아",
        "단품/23 누카다미아",
        "23호 누카다미아",
    ]
    assert canonical[0].source_option_ids == ["0", "1", "2"]

    sections = _split(
        "23 누카다미아 정제수, 글리세린",
        [option.raw_option_name for option in options],
    )
    assert len(sections) == 1
    assert sections[0].mapping_status == "matched"


def test_different_mapping_keys_and_same_number_stay_separate() -> None:
    canonical = canonicalize_product_options(
        [
            make_product_option("23호 누카다미아"),
            make_product_option("23호 베어피그"),
            make_product_option("24호 누카다미아"),
        ]
    )
    assert [option.normalized_name for option in canonical] == [
        "23누카다미아",
        "23베어피그",
        "24누카다미아",
    ]


def test_canonical_groups_do_not_cross_product_collection_calls() -> None:
    first = canonicalize_product_options(
        [make_product_option("23호 누카다미아", source_option_id="first")]
    )
    second = canonicalize_product_options(
        [make_product_option("23호 누카다미아", source_option_id="second")]
    )
    assert first[0].source_option_ids == ["first"]
    assert second[0].source_option_ids == ["second"]


# ---------------------------------------------------------------------------
# Step 2 보완: 빈 정규화 옵션명(mapping_key)에서도 internal_option_key가
# 유일해야 하고, production/shadow가 같은 canonical_options을 그대로
# 써서 동일한 id를 얻어야 한다.
# ---------------------------------------------------------------------------


def test_empty_mapping_key_options_get_unique_internal_option_keys() -> (
    None
):
    """'[기획]'/'[단품]'/'[증정]'처럼 promotion 문구만 있는 옵션명은
    mapping_key가 빈 문자열로 정규화된다(별도 canonical 옵션으로
    남아야 함). 이런 옵션이 여러 개 있어도 internal_option_key는
    canonicalize_product_options 안에서 서로 겹치지 않아야 한다."""

    options = [
        make_product_option("[기획]"),
        make_product_option("[단품]"),
        make_product_option("[증정]"),
    ]
    assert [
        normalize_option_mapping_key(option.raw_option_name)
        for option in options
    ] == ["", "", ""]

    canonical = canonicalize_product_options(options)
    assert len(canonical) == 3
    keys = [option.internal_option_key for option in canonical]
    assert len(set(keys)) == 3


def test_empty_mapping_key_option_prefers_source_option_id_for_key() -> (
    None
):
    """source id가 있으면 그 값을 우선 써서 키를 만들고, 없으면
    원본 index를 시드로 쓴다 - 둘 다 항상 서로 다른 값을 낸다."""

    with_source_id = canonicalize_product_options(
        [make_product_option("[기획]", source_option_id="external-1")]
    )
    without_source_id = canonicalize_product_options(
        [make_product_option("[기획]")]
    )
    assert (
        with_source_id[0].internal_option_key
        != without_source_id[0].internal_option_key
    )

    # 같은 source id를 쓰면 항상 같은 키가 나온다(결정적).
    again_with_source_id = canonicalize_product_options(
        [make_product_option("[기획]", source_option_id="external-1")]
    )
    assert (
        with_source_id[0].internal_option_key
        == again_with_source_id[0].internal_option_key
    )


def test_duplicate_normalized_names_still_share_one_deterministic_key() -> (
    None
):
    """정규화하면 같은 이름이 되는 옵션들(중복)은 여전히 하나의
    canonical 옵션으로 병합되고, 그 key는 항상 결정적이다."""

    options = [
        make_product_option("[기획] 23호 누카다미아"),
        make_product_option("단품/23 누카다미아"),
        make_product_option("23호 누카다미아"),
    ]
    canonical = canonicalize_product_options(options)
    assert len(canonical) == 1
    assert canonical[0].internal_option_key == make_internal_option_key(
        normalize_option_mapping_key("23호 누카다미아")
    )


def test_production_and_shadow_use_identical_option_id_from_canonicalize() -> (  # noqa: E501
    None
):
    """canonicalize_product_options가 확정한 internal_option_key를
    production/shadow가 재계산 없이 그대로 쓴다는 것을, 실제
    parse_option_full_sections/shadow_parse_option_ingredient_sections
    호출 결과로 직접 확인한다(빈 mapping_key 옵션 포함)."""

    from app.products.option_parser import (
        parse_option_full_sections,
        shadow_parse_option_ingredient_sections,
    )

    options = [
        make_product_option("19호"),
        make_product_option("[기획]"),
    ]
    canonical = canonicalize_product_options(options)
    raw_text = "[19호] 정제수, 글리세린, 향료"

    production = parse_option_full_sections(raw_text, canonical)
    shadow = shadow_parse_option_ingredient_sections(raw_text, canonical)

    canonical_keys = {option.internal_option_key for option in canonical}
    production_keys = {
        section.internal_option_key for section in production.sections
    }
    shadow_keys = {
        mapping.internal_option_key for mapping in shadow.mappings
    }
    assert production_keys == canonical_keys
    assert shadow_keys == canonical_keys


def test_mapping_normalization_does_not_change_display_name() -> None:
    option = make_product_option("[기획] 23호 누카다미아")
    assert option.option_name == "[기획] 23호 누카다미아"
    assert option.raw_option_name == "[기획] 23호 누카다미아"
    assert option.normalized_name == "기획23호누카다미아"
    assert normalize_option_mapping_key(option.raw_option_name) == "23누카다미아"


def test_target_product_minimal_fixture_reproduces_partial_mapping() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    sections = _split(
        "\n".join(fixture["raw_sections"]),
        fixture["options"],
    )
    assert fixture["product_id"] == "A000000241210"
    assert [section.mapping_status for section in sections] == fixture[
        "expected_mapping_statuses"
    ]


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
    # 분석용 canonical 표시명에서는 package token만 제거한다.
    assert sections[0].option_name == "17N"
    assert sections[1].option_name == "21P"


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


def test_repeated_header_uses_first_section_without_ambiguity() -> None:
    sections = _split(
        (
            "[19호] 정제수, 글리세린\n"
            "[19호] 향료, 티타늄디옥사이드"
        ),
        ["19호"],
    )

    assert sections[0].mapping_status == "matched"
    assert sections[0].ingredients == ["정제수", "글리세린"]
    assert sections[0].duplicate_header_count == 1


def test_identical_span_options_share_the_same_section() -> None:
    """같은 색상 코드를 가리키는 패키지 구성 옵션들은 헤더를 공유한다."""

    sections = _split(
        "17N 정제수, 글리세린, 향료",
        ["[본품+리필+파우치] 17N", "[본품+리필] 17N"],
    )

    assert [section.mapping_status for section in sections] == ["matched"]
    assert sections[0].matched_header == "17N"
    assert sections[0].ingredients == ["정제수", "글리세린", "향료"]


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

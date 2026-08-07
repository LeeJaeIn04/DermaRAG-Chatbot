import json
from pathlib import Path

from app.products.option_parser import (
    make_product_option,
    normalize_repeated_full_option_label,
    parse_option_full_sections,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / (
    "repeated_unbracketed_full_option_label.json"
)
REAL_COUNT_FIXTURE_PATH = Path(__file__).parent / "fixtures" / (
    "repeated_unbracketed_full_option_label_real_counts.json"
)
BODY = "정제수, 글리세린, 다이메티콘, 실리카, 토코페롤"


def _parse(raw_sections: list[str], options: list[str]):
    return parse_option_full_sections(
        " ".join(raw_sections),
        [make_product_option(option) for option in options],
    )


def test_production_sanitized_fixtures() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["contains_full_research_raw_text"] is False

    for case in fixture["cases"]:
        result = _parse(case["raw_sections"], case["options"])
        assert [section.mapping_status for section in result.sections] == (
            case["expected_statuses"]
        ), case["name"]
        assert {header.grammar for header in result.headers} == {
            "repeated_unbracketed_full_option_label"
        }
        assert {header.variant for header in result.headers} == {
            case["expected_variant"]
        }
        assert {header.mapping_rule for header in result.headers} == {
            "explicit_full_option_label_exact"
        }
        assert {
            section.mapping_method for section in result.sections
        } == {"explicit_full_option_label_exact"}


def test_research_product_count_fixtures() -> None:
    fixture = json.loads(
        REAL_COUNT_FIXTURE_PATH.read_text(encoding="utf-8")
    )
    assert fixture["contains_full_research_raw_text"] is False

    for case in fixture["cases"]:
        raw_sections = []
        for index, label in enumerate(case["document_labels"]):
            if case["variant"] == "product_prefix_plus_full_label":
                volume = " 3.5g" if index == 0 else ""
                header = (
                    f"롬앤 더 쥬시 래스팅 틴트{volume} {label}"
                )
            else:
                header = label
            raw_sections.append(f"{header} {BODY}")

        result = _parse(raw_sections, case["canonical_options"])
        statuses = [section.mapping_status for section in result.sections]

        assert statuses.count("matched") == case["expected_matched"], (
            case["product_id"]
        )
        assert statuses.count("unmatched") == case["expected_unmatched"], (
            case["product_id"]
        )
        assert [
            orphan.header.label for orphan in result.orphan_document_sections
        ] == case["expected_orphans"]
        assert {header.variant for header in result.headers} == {
            case["variant"]
        }


def test_full_label_normalization_only_ignores_unicode_case_and_spaces() -> None:
    assert normalize_repeated_full_option_label(
        " ０１ 포멜로스킨 "
    ) == normalize_repeated_full_option_label("01포멜로스킨")
    assert normalize_repeated_full_option_label(
        "01 PEACH BEIGE"
    ) == normalize_repeated_full_option_label("01peachbeige")
    assert normalize_repeated_full_option_label(
        "[기획] 01 포멜로스킨"
    ) != normalize_repeated_full_option_label("01 포멜로스킨")


def test_partial_full_label_is_not_mapped() -> None:
    result = _parse(
        [
            f"01 포멜로 {BODY}",
            f"02 누카다미아 {BODY}",
            f"03 베어 그레이프 {BODY}",
        ],
        ["01 포멜로스킨", "02 누카다미아", "03 베어 그레이프"],
    )

    assert [section.mapping_status for section in result.sections] == [
        "unmatched",
        "matched",
        "matched",
    ]
    assert [
        orphan.header.label for orphan in result.orphan_document_sections
    ] == ["01 포멜로"]


def test_number_only_and_color_only_do_not_activate_grammar() -> None:
    number_only = _parse(
        [f"01 {BODY}", f"02 {BODY}", f"03 {BODY}"],
        ["01 로즈", "02 피치", "03 베이지"],
    )
    color_only = _parse(
        [f"로즈 {BODY}", f"피치 {BODY}", f"베이지 {BODY}"],
        ["01 로즈", "02 피치", "03 베이지"],
    )

    assert {section.mapping_status for section in number_only.sections} == {
        "unmatched"
    }
    assert {section.mapping_status for section in color_only.sections} == {
        "unmatched"
    }
    assert number_only.headers == ()
    assert color_only.headers == ()


def test_duplicate_full_label_is_ambiguous() -> None:
    result = _parse(
        [f"01 로즈 {BODY}", f"01 로즈 {BODY}", f"02 피치 {BODY}"],
        ["01 로즈", "02 피치"],
    )

    assert [section.mapping_status for section in result.sections] == [
        "ambiguous",
        "matched",
    ]
    assert result.ambiguous_header_count == 2


def test_missing_body_disables_unbracketed_grammar() -> None:
    result = _parse(
        [f"01 로즈 {BODY}", f"02 피치 {BODY}", "03 베이지"],
        ["01 로즈", "02 피치", "03 베이지"],
    )

    assert result.headers == ()
    assert {section.mapping_status for section in result.sections} == {
        "unmatched"
    }


def test_option_name_mention_inside_body_is_not_a_header() -> None:
    result = _parse(
        [
            "01 로즈 정제수, 글리세린, 설명 문구 02 피치 정제수, "
            "다이메티콘, 실리카, 토코페롤"
        ],
        ["01 로즈", "02 피치"],
    )

    assert result.headers == ()
    assert {section.mapping_status for section in result.sections} == {
        "unmatched"
    }


def test_orphan_and_missing_current_option_remain_separate() -> None:
    result = _parse(
        [f"01 로즈 {BODY}", f"02 피치 {BODY}", f"12 과거색상 {BODY}"],
        ["01 로즈", "02 피치", "03 베이지"],
    )

    assert [section.mapping_status for section in result.sections] == [
        "matched",
        "matched",
        "unmatched",
    ]
    assert [
        orphan.header.label for orphan in result.orphan_document_sections
    ] == ["12 과거색상"]


def test_hierarchical_structure_is_blocked_before_new_grammar() -> None:
    result = _parse(
        [
            "01 로즈 [왼쪽] 마이카, 실리카, 적색산화철 "
            "[오른쪽] 마이카, 실리카, 황색산화철",
            "02 피치 [왼쪽] 마이카, 실리카, 적색산화철 "
            "[오른쪽] 마이카, 실리카, 황색산화철",
        ],
        ["01 로즈", "02 피치"],
    )

    assert result.document_format == "hierarchical_option_internal_sections"
    assert {section.mapping_status for section in result.sections} == {
        "unsupported"
    }
    assert all(
        header.grammar != "repeated_unbracketed_full_option_label"
        for header in result.headers
    )


def test_malformed_bracket_and_hash_english_are_not_added() -> None:
    malformed = _parse(
        ["[누디스트) 오일, 왁스, 적색산화철"],
        ["401 누디스트"],
    )
    hash_english = _parse(
        ["#HALO 정제수, 글리세린, 실리카"],
        ["헤일로(HALO)"],
    )

    assert malformed.sections[0].mapping_status == "unmatched"
    assert malformed.malformed_header_count == 1
    assert hash_english.sections[0].mapping_status == "unmatched"
    assert hash_english.headers == ()

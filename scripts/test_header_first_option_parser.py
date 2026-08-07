import json
from pathlib import Path

import pytest

from app.products.option_parser import (
    PARSER_VERSION,
    canonicalize_product_options,
    make_product_option,
    parse_option_full_sections,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / (
    "header_first_option_full_sections.json"
)
RESEARCH_ARTIFACT_DIR = Path(__file__).parents[1] / (
    "research/ingredient_documents"
)


def _parse(raw_sections: list[str], option_names: list[str]):
    return parse_option_full_sections(
        " ".join(raw_sections),
        [make_product_option(name) for name in option_names],
    )


def test_sanitized_option_full_section_fixtures() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["contains_full_research_raw_text"] is False

    for case in fixture["cases"]:
        options = [make_product_option(name) for name in case["options"]]
        canonical = canonicalize_product_options(options)
        result = parse_option_full_sections(
            " ".join(case["raw_sections"]), options
        )

        assert len(canonical) == case["expected_canonical_count"], case["name"]
        assert [section.mapping_status for section in result.sections] == case[
            "expected_statuses"
        ], case["name"]
        assert [
            section.header.raw_header
            for section in result.orphan_document_sections
        ] == case["expected_orphan_headers"], case["name"]
        assert result.malformed_header_count == case[
            "expected_malformed_header_count"
        ], case["name"]
        assert result.ambiguous_header_count == case[
            "expected_ambiguous_header_count"
        ], case["name"]
        assert result.document_format == case.get(
            "expected_document_format",
            "option_full_sections",
        ), case["name"]


def test_orphan_section_is_not_appended_to_matched_ingredients() -> None:
    result = _parse(
        [
            "[3C 웨딩피치] 정제수, 글리세린, 적색산화철",
            "[기존 21호 아이보리] 오일, 왁스, 흑색산화철",
        ],
        ["[AD][단품] 3C 웨딩피치"],
    )

    assert result.sections[0].ingredients == [
        "정제수",
        "글리세린",
        "적색산화철",
    ]
    assert "오일" not in result.sections[0].ingredients
    assert result.orphan_document_sections[0].ingredients == (
        "오일",
        "왁스",
        "흑색산화철",
    )


def test_color_alias_collision_is_ambiguous_not_first_match() -> None:
    result = _parse(
        ["[로즈] 오일, 왁스, 적색산화철"],
        ["01 로즈", "02 로즈"],
    )

    assert [section.mapping_status for section in result.sections] == [
        "ambiguous",
        "ambiguous",
    ]
    assert result.ambiguous_header_count == 1
    assert result.orphan_document_section_count == 0


def test_hierarchical_internal_sections_are_not_flattened() -> None:
    result = _parse(
        [
            "[02호 생기 블러링]",
            "[시스루] 마이카, 실리카, 적색산화철",
            "[스너그] 마이카, 실리카, 황색산화철",
        ],
        ["02 생기 블러링"],
    )

    assert result.sections[0].mapping_status == "unsupported"
    assert result.sections[0].ingredients == []
    assert [
        section.header.raw_header
        for section in result.orphan_document_sections
    ] == ["[시스루]", "[스너그]"]


def test_no_fuzzy_or_typo_repair() -> None:
    result = _parse(
        ["[유즈 시트러스 티] 마이카, 실리카, 황색산화철"],
        ["[단품] 유자 시트러스 티"],
    )

    assert result.sections[0].mapping_status == "unmatched"
    assert result.orphan_document_sections[0].header.raw_header == (
        "[유즈 시트러스 티]"
    )


def test_parser_version_marks_header_first_contract() -> None:
    assert PARSER_VERSION == "option-sections-v4-unbracketed-full-label"


@pytest.mark.parametrize(
    ("product_id", "expected_format", "expected_status", "expected_count"),
    [
        (
            "A000000258200",
            "hierarchical_option_internal_sections",
            "unsupported",
            6,
        ),
        (
            "A000000180532",
            "hierarchical_option_internal_sections",
            "unsupported",
            12,
        ),
        (
            "A000000145650",
            "hierarchical_option_internal_sections",
            "unsupported",
            4,
        ),
        (
            "A000000174064",
            "option_full_sections",
            "matched",
            10,
        ),
    ],
)
def test_existing_research_artifact_structure_guard(
    product_id: str,
    expected_format: str,
    expected_status: str,
    expected_count: int,
) -> None:
    artifact = json.loads(
        (RESEARCH_ARTIFACT_DIR / f"{product_id}.json").read_text(
            encoding="utf-8"
        )
    )
    options = [
        make_product_option(
            option["raw_option_name"],
            source_option_id=option.get("option_number"),
        )
        for option in artifact["sales_options"]
    ]

    result = parse_option_full_sections(
        artifact["ingredient_document"]["raw_text"],
        options,
    )

    assert result.document_format == expected_format
    assert len(result.sections) == expected_count
    assert {
        section.mapping_status for section in result.sections
    } == {expected_status}
    if product_id == "A000000174064":
        assert result.orphan_document_section_count == 4

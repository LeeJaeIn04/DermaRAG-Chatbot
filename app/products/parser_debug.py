"""production/shadow option parser 비교 진단(개발 환경 전용, read-only).

이 모듈은 DB 캐시나 수집 상태를 절대 변경하지 않는다. 상품 옵션
추출기를 다시 호출하더라도 결과를 저장하지 않고, production
parser(parse_option_full_sections)와 shadow parser
(shadow_parse_option_ingredient_sections)를 순수 함수로만
호출해 비교용 진단 정보를 만든다.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.products.option_parser import (
    PARSER_VERSION,
    SHADOW_PARSER_VERSION,
    IngredientSection,
    ShadowParseResult,
    _find_formula_boundary_splits,
    _shadow_normalize_label,
    _split_comma_chunks_with_offsets,
    canonicalize_product_options,
    parse_option_full_sections,
    shadow_parse_option_ingredient_sections,
)
from app.products.option_parser import (
    FormulaBoundaryDiagnostic as ShadowFormulaBoundaryDiagnostic,
)
from app.products.option_models import ProductOption


_MAX_FIRST_INGREDIENTS = 3
_MAX_LAST_INGREDIENTS = 2

_STATUS_KEYS = ("matched", "unmatched", "ambiguous", "unsupported")

_TRAILING_BRACKET_SUFFIX_PATTERN = re.compile(
    r"^(?P<preceding>.+?)\s+(?P<trailing>\[[^\[\]]*\])$"
)


class ParserDebugUnavailableError(Exception):
    """진단에 필요한 상품 정보나 전성분 원문을 확보하지 못했을 때 발생한다."""


class FormulaBoundaryCandidate(BaseModel):
    """rule 1(문자열형 내부 formula)이 실제로 사용하는
    _find_formula_boundary_splits 결과를 그대로 노출한다. 유일한
    분할이 나온 chunk만 여기 포함된다(사람이 원인을 볼 수 있게).
    """

    chunk_index: int
    raw_chunk: str
    boundary_text: str
    right_ingredient: str
    left_ingredient: str = ""
    body_ingredient_count: int = 0
    body_exact_known_count: int = 0
    decision: str = ""


class AmbiguousBoundary(BaseModel):
    """같은 chunk에서 유효한 분할이 2개 이상 나와 boundary
    candidate로 확정되지 못한 경우."""

    chunk_index: int
    raw_chunk: str
    split_count: int


class AnnotationCandidateDebug(BaseModel):
    text: str
    start_index: int
    end_index: int


class ShadowSectionDebug(BaseModel):
    raw_header: str
    section_kind: str
    ingredient_count: int
    first_ingredients: list[str]
    last_ingredients: list[str]
    mapped_option_name: str | None
    mapping_status: str
    nested_formula_count: int
    formula_boundary_candidates: list[FormulaBoundaryCandidate] = Field(
        default_factory=list
    )
    ambiguous_boundaries: list[AmbiguousBoundary] = Field(
        default_factory=list
    )
    ambiguous_annotation_candidates: list[AnnotationCandidateDebug] = Field(
        default_factory=list
    )


class ComponentGroupSummary(BaseModel):
    raw_header: str
    ingredient_count: int


class StringFormulaPrefixCandidate(BaseModel):
    """알 수 없는 prefix 뒤에 이미 알려진(=해당 section의 첫 성분)
    값이 다시 등장하는 chunk 후보. nested formula로 확정하지
    않으며, 사람이 판단할 근거만 제공한다.
    """

    section_raw_header: str
    chunk_index: int
    raw_chunk: str
    prefix_candidate: str
    first_ingredient_candidate: str
    ingredient_count_until_next_candidate: int


class TrailingDescriptionCandidate(BaseModel):
    """section/문서 끝에 붙은 bracket text 후보.

    annotation으로 확정하거나 제거하지 않으며, 사람이 판단할
    근거(전후 맥락)만 제공한다.
    """

    section_raw_header: str
    preceding_ingredient: str
    trailing_text: str
    has_additional_ingredient_body_after: bool
    boundary_type: str


class ParserDebugResponse(BaseModel):
    product_id: str
    production_parser_version: str
    shadow_parser_version: str
    canonical_option_count: int
    production_document_format: str
    production_status_counts: dict[str, int]
    shadow_document_format: str
    shadow_section_count: int
    shadow_status_counts: dict[str, int]
    shadow_orphan_count: int
    shadow_sections: list[ShadowSectionDebug]
    format_diff: bool
    status_diff: dict[str, int]
    string_formula_prefix_candidates: list[StringFormulaPrefixCandidate] = (
        Field(default_factory=list)
    )
    trailing_description_candidates: list[TrailingDescriptionCandidate] = (
        Field(default_factory=list)
    )
    component_group_sections: list[ComponentGroupSummary] = Field(
        default_factory=list
    )


def _not_applicable_response(product_id: str) -> ParserDebugResponse:
    zero_counts = {key: 0 for key in _STATUS_KEYS}
    return ParserDebugResponse(
        product_id=product_id,
        production_parser_version=PARSER_VERSION,
        shadow_parser_version=SHADOW_PARSER_VERSION,
        canonical_option_count=0,
        production_document_format="not_applicable",
        production_status_counts=dict(zero_counts),
        shadow_document_format="not_applicable",
        shadow_section_count=0,
        shadow_status_counts=dict(zero_counts),
        shadow_orphan_count=0,
        shadow_sections=[],
        format_diff=False,
        status_diff={},
    )


def _formula_boundary_candidates_from_diagnostics(
    diagnostics: tuple[ShadowFormulaBoundaryDiagnostic, ...],
) -> list[FormulaBoundaryCandidate]:
    """hierarchical로 확정된 section은 재구성 후 raw_ingredient_text가
    비어 있어 다시 스캔해도 후보를 재현할 수 없다. 확정 당시 shadow
    parser가 보존해 둔 진단 정보를 그대로 노출한다(재계산 아님)."""

    return [
        FormulaBoundaryCandidate(
            chunk_index=diagnostic.chunk_index,
            raw_chunk=diagnostic.raw_chunk,
            boundary_text=diagnostic.boundary_text,
            right_ingredient=diagnostic.right_ingredient,
            left_ingredient=diagnostic.left_ingredient,
            body_ingredient_count=diagnostic.body_ingredient_count,
            body_exact_known_count=diagnostic.body_exact_known_count,
            decision=diagnostic.decision,
        )
        for diagnostic in diagnostics
    ]


def _scan_section_formula_boundaries(
    section: IngredientSection,
    raw_text: str,
) -> tuple[list[FormulaBoundaryCandidate], list[AmbiguousBoundary]]:
    """section의 comma chunk 각각을 rule 1과 동일한
    _find_formula_boundary_splits로 다시 훑어, 유일한 분할이 나온
    chunk는 확정 후보로, 복수 분할이 나온 chunk는 ambiguous로
    보여준다. shadow parser의 실제 판정 로직을 그대로 재사용하므로
    별도의 heuristic이 아니다.

    hierarchical로 확정된 section(subsections가 있는 section)은
    재구성 과정에서 raw_ingredient_text가 비어 재스캔이 무의미하므로,
    확정 당시 보존된 formula_boundary_diagnostics를 그대로 사용한다
    (재스캔하지 않는다).
    """

    if section.subsections:
        return (
            _formula_boundary_candidates_from_diagnostics(
                section.formula_boundary_diagnostics
            ),
            [],
        )

    if not section.raw_header:
        return [], []

    body = raw_text[section.body_start_index:section.body_end_index]
    confirmed: list[FormulaBoundaryCandidate] = []
    ambiguous: list[AmbiguousBoundary] = []
    for chunk_index, (chunk_text, _local_start, _local_end) in enumerate(
        _split_comma_chunks_with_offsets(body)
    ):
        tokens = [
            match.group(0) for match in re.finditer(r"\S+", chunk_text)
        ]
        if len(tokens) < 2:
            continue

        has_left = chunk_index != 0
        splits = _find_formula_boundary_splits(
            tokens, has_left_ingredient=has_left
        )
        if len(splits) == 1:
            left_end, right_start = splits[0]
            confirmed.append(
                FormulaBoundaryCandidate(
                    chunk_index=chunk_index,
                    raw_chunk=chunk_text.strip(),
                    boundary_text=" ".join(tokens[left_end:right_start]),
                    right_ingredient=" ".join(tokens[right_start:]),
                )
            )
        elif len(splits) > 1:
            ambiguous.append(
                AmbiguousBoundary(
                    chunk_index=chunk_index,
                    raw_chunk=chunk_text.strip(),
                    split_count=len(splits),
                )
            )
    return confirmed, ambiguous


def _describe_shadow_sections(
    shadow_result: ShadowParseResult,
    canonical_options: list[ProductOption],
    raw_text: str,
) -> list[ShadowSectionDebug]:
    matched_by_section: dict[int, str] = {
        mapping.section_index: mapping.option_name
        for mapping in shadow_result.mappings
        if (
            mapping.mapping_status == "matched"
            and mapping.section_index is not None
        )
    }
    option_labels = {
        _shadow_normalize_label(option.raw_option_name)
        for option in canonical_options
    }

    descriptions: list[ShadowSectionDebug] = []
    for index, section in enumerate(shadow_result.sections):
        ingredients = section.ingredients
        if index in matched_by_section:
            status = "matched"
            mapped_name: str | None = matched_by_section[index]
        elif shadow_result.document_format != "option_full_sections":
            status = "unsupported"
            mapped_name = None
        elif not section.raw_header:
            status = "unmatched"
            mapped_name = None
        elif section.section_kind != "ingredient_section":
            status = "excluded"
            mapped_name = None
        else:
            normalized_header = _shadow_normalize_label(section.raw_header)
            status = (
                "ambiguous"
                if normalized_header in option_labels
                else "orphan"
            )
            mapped_name = None

        formula_candidates, ambiguous_boundaries = (
            _scan_section_formula_boundaries(section, raw_text)
        )

        annotation_debug = [
            AnnotationCandidateDebug(
                text=candidate.text,
                start_index=candidate.start_index,
                end_index=candidate.end_index,
            )
            for candidate in section.annotation_candidates
        ]
        if section.section_kind == "ambiguous_annotation_candidate":
            annotation_debug.append(
                AnnotationCandidateDebug(
                    text=section.raw_header,
                    start_index=section.header_start_index,
                    end_index=section.header_end_index,
                )
            )

        descriptions.append(
            ShadowSectionDebug(
                raw_header=section.raw_header,
                section_kind=section.section_kind,
                ingredient_count=len(ingredients),
                first_ingredients=list(
                    ingredients[:_MAX_FIRST_INGREDIENTS]
                ),
                last_ingredients=(
                    list(ingredients[-_MAX_LAST_INGREDIENTS:])
                    if ingredients
                    else []
                ),
                mapped_option_name=mapped_name,
                mapping_status=status,
                nested_formula_count=len(section.subsections),
                formula_boundary_candidates=formula_candidates,
                ambiguous_boundaries=ambiguous_boundaries,
                ambiguous_annotation_candidates=annotation_debug,
            )
        )
    return descriptions


def _summarize_component_groups(
    shadow_result: ShadowParseResult,
) -> list[ComponentGroupSummary]:
    return [
        ComponentGroupSummary(
            raw_header=section.raw_header,
            ingredient_count=len(section.ingredients),
        )
        for section in shadow_result.sections
        if section.section_kind == "component_group"
    ]


def _clean_chunk_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n:;-–—")


def _extract_string_formula_prefix_candidates(
    shadow_result: ShadowParseResult,
    raw_text: str,
) -> list[StringFormulaPrefixCandidate]:
    """top-level section 안에서 '알 수 없는 prefix + 이미 알려진(=이
    section의 첫 성분) 값'이 다시 나타나는 chunk를 후보로만
    나열한다.

    shadow parser의 section/구조 판정 결과(raw_text, section 경계)는
    읽기만 하고 절대 바꾸지 않는다. 후보를 nested formula로
    확정하거나 document_format을 바꾸는 로직은 여기에 없다.
    """

    candidates: list[StringFormulaPrefixCandidate] = []
    for section in shadow_result.sections:
        if not section.ingredients:
            continue
        known_first_ingredient = section.ingredients[0]
        if not known_first_ingredient:
            continue

        body = raw_text[
            section.body_start_index:section.body_end_index
        ]
        raw_chunks = [
            chunk_text
            for chunk_text, _start, _end in (
                _split_comma_chunks_with_offsets(body)
            )
        ]
        cleaned_chunks = [_clean_chunk_text(chunk) for chunk in raw_chunks]

        section_hits: list[tuple[int, str, str]] = []
        for chunk_index, cleaned in enumerate(cleaned_chunks):
            if not cleaned:
                continue
            match_start = cleaned.find(known_first_ingredient)
            if match_start <= 0:
                continue
            prefix_candidate = cleaned[:match_start].strip()
            if not prefix_candidate:
                continue
            section_hits.append(
                (chunk_index, raw_chunks[chunk_index].strip(), prefix_candidate)
            )

        for hit_index, (
            chunk_index,
            raw_chunk,
            prefix_candidate,
        ) in enumerate(section_hits):
            next_chunk_index = (
                section_hits[hit_index + 1][0]
                if hit_index + 1 < len(section_hits)
                else len(cleaned_chunks)
            )
            candidates.append(
                StringFormulaPrefixCandidate(
                    section_raw_header=section.raw_header,
                    chunk_index=chunk_index,
                    raw_chunk=raw_chunk,
                    prefix_candidate=prefix_candidate,
                    first_ingredient_candidate=known_first_ingredient,
                    ingredient_count_until_next_candidate=(
                        next_chunk_index - chunk_index
                    ),
                )
            )
    return candidates


def _trailing_bracket_section_candidates(
    sections: tuple[IngredientSection, ...],
    option_labels: set[str],
) -> list[TrailingDescriptionCandidate]:
    """comma로 분리된 독립 bracket chunk가 그 자체로 별도 section이
    되어버린 경우(shadow parser의 기존 동작)를 후보로 잡는다.

    hierarchical로 확정된 section(subsections가 있는 section)은
    ingredients가 비어 있는 게 정상 구조(성분이 nested formula로
    옮겨감)이므로, 성분 body 없는 trailing bracket 후보로 오진단하지
    않도록 스캔 대상에서 제외한다.
    """

    candidates: list[TrailingDescriptionCandidate] = []
    total = len(sections)
    for index, section in enumerate(sections):
        if section.subsections:
            continue
        header = section.raw_header.strip()
        if not (header.startswith("[") and header.endswith("]")):
            continue
        if _shadow_normalize_label(header) in option_labels:
            continue

        previous_section = sections[index - 1] if index > 0 else None
        preceding_ingredient = ""
        if previous_section is not None and previous_section.ingredients:
            preceding_ingredient = previous_section.ingredients[-1]

        candidates.append(
            TrailingDescriptionCandidate(
                section_raw_header=(
                    previous_section.raw_header
                    if previous_section is not None
                    else ""
                ),
                preceding_ingredient=preceding_ingredient,
                trailing_text=header,
                has_additional_ingredient_body_after=bool(
                    section.ingredients
                ),
                boundary_type=(
                    "document_end"
                    if index == total - 1
                    else "section_end_only"
                ),
            )
        )
    return candidates


def _trailing_bracket_suffix_candidates(
    sections: tuple[IngredientSection, ...],
) -> list[TrailingDescriptionCandidate]:
    """section의 마지막 ingredient 문자열 끝에 bracket 텍스트가 붙어
    하나의 항목으로 병합된 경우를 후보로 잡는다.
    """

    candidates: list[TrailingDescriptionCandidate] = []
    total = len(sections)
    for index, section in enumerate(sections):
        if section.subsections or not section.ingredients:
            continue
        last_ingredient = section.ingredients[-1]
        match = _TRAILING_BRACKET_SUFFIX_PATTERN.match(last_ingredient)
        if match is None:
            continue
        candidates.append(
            TrailingDescriptionCandidate(
                section_raw_header=section.raw_header,
                preceding_ingredient=match.group("preceding").strip(),
                trailing_text=match.group("trailing").strip(),
                has_additional_ingredient_body_after=False,
                boundary_type=(
                    "document_end"
                    if index == total - 1
                    else "section_end_only"
                ),
            )
        )
    return candidates


def _extract_trailing_description_candidates(
    shadow_result: ShadowParseResult,
    canonical_options: list[ProductOption],
) -> list[TrailingDescriptionCandidate]:
    """section/문서 끝에 붙은 bracket text 후보를 모두 추출한다.

    shadow parser가 실제로 만들어내는 두 가지 모양을 그대로
    읽기만 한다: (1) comma로 분리된 bracket-only chunk가 자체
    section이 되어버린 경우, (2) 마지막 ingredient 문자열 끝에
    bracket이 그대로 붙어버린 경우. 어느 쪽도 annotation으로
    확정하거나 삭제하지 않는다.
    """

    option_labels = {
        _shadow_normalize_label(option.raw_option_name)
        for option in canonical_options
    }
    return [
        *_trailing_bracket_section_candidates(
            shadow_result.sections, option_labels
        ),
        *_trailing_bracket_suffix_candidates(shadow_result.sections),
    ]


def build_parser_debug_response(
    product_id: str,
    *,
    repository,
    option_extractor,
) -> ParserDebugResponse:
    """DB/실시간 추출기를 읽기만 하고 production/shadow 결과를 비교한다.

    옵션이 없는(no_options) 상품은 캐시에 원문이 남아 있으므로
    추출기를 다시 호출하지 않는다. 옵션이 있는 상품은 캐시가
    옵션별로 이미 잘려 저장돼 있어 원문 전체를 복원할 수 없으므로,
    추출기를 다시 호출해 raw_document만 읽고 어떤 저장도 하지
    않는다(store_collection/mark_collection_complete/
    start_collection_attempt 등을 절대 호출하지 않는다).
    """

    product = repository.get_product_candidate(
        source="oliveyoung",
        external_product_id=product_id,
    )
    if product is None:
        raise ParserDebugUnavailableError(
            f"저장된 상품 정보를 찾을 수 없습니다: {product_id}"
        )

    cached_common = repository.get_cached_ingredients(
        source=product.source,
        external_product_id=product.product_id,
        option_id="",
    )
    if cached_common is not None and cached_common.raw_ingredients.strip():
        return _not_applicable_response(product_id)

    extraction = option_extractor.extract(
        product_id=product.product_id,
        product_url=product.product_url,
    )
    if extraction.status == "failed" or extraction.raw_document is None:
        raise ParserDebugUnavailableError(
            "전성분 원문을 확보하지 못해 진단할 수 없습니다."
        )

    raw_text = extraction.raw_document.raw_text
    if not raw_text.strip():
        raise ParserDebugUnavailableError(
            "전성분 원문이 비어 있어 진단할 수 없습니다."
        )

    canonical_options = canonicalize_product_options(extraction.options)
    if extraction.status == "no_options" or not canonical_options:
        return _not_applicable_response(product_id)

    parse_result = parse_option_full_sections(raw_text, canonical_options)
    production_status_counts = {key: 0 for key in _STATUS_KEYS}
    for section in parse_result.sections:
        production_status_counts[section.mapping_status] += 1

    shadow_result = shadow_parse_option_ingredient_sections(
        raw_text, canonical_options
    )
    shadow_status_counts = {
        "matched": shadow_result.matched_count,
        "unmatched": shadow_result.unmatched_count,
        "ambiguous": shadow_result.ambiguous_count,
        "unsupported": shadow_result.unsupported_count,
    }
    status_diff = {
        status: (
            production_status_counts[status] - shadow_status_counts[status]
        )
        for status in _STATUS_KEYS
        if production_status_counts[status] != shadow_status_counts[status]
    }

    return ParserDebugResponse(
        product_id=product_id,
        production_parser_version=PARSER_VERSION,
        shadow_parser_version=SHADOW_PARSER_VERSION,
        canonical_option_count=len(canonical_options),
        production_document_format=parse_result.document_format,
        production_status_counts=production_status_counts,
        shadow_document_format=shadow_result.document_format,
        shadow_section_count=len(shadow_result.sections),
        shadow_status_counts=shadow_status_counts,
        shadow_orphan_count=shadow_result.orphan_section_count,
        shadow_sections=_describe_shadow_sections(
            shadow_result, canonical_options, raw_text
        ),
        format_diff=(
            parse_result.document_format != shadow_result.document_format
        ),
        status_diff=status_diff,
        string_formula_prefix_candidates=(
            _extract_string_formula_prefix_candidates(
                shadow_result, raw_text
            )
        ),
        trailing_description_candidates=(
            _extract_trailing_description_candidates(
                shadow_result, canonical_options
            )
        ),
        component_group_sections=_summarize_component_groups(shadow_result),
    )

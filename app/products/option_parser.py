from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Literal

from app.products.ingredient_dictionary import (
    is_known_ingredient,
)
from app.products.ingredient_parsing import (
    split_raw_ingredient_text,
)
from app.products.option_models import (
    NormalizedTextIndex,
    OptionIngredientSection,
    OptionMappingStatus,
    ProductOption,
)


PARSER_VERSION = "option-sections-v4-unbracketed-full-label"
_REMOVED_CHARACTERS = set("[](){}·ㆍ_/,.\\-:;")
_OPTION_CODE_PATTERN = re.compile(
    r"(?i)(?:[a-z]+\s*)?\d+(?:\s*[a-z]+)?(?:\s*호)?"
)
_BRACKET_BLOCK_PATTERN = re.compile(r"\[[^\[\]]*\]")
_LEADING_BRACKET_BLOCKS_PATTERN = re.compile(
    r"^\s*((?:\[[^\[\]]*\]\s*)+)"
)
_VERIFIED_PROMOTION_MARKERS = (
    "기획",
    "단품",
    "new",
    "단독",
    "본품",
    "리필",
    "증정",
    "한정",
    "재입고",
    "pick",
    "ad",
    "컬렉션",
    "올영",
    "용기",
)
_LEADING_PROMOTION_TEXT_PATTERN = re.compile(
    r"(?i)^\s*(?:기획|단품|new|단독|한정|재입고)"
    r"(?=\s|[/_\-·])(?:\s|[/_\-·])*"
)
_TRAILING_PACKAGE_TEXT_PATTERN = re.compile(
    r"(?i)(?:\s|[/_\-·])+"
    r"(?:\((?:단품|본품|리필)(?:\s*\+\s*(?:단품|본품|리필))*\)"
    r"|(?:단품|본품|리필|기획)(?:\s*\+\s*(?:단품|본품|리필))*)\s*$"
)
_EXPLICIT_BRACKET_HEADER_PATTERN = re.compile(
    r"\[(?P<label>[^\[\]\r\n]{1,120})\]"
)
_EXPLICIT_STAR_COLON_HEADER_PATTERN = re.compile(
    r"★\s*(?P<label>[^,:;\[\]\r\n]{1,80}?)\s*:"
)
_EXPLICIT_HASH_CODE_HEADER_PATTERN = re.compile(
    r"(?<![0-9A-Za-z가-힣])#\s*"
    r"(?P<label>(?:[A-Za-z]+\d+|\d+[A-Za-z]+))"
    r"(?=\s)"
)
_MALFORMED_BRACKET_HEADER_PATTERNS = (
    re.compile(r"\[(?P<label>[^\[\]()\],:\r\n]{1,80})\)"),
    re.compile(r"\((?P<label>[^\[\]()\],:\r\n]{1,80})\]"),
)
_UNBRACKETED_BILINGUAL_HEADER_PATTERN = re.compile(
    r"(?<![A-Za-z가-힣])"
    r"(?P<label>[가-힣]{1,10}(?:\s+[가-힣]{1,10}){0,1}\s+"
    r"[A-Z][a-z]{1,24}(?:\s+[A-Z][a-z]{1,24}){0,3})"
    r"(?=\s*[가-힣])"
)
_REPEATED_FULL_OPTION_LABEL_PATTERN = re.compile(
    r"(?<![0-9A-Za-z가-힣])"
    r"(?P<label>\d{2}\s*[가-힣]{1,15}"
    r"(?:\s+[가-힣]{1,15}){0,2})"
    r"(?=\s+[가-힣A-Za-z][^,\[\]\r\n]{0,50},)"
)
_VERIFIED_REPEATED_PRODUCT_PREFIX_PATTERN = re.compile(
    r"롬앤\s+더\s+쥬시\s+래스팅\s+틴트"
    r"(?:\s+3\.5g)?\s*$",
    re.IGNORECASE,
)
_REPEATED_PREFIX_LOOKBEHIND_LIMIT = 80
_MIN_REPEATED_FULL_LABEL_HEADERS = 3
_MIN_REPEATED_FULL_LABEL_BODY_LENGTH = 20


def _strip_bracket_blocks(value: str) -> str:
    """
    "[본품+리필+파우치] 17N"처럼 구성 문구를 담은 대괄호 블록을
    헤더 후보 생성 전에 제거한다. 소괄호는 CI 번호 등 실제 성분
    표기에도 쓰이므로 건드리지 않는다.
    """

    without_brackets = _BRACKET_BLOCK_PATTERN.sub(
        " ", value
    )
    return re.sub(r"\s+", " ", without_brackets).strip()


def normalize_option_label(value: str) -> str:
    return normalize_text_with_indexes(value).normalized_text


def _strip_verified_promotion_prefix(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    normalized = _LEADING_PROMOTION_TEXT_PATTERN.sub("", normalized).strip()
    bracket_prefix = _LEADING_BRACKET_BLOCKS_PATTERN.match(normalized)
    if bracket_prefix is not None:
        contents = _BRACKET_BLOCK_PATTERN.findall(bracket_prefix.group(1))
        normalized_contents = [
            normalize_option_label(content[1:-1])
            for content in contents
        ]
        if any(
            marker in content
            for content in normalized_contents
            for marker in _VERIFIED_PROMOTION_MARKERS
        ):
            normalized = normalized[bracket_prefix.end():]

    return _LEADING_PROMOTION_TEXT_PATTERN.sub("", normalized).strip()


def normalize_option_mapping_key(value: str) -> str:
    """표시값을 보존한 채 옵션 매핑 비교에만 쓰는 정규화 키."""

    without_promotion = _strip_verified_promotion_prefix(value)
    without_promotion = _TRAILING_PACKAGE_TEXT_PATTERN.sub(
        "", without_promotion
    )
    without_shade_suffix = re.sub(
        r"(?<=\d)\s*호",
        "",
        without_promotion,
    )
    return normalize_option_label(without_shade_suffix)


def normalize_repeated_full_option_label(value: str) -> str:
    """반복 full-label 문법 전용 비교 key.

    연구에서 확인된 NFKC·대소문자·공백 차이만 정규화한다.
    기획 문구, `호`, 구두점이나 label 일부는 제거하지 않는다.
    """

    return "".join(
        character.casefold()
        for character in unicodedata.normalize("NFKC", value.strip())
        if not character.isspace()
    )


def _canonical_option_display_name(value: str) -> str:
    """첫 원본 옵션에서 프로모션 표기만 걷어낸 안정적인 표시명."""

    without_promotion = _strip_verified_promotion_prefix(value)
    without_promotion = _TRAILING_PACKAGE_TEXT_PATTERN.sub(
        "", without_promotion
    )
    without_shade_suffix = re.sub(
        r"(?<=\d)\s*호",
        "",
        without_promotion,
    )
    separated = re.sub(r"[/_·-]+", " ", without_shade_suffix)
    display_name = " ".join(
        unicodedata.normalize("NFKC", separated).split()
    )
    return display_name or " ".join(value.split())


def canonicalize_product_options(
    options: list[ProductOption],
) -> list[ProductOption]:
    """한 상품의 옵션을 비교용 key 기준 canonical 그룹으로 병합한다."""

    grouped: dict[str, ProductOption] = {}
    ordered_keys: list[str] = []

    for option_index, option in enumerate(options):
        mapping_key = normalize_option_mapping_key(
            option.raw_option_name
        )
        # 빈 key는 다른 빈 key와 합치지 않고 각자 unsupported 판정을
        # 받을 수 있도록 원본 순서 기반 내부 group key를 사용한다.
        group_key = mapping_key or f"__empty__:{option_index}"
        source_names = option.source_option_names or [
            option.raw_option_name
        ]
        source_ids = option.source_option_ids or (
            [option.source_option_id]
            if option.source_option_id
            else []
        )

        canonical = grouped.get(group_key)
        if canonical is None:
            ordered_keys.append(group_key)
            if not mapping_key:
                # mapping_key가 비어 group_key가 option_index로만
                # 갈라진 옵션도, internal_option_key는 여기서 새로
                # 확정한다(원본 option.internal_option_key를 그대로
                # 두지 않는다) - source id/value가 있으면 그것을,
                # 없으면 option_index를 시드로 써서 이 함수 호출
                # 안에서 항상 고유하게 만든다.
                empty_key_seed = (
                    source_ids[0]
                    if source_ids
                    else f"__empty_index__:{option_index}"
                )
                grouped[group_key] = option.model_copy(
                    update={
                        "internal_option_key": make_internal_option_key(
                            f"__unmapped__:{empty_key_seed}"
                        ),
                        "source_option_names": list(source_names),
                        "source_option_ids": list(source_ids),
                    }
                )
                continue

            display_name = _canonical_option_display_name(
                option.raw_option_name
            )
            grouped[group_key] = option.model_copy(
                update={
                    "internal_option_key": make_internal_option_key(
                        mapping_key
                    ),
                    "option_name": display_name,
                    "normalized_name": mapping_key,
                    "source_option_names": list(source_names),
                    "source_option_ids": list(source_ids),
                }
            )
            continue

        merged_names = list(canonical.source_option_names)
        for source_name in source_names:
            if source_name not in merged_names:
                merged_names.append(source_name)
        merged_ids = list(canonical.source_option_ids)
        for source_id in source_ids:
            if source_id not in merged_ids:
                merged_ids.append(source_id)
        grouped[group_key] = canonical.model_copy(
            update={
                "source_option_names": merged_names,
                "source_option_ids": merged_ids,
            }
        )

    return [grouped[key] for key in ordered_keys]


def normalize_text_with_indexes(value: str) -> NormalizedTextIndex:
    normalized: list[str] = []
    indexes: list[int] = []

    for original_index, character in enumerate(value):
        if character.isspace() or character in _REMOVED_CHARACTERS:
            continue

        # 문자 단위로 NFKC 정규화해 전각/반각, 호환 문자 차이를
        # 없애면서도, 정규화로 문자 수가 늘어나더라도 각 결과
        # 문자를 같은 original_index에 매핑해 raw_text 슬라이싱이
        # 항상 원본 위치를 가리키도록 한다.
        for folded_character in unicodedata.normalize(
            "NFKC", character
        ).casefold():
            if (
                folded_character.isspace()
                or folded_character in _REMOVED_CHARACTERS
            ):
                continue
            normalized.append(folded_character)
            indexes.append(original_index)

    return NormalizedTextIndex(
        normalized_text="".join(normalized),
        original_indexes=indexes,
    )


def normalize_option_mapping_text_with_indexes(
    value: str,
) -> NormalizedTextIndex:
    """원문 위치를 보존하면서 숫자 뒤의 색상 단위 `호`만 제거한다."""

    indexed = normalize_text_with_indexes(value)
    normalized: list[str] = []
    indexes: list[int] = []
    for character, original_index in zip(
        indexed.normalized_text,
        indexed.original_indexes,
        strict=True,
    ):
        if (
            character == "호"
            and normalized
            and normalized[-1].isdigit()
        ):
            continue
        normalized.append(character)
        indexes.append(original_index)
    return NormalizedTextIndex(
        normalized_text="".join(normalized),
        original_indexes=indexes,
    )


def make_internal_option_key(
    normalized_name: str,
) -> str:
    if not normalized_name:
        raise ValueError(
            "내부 옵션 키를 생성할 정규화 옵션명이 비어 있습니다."
        )
    return hashlib.sha256(
        normalized_name.encode("utf-8")
    ).hexdigest()[:16]


def make_product_option(
    option_name: str,
    *,
    source_option_id: str | None = None,
    image_url: str | None = None,
) -> ProductOption:
    raw_name = option_name.strip()
    normalized_name = normalize_option_label(raw_name)
    if not raw_name or not normalized_name:
        raise ValueError("리뷰 옵션명이 비어 있습니다.")

    return ProductOption(
        internal_option_key=make_internal_option_key(
            normalized_name
        ),
        source_option_id=(
            source_option_id.strip()
            if source_option_id and source_option_id.strip()
            else None
        ),
        option_name=raw_name,
        raw_option_name=raw_name,
        normalized_name=normalized_name,
        image_url=(
            image_url.strip()
            if image_url and image_url.strip()
            else None
        ),
    )


@dataclass(frozen=True)
class _HeaderMatch:
    option_index: int
    normalized_start: int
    normalized_end: int
    original_start: int
    original_end: int
    method: str
    confidence: float
    duplicate_header_spans: tuple[tuple[int, int], ...] = ()


ExplicitHeaderGrammar = Literal[
    "bracketed",
    "star_colon",
    "hash_alphanumeric_code",
    "malformed_bracket",
    "unbracketed_option_exact",
    "unbracketed_bilingual",
    "repeated_unbracketed_full_option_label",
]
RepeatedFullLabelVariant = Literal[
    "full_label_direct",
    "product_prefix_plus_full_label",
]
DocumentFormat = Literal[
    "option_full_sections",
    "hierarchical_option_internal_sections",
    "needs_review",
]
DocumentHeaderStatus = Literal[
    "matched",
    "orphan",
    "ambiguous",
    "malformed",
]


@dataclass(frozen=True)
class DocumentHeaderDiagnostic:
    raw_header: str
    label: str
    normalized_label: str
    grammar: ExplicitHeaderGrammar
    start_index: int
    end_index: int
    status: DocumentHeaderStatus
    matched_option_keys: tuple[str, ...] = ()
    variant: RepeatedFullLabelVariant | None = None
    section_body_start_index: int | None = None
    section_body_end_index: int | None = None
    mapping_rule: str | None = None


@dataclass(frozen=True)
class OrphanDocumentSection:
    header: DocumentHeaderDiagnostic
    raw_ingredient_text: str
    ingredients: tuple[str, ...]
    start_index: int
    end_index: int


@dataclass(frozen=True)
class OptionFullSectionParseResult:
    sections: tuple[OptionIngredientSection, ...]
    headers: tuple[DocumentHeaderDiagnostic, ...]
    orphan_document_sections: tuple[OrphanDocumentSection, ...]
    document_format: DocumentFormat = "option_full_sections"
    structure_reason: str | None = None
    top_level_header_count: int = 0
    nested_header_count: int = 0

    @property
    def orphan_document_section_count(self) -> int:
        return len(self.orphan_document_sections)

    @property
    def unmatched_sale_option_count(self) -> int:
        return sum(
            section.mapping_status == "unmatched"
            for section in self.sections
        )

    @property
    def malformed_header_count(self) -> int:
        return sum(header.status == "malformed" for header in self.headers)

    @property
    def ambiguous_header_count(self) -> int:
        return sum(header.status == "ambiguous" for header in self.headers)


@dataclass(frozen=True)
class _ExplicitHeader:
    raw_header: str
    label: str
    normalized_label: str
    grammar: ExplicitHeaderGrammar
    start_index: int
    end_index: int
    malformed: bool = False
    variant: RepeatedFullLabelVariant | None = None


@dataclass(frozen=True)
class _OptionHeaderAliases:
    full: str
    shade_code: str | None
    color_name: str | None
    conservative_full: str


@dataclass(frozen=True)
class _TopLevelOptionHeader:
    option_index: int
    header: _ExplicitHeader


@dataclass(frozen=True)
class _DocumentStructureAssessment:
    document_format: DocumentFormat
    reason: str | None = None
    top_level_headers: tuple[_TopLevelOptionHeader, ...] = ()
    nested_headers: tuple[_ExplicitHeader, ...] = ()


def _normalized_shade_code(value: str) -> str:
    normalized = normalize_option_mapping_key(value)
    match = re.fullmatch(
        r"(?i)(?:(?P<prefix>[a-z]+)(?P<number_a>\d+)|"
        r"(?P<number_b>\d+(?:\.\d+)?)(?P<suffix>[a-z]+)?)",
        normalized,
    )
    if match is None:
        return normalized
    number = match.group("number_a") or match.group("number_b") or ""
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    else:
        number = str(int(number))
    return (
        f"{(match.group('prefix') or '').casefold()}"
        f"{number}{(match.group('suffix') or '').casefold()}"
    )


def _option_header_aliases(option: ProductOption) -> _OptionHeaderAliases:
    display_name = _canonical_option_display_name(option.raw_option_name)
    code_match = re.match(
        r"(?i)^\s*(?P<code>(?:[a-z]+\s*)?\d+(?:\.\d+)?"
        r"(?:\s*[a-z]+)?)(?:\s*호)?(?=\s|$)",
        display_name,
    )
    if code_match is None:
        return _OptionHeaderAliases(
            full=normalize_option_mapping_key(display_name),
            shade_code=None,
            color_name=normalize_option_mapping_key(display_name) or None,
            conservative_full=(
                normalize_repeated_full_option_label(display_name)
            ),
        )

    code = _normalized_shade_code(code_match.group("code"))
    color_name = normalize_option_mapping_key(
        display_name[code_match.end():]
    )
    return _OptionHeaderAliases(
        full=normalize_option_mapping_key(display_name),
        shade_code=code or None,
        color_name=color_name or None,
        conservative_full=(
            normalize_repeated_full_option_label(display_name)
        ),
    )


def _extract_explicit_headers(raw_text: str) -> list[_ExplicitHeader]:
    headers: list[_ExplicitHeader] = []
    patterns: tuple[tuple[re.Pattern[str], ExplicitHeaderGrammar], ...] = (
        (_EXPLICIT_BRACKET_HEADER_PATTERN, "bracketed"),
        (_EXPLICIT_STAR_COLON_HEADER_PATTERN, "star_colon"),
        (_EXPLICIT_HASH_CODE_HEADER_PATTERN, "hash_alphanumeric_code"),
    )
    for pattern, grammar in patterns:
        for match in pattern.finditer(raw_text):
            label = match.group("label").strip()
            headers.append(
                _ExplicitHeader(
                    raw_header=match.group(0),
                    label=label,
                    normalized_label=normalize_option_mapping_key(label),
                    grammar=grammar,
                    start_index=match.start(),
                    end_index=match.end(),
                )
            )

    for pattern in _MALFORMED_BRACKET_HEADER_PATTERNS:
        for match in pattern.finditer(raw_text):
            label = match.group("label").strip()
            headers.append(
                _ExplicitHeader(
                    raw_header=match.group(0),
                    label=label,
                    normalized_label=normalize_option_mapping_key(label),
                    grammar="malformed_bracket",
                    start_index=match.start(),
                    end_index=match.end(),
                    malformed=True,
                )
            )

    # 서로 겹치는 grammar가 생기면 더 긴 명시적 표기 하나만 남긴다.
    ordered = sorted(
        headers,
        key=lambda header: (
            header.start_index,
            -(header.end_index - header.start_index),
            header.grammar,
        ),
    )
    distinct: list[_ExplicitHeader] = []
    for header in ordered:
        if distinct and header.start_index < distinct[-1].end_index:
            continue
        distinct.append(header)
    return distinct


def _header_option_candidates(
    header: _ExplicitHeader,
    aliases: list[_OptionHeaderAliases],
) -> list[int]:
    if header.grammar == "repeated_unbracketed_full_option_label":
        return [
            option_index
            for option_index, alias in enumerate(aliases)
            if alias.conservative_full == header.normalized_label
        ]

    key = _normalized_shade_code(header.normalized_label)
    candidates = [
        option_index
        for option_index, alias in enumerate(aliases)
        if alias.full == header.normalized_label
    ]
    if not candidates:
        candidates = [
            option_index
            for option_index, alias in enumerate(aliases)
            if alias.shade_code == key
        ]
    if not candidates:
        candidates = [
            option_index
            for option_index, alias in enumerate(aliases)
            if alias.color_name == header.normalized_label
        ]
    return candidates


def _find_top_level_option_headers(
    raw_text: str,
    canonical_options: list[ProductOption],
    valid_headers: list[_ExplicitHeader],
    aliases: list[_OptionHeaderAliases],
) -> list[_TopLevelOptionHeader]:
    candidates: list[_TopLevelOptionHeader] = []
    explicitly_linked: set[int] = set()
    for header in valid_headers:
        option_indexes = _header_option_candidates(header, aliases)
        if len(option_indexes) != 1:
            continue
        option_index = option_indexes[0]
        explicitly_linked.add(option_index)
        candidates.append(
            _TopLevelOptionHeader(option_index=option_index, header=header)
        )

    raw_index = normalize_text_with_indexes(raw_text)
    mapping_index = normalize_option_mapping_text_with_indexes(raw_text)
    for option_index, option in enumerate(canonical_options):
        if option_index in explicitly_linked:
            continue
        match, ambiguous = _find_header_match(
            raw_text,
            raw_index,
            mapping_index,
            option,
            option_index,
        )
        if (
            ambiguous
            or match is None
            or match.duplicate_header_spans
            or match.confidence < 0.9
        ):
            continue
        candidates.append(
            _TopLevelOptionHeader(
                option_index=option_index,
                header=_ExplicitHeader(
                    raw_header=raw_text[
                        match.original_start:match.original_end
                    ],
                    label=option.option_name,
                    normalized_label=normalize_option_mapping_key(
                        option.option_name
                    ),
                    grammar="unbracketed_option_exact",
                    start_index=match.original_start,
                    end_index=match.original_end,
                ),
            )
        )

    # 동일 canonical 옵션에 복수 top-level 후보가 있으면 구조 판단에
    # 임의의 첫 후보를 사용하지 않는다.
    by_option: dict[int, list[_TopLevelOptionHeader]] = {}
    for candidate in candidates:
        by_option.setdefault(candidate.option_index, []).append(candidate)
    unique = [
        headers[0]
        for headers in by_option.values()
        if len(headers) == 1
    ]
    return sorted(unique, key=lambda item: item.header.start_index)


def _unbracketed_bilingual_headers(
    raw_text: str,
) -> list[_ExplicitHeader]:
    return [
        _ExplicitHeader(
            raw_header=match.group("label"),
            label=match.group("label"),
            normalized_label=normalize_option_mapping_key(
                match.group("label")
            ),
            grammar="unbracketed_bilingual",
            start_index=match.start("label"),
            end_index=match.end("label"),
        )
        for match in _UNBRACKETED_BILINGUAL_HEADER_PATTERN.finditer(raw_text)
    ]


def _classify_document_structure(
    raw_text: str,
    canonical_options: list[ProductOption],
    valid_headers: list[_ExplicitHeader],
    aliases: list[_OptionHeaderAliases],
) -> _DocumentStructureAssessment:
    top_headers = _find_top_level_option_headers(
        raw_text,
        canonical_options,
        valid_headers,
        aliases,
    )
    if len(top_headers) < 2:
        return _DocumentStructureAssessment(
            document_format="option_full_sections",
            top_level_headers=tuple(top_headers),
        )

    top_spans = {
        (item.header.start_index, item.header.end_index)
        for item in top_headers
    }
    bilingual_headers = _unbracketed_bilingual_headers(raw_text)
    nested_by_top: list[list[_ExplicitHeader]] = []
    for top_index, top in enumerate(top_headers):
        section_end = (
            top_headers[top_index + 1].header.start_index
            if top_index + 1 < len(top_headers)
            else len(raw_text)
        )
        candidates = [
            header
            for header in (*valid_headers, *bilingual_headers)
            if (
                header.start_index >= top.header.end_index
                and header.start_index < section_end
                and (header.start_index, header.end_index) not in top_spans
                and not _header_option_candidates(header, aliases)
            )
        ]
        candidates.sort(key=lambda header: header.start_index)
        distinct: list[_ExplicitHeader] = []
        for header in candidates:
            if distinct and header.start_index < distinct[-1].end_index:
                continue
            distinct.append(header)

        valid_nested: list[_ExplicitHeader] = []
        for nested_index, header in enumerate(distinct):
            ingredient_end = (
                distinct[nested_index + 1].start_index
                if nested_index + 1 < len(distinct)
                else section_end
            )
            if len(_ingredient_list(raw_text[header.end_index:ingredient_end])) >= 2:
                valid_nested.append(header)
        nested_by_top.append(valid_nested)

    nested_counts = [len(headers) for headers in nested_by_top]
    repeated_sections = sum(count >= 2 for count in nested_counts)
    nested_headers = tuple(
        header for headers in nested_by_top for header in headers
    )
    if repeated_sections >= 2:
        return _DocumentStructureAssessment(
            document_format="hierarchical_option_internal_sections",
            reason=(
                "multiple_top_level_options_with_repeated_valid_nested_headers"
            ),
            top_level_headers=tuple(top_headers),
            nested_headers=nested_headers,
        )

    label_sections: dict[str, set[int]] = {}
    for section_index, headers in enumerate(nested_by_top):
        for header in headers:
            label_sections.setdefault(
                header.normalized_label,
                set(),
            ).add(section_index)
    repeated_nested_label = any(
        len(section_indexes) >= 2
        for section_indexes in label_sections.values()
    )
    sections_with_nested = sum(bool(headers) for headers in nested_by_top)
    if sections_with_nested >= 2 and repeated_nested_label:
        return _DocumentStructureAssessment(
            document_format="needs_review",
            reason="repeated_nested_header_pattern_needs_review",
            top_level_headers=tuple(top_headers),
            nested_headers=nested_headers,
        )

    return _DocumentStructureAssessment(
        document_format="option_full_sections",
        top_level_headers=tuple(top_headers),
        nested_headers=nested_headers,
    )


def _unsupported_structure_result(
    raw_text: str,
    canonical_options: list[ProductOption],
    explicit_headers: list[_ExplicitHeader],
    aliases: list[_OptionHeaderAliases],
    assessment: _DocumentStructureAssessment,
) -> OptionFullSectionParseResult:
    top_by_span = {
        (item.header.start_index, item.header.end_index): item
        for item in assessment.top_level_headers
    }
    structural_headers = [
        *explicit_headers,
        *(
            item.header
            for item in assessment.top_level_headers
            if item.header.grammar == "unbracketed_option_exact"
        ),
        *assessment.nested_headers,
    ]
    ordered: list[_ExplicitHeader] = []
    for header in sorted(
        structural_headers,
        key=lambda item: (item.start_index, item.end_index),
    ):
        if ordered and (
            header.start_index == ordered[-1].start_index
            and header.end_index == ordered[-1].end_index
        ):
            continue
        ordered.append(header)

    diagnostics: list[DocumentHeaderDiagnostic] = []
    orphans: list[OrphanDocumentSection] = []
    for header_index, header in enumerate(ordered):
        span = (header.start_index, header.end_index)
        top = top_by_span.get(span)
        if header.malformed:
            status: DocumentHeaderStatus = "malformed"
        elif top is not None:
            status = "matched"
        else:
            status = "orphan"
        candidates = (
            [top.option_index]
            if top is not None
            else _header_option_candidates(header, aliases)
        )
        diagnostic = DocumentHeaderDiagnostic(
            raw_header=header.raw_header,
            label=header.label,
            normalized_label=header.normalized_label,
            grammar=header.grammar,
            start_index=header.start_index,
            end_index=header.end_index,
            status=status,
            matched_option_keys=tuple(
                canonical_options[index].internal_option_key
                for index in candidates
            ),
        )
        diagnostics.append(diagnostic)
        if status == "orphan":
            section_end = (
                ordered[header_index + 1].start_index
                if header_index + 1 < len(ordered)
                else len(raw_text)
            )
            raw_section = raw_text[header.end_index:section_end].strip()
            orphans.append(
                OrphanDocumentSection(
                    header=diagnostic,
                    raw_ingredient_text=raw_section,
                    ingredients=tuple(_ingredient_list(raw_section)),
                    start_index=header.end_index,
                    end_index=section_end,
                )
            )

    return OptionFullSectionParseResult(
        sections=tuple(
            OptionIngredientSection(
                internal_option_key=option.internal_option_key,
                source_option_id=option.source_option_id,
                option_name=option.option_name,
                mapping_status="unsupported",
                mapping_method=(
                    assessment.reason
                    or "hierarchical_option_internal_sections"
                ),
                mapping_confidence=0.0,
            )
            for option in canonical_options
        ),
        headers=tuple(diagnostics),
        orphan_document_sections=tuple(orphans),
        document_format=assessment.document_format,
        structure_reason=assessment.reason,
        top_level_header_count=len(assessment.top_level_headers),
        nested_header_count=len(assessment.nested_headers),
    )


def _repeated_full_label_prefix_start(
    raw_text: str,
    label_start: int,
) -> int | None:
    window_start = max(
        0,
        label_start - _REPEATED_PREFIX_LOOKBEHIND_LIMIT,
    )
    prefix = _VERIFIED_REPEATED_PRODUCT_PREFIX_PATTERN.search(
        raw_text[window_start:label_start]
    )
    if prefix is None:
        return None
    return window_start + prefix.start()


def _detect_repeated_unbracketed_full_option_headers(
    raw_text: str,
    aliases: list[_OptionHeaderAliases],
) -> list[_ExplicitHeader]:
    """연구로 확인된 반복 숫자+색상 full label만 탐지한다."""

    candidates: list[_ExplicitHeader] = []
    shade_numbers: list[int] = []
    for match in _REPEATED_FULL_OPTION_LABEL_PATTERN.finditer(raw_text):
        label = match.group("label").strip()
        normalized_label = normalize_repeated_full_option_label(label)
        number_match = re.match(r"\d{2}", normalized_label)
        if number_match is None:
            continue

        prefix_start = _repeated_full_label_prefix_start(
            raw_text,
            match.start("label"),
        )
        start_index = (
            prefix_start
            if prefix_start is not None
            else match.start("label")
        )
        variant: RepeatedFullLabelVariant = (
            "product_prefix_plus_full_label"
            if prefix_start is not None
            else "full_label_direct"
        )
        candidates.append(
            _ExplicitHeader(
                raw_header=raw_text[start_index:match.end("label")],
                label=label,
                normalized_label=normalized_label,
                grammar="repeated_unbracketed_full_option_label",
                start_index=start_index,
                end_index=match.end("label"),
                variant=variant,
            )
        )
        shade_numbers.append(int(number_match.group(0)))

    if len(candidates) < _MIN_REPEATED_FULL_LABEL_HEADERS:
        return []
    if len({header.variant for header in candidates}) != 1:
        return []
    if raw_text[:candidates[0].start_index].strip():
        return []
    if shade_numbers != sorted(shade_numbers):
        return []

    exact_candidate_count = sum(
        len(_header_option_candidates(header, aliases)) == 1
        for header in candidates
    )
    if exact_candidate_count < 2:
        return []

    first_ingredient_keys: list[str] = []
    for index, header in enumerate(candidates):
        section_end = (
            candidates[index + 1].start_index
            if index + 1 < len(candidates)
            else len(raw_text)
        )
        raw_section = raw_text[header.end_index:section_end].strip()
        ingredients = _ingredient_list(raw_section)
        if (
            len(raw_section) < _MIN_REPEATED_FULL_LABEL_BODY_LENGTH
            or len(ingredients) < 3
        ):
            return []
        first_ingredient_keys.append(
            normalize_repeated_full_option_label(ingredients[0])
        )

    # 두 연구 문서는 모든 full formula가 같은 첫 base 원료로 시작한다.
    # 이 반복 signature가 없으면 body 중간의 옵션명 언급과 구분할 수
    # 없으므로 새 grammar를 활성화하지 않는다.
    if len(set(first_ingredient_keys)) != 1:
        return []
    return candidates


def parse_option_full_sections(
    raw_text: str,
    options: list[ProductOption],
) -> OptionFullSectionParseResult:
    """명시적 header를 먼저 찾고 option_full_sections만 보수적으로 매핑한다."""

    canonical_options = canonicalize_product_options(options)
    if not raw_text.strip():
        return OptionFullSectionParseResult(
            sections=tuple(
                OptionIngredientSection(
                    internal_option_key=option.internal_option_key,
                    source_option_id=option.source_option_id,
                    option_name=option.option_name,
                    mapping_status="unsupported",
                    mapping_method="raw_text_empty",
                    mapping_confidence=0.0,
                )
                for option in canonical_options
            ),
            headers=(),
            orphan_document_sections=(),
        )

    explicit_headers = _extract_explicit_headers(raw_text)
    valid_headers = [header for header in explicit_headers if not header.malformed]
    malformed_headers = [header for header in explicit_headers if header.malformed]
    aliases = [_option_header_aliases(option) for option in canonical_options]
    structure = _classify_document_structure(
        raw_text,
        canonical_options,
        valid_headers,
        aliases,
    )
    if structure.document_format != "option_full_sections":
        return _unsupported_structure_result(
            raw_text,
            canonical_options,
            explicit_headers,
            aliases,
            structure,
        )

    repeated_full_label_headers = (
        _detect_repeated_unbracketed_full_option_headers(
            raw_text,
            aliases,
        )
        if not valid_headers
        else []
    )
    valid_headers = sorted(
        [*valid_headers, *repeated_full_label_headers],
        key=lambda header: header.start_index,
    )

    assignments: dict[int, list[int]] = {}
    header_candidates: dict[int, list[int]] = {}
    ambiguous_header_indexes: set[int] = set()
    colliding_option_indexes: set[int] = set()
    for header_index, header in enumerate(valid_headers):
        candidates = _header_option_candidates(header, aliases)
        header_candidates[header_index] = candidates
        if len(candidates) == 1:
            assignments.setdefault(candidates[0], []).append(header_index)
        elif len(candidates) > 1:
            ambiguous_header_indexes.add(header_index)
            colliding_option_indexes.update(candidates)

    ambiguous_option_indexes = colliding_option_indexes | {
        option_index
        for option_index, header_indexes in assignments.items()
        if len(header_indexes) > 1
    }
    for option_index in ambiguous_option_indexes:
        ambiguous_header_indexes.update(assignments.get(option_index, []))

    malformed_option_indexes: set[int] = set()
    for header in malformed_headers:
        key = _normalized_shade_code(header.normalized_label)
        candidates = [
            option_index
            for option_index, alias in enumerate(aliases)
            if header.normalized_label in {
                alias.full,
                alias.color_name,
            }
            or key == alias.shade_code
        ]
        if len(candidates) == 1:
            malformed_option_indexes.add(candidates[0])

    boundary_headers = sorted(
        [*explicit_headers, *repeated_full_label_headers],
        key=lambda header: header.start_index,
    )
    next_start: dict[tuple[int, int], int] = {}
    for index, header in enumerate(boundary_headers):
        next_start[(header.start_index, header.end_index)] = (
            boundary_headers[index + 1].start_index
            if index + 1 < len(boundary_headers)
            else len(raw_text)
        )

    sections: list[OptionIngredientSection] = []
    matched_header_indexes: set[int] = set()
    for option_index, option in enumerate(canonical_options):
        if option_index in ambiguous_option_indexes:
            sections.append(
                OptionIngredientSection(
                    internal_option_key=option.internal_option_key,
                    source_option_id=option.source_option_id,
                    option_name=option.option_name,
                    mapping_status="ambiguous",
                    mapping_method="duplicate_explicit_headers",
                    mapping_confidence=0.0,
                    duplicate_header_count=max(
                        0, len(assignments.get(option_index, [])) - 1
                    ),
                )
            )
            continue

        assigned = assignments.get(option_index, [])
        if len(assigned) != 1:
            sections.append(
                OptionIngredientSection(
                    internal_option_key=option.internal_option_key,
                    source_option_id=option.source_option_id,
                    option_name=option.option_name,
                    mapping_status="unmatched",
                    mapping_method=(
                        "malformed_explicit_header"
                        if option_index in malformed_option_indexes
                        else "unmatched_sale_option"
                    ),
                    mapping_confidence=0.0,
                )
            )
            continue

        header_index = assigned[0]
        if header_index in ambiguous_header_indexes:
            sections.append(
                OptionIngredientSection(
                    internal_option_key=option.internal_option_key,
                    source_option_id=option.source_option_id,
                    option_name=option.option_name,
                    mapping_status="ambiguous",
                    mapping_method="colliding_explicit_header_alias",
                    mapping_confidence=0.0,
                )
            )
            continue

        header = valid_headers[header_index]
        matched_header_indexes.add(header_index)
        section_end = next_start[(header.start_index, header.end_index)]
        raw_section = raw_text[header.end_index:section_end].strip()
        ingredients = _ingredient_list(raw_section)
        valid = len(ingredients) >= 2
        sections.append(
            OptionIngredientSection(
                internal_option_key=option.internal_option_key,
                source_option_id=option.source_option_id,
                option_name=option.option_name,
                matched_header=header.raw_header,
                raw_ingredient_text=raw_section,
                ingredients=ingredients if valid else [],
                mapping_status="matched" if valid else "unsupported",
                mapping_method=(
                    "explicit_full_option_label_exact"
                    if (
                        valid
                        and header.grammar
                        == "repeated_unbracketed_full_option_label"
                    )
                    else f"explicit_{header.grammar}_exact"
                    if valid
                    else "invalid_ingredient_section"
                ),
                mapping_confidence=1.0 if valid else 0.0,
            )
        )

    diagnostics: list[DocumentHeaderDiagnostic] = []
    orphans: list[OrphanDocumentSection] = []
    for header_index, header in enumerate(valid_headers):
        candidates = header_candidates.get(header_index, [])
        if header_index in ambiguous_header_indexes:
            status: DocumentHeaderStatus = "ambiguous"
        elif header_index in matched_header_indexes:
            status = "matched"
        else:
            status = "orphan"
        diagnostic = DocumentHeaderDiagnostic(
            raw_header=header.raw_header,
            label=header.label,
            normalized_label=header.normalized_label,
            grammar=header.grammar,
            start_index=header.start_index,
            end_index=header.end_index,
            status=status,
            matched_option_keys=tuple(
                canonical_options[index].internal_option_key
                for index in candidates
            ),
            variant=header.variant,
            section_body_start_index=header.end_index,
            section_body_end_index=next_start[
                (header.start_index, header.end_index)
            ],
            mapping_rule=(
                "explicit_full_option_label_exact"
                if header.grammar
                == "repeated_unbracketed_full_option_label"
                else f"explicit_{header.grammar}_exact"
            ),
        )
        diagnostics.append(diagnostic)
        if status == "orphan":
            section_end = next_start[(header.start_index, header.end_index)]
            raw_section = raw_text[header.end_index:section_end].strip()
            orphans.append(
                OrphanDocumentSection(
                    header=diagnostic,
                    raw_ingredient_text=raw_section,
                    ingredients=tuple(_ingredient_list(raw_section)),
                    start_index=header.end_index,
                    end_index=section_end,
                )
            )

    diagnostics.extend(
        DocumentHeaderDiagnostic(
            raw_header=header.raw_header,
            label=header.label,
            normalized_label=header.normalized_label,
            grammar=header.grammar,
            start_index=header.start_index,
            end_index=header.end_index,
            status="malformed",
        )
        for header in malformed_headers
    )
    diagnostics.sort(key=lambda header: header.start_index)
    return OptionFullSectionParseResult(
        sections=tuple(sections),
        headers=tuple(diagnostics),
        orphan_document_sections=tuple(orphans),
        document_format=structure.document_format,
        structure_reason=structure.reason,
        top_level_header_count=len(structure.top_level_headers),
        nested_header_count=len(structure.nested_headers),
    )


def _all_occurrences(
    haystack: str,
    needle: str,
) -> list[int]:
    if not needle:
        return []

    positions: list[int] = []
    start = 0
    while True:
        position = haystack.find(needle, start)
        if position < 0:
            return positions
        positions.append(position)
        start = position + 1


def _code_and_label_candidate(
    option_name: str,
) -> str | None:
    header_source = _strip_bracket_blocks(option_name)
    code_match = _OPTION_CODE_PATTERN.search(header_source)
    if code_match is None:
        return None

    candidate = normalize_option_mapping_key(
        header_source[code_match.start():]
    )
    code = normalize_option_mapping_key(code_match.group(0))
    if len(candidate) <= len(code):
        # 17N처럼 문자와 숫자가 결합된 전체 shade code는 기존의
        # 안전한 exact match를 유지한다. 숫자만 있는 code fallback은
        # 성분 표기의 숫자와 충돌할 수 있으므로 허용하지 않는다.
        return (
            candidate
            if any(character.isdigit() for character in candidate)
            and any(character.isalpha() for character in candidate)
            else None
        )
    return candidate


def _has_number_and_color_name(value: str) -> bool:
    return any(character.isdigit() for character in value) and any(
        character.isalpha() for character in value
    )


def _safe_alphanumeric_code_candidate(
    option_name: str,
) -> str | None:
    header_source = _strip_bracket_blocks(option_name)
    code_match = _OPTION_CODE_PATTERN.search(header_source)
    if code_match is None:
        return None
    code = normalize_option_mapping_key(code_match.group(0))
    return code if _has_number_and_color_name(code) else None


def _find_header_match(
    raw_text: str,
    raw_index: NormalizedTextIndex,
    mapping_index: NormalizedTextIndex,
    option: ProductOption,
    option_index: int,
) -> tuple[_HeaderMatch | None, bool]:
    mapping_key = normalize_option_mapping_key(option.raw_option_name)
    full_name = normalize_option_label(option.raw_option_name)
    candidates: list[
        tuple[str, str, float, NormalizedTextIndex]
    ] = []
    if mapping_key and _has_number_and_color_name(mapping_key):
        candidates.append(
            (
                mapping_key,
                "normalized_mapping_key",
                1.0,
                mapping_index,
            )
        )
    if full_name and all(
        full_name != candidate
        for candidate, _, _, _ in candidates
    ):
        candidates.append(
            (
                full_name,
                "normalized_full_name",
                0.95,
                raw_index,
            )
        )

    code_and_label = _code_and_label_candidate(
        option.raw_option_name
    )
    if (
        code_and_label
        and _has_number_and_color_name(code_and_label)
        and all(
            code_and_label != candidate
            for candidate, _, _, _ in candidates
        )
    ):
        candidates.append(
            (
                code_and_label,
                "code_and_label",
                0.9,
                mapping_index,
            )
        )

    safe_code = _safe_alphanumeric_code_candidate(
        option.raw_option_name
    )
    if (
        safe_code
        and all(
            safe_code != candidate
            for candidate, _, _, _ in candidates
        )
    ):
        candidates.append(
            (
                safe_code,
                "exact_alphanumeric_code",
                0.8,
                mapping_index,
            )
        )

    for needle, method, confidence, candidate_index in candidates:
        occurrences = _all_occurrences(
            candidate_index.normalized_text,
            needle,
        )
        if len(occurrences) == 0:
            continue

        def original_span(normalized_start: int) -> tuple[int, int]:
            normalized_end = normalized_start + len(needle)
            original_start = candidate_index.original_indexes[
                normalized_start
            ]
            original_end = (
                candidate_index.original_indexes[
                    normalized_end - 1
                ]
                + 1
            )

            # 대괄호 헤더는 괄호까지, 상품명이 옵션 앞에 붙은
            # 헤더는 해당 줄의 시작까지 헤더 범위로 보존한다.
            line_start = raw_text.rfind("\n", 0, original_start) + 1
            header_prefix = raw_text[line_start:original_start]
            if (
                header_prefix.strip()
                and "," not in header_prefix
                and len(normalize_option_label(header_prefix)) <= 100
            ):
                original_start = line_start
            elif (
                original_start > 0
                and raw_text[original_start - 1] in "[({"
            ):
                original_start -= 1

            while (
                original_end < len(raw_text)
                and raw_text[original_end] in "])}"
            ):
                original_end += 1
            return original_start, original_end

        spans = [original_span(position) for position in occurrences]
        original_start, original_end = spans[0]
        normalized_start = occurrences[0]
        normalized_end = normalized_start + len(needle)

        return (
            _HeaderMatch(
                option_index=option_index,
                normalized_start=normalized_start,
                normalized_end=normalized_end,
                original_start=original_start,
                original_end=original_end,
                method=method,
                confidence=confidence,
                duplicate_header_spans=tuple(spans[1:]),
            ),
            False,
        )

    return None, False


def _clean_ingredient_text(value: str) -> str:
    text = value.strip(" \t\r\n:;-–—")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(
        r"(?<=[가-힣A-Za-z])\s*\n\s*(?=[가-힣A-Za-z])",
        "",
        text,
    )
    text = re.sub(r"\s*\n\s*", " ", text)
    return text.strip()


def _ingredient_list(raw_section: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()

    for ingredient in split_raw_ingredient_text(
        _clean_ingredient_text(raw_section)
    ):
        cleaned = re.sub(
            r"\s+",
            " ",
            ingredient,
        ).strip(" \t\r\n:;-–—")
        if not cleaned:
            continue

        dedupe_key = cleaned.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        values.append(cleaned)

    return values


def split_option_ingredient_sections(
    raw_text: str,
    options: list[ProductOption],
) -> list[OptionIngredientSection]:
    options = canonicalize_product_options(options)
    if not raw_text.strip():
        return [
            OptionIngredientSection(
                internal_option_key=option.internal_option_key,
                source_option_id=option.source_option_id,
                option_name=option.option_name,
                mapping_status="unsupported",
                mapping_method="raw_text_empty",
                mapping_confidence=0.0,
            )
            for option in options
        ]

    raw_index = normalize_text_with_indexes(raw_text)
    mapping_index = normalize_option_mapping_text_with_indexes(raw_text)
    matches: dict[int, _HeaderMatch] = {}
    ambiguous_indexes: set[int] = set()
    unsupported_indexes: set[int] = {
        option_index
        for option_index, option in enumerate(options)
        if not normalize_option_mapping_key(option.raw_option_name)
    }

    for option_index, option in enumerate(options):
        if option_index in unsupported_indexes:
            continue
        match, ambiguous = _find_header_match(
            raw_text,
            raw_index,
            mapping_index,
            option,
            option_index,
        )
        if ambiguous:
            ambiguous_indexes.add(option_index)
        elif match is not None:
            matches[option_index] = match

    # 서로 다른 옵션이 정확히 같은 (original_start, original_end)
    # 구간을 가리키면 같은 헤더를 공유하는 패키지 구성 옵션(예:
    # "[본품+리필+파우치] 17N" vs "[본품+리필] 17N")으로 보고
    # ambiguous 처리하지 않는다. 구간이 일부만 겹치거나 경계가
    # 다르면 기존처럼 ambiguous로 남긴다.
    match_items = list(matches.items())
    for left_index, left in match_items:
        for right_index, right in match_items:
            if left_index >= right_index:
                continue
            same_span = (
                left.original_start == right.original_start
                and left.original_end == right.original_end
            )
            if same_span:
                continue
            overlaps = (
                left.original_start < right.original_end
                and right.original_start < left.original_end
            )
            if overlaps:
                ambiguous_indexes.update(
                    {left_index, right_index}
                )

    for option_index in ambiguous_indexes:
        matches.pop(option_index, None)

    ordered_matches = sorted(
        matches.values(),
        key=lambda item: item.original_start,
    )

    # 같은 헤더를 공유하는 옵션들이 항상 같은 구간과 성분 목록을
    # 받도록, 고유한 (start, end) 구간 단위로 다음 경계를 계산한다.
    distinct_spans: list[tuple[int, int]] = []
    for match in ordered_matches:
        distinct_spans.extend(
            [
                (match.original_start, match.original_end),
                *match.duplicate_header_spans,
            ]
        )
    distinct_spans = sorted(set(distinct_spans))

    next_start_by_span: dict[tuple[int, int], int] = {}
    for position, span in enumerate(distinct_spans):
        next_start_by_span[span] = (
            distinct_spans[position + 1][0]
            if position + 1 < len(distinct_spans)
            else len(raw_text)
        )

    section_cache: dict[
        tuple[int, int], tuple[str, list[str], bool]
    ] = {}

    sections: list[OptionIngredientSection] = []
    for option_index, option in enumerate(options):
        if option_index in unsupported_indexes:
            sections.append(
                OptionIngredientSection(
                    internal_option_key=option.internal_option_key,
                    source_option_id=option.source_option_id,
                    option_name=option.option_name,
                    mapping_status="unsupported",
                    mapping_method="empty_mapping_key",
                    mapping_confidence=0.0,
                )
            )
            continue
        if option_index in ambiguous_indexes:
            sections.append(
                OptionIngredientSection(
                    internal_option_key=option.internal_option_key,
                    source_option_id=option.source_option_id,
                    option_name=option.option_name,
                    mapping_status="ambiguous",
                    mapping_method="multiple_or_overlapping_headers",
                    mapping_confidence=0.0,
                )
            )
            continue

        match = matches.get(option_index)
        if match is None:
            sections.append(
                OptionIngredientSection(
                    internal_option_key=option.internal_option_key,
                    source_option_id=option.source_option_id,
                    option_name=option.option_name,
                    mapping_status="unmatched",
                    mapping_method="not_found",
                    mapping_confidence=0.0,
                )
            )
            continue

        span = (match.original_start, match.original_end)
        section_end = next_start_by_span[span]

        if span not in section_cache:
            raw_section = raw_text[
                match.original_end:section_end
            ].strip()
            ingredients = _ingredient_list(raw_section)

            remaining_headers = [
                other_span
                for other_span in distinct_spans
                if (
                    other_span != span
                    and other_span[0] >= match.original_end
                    and other_span[0] < section_end
                )
            ]
            valid = (
                len(ingredients) >= 2
                and not remaining_headers
            )
            section_cache[span] = (
                raw_section,
                ingredients,
                valid,
            )

        raw_section, ingredients, valid = section_cache[span]

        sections.append(
            OptionIngredientSection(
                internal_option_key=option.internal_option_key,
                source_option_id=option.source_option_id,
                option_name=option.option_name,
                matched_header=raw_text[
                    match.original_start:match.original_end
                ],
                raw_ingredient_text=raw_section,
                ingredients=ingredients if valid else [],
                mapping_status=(
                    "matched" if valid else "unsupported"
                ),
                mapping_method=(
                    match.method
                    if valid
                    else "invalid_ingredient_section"
                ),
                mapping_confidence=(
                    match.confidence if valid else 0.0
                ),
                duplicate_header_count=len(
                    match.duplicate_header_spans
                ),
            )
        )

    return sections


# ============================================================
# Shadow parser (진단 전용, production 흐름과 완전히 분리됨)
#
# 아래 코드는 parse_option_full_sections/split_option_ingredient_
# sections와 나란히 실행해 볼 실험용 파서다. 기존 함수는 하나도
# 수정하지 않으며, option_service.py에서도 production
# parse_result나 ready 판정, 캐시 저장에는 전혀 관여하지 않고
# 비교·로깅용 ShadowParseResult만 생성한다.
# ============================================================

SHADOW_PARSER_VERSION = "shadow-option-sections-v1"

_NUMERIC_CHUNK_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")
_ALPHANUMERIC_CHUNK_PATTERN = re.compile(r"(?i)^[a-z]*\d+[a-z]*$")
_SHADOW_LEADING_NUMBER_PATTERN = re.compile(r"\d{1,3}")
_SHADOW_HEADER_STRIP_CHARS = "[](){}★#: "
_SHADOW_OUTER_STRIP_CHARS = "[](){}:;·-–—.,★# "

# production의 _MALFORMED_BRACKET_HEADER_PATTERNS는 "[label)"/"(label]"만
# 다룬다. 실제 웨이크메이크 립 문서에서 관찰된 "{label]" 오타(중괄호로
# 열고 대괄호로 닫음)는 production 문법에 없으므로 shadow 전용으로
# 추가한다. production 패턴/문법 목록 자체는 건드리지 않는다.
_SHADOW_MALFORMED_CURLY_BRACKET_PATTERN = re.compile(
    r"\{(?P<label>[^{}\[\]()\],:\r\n]{1,80})\]"
)

# "1." ~ "9."처럼 숫자+마침표로 이어지는 nested formula 번호는 어떤
# production/shadow header grammar에도 없다. 단일 등장만으로는 절대
# 확정하지 않고(숫자 boundary 단독 확정 금지), 문서 전체에서 1부터
# 끊김 없이 이어지는 연속열일 때만 _split_numbered_dot_body에서
# 유효한 nested formula 경계로 채택한다.
_NUMBERED_DOT_PATTERN = re.compile(
    r"(?<![0-9A-Za-z가-힣.])(?P<label>\d{1,2})\.(?=\s)"
)
_MIN_NUMBERED_DOT_SEQUENCE = 3

_SHADOW_HEADER_GRAMMAR_PATTERNS: tuple[
    tuple[re.Pattern[str], str], ...
] = (
    (_EXPLICIT_BRACKET_HEADER_PATTERN, "bracketed"),
    (_EXPLICIT_STAR_COLON_HEADER_PATTERN, "star_colon"),
    (_EXPLICIT_HASH_CODE_HEADER_PATTERN, "hash_alphanumeric_code"),
    (_MALFORMED_BRACKET_HEADER_PATTERNS[0], "malformed_bracket"),
    (_MALFORMED_BRACKET_HEADER_PATTERNS[1], "malformed_bracket"),
    (
        _SHADOW_MALFORMED_CURLY_BRACKET_PATTERN,
        "shadow_malformed_curly_bracket",
    ),
)


@dataclass(frozen=True)
class BoundaryCandidate:
    """쉼표 청크 단위로 관찰된 잠재적 section 경계 후보.

    성분 사전이 없으므로 사전 부재만으로 header 여부를 확정하지
    않는다. numeric/alphanumeric/text 청크는 그 자체만으로 구조를
    확정하지 않고, embedded_header만 '성분 + 중간 문자열 + 성분'
    패턴에서 실제 경계로 다뤄진다.
    """

    chunk_index: int
    start_index: int
    end_index: int
    preceding_text: str
    boundary_text: str
    following_text: str
    kind: Literal["numeric", "alphanumeric", "text", "embedded_header"]
    grammar: str | None = None


@dataclass(frozen=True)
class IngredientSubsection:
    label: str
    raw_text: str
    ingredients: tuple[str, ...]
    start_index: int
    end_index: int


SectionKind = Literal[
    "ingredient_section",
    "component_group",
    "ambiguous_annotation_candidate",
]


@dataclass(frozen=True)
class AnnotationCandidate:
    """ingredient 문자열 끝에 붙어 있던 bracket 주석을 성분에서 분리해
    보존한 결과. ingredient 분석에서는 제외하되 원문 텍스트와
    원본 위치는 그대로 남긴다."""

    text: str
    start_index: int
    end_index: int


@dataclass(frozen=True)
class IngredientSection:
    raw_header: str
    header_start_index: int
    header_end_index: int
    body_start_index: int
    body_end_index: int
    raw_ingredient_text: str
    ingredients: tuple[str, ...]
    subsections: tuple[IngredientSubsection, ...] = ()
    section_kind: SectionKind = "ingredient_section"
    annotation_candidates: tuple[AnnotationCandidate, ...] = ()
    formula_boundary_diagnostics: tuple["FormulaBoundaryDiagnostic", ...] = ()


@dataclass(frozen=True)
class OptionSectionMapping:
    internal_option_key: str
    option_name: str
    section_index: int | None
    mapping_status: OptionMappingStatus
    mapping_method: str
    mapping_confidence: float


@dataclass(frozen=True)
class ShadowParseResult:
    sections: tuple[IngredientSection, ...]
    boundary_candidates: tuple[BoundaryCandidate, ...]
    document_format: DocumentFormat
    structure_reason: str | None
    mappings: tuple[OptionSectionMapping, ...]
    orphan_section_count: int
    matched_count: int
    unmatched_count: int
    ambiguous_count: int
    unsupported_count: int
    parser_version: str = SHADOW_PARSER_VERSION


def _split_comma_chunks_with_offsets(
    raw_text: str,
) -> list[tuple[str, int, int]]:
    """괄호 안/숫자 사이 쉼표는 보존하며 원본 위치를 함께 반환한다.

    ingredient_parsing.split_raw_ingredient_text와 같은 깊이 추적
    규칙을 쓰므로 "(CI 77891)" 같은 표기는 항상 하나의 청크로
    보존된다.
    """

    chunks: list[tuple[str, int, int]] = []
    depth = 0
    chunk_start = 0
    for index, char in enumerate(raw_text):
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            previous = raw_text[index - 1] if index > 0 else ""
            following = (
                raw_text[index + 1] if index + 1 < len(raw_text) else ""
            )
            if previous.isdigit() and following.isdigit():
                continue
            chunks.append((raw_text[chunk_start:index], chunk_start, index))
            chunk_start = index + 1
    chunks.append((raw_text[chunk_start:], chunk_start, len(raw_text)))
    return chunks


def _trim_span(
    raw_text: str,
    start: int,
    end: int,
) -> tuple[str, int, int]:
    segment = raw_text[start:end]
    left_trim = len(segment) - len(segment.lstrip())
    right_trim = len(segment) - len(segment.rstrip())
    return (
        segment.strip(),
        start + left_trim,
        end - right_trim,
    )


def _classify_chunk_kind(
    chunk_text: str,
) -> Literal["numeric", "alphanumeric", "text"]:
    stripped = chunk_text.strip()
    if not stripped:
        return "text"
    if _NUMERIC_CHUNK_PATTERN.fullmatch(stripped):
        return "numeric"
    if (
        len(stripped) <= 8
        and _ALPHANUMERIC_CHUNK_PATTERN.fullmatch(stripped)
        and any(character.isdigit() for character in stripped)
        and any(character.isalpha() for character in stripped)
    ):
        return "alphanumeric"
    return "text"


def _first_header_match_in_chunk(
    chunk_text: str,
) -> tuple[re.Match[str], str] | None:
    best: tuple[re.Match[str], str] | None = None
    for pattern, grammar in _SHADOW_HEADER_GRAMMAR_PATTERNS:
        match = pattern.search(chunk_text)
        if match is None:
            continue
        if best is None or match.start() < best[0].start():
            best = (match, grammar)
    return best


def extract_boundary_candidates(
    raw_text: str,
) -> list[BoundaryCandidate]:
    """쉼표 청크를 순차 처리하며 잠재적 section 경계를 모은다.

    청크 안에서 '성분 + 중간 문자열 + 성분' 형태로 header 표기가
    끼어 있으면 embedded_header 후보를 만든다. 그 외 청크는
    numeric/alphanumeric/text로만 분류하고, 이 분류 자체는 어떤
    top-level/formula 경계도 즉시 확정하지 않는다.
    """

    candidates: list[BoundaryCandidate] = []
    for chunk_index, (chunk_text, chunk_start, chunk_end) in enumerate(
        _split_comma_chunks_with_offsets(raw_text)
    ):
        trimmed, trimmed_start, trimmed_end = _trim_span(
            raw_text, chunk_start, chunk_end
        )
        if not trimmed:
            continue

        header_hit = _first_header_match_in_chunk(trimmed)
        if header_hit is not None and header_hit[0].start() > 0:
            match, grammar = header_hit
            preceding_text = trimmed[: match.start()].strip()
            following_text = trimmed[match.end():].strip()
            if preceding_text and following_text:
                candidates.append(
                    BoundaryCandidate(
                        chunk_index=chunk_index,
                        start_index=trimmed_start + match.start(),
                        end_index=trimmed_start + match.end(),
                        preceding_text=preceding_text,
                        boundary_text=match.group(0),
                        following_text=following_text,
                        kind="embedded_header",
                        grammar=grammar,
                    )
                )
                continue

        candidates.append(
            BoundaryCandidate(
                chunk_index=chunk_index,
                start_index=trimmed_start,
                end_index=trimmed_end,
                preceding_text="",
                boundary_text=trimmed,
                following_text="",
                kind=_classify_chunk_kind(trimmed),
            )
        )

    return candidates


def build_ingredient_sections(
    raw_text: str,
) -> tuple[IngredientSection, ...]:
    """comma chunk를 순차 처리해 header/body 경계만으로 section을 만든다.

    canonical option 정보는 전혀 사용하지 않는다. 첫 section은
    원문이 'raw header + 첫 성분'으로 붙어 있을 수 있으므로 첫
    청크에서만 header와 첫 성분을 분리해서 처리하고, 이후 청크는
    embedded_header 경계를 만나기 전까지 현재 section에 누적한다.
    """

    if not raw_text.strip():
        return ()

    chunks = _split_comma_chunks_with_offsets(raw_text)
    boundary_by_chunk = {
        candidate.chunk_index: candidate
        for candidate in extract_boundary_candidates(raw_text)
        if candidate.kind == "embedded_header"
    }

    open_sections: list[dict] = []

    def _open_section(
        raw_header: str,
        header_start: int,
        header_end: int,
        body_start: int,
    ) -> None:
        open_sections.append(
            {
                "raw_header": raw_header,
                "header_start_index": header_start,
                "header_end_index": header_end,
                "body_start_index": body_start,
                "body_end_index": body_start,
                "ingredients": [],
            }
        )

    def _append_ingredient(text: str, end_index: int) -> None:
        cleaned = re.sub(r"\s+", " ", text).strip(" \t\r\n:;-–—")
        if not open_sections:
            _open_section("", end_index, end_index, end_index)
        current = open_sections[-1]
        if cleaned:
            current["ingredients"].append(cleaned)
        current["body_end_index"] = end_index

    for chunk_index, (chunk_text, chunk_start, chunk_end) in enumerate(
        chunks
    ):
        trimmed, trimmed_start, trimmed_end = _trim_span(
            raw_text, chunk_start, chunk_end
        )
        if not trimmed:
            continue

        if chunk_index == 0:
            header_hit = _first_header_match_in_chunk(trimmed)
            if header_hit is not None and header_hit[0].start() == 0:
                match, _grammar = header_hit
                header_end = trimmed_start + match.end()
                _open_section(
                    match.group(0),
                    trimmed_start,
                    header_end,
                    header_end,
                )
                remainder = trimmed[match.end():]
                if remainder.strip():
                    _append_ingredient(remainder, trimmed_end)
                continue
            _open_section("", trimmed_start, trimmed_start, trimmed_start)
            _append_ingredient(trimmed, trimmed_end)
            continue

        candidate = boundary_by_chunk.get(chunk_index)
        if candidate is not None:
            if candidate.preceding_text:
                _append_ingredient(
                    candidate.preceding_text, candidate.start_index
                )
            _open_section(
                candidate.boundary_text,
                candidate.start_index,
                candidate.end_index,
                candidate.end_index,
            )
            if candidate.following_text:
                _append_ingredient(candidate.following_text, trimmed_end)
            continue

        header_hit = _first_header_match_in_chunk(trimmed)
        if (
            header_hit is not None
            and header_hit[0].start() == 0
            and not trimmed[header_hit[0].end():].strip()
        ):
            match, _grammar = header_hit
            header_end = trimmed_start + match.end()
            _open_section(
                match.group(0),
                trimmed_start,
                header_end,
                header_end,
            )
            continue

        _append_ingredient(trimmed, trimmed_end)

    sections: list[IngredientSection] = []
    for entry in open_sections:
        raw_body = raw_text[
            entry["body_start_index"]:entry["body_end_index"]
        ].strip()
        seen: set[str] = set()
        ingredients: list[str] = []
        for ingredient in entry["ingredients"]:
            key = ingredient.casefold()
            if key in seen:
                continue
            seen.add(key)
            ingredients.append(ingredient)
        sections.append(
            IngredientSection(
                raw_header=entry["raw_header"],
                header_start_index=entry["header_start_index"],
                header_end_index=entry["header_end_index"],
                body_start_index=entry["body_start_index"],
                body_end_index=entry["body_end_index"],
                raw_ingredient_text=raw_body,
                ingredients=tuple(ingredients),
            )
        )
    return tuple(sections)


def _leading_header_number(raw_header: str) -> int | None:
    if not raw_header:
        return None
    stripped = raw_header.strip(_SHADOW_HEADER_STRIP_CHARS)
    match = _SHADOW_LEADING_NUMBER_PATTERN.match(stripped)
    if match is None:
        return None
    return int(match.group(0))


def _split_numbered_dot_body(
    raw_text: str,
    body_start: int,
    body_end: int,
    numbered_dot_matches: list[re.Match[str]],
) -> tuple[IngredientSubsection, ...] | None:
    """단일 top-level header 바로 다음에 오는 1..N 연속 번호 formula만 채택한다.

    최소 개수(_MIN_NUMBERED_DOT_SEQUENCE) 미만이거나, 1부터 끊김
    없이 이어지지 않거나, body 맨 앞이 아닌 중간에서 시작하면
    nested formula로 확정하지 않고 None을 반환한다. 숫자 하나만
    보고 확정하지 않는다는 안전 조건을 그대로 지킨다.
    """

    local_matches = [
        match
        for match in numbered_dot_matches
        if body_start <= match.start() < body_end
    ]
    if len(local_matches) < _MIN_NUMBERED_DOT_SEQUENCE:
        return None
    numbers = [int(match.group("label")) for match in local_matches]
    if numbers != list(range(1, len(numbers) + 1)):
        return None

    first_match = local_matches[0]
    if raw_text[body_start:first_match.start()].strip():
        return None

    boundaries = [match.start() for match in local_matches] + [body_end]
    subsections: list[IngredientSubsection] = []
    for index, match in enumerate(local_matches):
        segment_start = match.end()
        segment_end = boundaries[index + 1]
        raw_segment = raw_text[segment_start:segment_end].strip()
        ingredients: list[str] = []
        seen: set[str] = set()
        for chunk_text, _chunk_start, _chunk_end in (
            _split_comma_chunks_with_offsets(
                raw_text[segment_start:segment_end]
            )
        ):
            cleaned = re.sub(r"\s+", " ", chunk_text).strip(" \t\r\n:;-–—")
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            ingredients.append(cleaned)
        subsections.append(
            IngredientSubsection(
                label=raw_text[match.start():match.end()],
                raw_text=raw_segment,
                ingredients=tuple(ingredients),
                start_index=match.start(),
                end_index=segment_end,
            )
        )
    return tuple(subsections)


_MIN_STRING_FORMULA_CANDIDATES = 2
_MIN_KNOWN_INGREDIENTS_PER_FORMULA = 4
_MAX_FORMULA_BOUNDARY_SUFFIX_WORDS = 4


@dataclass(frozen=True)
class _StringFormulaBoundary:
    middle_start_index: int
    middle_text: str
    right_start_index: int
    chunk_index: int
    raw_chunk: str
    left_ingredient: str
    right_ingredient: str


@dataclass(frozen=True)
class FormulaBoundaryDiagnostic:
    """hierarchical 확정 당시 실제로 사용된 boundary 후보와 body
    평가 결과를 그대로 보존한다. section이 hierarchical로 재구성된
    뒤에는 raw_ingredient_text가 비므로, parser-debug가 나중에 다시
    스캔해도 후보를 재현할 수 없다 - 그래서 확정 시점의 값을 section에
    함께 담아 둔다(재계산이 아니라 보존)."""

    chunk_index: int
    raw_chunk: str
    left_ingredient: str
    boundary_text: str
    right_ingredient: str
    body_ingredient_count: int
    body_exact_known_count: int
    decision: str


@dataclass(frozen=True)
class _StringFormulaEvaluation:
    outcome: Literal["hierarchical", "needs_review", "none"]
    subsections: tuple[IngredientSubsection, ...] = ()
    diagnostics: tuple[FormulaBoundaryDiagnostic, ...] = ()


def _find_formula_boundary_splits(
    words: list[str],
    *,
    has_left_ingredient: bool,
) -> list[tuple[int, int]]:
    """[left?][middle][right] 형태의 유효한 분할을 찾는다.

    왼쪽/오른쪽은 ingredient dictionary exact match만 허용하고,
    중간 문자열은 exact match가 아니어야 한다. 여러 단어로 이뤄진
    성분명(사전에 실제로 존재하는 경우)도 놓치지 않도록 오른쪽/
    왼쪽 단어 개수를 제한된 범위에서 늘려가며 시도하지만, 이 함수
    자체는 어떤 분할도 확정하지 않고 후보만 모두 반환한다.

    section의 첫 chunk가 아닌 일반 chunk(has_left_ingredient=True)도
    실제 문서에서는 콤마가 이미 이전 formula와 깨끗이 분리해 둔
    경우가 있다("소프트 레이 Soft Ray 탤크"처럼 chunk 안에 왼쪽
    성분이 전혀 없는 경우). 이런 chunk를 후보 0개로 흘리지 않도록,
    실제로 exact-known 왼쪽 성분이 존재하는 분할이 하나도 없을
    때만 왼쪽 없는 [middle][right] 분할을 보조로 시도한다. 왼쪽
    성분이 있는 분할이 이미 존재하면 그 결과만 쓰고 왼쪽 없는
    해석은 섞지 않는다(기존에 통과하던 case의 유일성 판정을
    깨뜨리지 않기 위함 - 기준 완화가 아니라 chunk별 우선순위다).
    """

    n = len(words)
    with_left_results: list[tuple[int, int]] = []
    no_left_results: list[tuple[int, int]] = []

    for right_start in range(1, n):
        max_suffix = min(_MAX_FORMULA_BOUNDARY_SUFFIX_WORDS, n - right_start)
        right_matched = False
        for suffix_len in range(1, max_suffix + 1):
            right_candidate = " ".join(
                words[right_start:right_start + suffix_len]
            )
            if is_known_ingredient(right_candidate):
                right_matched = True
                break
        if not right_matched:
            continue

        if has_left_ingredient:
            for left_end in range(1, right_start):
                left_ingredient = " ".join(words[:left_end])
                if not is_known_ingredient(left_ingredient):
                    continue
                middle_text = " ".join(words[left_end:right_start])
                if not middle_text.strip():
                    continue
                if is_known_ingredient(middle_text):
                    continue
                with_left_results.append((left_end, right_start))

        middle_text = " ".join(words[:right_start])
        if middle_text.strip() and not is_known_ingredient(middle_text):
            no_left_results.append((0, right_start))

    # 같은 (left_end, right_start) 경계라도 오른쪽 성분명이 여러
    # 단어 길이로 동시에 매칭될 수 있으므로 경계 위치 기준으로만
    # 유일성을 센다.
    if with_left_results:
        return sorted(set(with_left_results))
    return sorted(set(no_left_results))


def _evaluate_string_formula_structure(
    section: IngredientSection,
    raw_text: str,
) -> _StringFormulaEvaluation:
    """문자열형 내부 formula(번호 없이 이름+성분이 반복되는 구조)를
    ingredient dictionary exact match만으로 탐지한다.

    유일한 분할만 BoundaryCandidate로 인정하고, 같은 chunk에서
    복수 분할이 나오면 ambiguous로 남겨 needs_review 쪽으로
    기운다. 확정된 후보가 2개 미만이거나 formula body가 exact-known
    성분 4개 미만이면 hierarchical로 확정하지 않는다.
    """

    body = raw_text[section.body_start_index:section.body_end_index]
    chunks = _split_comma_chunks_with_offsets(body)

    confirmed: list[_StringFormulaBoundary] = []
    has_ambiguous = False

    for chunk_index, (chunk_text, local_start, _local_end) in enumerate(
        chunks
    ):
        tokens = [
            (match.group(0), match.start(), match.end())
            for match in re.finditer(r"\S+", chunk_text)
        ]
        if len(tokens) < 2:
            continue

        words = [token[0] for token in tokens]
        has_left = chunk_index != 0
        splits = _find_formula_boundary_splits(
            words, has_left_ingredient=has_left
        )
        if not splits:
            continue
        if len(splits) > 1:
            has_ambiguous = True
            continue

        left_end, right_start = splits[0]
        middle_start_local = (
            tokens[left_end][1] if has_left else tokens[0][1]
        )
        right_start_local = tokens[right_start][1]
        middle_text = chunk_text[
            middle_start_local:right_start_local
        ].strip()
        confirmed.append(
            _StringFormulaBoundary(
                middle_start_index=(
                    section.body_start_index
                    + local_start
                    + middle_start_local
                ),
                middle_text=middle_text,
                right_start_index=(
                    section.body_start_index
                    + local_start
                    + right_start_local
                ),
                chunk_index=chunk_index,
                raw_chunk=chunk_text.strip(),
                left_ingredient=(
                    " ".join(words[:left_end]) if has_left else ""
                ),
                right_ingredient=" ".join(words[right_start:]),
            )
        )

    if len(confirmed) < 1:
        return _StringFormulaEvaluation(outcome="none")

    if has_ambiguous:
        return _StringFormulaEvaluation(outcome="needs_review")

    if len(confirmed) < _MIN_STRING_FORMULA_CANDIDATES:
        return _StringFormulaEvaluation(outcome="none")

    segment_starts = [section.body_start_index] + [
        boundary.right_start_index for boundary in confirmed
    ]
    segment_ends = [
        boundary.middle_start_index for boundary in confirmed
    ] + [section.body_end_index]
    segment_labels = [""] + [
        boundary.middle_text for boundary in confirmed
    ]

    subsections: list[IngredientSubsection] = []
    diagnostics: list[FormulaBoundaryDiagnostic] = []
    for position, (label, start, end) in enumerate(
        zip(segment_labels, segment_starts, segment_ends, strict=True)
    ):
        if start >= end or not raw_text[start:end].strip():
            # section 첫 chunk 자체가 boundary candidate였던 경우
            # (예: "1. 정제수, ...") 앞에 남는 빈/공백뿐인 구간은
            # formula가 아니므로 건너뛴다.
            continue

        raw_segment = raw_text[start:end].strip()
        ingredients: list[str] = []
        seen: set[str] = set()
        for chunk_text, _s, _e in _split_comma_chunks_with_offsets(
            raw_text[start:end]
        ):
            cleaned = re.sub(r"\s+", " ", chunk_text).strip(" \t\r\n:;-–—")
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            ingredients.append(cleaned)

        known_count = sum(
            1 for ingredient in ingredients if is_known_ingredient(ingredient)
        )
        if known_count < _MIN_KNOWN_INGREDIENTS_PER_FORMULA:
            return _StringFormulaEvaluation(outcome="needs_review")

        subsections.append(
            IngredientSubsection(
                label=label,
                raw_text=raw_segment,
                ingredients=tuple(ingredients),
                start_index=start,
                end_index=end,
            )
        )
        # position 0은 section의 첫 body(어떤 boundary도 열지 않은
        # 구간)이므로 boundary 정보가 없다. position > 0은
        # confirmed[position - 1]이 이 body를 연 boundary다
        # (segment_labels/starts/ends가 [""] + confirmed 순서로
        # 만들어졌기 때문).
        boundary = confirmed[position - 1] if position > 0 else None
        diagnostics.append(
            FormulaBoundaryDiagnostic(
                chunk_index=boundary.chunk_index if boundary else -1,
                raw_chunk=boundary.raw_chunk if boundary else "",
                left_ingredient=(
                    boundary.left_ingredient if boundary else ""
                ),
                boundary_text=label,
                right_ingredient=(
                    boundary.right_ingredient if boundary else ""
                ),
                body_ingredient_count=len(ingredients),
                body_exact_known_count=known_count,
                decision="confirmed",
            )
        )

    if len(subsections) < _MIN_STRING_FORMULA_CANDIDATES:
        return _StringFormulaEvaluation(outcome="none")

    return _StringFormulaEvaluation(
        outcome="hierarchical",
        subsections=tuple(subsections),
        diagnostics=tuple(diagnostics),
    )


def classify_shadow_document_structure(
    sections: tuple[IngredientSection, ...],
    raw_text: str,
) -> tuple[tuple[IngredientSection, ...], DocumentFormat, str | None]:
    """반복·번호열·번호 재시작·상위 header 존재 여부로 구조를 판정한다.

    0) ingredient dictionary exact match로만 판정하는 문자열형
       내부 formula가 확인되면(유일한 분할 후보 2개 이상, 각 formula
       body가 exact-known 성분 4개 이상) 그 결과를 우선 채택한다.
       분할이 애매하면(복수 분할, 성분 수 미달) flat으로 강제하지
       않고 needs_review로 남긴다.
    1) 그 외의 경우, 단일 top-level header 바로 다음에 1..N 연속
       번호 formula가 이어지면(예: "1." ~ "9.") 그 header 하나를
       top-level로 두고 번호 formula들을 subsections로 묶는다
       (기존 규칙, 변경 없음).
    2) 그 외에는 번호가 재시작되는 지점을 기준으로 flat 목록을
       상위/하위 구조로 재구성한다(기존 규칙, 변경 없음).
    재구성된 상위 section은 자신의 ingredients를 갖지 않고, 원래
    section/formula들을 subsections로만 보존한다(내부 formula
    병합 금지). nested formula가 확정되면 판매 옵션 매핑은
    map_sections_to_canonical_options에서 unsupported로 남는다.
    """

    # 0) 문자열형 내부 formula는 top-level section이 하나뿐인 문서로
    # 국한되지 않는다 - 여러 top-level section(예: 여러 색상 옵션)
    # 각각이 독립적으로 내부 formula 반복 구조를 가질 수 있으므로
    # header가 있는 모든 section을 개별적으로 평가한다.
    string_formula_evaluations = [
        (index, _evaluate_string_formula_structure(section, raw_text))
        for index, section in enumerate(sections)
        if section.raw_header
    ]
    if any(
        result.outcome == "needs_review"
        for _, result in string_formula_evaluations
    ):
        return (
            sections,
            "needs_review",
            "shadow_string_formula_boundary_ambiguous",
        )

    hierarchical_by_index = {
        index: result
        for index, result in string_formula_evaluations
        if result.outcome == "hierarchical"
    }
    if hierarchical_by_index:
        restructured = tuple(
            (
                IngredientSection(
                    raw_header=section.raw_header,
                    header_start_index=section.header_start_index,
                    header_end_index=section.header_end_index,
                    body_start_index=section.body_start_index,
                    body_end_index=section.body_end_index,
                    raw_ingredient_text="",
                    ingredients=(),
                    subsections=hierarchical_by_index[index].subsections,
                    formula_boundary_diagnostics=(
                        hierarchical_by_index[index].diagnostics
                    ),
                )
                if index in hierarchical_by_index
                else section
            )
            for index, section in enumerate(sections)
        )
        return (
            restructured,
            "hierarchical_option_internal_sections",
            "shadow_string_formula_boundary_sequence",
        )

    if len(sections) == 1 and sections[0].raw_header:
        single = sections[0]

        numbered_dot_matches = list(_NUMBERED_DOT_PATTERN.finditer(raw_text))
        numbered_subsections = _split_numbered_dot_body(
            raw_text,
            single.body_start_index,
            single.body_end_index,
            numbered_dot_matches,
        )
        if numbered_subsections is not None:
            top_section = IngredientSection(
                raw_header=single.raw_header,
                header_start_index=single.header_start_index,
                header_end_index=single.header_end_index,
                body_start_index=single.body_start_index,
                body_end_index=single.body_end_index,
                raw_ingredient_text="",
                ingredients=(),
                subsections=numbered_subsections,
            )
            return (
                (top_section,),
                "hierarchical_option_internal_sections",
                "shadow_numbered_dot_formula_sequence",
            )

    headered = [
        (index, section)
        for index, section in enumerate(sections)
        if section.raw_header
    ]
    if len(headered) < 2:
        return sections, "option_full_sections", None

    numbers = [
        _leading_header_number(section.raw_header)
        for _, section in headered
    ]

    # 완전히 같은 header가 다시 나타나는 인접 중복은 새 top-level
    # 그룹의 시작이 아니라 같은 옵션을 가리키는 duplicate이므로
    # restart로 세지 않는다. 이 경우는 duplicate section mapping이
    # 되어 map_sections_to_canonical_options에서 ambiguous로
    # 걸러진다.
    restart_positions: list[int] = []
    running_max: int | None = None
    for position, number in enumerate(numbers):
        if number is None:
            continue
        if (
            running_max is not None
            and number <= running_max
            and position > 0
            and _shadow_normalize_label(headered[position][1].raw_header)
            != _shadow_normalize_label(headered[position - 1][1].raw_header)
        ):
            restart_positions.append(position)
        running_max = (
            number if running_max is None else max(running_max, number)
        )

    if not restart_positions:
        return sections, "option_full_sections", None

    group_boundaries = [0, *restart_positions, len(headered)]
    groups = [
        [
            headered[position][0]
            for position in range(
                group_boundaries[group_index],
                group_boundaries[group_index + 1],
            )
        ]
        for group_index in range(len(group_boundaries) - 1)
    ]
    groups = [group for group in groups if group]
    if len(groups) < 2:
        return sections, "option_full_sections", None

    regrouped: list[IngredientSection] = []
    for group in groups:
        first_section = sections[group[0]]
        last_section = sections[group[-1]]
        subsections = tuple(
            IngredientSubsection(
                label=sections[section_index].raw_header,
                raw_text=sections[section_index].raw_ingredient_text,
                ingredients=sections[section_index].ingredients,
                start_index=sections[section_index].header_start_index,
                end_index=sections[section_index].body_end_index,
            )
            for section_index in group
        )
        regrouped.append(
            IngredientSection(
                raw_header=first_section.raw_header,
                header_start_index=first_section.header_start_index,
                header_end_index=first_section.header_end_index,
                body_start_index=first_section.body_start_index,
                body_end_index=last_section.body_end_index,
                raw_ingredient_text="",
                ingredients=(),
                subsections=subsections,
            )
        )

    return (
        tuple(regrouped),
        "hierarchical_option_internal_sections",
        "shadow_numbered_header_sequence_restart",
    )


def _shadow_normalize_label(value: str) -> str:
    """section 매핑 전용 보수적 정규화.

    허용: NFKC, casefold, 공백 정리, 외곽 괄호/구두점 제거, 선행 0
    정규화, 숫자 뒤 '호' 유무 무시.
    금지: fuzzy matching, 색상명 부분 일치, 번호-only 매칭. 이
    함수는 항상 label 전체를 비교 대상으로 남긴다.
    """

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = normalized.strip(_SHADOW_OUTER_STRIP_CHARS)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    match = re.match(r"^0*(\d+)(.*)$", normalized)
    if match:
        normalized = match.group(1) + match.group(2)
    normalized = re.sub(r"(?<=\d)\s*호(?=\s|$)", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


_TRAILING_BRACKET_SUFFIX_PATTERN = re.compile(
    r"^(?P<preceding>.+?)\s+(?P<trailing>\[[^\[\]]*\])$"
)


def split_trailing_bracket_annotations(
    sections: tuple[IngredientSection, ...],
    raw_text: str,
) -> tuple[IngredientSection, ...]:
    """마지막 ingredient 문자열 끝에 붙은 bracket 주석을 분리한다.

    "글리세릴카프릴레이트 [헬시 글로우 밤 스틱 기획(...)]"처럼 콤마
    없이 성분과 bracket 주석이 한 항목으로 병합된 경우, 성분
    이름만 ingredients에 남기고 bracket 텍스트는
    annotation_candidates로 따로 보존한다(원문 위치 포함). 주석
    후보는 ingredient 분석에서 제외되지만 section 자체나 다른
    section의 매핑에는 관여하지 않는다.
    """

    result: list[IngredientSection] = []
    for section in sections:
        if section.subsections or not section.ingredients:
            result.append(section)
            continue

        last_ingredient = section.ingredients[-1]
        match = _TRAILING_BRACKET_SUFFIX_PATTERN.match(last_ingredient)
        if match is None:
            result.append(section)
            continue

        preceding = match.group("preceding").strip()
        trailing = match.group("trailing").strip()
        if not preceding:
            result.append(section)
            continue

        body = raw_text[section.body_start_index:section.body_end_index]
        annotation_start: int | None = None
        for chunk_text, chunk_local_start, _chunk_local_end in reversed(
            _split_comma_chunks_with_offsets(body)
        ):
            cleaned = re.sub(r"\s+", " ", chunk_text).strip(
                " \t\r\n:;-–—"
            )
            if cleaned != last_ingredient:
                continue
            bracket_position = chunk_text.find(trailing)
            if bracket_position == -1:
                break
            annotation_start = (
                section.body_start_index
                + chunk_local_start
                + bracket_position
            )
            break

        if annotation_start is None:
            # 원문에서 정확한 위치를 다시 찾지 못하면(방어적) 분리
            # 하지 않고 원래 section을 그대로 둔다.
            result.append(section)
            continue

        result.append(
            replace(
                section,
                ingredients=tuple(section.ingredients[:-1]) + (preceding,),
                annotation_candidates=(
                    section.annotation_candidates
                    + (
                        AnnotationCandidate(
                            text=trailing,
                            start_index=annotation_start,
                            end_index=annotation_start + len(trailing),
                        ),
                    )
                ),
            )
        )

    return tuple(result)


_COMPONENT_GROUP_LABELS = frozenset({"증정", "본품", "리필"})


def classify_bracket_section_kinds(
    sections: tuple[IngredientSection, ...],
    raw_text: str,
) -> tuple[IngredientSection, ...]:
    """bracket header section을 ingredient_section/component_group/
    ambiguous_annotation_candidate로 분류한다.

    - bracket header 뒤 exact-known 성분이 4개 이상이면
      ingredient_section(기본값)으로 남긴다.
    - [증정]/[본품]/[리필] 뒤 성분이 4개 이상이면 component_group으로
      분류한다(판매 옵션과 매핑하지 않는다).
    - 문서 끝(마지막 section이며 뒤에 성분 body가 전혀 없음)에
      붙은 bracket text는 ambiguous_annotation_candidate로 분리해
      보존한다(ingredient 분석에서 제외하되 삭제하지 않는다).
    - hierarchical 재구성으로 만들어진 상위 section(subsections
      보유)은 이 분류 대상이 아니다.
    - 후보 하나가 다른 section의 분류나 매핑을 막지 않도록, section
      마다 독립적으로 판단한다.
    """

    total = len(sections)
    classified: list[IngredientSection] = []
    for index, section in enumerate(sections):
        if section.subsections:
            classified.append(section)
            continue

        header = section.raw_header.strip()
        if not (header.startswith("[") and header.endswith("]")):
            classified.append(section)
            continue

        label = header[1:-1].strip()
        known_count = sum(
            1
            for ingredient in section.ingredients
            if is_known_ingredient(ingredient)
        )

        if (
            label in _COMPONENT_GROUP_LABELS
            and known_count >= _MIN_KNOWN_INGREDIENTS_PER_FORMULA
        ):
            classified.append(
                replace(section, section_kind="component_group")
            )
            continue

        if known_count >= _MIN_KNOWN_INGREDIENTS_PER_FORMULA:
            classified.append(section)
            continue

        is_last_section = index == total - 1
        at_document_end = (
            is_last_section
            and section.body_end_index >= len(raw_text.rstrip())
        )
        if at_document_end and not section.ingredients:
            classified.append(
                replace(
                    section,
                    section_kind="ambiguous_annotation_candidate",
                )
            )
            continue

        classified.append(section)

    return tuple(classified)


def map_sections_to_canonical_options(
    sections: tuple[IngredientSection, ...],
    document_format: DocumentFormat,
    canonical_options: list[ProductOption],
) -> tuple[tuple[OptionSectionMapping, ...], int]:
    """section 추출이 끝난 뒤에만 canonical option과 대조한다.

    document_format이 option_full_sections가 아니면 모든 옵션을
    unsupported로 남기고 매핑 자체를 시도하지 않는다(임의 promotion
    제거나 부분 매칭으로 ready 취급하지 않기 위함). component_group/
    ambiguous_annotation_candidate로 분류된 section은 ingredient_section이
    아니므로 판매 옵션 매핑 대상에서 제외한다(이 section들 때문에
    다른 section이 orphan/unsupported로 밀리지 않는다).
    """

    if document_format != "option_full_sections":
        mappings = tuple(
            OptionSectionMapping(
                internal_option_key=option.internal_option_key,
                option_name=option.option_name,
                section_index=None,
                mapping_status="unsupported",
                mapping_method=f"shadow_{document_format}",
                mapping_confidence=0.0,
            )
            for option in canonical_options
        )
        return mappings, 0

    option_labels = [
        _shadow_normalize_label(option.raw_option_name)
        for option in canonical_options
    ]

    header_to_options: dict[int, list[int]] = {}
    orphan_count = 0
    for section_index, section in enumerate(sections):
        if section.section_kind != "ingredient_section":
            continue
        normalized_header = _shadow_normalize_label(section.raw_header)
        if not normalized_header:
            continue
        matches = [
            option_index
            for option_index, label in enumerate(option_labels)
            if label == normalized_header
        ]
        header_to_options[section_index] = matches
        if not matches:
            orphan_count += 1

    option_to_sections: dict[int, list[int]] = {}
    for section_index, matches in header_to_options.items():
        for option_index in matches:
            option_to_sections.setdefault(option_index, []).append(
                section_index
            )

    ambiguous_options = {
        option_index
        for option_index, section_indexes in option_to_sections.items()
        if len(section_indexes) > 1
    } | {
        option_index
        for matches in header_to_options.values()
        if len(matches) > 1
        for option_index in matches
    }

    mappings: list[OptionSectionMapping] = []
    for option_index, option in enumerate(canonical_options):
        if option_index in ambiguous_options:
            mappings.append(
                OptionSectionMapping(
                    internal_option_key=option.internal_option_key,
                    option_name=option.option_name,
                    section_index=None,
                    mapping_status="ambiguous",
                    mapping_method="shadow_duplicate_or_colliding_header",
                    mapping_confidence=0.0,
                )
            )
            continue

        section_indexes = option_to_sections.get(option_index, [])
        if len(section_indexes) == 1:
            mappings.append(
                OptionSectionMapping(
                    internal_option_key=option.internal_option_key,
                    option_name=option.option_name,
                    section_index=section_indexes[0],
                    mapping_status="matched",
                    mapping_method="shadow_exact_normalized_label",
                    mapping_confidence=1.0,
                )
            )
        else:
            mappings.append(
                OptionSectionMapping(
                    internal_option_key=option.internal_option_key,
                    option_name=option.option_name,
                    section_index=None,
                    mapping_status="unmatched",
                    mapping_method="shadow_no_matching_header",
                    mapping_confidence=0.0,
                )
            )

    return tuple(mappings), orphan_count


def shadow_parse_option_ingredient_sections(
    raw_text: str,
    options: list[ProductOption],
) -> ShadowParseResult:
    """production parse_option_full_sections와 나란히 실행하는 진단 파서.

    production의 parse_result, ready 판정, 캐시 저장 흐름에는
    전혀 관여하지 않는다. 호출자는 이 함수의 예외를 반드시
    production 흐름과 분리해 처리해야 한다.
    """

    canonical_options = canonicalize_product_options(options)
    boundary_candidates = tuple(extract_boundary_candidates(raw_text))
    raw_sections = build_ingredient_sections(raw_text)
    sections, document_format, structure_reason = (
        classify_shadow_document_structure(raw_sections, raw_text)
    )
    if document_format == "option_full_sections":
        sections = split_trailing_bracket_annotations(sections, raw_text)
        sections = classify_bracket_section_kinds(sections, raw_text)
    mappings, orphan_count = map_sections_to_canonical_options(
        sections,
        document_format,
        canonical_options,
    )

    status_counts = {
        "matched": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "unsupported": 0,
    }
    for mapping in mappings:
        status_counts[mapping.mapping_status] += 1

    return ShadowParseResult(
        sections=sections,
        boundary_candidates=boundary_candidates,
        document_format=document_format,
        structure_reason=structure_reason,
        mappings=mappings,
        orphan_section_count=orphan_count,
        matched_count=status_counts["matched"],
        unmatched_count=status_counts["unmatched"],
        ambiguous_count=status_counts["ambiguous"],
        unsupported_count=status_counts["unsupported"],
    )

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from app.products.ingredient_parsing import (
    split_raw_ingredient_text,
)
from app.products.option_models import (
    NormalizedTextIndex,
    OptionIngredientSection,
    ProductOption,
)


PARSER_VERSION = "option-sections-v1"
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
)
_LEADING_PROMOTION_TEXT_PATTERN = re.compile(
    r"(?i)^\s*(?:기획|단품)(?=\s|[/_\-·])(?:\s|[/_\-·])*"
)


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
    without_shade_suffix = re.sub(
        r"(?<=\d)\s*호",
        "",
        without_promotion,
    )
    return normalize_option_label(without_shade_suffix)


def _canonical_option_display_name(value: str) -> str:
    """첫 원본 옵션에서 프로모션 표기만 걷어낸 안정적인 표시명."""

    without_promotion = _strip_verified_promotion_prefix(value)
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
                grouped[group_key] = option.model_copy(
                    update={
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

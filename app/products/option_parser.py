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

    candidate = normalize_option_label(
        header_source[code_match.start():]
    )
    code = normalize_option_label(code_match.group(0))
    if len(candidate) <= len(code):
        return None
    return candidate


def _code_candidate(
    option_name: str,
) -> str | None:
    header_source = _strip_bracket_blocks(option_name)
    code_match = _OPTION_CODE_PATTERN.search(header_source)
    if code_match is None:
        return None
    code = normalize_option_label(code_match.group(0))
    return code or None


def _find_header_match(
    raw_text: str,
    raw_index: NormalizedTextIndex,
    option: ProductOption,
    option_index: int,
) -> tuple[_HeaderMatch | None, bool]:
    candidates: list[tuple[str, str, float]] = [
        (
            option.normalized_name,
            "normalized_full_name",
            1.0,
        )
    ]

    code_and_label = _code_and_label_candidate(
        option.raw_option_name
    )
    if (
        code_and_label
        and code_and_label != option.normalized_name
    ):
        candidates.append(
            (code_and_label, "code_and_label", 0.9)
        )

    code = _code_candidate(option.raw_option_name)
    if (
        code
        and all(code != candidate for candidate, _, _ in candidates)
    ):
        candidates.append((code, "exact_code", 0.75))

    for needle, method, confidence in candidates:
        occurrences = _all_occurrences(
            raw_index.normalized_text,
            needle,
        )
        if len(occurrences) > 1:
            return None, True
        if len(occurrences) == 0:
            continue

        normalized_start = occurrences[0]
        normalized_end = normalized_start + len(needle)
        original_start = raw_index.original_indexes[
            normalized_start
        ]
        original_end = (
            raw_index.original_indexes[
                normalized_end - 1
            ]
            + 1
        )

        # 대괄호 헤더는 괄호까지, 상품명이 옵션 앞에 붙은
        # 헤더는 해당 줄의 시작까지 헤더 범위로 보존한다.
        line_start = raw_text.rfind(
            "\n",
            0,
            original_start,
        ) + 1
        header_prefix = raw_text[
            line_start:original_start
        ]
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

        return (
            _HeaderMatch(
                option_index=option_index,
                normalized_start=normalized_start,
                normalized_end=normalized_end,
                original_start=original_start,
                original_end=original_end,
                method=method,
                confidence=confidence,
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
    matches: dict[int, _HeaderMatch] = {}
    ambiguous_indexes: set[int] = set()

    for option_index, option in enumerate(options):
        match, ambiguous = _find_header_match(
            raw_text,
            raw_index,
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
                left.normalized_start < right.normalized_end
                and right.normalized_start < left.normalized_end
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
        span = (match.original_start, match.original_end)
        if not distinct_spans or distinct_spans[-1] != span:
            distinct_spans.append(span)

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
            )
        )

    return sections

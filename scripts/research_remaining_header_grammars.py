"""남은 전성분 header 문법을 sanitized fixture로만 검증한다.

Production parser와 무관한 연구용 도구다. fuzzy matching이나 의미 기반
보정 없이 명시적인 영문 alias, full option label, bracket 오류만 탐지한다.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "research_remaining_header_grammars.json"
)
HASH_ENGLISH_PATTERN = re.compile(
    r"(?<![0-9A-Za-z가-힣])#\s*"
    r"(?P<label>[A-Za-z]+(?:[ -][A-Za-z]+)*)"
    r"(?=\s)"
)
MALFORMED_BRACKET_PATTERNS = (
    re.compile(r"\[(?P<label>[^\[\]()\],:\r\n]{1,80})\)"),
    re.compile(r"\((?P<label>[^\[\]()\],:\r\n]{1,80})\]"),
)


def _normalize_alias(value: str) -> str:
    return "".join(
        character.casefold()
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace()
    )


def _normalize_full_label(value: str) -> str:
    return "".join(
        character.casefold()
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace()
    )


def _looks_like_ingredient_body(value: str) -> bool:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return len(parts) >= 2 and any(
        bool(re.search(r"[가-힣A-Za-z]", part)) for part in parts[:3]
    )


def _option_aliases(options: list[str]) -> dict[str, list[str]]:
    aliases: dict[str, list[str]] = {}
    for option in options:
        for raw_alias in re.findall(r"\(([^()]*)\)", option):
            if not re.fullmatch(r"[A-Za-z][A-Za-z -]*", raw_alias.strip()):
                continue
            aliases.setdefault(
                _normalize_alias(raw_alias), []
            ).append(option)
    return aliases


def _hash_candidates(text: str, options: list[str]) -> list[dict[str, Any]]:
    aliases = _option_aliases(options)
    matches = list(HASH_ENGLISH_PATTERN.finditer(text))
    label_counts = Counter(
        _normalize_alias(match.group("label")) for match in matches
    )
    candidates: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        alias = _normalize_alias(match.group("label"))
        exact_options = aliases.get(alias, [])
        body = text[match.end():end].strip()
        unique = len(exact_options) == 1 and label_counts[alias] == 1
        valid_body = _looks_like_ingredient_body(body)
        candidates.append(
            {
                "raw_header": match.group(0),
                "grammar": "hash_english_alias",
                "candidate_span": [match.start(), match.end()],
                "following_body_span": [match.end(), end],
                "following_body_length": len(body),
                "exact_option_candidates": exact_options,
                "duplicate_count": label_counts[alias] - 1,
                "mapping_status": (
                    "matched" if unique and valid_body else "ambiguous"
                    if len(exact_options) > 1 or label_counts[alias] > 1
                    else "unmatched"
                ),
                "reason": (
                    "unique_parenthesized_alias_and_valid_body"
                    if unique and valid_body
                    else "alias_or_header_not_unique"
                    if len(exact_options) > 1 or label_counts[alias] > 1
                    else "no_exact_parenthesized_alias_or_invalid_body"
                ),
            }
        )
    return candidates


def _full_label_candidates(
    text: str,
    options: list[str],
    document_labels: list[str],
) -> list[dict[str, Any]]:
    normalized_options: dict[str, list[str]] = {}
    for option in options:
        normalized_options.setdefault(
            _normalize_full_label(option), []
        ).append(option)

    located: list[tuple[int, int, str]] = []
    cursor = 0
    for label in document_labels:
        match = re.search(re.escape(label), text[cursor:], re.IGNORECASE)
        if match is None:
            continue
        start = cursor + match.start()
        end = cursor + match.end()
        located.append((start, end, label))
        cursor = end

    candidates: list[dict[str, Any]] = []
    counts = Counter(_normalize_full_label(label) for _, _, label in located)
    for index, (start, end, label) in enumerate(located):
        next_start = located[index + 1][0] if index + 1 < len(located) else len(text)
        body = text[end:next_start].strip()
        key = _normalize_full_label(label)
        exact_options = normalized_options.get(key, [])
        unique = len(exact_options) == 1 and counts[key] == 1
        valid_body = _looks_like_ingredient_body(body)
        candidates.append(
            {
                "raw_header": label,
                "grammar": "repeated_unbracketed_full_option_label",
                "candidate_span": [start, end],
                "following_body_span": [end, next_start],
                "following_body_length": len(body),
                "exact_option_candidates": exact_options,
                "duplicate_count": counts[key] - 1,
                "mapping_status": (
                    "matched" if unique and valid_body else "ambiguous"
                    if len(exact_options) > 1 or counts[key] > 1
                    else "orphan"
                ),
                "reason": (
                    "unique_full_label_and_valid_body"
                    if unique and valid_body
                    else "full_label_or_document_header_not_unique"
                    if len(exact_options) > 1 or counts[key] > 1
                    else "no_exact_sale_option_identity"
                ),
            }
        )
    return candidates


def _malformed_candidates(text: str, options: list[str]) -> list[dict[str, Any]]:
    matches = sorted(
        (
            match
            for pattern in MALFORMED_BRACKET_PATTERNS
            for match in pattern.finditer(text)
        ),
        key=lambda match: match.start(),
    )
    candidates: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        label = _normalize_full_label(match.group("label"))
        exact_options = [
            option for option in options
            if _normalize_full_label(option).endswith(label)
        ]
        candidates.append(
            {
                "raw_header": match.group(0),
                "grammar": "single_mismatched_bracket",
                "candidate_span": [match.start(), match.end()],
                "following_body_span": [match.end(), end],
                "following_body_length": len(body),
                "exact_option_candidates": exact_options,
                "duplicate_count": 0,
                "mapping_status": "repair_candidate"
                if len(exact_options) == 1 and _looks_like_ingredient_body(body)
                else "ambiguous",
                "reason": "unique_suffix_identity_and_valid_body"
                if len(exact_options) == 1 and _looks_like_ingredient_body(body)
                else "repair_not_uniquely_supported",
            }
        )
    return candidates


def analyze_case(case: dict[str, Any]) -> dict[str, Any]:
    grammar = case["grammar"]
    text = case["sanitized_text"]
    options = case["canonical_options"]
    if grammar == "hash_english_alias":
        candidates = _hash_candidates(text, options)
    elif grammar == "repeated_unbracketed_full_option_label":
        candidates = _full_label_candidates(
            text,
            options,
            case["document_labels"],
        )
    elif grammar == "single_mismatched_bracket":
        candidates = _malformed_candidates(text, options)
    else:
        raise ValueError(f"unsupported research grammar: {grammar}")
    return {"case_id": case["case_id"], "candidates": candidates}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    results = [analyze_case(case) for case in fixture["cases"]]
    if args.check:
        actual = {
            result["case_id"]: [
                candidate["mapping_status"]
                for candidate in result["candidates"]
            ]
            for result in results
        }
        expected = {
            case["case_id"]: case["expected_mapping_statuses"]
            for case in fixture["cases"]
        }
        if actual != expected:
            raise SystemExit(
                json.dumps(
                    {"expected": expected, "actual": actual},
                    ensure_ascii=False,
                    indent=2,
                )
            )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

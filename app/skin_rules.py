import json
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
from pydantic import ValidationError
from collections import defaultdict
from app.skin_rule_schemas import (
    IngredientSkinRule,
    SkinProfileDefinition,
    SkinRuleDataset,
    SkinRuleSource,
)


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

SKIN_RULES_PATH = (
    DATA_DIR / "dermarag_skin_rules_v0_2.json"
)


@lru_cache(maxsize=1)
def load_skin_rule_dataset() -> SkinRuleDataset:
    """
    피부 타입·성분 규칙 JSON을 읽고
    Pydantic 모델로 검증한다.
    """
    if not SKIN_RULES_PATH.exists():
        raise FileNotFoundError(
            "피부 규칙 데이터 파일을 찾을 수 없습니다: "
            f"{SKIN_RULES_PATH}"
        )

    try:
        with SKIN_RULES_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:
            raw_data = json.load(file)

    except json.JSONDecodeError as exc:
        raise ValueError(
            "피부 규칙 JSON 형식이 올바르지 않습니다: "
            f"{SKIN_RULES_PATH}"
        ) from exc

    try:
        return SkinRuleDataset.model_validate(raw_data)

    except ValidationError as exc:
        raise ValueError(
            "피부 규칙 데이터 스키마 검증에 실패했습니다."
        ) from exc


def get_skin_profiles() -> list[SkinProfileDefinition]:
    return load_skin_rule_dataset().skin_profiles


def get_ingredient_rules() -> list[IngredientSkinRule]:
    return load_skin_rule_dataset().rules


def get_rule_sources() -> dict[str, SkinRuleSource]:
    return load_skin_rule_dataset().sources


def normalize_ingredient_name(
    value: str | None,
) -> str:
    """
    성분명 exact match를 위한 정규화 함수.

    - 유니코드 정규화
    - 소문자 변환
    - 양쪽 공백 제거
    - 괄호 안 CI·보조 표기 제거
    - 공백과 일부 구분 기호 제거
    """
    if not value:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        value,
    )

    text = text.casefold().strip()

    # 예: "황색5호 (CI 15985)"
    # 일단 괄호 앞 이름도 별도로 매칭할 수 있도록 정리한다.
    text = re.sub(
        r"\([^)]*\)",
        "",
        text,
    )

    text = re.sub(
        r"[\s_\-./]+",
        "",
        text,
    )

    return text

def build_ingredient_match_keys(
    value: str | None,
) -> set[str]:
    """
    하나의 성분 표기에서 검색 가능한 키 여러 개를 생성한다.
    """
    if not value:
        return set()

    keys: set[str] = set()

    normalized_full = normalize_ingredient_name(value)

    if normalized_full:
        keys.add(normalized_full)

    ci_matches = re.findall(
        r"\bCI\s*[\d:]+\b",
        value,
        flags=re.IGNORECASE,
    )

    for ci_value in ci_matches:
        ci_key = re.sub(
            r"\s+",
            "",
            ci_value.casefold(),
        )
        keys.add(ci_key)

    name_without_parentheses = re.sub(
        r"\([^)]*\)",
        "",
        value,
    )

    normalized_name = normalize_ingredient_name(
        name_without_parentheses
    )

    if normalized_name:
        keys.add(normalized_name)

    return keys


@lru_cache(maxsize=1)
def build_rule_alias_index(
) -> dict[str, list[IngredientSkinRule]]:
    """
    정규화한 성분 별칭을 키로 사용해
    관련 규칙을 빠르게 찾을 수 있는 인덱스를 만든다.
    """
    index: dict[
        str,
        list[IngredientSkinRule],
    ] = defaultdict(list)

    for rule in get_ingredient_rules():
        candidate_names = {
            rule.display_name_ko,
            *rule.aliases,
        }

        for candidate in candidate_names:
            key = normalize_ingredient_name(candidate)

            if not key:
                continue

            index[key].append(rule)

    return dict(index)

def find_rules_for_ingredient(
    ingredient_name: str,
) -> list[IngredientSkinRule]:
    """
    제품 성분명과 일치하는 피부 타입 규칙을 반환한다.
    """
    alias_index = build_rule_alias_index()
    match_keys = build_ingredient_match_keys(
        ingredient_name
    )

    matched_rules: dict[
        str,
        IngredientSkinRule,
    ] = {}

    for key in match_keys:
        for rule in alias_index.get(key, []):
            matched_rules[rule.rule_id] = rule

    return list(matched_rules.values())
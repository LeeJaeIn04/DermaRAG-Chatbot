"""shadow parser 전용 exact-match 성분 사전.

식약처 원료성분 raw 데이터(data/mfds_ingredients_raw.jsonl)를 읽어
정규화된 이름 집합을 만든다. production parser는 이 모듈을 쓰지
않는다. 여기서 제공하는 것은 오직 "정확히 일치하는가"뿐이며,
유사도·부분 문자열·형태소 기반 매칭은 하지 않는다.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
INGREDIENT_DICTIONARY_PATH = (
    BASE_DIR / "data" / "mfds_ingredients_raw.jsonl"
)

_CI_SUFFIX_PATTERN = re.compile(
    r"\s*\(\s*ci\s*\d+\s*\)\s*$",
    re.IGNORECASE,
)


def _normalize_dictionary_entry(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", "", normalized).strip()


@lru_cache(maxsize=1)
def _load_known_ingredient_names() -> frozenset[str]:
    if not INGREDIENT_DICTIONARY_PATH.exists():
        return frozenset()

    names: set[str] = set()
    with INGREDIENT_DICTIONARY_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            kor_name = record.get("ingredient_kor_name") or ""
            if kor_name:
                names.add(_normalize_dictionary_entry(kor_name))
            synonym = record.get("synonym") or ""
            for entry in synonym.split(","):
                entry = entry.strip()
                if entry:
                    names.add(_normalize_dictionary_entry(entry))
    return frozenset(names)


def is_known_ingredient(value: str) -> bool:
    """정규화 후 사전에 정확히 일치할 때만 True.

    "마이카(CI 77019)"처럼 끝에 색소 CI 표기가 붙은 형태는 CI
    표기를 뗀 기본 성분명으로도 조회한다(exact match 정책은
    유지하고, 관용적인 CI 접미사만 별도로 처리한다). 그 외에는
    fuzzy/부분 매칭을 절대 하지 않는다.
    """

    stripped = value.strip()
    if not stripped:
        return False

    known_names = _load_known_ingredient_names()
    if _normalize_dictionary_entry(stripped) in known_names:
        return True

    without_ci = _CI_SUFFIX_PATTERN.sub("", stripped)
    if without_ci != stripped and without_ci.strip():
        return _normalize_dictionary_entry(without_ci) in known_names

    return False

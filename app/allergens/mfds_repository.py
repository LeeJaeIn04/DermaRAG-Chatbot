from __future__ import annotations
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from app.allergens.schemas import (
    FragranceAllergen,
    FragranceAllergenMatch,
)


BASE_DIR = Path(__file__).resolve().parents[2]

ALLERGEN_DATA_PATH = (
    BASE_DIR
    / "data"
    / "allergens"
    / "mfds"
    / "processed"
    / "mfds_fragrance_allergens.jsonl"
)


def clean_text(value: Any) -> str:
    """
    None, 줄바꿈, 연속 공백을 정리한다.
    """
    if value is None:
        return ""

    return " ".join(
        str(value)
        .replace("\r", " ")
        .replace("\n", " ")
        .split()
    )


def normalize_ingredient_name(
    value: Any,
) -> str:
    """
    성분명 exact match를 위한 정규화 함수.

    수행 작업:
    - 앞뒤 및 연속 공백 제거
    - 영문 소문자화
    - 일반 공백 제거
    - 하이픈 형태 통일
    - 일부 문장부호 제거

    알레르겐 매칭은 법적 표시 대상 판정과 연결되므로
    유사도 검색을 사용하지 않는다.
    """
    text = clean_text(value).lower()

    text = re.sub(
        r"\s+",
        "",
        text,
    )

    text = text.replace("‐", "-")
    text = text.replace("–", "-")
    text = text.replace("—", "-")

    text = re.sub(
        r"[·ㆍ,./]",
        "",
        text,
    )

    return text


def normalize_cas_no(
    value: Any,
) -> str:
    """
    CAS 번호의 공백을 제거한다.
    """
    return clean_text(value).replace(
        " ",
        "",
    )


class MFDSFragranceAllergenRepository:
    """
    식약처 향료 알레르기 유발성분 JSONL을
    메모리에 적재하고 exact match로 검색한다.
    """

    def __init__(
        self,
        data_path: Path = ALLERGEN_DATA_PATH,
    ) -> None:
        self.data_path = data_path

        self.records = self._load_records()

        self._ingredient_name_index: dict[
            str,
            list[FragranceAllergen],
        ] = {}

        self._english_name_index: dict[
            str,
            list[FragranceAllergen],
        ] = {}

        self._inci_name_index: dict[
            str,
            list[FragranceAllergen],
        ] = {}

        self._alias_index: dict[
            str,
            list[FragranceAllergen],
        ] = {}

        self._cas_index: dict[
            str,
            list[FragranceAllergen],
        ] = {}

        self._build_indexes()

    def _load_records(
        self,
    ) -> list[FragranceAllergen]:
        """
        JSONL 파일을 읽고 Pydantic 모델로 검증한다.
        """
        if not self.data_path.exists():
            raise FileNotFoundError(
                "식약처 향료 알레르겐 JSONL 파일을 "
                f"찾을 수 없습니다: {self.data_path}"
            )

        records: list[
            FragranceAllergen
        ] = []

        with self.data_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            for line_number, line in enumerate(
                file,
                start=1,
            ):
                line = line.strip()

                if not line:
                    continue

                try:
                    raw_record = json.loads(
                        line
                    )

                    record = (
                        FragranceAllergen
                        .model_validate(
                            raw_record
                        )
                    )

                except (
                    json.JSONDecodeError,
                    ValueError,
                ) as error:
                    raise ValueError(
                        "식약처 향료 알레르겐 데이터 "
                        "처리 실패: "
                        f"{self.data_path.name} "
                        f"{line_number}번째 줄"
                    ) from error

                records.append(record)

        return records

    @staticmethod
    def _append_index(
        index: dict[
            str,
            list[FragranceAllergen],
        ],
        key: str,
        allergen: FragranceAllergen,
    ) -> None:
        """
        하나의 인덱스 키에 알레르겐 레코드를 추가한다.
        """
        if not key:
            return

        index.setdefault(
            key,
            [],
        ).append(allergen)

    def _build_indexes(self) -> None:
        """
        한글명, 영문명, INCI명, 별칭, CAS 인덱스를 만든다.
        """
        for allergen in self.records:
            ingredient_key = (
                normalize_ingredient_name(
                    allergen
                    .ingredient_kor_name
                )
            )

            self._append_index(
                self._ingredient_name_index,
                ingredient_key,
                allergen,
            )

            english_key = (
                normalize_ingredient_name(
                    allergen
                    .ingredient_eng_name
                )
            )

            self._append_index(
                self._english_name_index,
                english_key,
                allergen,
            )

            inci_key = (
                normalize_ingredient_name(
                    allergen.inci_name
                )
            )

            self._append_index(
                self._inci_name_index,
                inci_key,
                allergen,
            )

            for alias in allergen.aliases:
                alias_key = (
                    normalize_ingredient_name(
                        alias
                    )
                )

                self._append_index(
                    self._alias_index,
                    alias_key,
                    allergen,
                )

            for cas_no in (
                allergen.cas_numbers
            ):
                cas_key = normalize_cas_no(
                    cas_no
                )

                self._append_index(
                    self._cas_index,
                    cas_key,
                    allergen,
                )

    def find_by_name(
        self,
        ingredient_name: str,
    ) -> list[FragranceAllergenMatch]:
        """
        한글명, 영문명, INCI명, 별칭을 exact match한다.
        """
        query_key = (
            normalize_ingredient_name(
                ingredient_name
            )
        )

        if not query_key:
            return []

        matches: list[
            FragranceAllergenMatch
        ] = []

        seen: set[
            tuple[str, int]
        ] = set()

        indexes = [
            (
                "ingredient_kor_name",
                self._ingredient_name_index,
            ),
            (
                "ingredient_eng_name",
                self._english_name_index,
            ),
            (
                "inci_name",
                self._inci_name_index,
            ),
            (
                "alias",
                self._alias_index,
            ),
        ]

        for match_type, index in indexes:
            allergens = index.get(
                query_key,
                [],
            )

            for allergen in allergens:
                unique_key = (
                    allergen
                    .ingredient_kor_name,
                    allergen.source_row,
                )

                if unique_key in seen:
                    continue

                seen.add(unique_key)

                if (
                    match_type
                    == "ingredient_kor_name"
                ):
                    matched_name = (
                        allergen
                        .ingredient_kor_name
                    )
                elif (
                    match_type
                    == "ingredient_eng_name"
                ):
                    matched_name = (
                        allergen
                        .ingredient_eng_name
                        or ""
                    )
                elif (
                    match_type
                    == "inci_name"
                ):
                    matched_name = (
                        allergen.inci_name
                        or ""
                    )
                else:
                    matched_name = (
                        ingredient_name
                    )

                matches.append(
                    FragranceAllergenMatch(
                        query_ingredient=(
                            ingredient_name
                        ),
                        matched_name=(
                            matched_name
                        ),
                        match_type=match_type,
                        allergen=allergen,
                    )
                )

        return matches

    def find_by_cas_no(
        self,
        cas_no: str,
    ) -> list[FragranceAllergenMatch]:
        """
        CAS 번호로 exact match한다.
        """
        query_key = normalize_cas_no(
            cas_no
        )

        if not query_key:
            return []

        allergens = self._cas_index.get(
            query_key,
            [],
        )

        return [
            FragranceAllergenMatch(
                query_ingredient=cas_no,
                matched_name=query_key,
                match_type="cas_no",
                allergen=allergen,
            )
            for allergen in allergens
        ]

    def find_for_ingredients(
        self,
        ingredient_names: list[str],
    ) -> list[FragranceAllergenMatch]:
        """
        제품 전성분 전체를 알레르겐 데이터와 비교한다.
        """
        matches: list[
            FragranceAllergenMatch
        ] = []

        seen: set[
            tuple[str, str, int]
        ] = set()

        for ingredient_name in ingredient_names:
            ingredient_matches = (
                self.find_by_name(
                    ingredient_name
                )
            )

            for match in (
                ingredient_matches
            ):
                allergen = match.allergen

                unique_key = (
                    normalize_ingredient_name(
                        ingredient_name
                    ),
                    allergen
                    .ingredient_kor_name,
                    allergen.source_row,
                )

                if unique_key in seen:
                    continue

                seen.add(unique_key)
                matches.append(match)

        return matches


@lru_cache(maxsize=1)
def get_mfds_fragrance_allergen_repository(
) -> MFDSFragranceAllergenRepository:
    """
    앱 실행 중 Repository를 한 번만 생성한다.
    """
    return MFDSFragranceAllergenRepository()
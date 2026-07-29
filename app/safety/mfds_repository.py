from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.safety.schemas import (
    IngredientRegulation,
    IngredientRegulationMatch,
)


BASE_DIR = Path(__file__).resolve().parents[2]

REGULATION_DATA_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "processed"
    / "mfds_cosmetic_regulations.jsonl"
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
    - 하이픈 주변 차이 제거
    - 일부 문장부호 제거

    주의:
    규제 판정이므로 유사도 검색은 하지 않는다.
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

    원본에 여러 CAS 번호가 들어 있는 경우에는
    별도로 분리해서 인덱스에 등록한다.
    """
    return clean_text(value).replace(" ", "")


def split_cas_numbers(
    value: Any,
) -> list[str]:
    """
    다음 형태의 여러 CAS 번호를 분리한다.

    예:
    16807-48-0 / 520-45-6
    → ["16807-48-0", "520-45-6"]

    10117-38-1 23873-77-0
    → ["10117-38-1", "23873-77-0"]
    """
    text = clean_text(value)

    if not text or text == "-":
        return []

    return re.findall(
        r"\b\d{2,7}-\d{2}-\d\b",
        text,
    )


class MFDSRegulationRepository:
    """
    식약처 규제 JSONL을 메모리에 적재하고
    exact match로 검색한다.
    """

    def __init__(
        self,
        data_path: Path = REGULATION_DATA_PATH,
    ) -> None:
        self.data_path = data_path

        self.records = self._load_records()

        self._ingredient_name_index: dict[
            str,
            list[IngredientRegulation],
        ] = {}

        self._chemical_name_index: dict[
            str,
            list[IngredientRegulation],
        ] = {}

        self._cas_index: dict[
            str,
            list[IngredientRegulation],
        ] = {}

        self._build_indexes()

    def _load_records(
        self,
    ) -> list[IngredientRegulation]:
        """
        JSONL 파일을 읽고 Pydantic 모델로 검증한다.
        """
        if not self.data_path.exists():
            raise FileNotFoundError(
                "식약처 규제 JSONL 파일을 "
                f"찾을 수 없습니다: {self.data_path}"
            )

        records: list[IngredientRegulation] = []

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
                    raw_record = json.loads(line)

                    record = (
                        IngredientRegulation
                        .model_validate(raw_record)
                    )

                except (
                    json.JSONDecodeError,
                    ValueError,
                ) as error:
                    raise ValueError(
                        "식약처 규제 데이터 처리 실패: "
                        f"{self.data_path.name} "
                        f"{line_number}번째 줄"
                    ) from error

                records.append(record)

        return records

    @staticmethod
    def _append_index(
        index: dict[
            str,
            list[IngredientRegulation],
        ],
        key: str,
        regulation: IngredientRegulation,
    ) -> None:
        """
        하나의 인덱스 키에 규제 레코드를 추가한다.

        같은 이름이 여러 규제 레코드와 연결될 수 있으므로
        값은 단일 객체가 아니라 리스트로 저장한다.
        """
        if not key:
            return

        index.setdefault(
            key,
            [],
        ).append(regulation)

    def _build_indexes(self) -> None:
        """
        성분명, 화학물질명, CAS 번호 인덱스를 만든다.
        """
        for regulation in self.records:
            ingredient_key = (
                normalize_ingredient_name(
                    regulation.ingredient_kor_name
                )
            )

            self._append_index(
                self._ingredient_name_index,
                ingredient_key,
                regulation,
            )

            chemical_key = (
                normalize_ingredient_name(
                    regulation.chemical_name
                )
            )

            self._append_index(
                self._chemical_name_index,
                chemical_key,
                regulation,
            )

            for cas_no in split_cas_numbers(
                regulation.cas_no
            ):
                cas_key = normalize_cas_no(
                    cas_no
                )

                self._append_index(
                    self._cas_index,
                    cas_key,
                    regulation,
                )

    def find_by_name(
        self,
        ingredient_name: str,
    ) -> list[IngredientRegulationMatch]:
        """
        한글 원료명과 화학물질명을 exact match한다.
        """
        query_key = normalize_ingredient_name(
            ingredient_name
        )

        if not query_key:
            return []

        matches: list[
            IngredientRegulationMatch
        ] = []

        seen: set[
            tuple[str, str, str, int]
        ] = set()

        for match_type, index in [
            (
                "ingredient_kor_name",
                self._ingredient_name_index,
            ),
            (
                "chemical_name",
                self._chemical_name_index,
            ),
        ]:
            regulations = index.get(
                query_key,
                [],
            )

            for regulation in regulations:
                unique_key = (
                    regulation.regulation_type,
                    regulation.category,
                    regulation.cas_no,
                    regulation.source_row,
                )

                if unique_key in seen:
                    continue

                seen.add(unique_key)

                if (
                    match_type
                    == "ingredient_kor_name"
                ):
                    matched_name = (
                        regulation
                        .ingredient_kor_name
                    )
                else:
                    matched_name = (
                        regulation.chemical_name
                        or ""
                    )

                matches.append(
                    IngredientRegulationMatch(
                        query_ingredient=(
                            ingredient_name
                        ),
                        matched_name=matched_name,
                        match_type=match_type,
                        regulation=regulation,
                    )
                )

        return matches

    def find_by_cas_no(
        self,
        cas_no: str,
    ) -> list[IngredientRegulationMatch]:
        """
        CAS 번호로 exact match한다.
        """
        query_key = normalize_cas_no(
            cas_no
        )

        if not query_key:
            return []

        regulations = self._cas_index.get(
            query_key,
            [],
        )

        return [
            IngredientRegulationMatch(
                query_ingredient=cas_no,
                matched_name=query_key,
                match_type="cas_no",
                regulation=regulation,
            )
            for regulation in regulations
        ]

    def find_for_ingredients(
        self,
        ingredient_names: list[str],
    ) -> list[IngredientRegulationMatch]:
        """
        제품 전성분 전체를 규제 데이터와 비교한다.
        """
        matches: list[
            IngredientRegulationMatch
        ] = []

        seen: set[
            tuple[str, str, str, str, int]
        ] = set()

        for ingredient_name in ingredient_names:
            ingredient_matches = (
                self.find_by_name(
                    ingredient_name
                )
            )

            for match in ingredient_matches:
                regulation = match.regulation

                unique_key = (
                    normalize_ingredient_name(
                        ingredient_name
                    ),
                    regulation.regulation_type,
                    regulation.category,
                    regulation.cas_no,
                    regulation.source_row,
                )

                if unique_key in seen:
                    continue

                seen.add(unique_key)
                matches.append(match)

        return matches


@lru_cache(maxsize=1)
def get_mfds_regulation_repository(
) -> MFDSRegulationRepository:
    """
    앱 실행 중 Repository를 한 번만 생성한다.
    """
    return MFDSRegulationRepository()
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


RegulationType = Literal[
    "prohibited",
    "restricted",
]


RegulationCategory = Literal[
    "prohibited",
    "preservative",
    "uv_filter",
    "hair_dye",
    "restricted_other",
]


class IngredientRegulation(BaseModel):
    """
    식약처 화장품 규제 원료 한 건을 나타낸다.
    """

    ingredient_kor_name: str
    ingredient_eng_name: str | None = None
    cas_no: str = ""
    chemical_name: str | None = None

    regulation_type: RegulationType
    category: RegulationCategory

    max_concentration: str | None = None
    product_scope: str | None = None
    use_conditions: str | None = None
    warning_text: str | None = None

    source_authority: str
    source_document: str

    notice_number: str
    notice_label: str
    notice_date: str

    source_section: str
    source_table: int | None = None
    source_row: int


class IngredientRegulationMatch(BaseModel):
    """
    사용자 또는 제품 성분명과 규제 데이터가
    어떻게 일치했는지를 함께 반환한다.
    """

    query_ingredient: str
    matched_name: str
    match_type: Literal[
        "ingredient_kor_name",
        "chemical_name",
        "cas_no",
    ]

    regulation: IngredientRegulation
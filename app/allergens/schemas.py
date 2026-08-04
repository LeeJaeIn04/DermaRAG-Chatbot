from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class FragranceAllergen(BaseModel):
    """
    식약처 향료 알레르기 유발성분 표시 대상 레코드.
    """

    ingredient_kor_name: str
    ingredient_eng_name: str | None = None
    inci_name: str | None = None
    cas_numbers: list[str] = Field(
        default_factory=list
    )
    aliases: list[str] = Field(
        default_factory=list
    )

    allergen_type: str
    legal_status: str
    jurisdiction: str
    evidence_scope: str

    reaction_types: list[str] = Field(
        default_factory=list
    )
    sensitization_note: str | None = None
    oxidation_note: str | None = None

    rinse_off_threshold: str | None = None
    leave_on_threshold: str | None = None

    source_id: str
    source_authority: str
    source_document: str
    source_document_version: str | None = None
    source_document_date: str | None = None
    source_section: str | None = None
    source_page: int | None = None
    source_row: int


class FragranceAllergenMatch(BaseModel):
    """
    제품 전성분과 알레르겐 레코드의 exact match 결과.
    """

    query_ingredient: str
    matched_name: str
    match_type: Literal[
        "ingredient_kor_name",
        "ingredient_eng_name",
        "inci_name",
        "alias",
        "cas_no",
    ]
    allergen: FragranceAllergen
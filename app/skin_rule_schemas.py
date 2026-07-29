from typing import Literal

from pydantic import BaseModel, Field


class SkinRuleSource(BaseModel):
    """
    규칙을 만든 근거 자료.
    """

    title: str
    url: str
    type: str


class SkinProfileDefinition(BaseModel):
    """
    건성, 지성, 수부지 등 피부 프로필의 특징.
    """

    profile_id: str
    display_name_ko: str

    core_features: list[str] = Field(
        default_factory=list
    )

    priority_concerns: list[str] = Field(
        default_factory=list
    )

    helpful_function_groups: list[str] = Field(
        default_factory=list
    )

    caution_function_groups: list[str] = Field(
        default_factory=list
    )

    notes: str = ""
    source_ids: list[str] = Field(
        default_factory=list
    )


class IngredientSkinRule(BaseModel):
    """
    성분 또는 성분군이 특정 피부 상태에서
    어떤 주의·도움 요소가 될 수 있는지 정의한다.
    """

    rule_id: str
    canonical_group: str
    display_name_ko: str

    aliases: list[str] = Field(
        default_factory=list
    )

    functions: list[str] = Field(
        default_factory=list
    )

    beneficial_for: list[str] = Field(
        default_factory=list
    )

    caution_for: list[str] = Field(
        default_factory=list
    )

    possible_concerns: list[str] = Field(
        default_factory=list
    )

    condition: str = ""
    evidence_level: str
    severity_default: str
    user_message_ko: str

    source_ids: list[str] = Field(
        default_factory=list
    )


class SkinRuleDataset(BaseModel):
    """
    dermarag_skin_rules_v0_1.json 전체 구조.
    """

    dataset_name: str
    version: str
    created_at: str
    scope: str

    important_limitations: list[str] = Field(
        default_factory=list
    )

    sources: dict[str, SkinRuleSource]

    skin_profiles: list[SkinProfileDefinition]

    rules: list[IngredientSkinRule]


class SkinCompatibilityNotice(BaseModel):
    ingredient_name: str
    rule_id: str
    category: str

    level: Literal[
        "high",
        "caution",
        "reference",
        "beneficial",
    ]

    matched_profiles: list[str] = Field(
        default_factory=list
    )

    possible_concerns: list[str] = Field(
        default_factory=list
    )

    reason: str
    condition: str
    evidence_level: str

    source_titles: list[str] = Field(
        default_factory=list
    )

    source_urls: list[str] = Field(
        default_factory=list
    )
"""production/shadow parser 결과를 동일한 형식으로 표현하고, 둘 중
안전한 결과를 선택하는 순수 상태 모델(Step 1).

이 모듈은 어떤 parser도 직접 호출하지 않고, 어떤 값도 캐시/DB/API에
쓰지 않는다. production/shadow 각각이 만든 원시 매핑 상태
(OptionMappingStatus: matched/unmatched/ambiguous/unsupported)와
ingredient 목록을 건네받아 공통 상태 모델로만 변환하고, 두 결과를
비교해 어느 쪽을 신뢰할지만 판단한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

# Literal 유지: 이 상태값은 DB/API에 저장되는 공식 계약이 아니라
# parser_state 모듈 내부에서만 오가는 판정 결과이므로, 코드베이스
# 전반(option_models.py/option_parser.py)이 이미 쓰는 Literal 관례를
# 따르는 편이 str Enum 도입보다 일관적이다. DB/API 공식 상태값으로
# 승격되는 시점에 다시 검토한다.
OptionParseStatus = Literal["ready", "unmapped", "empty", "ambiguous", "error"]

CollectionStatus = Literal["ready", "partial", "failed"]

ParserSource = Literal["production", "shadow"]

# 상태 판단 우선순위: ERROR > AMBIGUOUS > UNMAPPED > EMPTY > READY.
# build_option_level_result가 이 순서로 상태를 판정하며, 다른 곳에서도
# 같은 우선순위가 필요할 때 재사용할 수 있도록 공개해 둔다.
OPTION_PARSE_STATUS_PRIORITY: tuple[OptionParseStatus, ...] = (
    "error",
    "ambiguous",
    "unmapped",
    "empty",
    "ready",
)

_UNMAPPED_RAW_STATUSES = {"unmatched", "unsupported"}


@dataclass(frozen=True)
class OptionLevelResult:
    """옵션 하나에 대한 production/shadow parser 결과를 공통 형식으로
    나타낸다. ingredients는 순서를 포함해 그대로 보존한다(성분 비교는
    항상 순서를 포함한 list 비교로만 한다).

    계약: option_id는 같은 실제 옵션이면 production과 shadow에서
    항상 동일하고 결정적(deterministic)이어야 한다. 호출부(빌더를
    쓰는 쪽)가 이 계약을 지키지 않으면(예: 호출마다 다른 값, 또는
    production/shadow가 서로 다른 필드를 넘김) select_safe_parser_result가
    실제로는 같은 옵션을 다른 옵션으로 오인해 잘못된 production_option_
    missing_in_shadow 판정을 내릴 수 있다."""

    option_id: str
    option_name: str
    status: OptionParseStatus
    ingredients: tuple[str, ...]
    raw_mapping_status: str


@dataclass(frozen=True)
class ParserResult:
    """하나의 parser(production 또는 shadow)가 만든 전체 옵션 결과."""

    source: ParserSource
    collection_status: CollectionStatus
    options: tuple[OptionLevelResult, ...]


@dataclass(frozen=True)
class ParserSelectionResult:
    """production/shadow 중 어느 결과를 신뢰할지에 대한 판단."""

    selected: ParserSource
    reason: str
    production: ParserResult
    shadow: ParserResult | None


def build_option_level_result(
    *,
    option_id: str,
    option_name: str,
    mapping_status: str,
    ingredients: Sequence[str] = (),
    has_error: bool = False,
) -> OptionLevelResult:
    """production/shadow의 원시 mapping_status(matched/unmatched/
    ambiguous/unsupported)와 ingredient 목록을 공통 OptionParseStatus로
    변환한다. 우선순위는 OPTION_PARSE_STATUS_PRIORITY와 같다:
    ERROR > AMBIGUOUS > UNMAPPED > EMPTY > READY.

    unmatched/unsupported는 모두 '판매 옵션에 안전하게 대응시킬 수
    없음'을 의미하므로 unmapped로 합친다(shadow의 hierarchical/
    component_group 결과도 unsupported로 들어오므로 동일하게 다룬다).
    """

    ingredients_tuple = tuple(ingredients)

    status: OptionParseStatus
    if has_error or mapping_status == "error":
        status = "error"
    elif mapping_status == "ambiguous":
        status = "ambiguous"
    elif mapping_status in _UNMAPPED_RAW_STATUSES:
        status = "unmapped"
    elif mapping_status == "matched" and not ingredients_tuple:
        status = "empty"
    elif mapping_status == "matched":
        status = "ready"
    else:
        # 알 수 없는 mapping_status는 안전하지 않다고 간주한다.
        status = "error"

    return OptionLevelResult(
        option_id=option_id,
        option_name=option_name,
        status=status,
        ingredients=ingredients_tuple,
        raw_mapping_status=mapping_status,
    )


def derive_collection_status(
    options: Sequence[OptionLevelResult],
) -> CollectionStatus:
    """모든 옵션이 ready면 ready, 일부만 ready면 partial, ready가
    하나도 없거나 옵션 목록이 비어 있으면 failed."""

    if not options:
        return "failed"

    ready_count = sum(1 for option in options if option.status == "ready")
    if ready_count == len(options):
        return "ready"
    if ready_count == 0:
        return "failed"
    return "partial"


def build_parser_result(
    source: ParserSource,
    options: Sequence[OptionLevelResult],
) -> ParserResult:
    options_tuple = tuple(options)
    return ParserResult(
        source=source,
        collection_status=derive_collection_status(options_tuple),
        options=options_tuple,
    )


def _has_duplicate_option_ids(options: Sequence[OptionLevelResult]) -> bool:
    option_ids = [option.option_id for option in options]
    return len(option_ids) != len(set(option_ids))


def select_safe_parser_result(
    production: ParserResult,
    shadow: ParserResult | None,
) -> ParserSelectionResult:
    """production을 기본값으로 두고, shadow가 순수하게 더 나은
    경우에만 shadow를 선택한다.

    순서대로 확인한다:
    1. shadow가 없으면 production.
    2. production 또는 shadow 옵션 목록에 option_id 중복이 있으면
       production(어느 쪽을 신뢰할지 판단할 수 없음).
    3. production 옵션이 shadow 결과에서 사라졌으면 production.
    4. production에서 ready였던 옵션이 shadow에서 ready가 아니면
       production(회귀 금지).
    5. production ready 옵션의 ingredient 목록이 shadow에서 순서
       포함해 달라지면 production(set 비교 금지).
    6. 위 회귀가 전혀 없고 shadow의 ready 옵션 수가 production보다
       많을 때만 shadow.
    7. 그 외(회귀는 없지만 개선도 없음)에는 production.
    """

    if shadow is None:
        return ParserSelectionResult(
            selected="production",
            reason="shadow_result_unavailable",
            production=production,
            shadow=shadow,
        )

    if _has_duplicate_option_ids(
        production.options
    ) or _has_duplicate_option_ids(shadow.options):
        return ParserSelectionResult(
            selected="production",
            reason="duplicate_option_id_detected",
            production=production,
            shadow=shadow,
        )

    shadow_by_id = {option.option_id: option for option in shadow.options}

    for production_option in production.options:
        shadow_option = shadow_by_id.get(production_option.option_id)
        if shadow_option is None:
            return ParserSelectionResult(
                selected="production",
                reason="production_option_missing_in_shadow",
                production=production,
                shadow=shadow,
            )

        if production_option.status != "ready":
            continue

        if shadow_option.status != "ready":
            return ParserSelectionResult(
                selected="production",
                reason="production_ready_option_not_ready_in_shadow",
                production=production,
                shadow=shadow,
            )

        if list(production_option.ingredients) != list(
            shadow_option.ingredients
        ):
            return ParserSelectionResult(
                selected="production",
                reason=(
                    "production_ready_option_ingredients_changed_in_shadow"
                ),
                production=production,
                shadow=shadow,
            )

    production_ready_count = sum(
        1 for option in production.options if option.status == "ready"
    )
    shadow_ready_count = sum(
        1 for option in shadow.options if option.status == "ready"
    )
    if shadow_ready_count > production_ready_count:
        return ParserSelectionResult(
            selected="shadow",
            reason="shadow_increases_ready_option_count_without_regression",
            production=production,
            shadow=shadow,
        )

    return ParserSelectionResult(
        selected="production",
        reason="no_safe_improvement_detected",
        production=production,
        shadow=shadow,
    )

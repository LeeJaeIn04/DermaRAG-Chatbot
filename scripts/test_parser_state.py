from app.products.parser_state import (
    OPTION_PARSE_STATUS_PRIORITY,
    OptionLevelResult,
    build_option_level_result,
    build_parser_result,
    derive_collection_status,
    select_safe_parser_result,
)


# ---------------------------------------------------------------------------
# build_option_level_result: 상태 판단 우선순위
# ERROR > AMBIGUOUS > UNMAPPED > EMPTY > READY
# ---------------------------------------------------------------------------


def test_status_priority_constant_matches_documented_order() -> None:
    assert OPTION_PARSE_STATUS_PRIORITY == (
        "error",
        "ambiguous",
        "unmapped",
        "empty",
        "ready",
    )


def test_build_option_level_result_error_from_has_error_flag() -> None:
    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="matched",
        ingredients=["정제수"],
        has_error=True,
    )
    assert result.status == "error"


def test_build_option_level_result_error_from_error_mapping_status() -> None:
    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="error",
        ingredients=[],
    )
    assert result.status == "error"


def test_build_option_level_result_ambiguous() -> None:
    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="ambiguous",
        ingredients=["정제수"],
    )
    assert result.status == "ambiguous"


def test_build_option_level_result_unmatched_is_unmapped() -> None:
    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="unmatched",
        ingredients=[],
    )
    assert result.status == "unmapped"


def test_build_option_level_result_unsupported_is_unmapped() -> None:
    """shadow의 hierarchical/component_group 결과(unsupported)도
    production의 unmatched와 동일하게 unmapped로 합쳐진다."""

    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="unsupported",
        ingredients=[],
    )
    assert result.status == "unmapped"


def test_build_option_level_result_matched_without_ingredients_is_empty() -> (
    None
):
    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="matched",
        ingredients=[],
    )
    assert result.status == "empty"


def test_build_option_level_result_matched_with_ingredients_is_ready() -> (
    None
):
    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="matched",
        ingredients=["정제수", "글리세린"],
    )
    assert result.status == "ready"
    assert result.ingredients == ("정제수", "글리세린")


def test_build_option_level_result_preserves_raw_mapping_status() -> None:
    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="unsupported",
        ingredients=[],
    )
    assert result.raw_mapping_status == "unsupported"


def test_build_option_level_result_unknown_mapping_status_is_error() -> None:
    result = build_option_level_result(
        option_id="opt-1",
        option_name="19호",
        mapping_status="something_unexpected",
        ingredients=["정제수"],
    )
    assert result.status == "error"


def _ready(option_id: str, ingredients: list[str]) -> OptionLevelResult:
    return build_option_level_result(
        option_id=option_id,
        option_name=option_id,
        mapping_status="matched",
        ingredients=ingredients,
    )


def _unmapped(option_id: str) -> OptionLevelResult:
    return build_option_level_result(
        option_id=option_id,
        option_name=option_id,
        mapping_status="unmatched",
        ingredients=[],
    )


def _ambiguous(option_id: str) -> OptionLevelResult:
    return build_option_level_result(
        option_id=option_id,
        option_name=option_id,
        mapping_status="ambiguous",
        ingredients=[],
    )


# ---------------------------------------------------------------------------
# derive_collection_status
# ---------------------------------------------------------------------------


def test_derive_collection_status_all_ready() -> None:
    options = [_ready("a", ["정제수"]), _ready("b", ["글리세린"])]
    assert derive_collection_status(options) == "ready"


def test_derive_collection_status_partial() -> None:
    options = [_ready("a", ["정제수"]), _unmapped("b")]
    assert derive_collection_status(options) == "partial"


def test_derive_collection_status_failed_when_no_ready() -> None:
    options = [_unmapped("a"), _ambiguous("b")]
    assert derive_collection_status(options) == "failed"


def test_derive_collection_status_failed_when_empty() -> None:
    assert derive_collection_status([]) == "failed"


def test_build_parser_result_wraps_options_and_derives_status() -> None:
    options = [_ready("a", ["정제수"]), _unmapped("b")]
    result = build_parser_result("production", options)
    assert result.source == "production"
    assert result.collection_status == "partial"
    assert result.options == tuple(options)


# ---------------------------------------------------------------------------
# select_safe_parser_result
# ---------------------------------------------------------------------------


def test_selector_picks_production_when_shadow_missing() -> None:
    production = build_parser_result("production", [_ready("a", ["정제수"])])
    result = select_safe_parser_result(production, None)
    assert result.selected == "production"
    assert result.reason == "shadow_result_unavailable"


def test_selector_picks_production_on_duplicate_option_id_in_production() -> (
    None
):
    production = build_parser_result(
        "production",
        [_ready("a", ["정제수"]), _ready("a", ["글리세린"])],
    )
    shadow = build_parser_result("shadow", [_ready("a", ["정제수"])])
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "production"
    assert result.reason == "duplicate_option_id_detected"


def test_selector_picks_production_on_duplicate_option_id_in_shadow() -> (
    None
):
    production = build_parser_result("production", [_ready("a", ["정제수"])])
    shadow = build_parser_result(
        "shadow",
        [_ready("a", ["정제수"]), _ready("a", ["정제수"])],
    )
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "production"
    assert result.reason == "duplicate_option_id_detected"


def test_selector_picks_production_when_option_missing_in_shadow() -> None:
    production = build_parser_result(
        "production", [_ready("a", ["정제수"]), _ready("b", ["글리세린"])]
    )
    shadow = build_parser_result("shadow", [_ready("a", ["정제수"])])
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "production"
    assert result.reason == "production_option_missing_in_shadow"


def test_selector_picks_production_when_ready_option_becomes_not_ready() -> (
    None
):
    production = build_parser_result("production", [_ready("a", ["정제수"])])
    shadow = build_parser_result("shadow", [_unmapped("a")])
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "production"
    assert result.reason == "production_ready_option_not_ready_in_shadow"


def test_selector_picks_production_when_ready_ingredients_reordered() -> (
    None
):
    """성분 비교는 순서를 포함한 list 비교다 - 같은 성분이라도 순서가
    다르면(= set으로 보면 동일) production을 선택해야 한다."""

    production = build_parser_result(
        "production", [_ready("a", ["정제수", "글리세린"])]
    )
    shadow = build_parser_result(
        "shadow", [_ready("a", ["글리세린", "정제수"])]
    )
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "production"
    assert (
        result.reason
        == "production_ready_option_ingredients_changed_in_shadow"
    )


def test_selector_picks_production_when_ready_ingredients_differ() -> None:
    production = build_parser_result(
        "production", [_ready("a", ["정제수", "글리세린"])]
    )
    shadow = build_parser_result("shadow", [_ready("a", ["정제수"])])
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "production"
    assert (
        result.reason
        == "production_ready_option_ingredients_changed_in_shadow"
    )


def test_selector_picks_shadow_when_it_increases_ready_count_safely() -> (
    None
):
    production = build_parser_result(
        "production", [_ready("a", ["정제수"]), _unmapped("b")]
    )
    shadow = build_parser_result(
        "shadow", [_ready("a", ["정제수"]), _ready("b", ["글리세린"])]
    )
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "shadow"
    assert (
        result.reason
        == "shadow_increases_ready_option_count_without_regression"
    )


def test_selector_picks_production_when_ready_count_unchanged() -> None:
    production = build_parser_result("production", [_ready("a", ["정제수"])])
    shadow = build_parser_result("shadow", [_ready("a", ["정제수"])])
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "production"
    assert result.reason == "no_safe_improvement_detected"


def test_selector_picks_production_when_shadow_has_fewer_ready_options() -> (
    None
):
    production = build_parser_result(
        "production", [_ready("a", ["정제수"]), _ready("b", ["글리세린"])]
    )
    shadow = build_parser_result(
        "shadow", [_ready("a", ["정제수"]), _unmapped("b")]
    )
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "production"
    # 이 케이스는 production ready 옵션(b)이 shadow에서 ready가
    # 아니므로 그 규칙이 먼저 걸린다.
    assert result.reason == "production_ready_option_not_ready_in_shadow"


def test_selector_ignores_non_ready_production_options_for_ingredient_check() -> (  # noqa: E501
    None
):
    """production에서 ready가 아니었던 옵션은 shadow에서 성분이
    달라져도 production 선택 이유가 되지 않는다 - shadow가 새로
    ready로 만든 옵션이 있으면 여전히 shadow를 선택할 수 있다."""

    production = build_parser_result(
        "production", [_ready("a", ["정제수"]), _unmapped("b")]
    )
    shadow = build_parser_result(
        "shadow",
        [_ready("a", ["정제수"]), _ready("b", ["글리세린", "폴리부텐"])],
    )
    result = select_safe_parser_result(production, shadow)
    assert result.selected == "shadow"


def test_selector_result_carries_both_parser_results() -> None:
    production = build_parser_result("production", [_ready("a", ["정제수"])])
    shadow = build_parser_result("shadow", [_ready("a", ["정제수"])])
    result = select_safe_parser_result(production, shadow)
    assert result.production is production
    assert result.shadow is shadow

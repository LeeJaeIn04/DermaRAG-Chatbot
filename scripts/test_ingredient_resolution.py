from app.rag_chain import (
    deduplicate_ingredient_names,
    normalize_ingredient_name,
    resolve_ingredients,
    split_ingredients,
)


def test_resolve_ingredients_prefers_structured_list_over_string() -> None:
    """
    ingredients 목록이 있으면 ingredient_list 문자열은
    무시하고 목록을 그대로 사용해야 한다.
    """

    result = resolve_ingredients(
        ingredients=[
            "1,2-헥산다이올",
            "코코-카프릴레이트/카프레이트",
        ],
        ingredient_list="사용되면 안 되는 문자열",
    )

    assert result == [
        "1,2-헥산다이올",
        "코코-카프릴레이트/카프레이트",
    ]


def test_resolve_ingredients_falls_back_to_string_when_list_empty() -> None:
    result = resolve_ingredients(
        ingredients=[],
        ingredient_list="정제수, 글리세린",
    )

    assert result == ["정제수", "글리세린"]


def test_resolve_ingredients_returns_empty_when_both_missing() -> None:
    result = resolve_ingredients(
        ingredients=None,
        ingredient_list=None,
    )

    assert result == []


def test_resolve_ingredients_preserves_internal_commas() -> None:
    """
    성분명 내부의 쉼표는 목록 입력에서는 애초에 분리 대상이
    아니므로 각각 하나의 성분으로 유지되어야 한다.
    """

    result = resolve_ingredients(
        ingredients=[
            "1,2-헥산다이올",
            "자작나무수액(1,425ppm)",
        ],
        ingredient_list=None,
    )

    assert result == [
        "1,2-헥산다이올",
        "자작나무수액(1,425ppm)",
    ]


def test_resolve_ingredients_preserves_slash() -> None:
    result = resolve_ingredients(
        ingredients=["코코-카프릴레이트/카프레이트"],
        ingredient_list=None,
    )

    assert result == ["코코-카프릴레이트/카프레이트"]


def test_resolve_ingredients_deduplicates_while_keeping_order() -> None:
    result = resolve_ingredients(
        ingredients=["정제수", "글리세린", "정제수"],
        ingredient_list=None,
    )

    assert result == ["정제수", "글리세린"]


def test_split_ingredients_does_not_use_slash_as_separator() -> None:
    """
    기존 /chat 하위 호환용 문자열 파서도 더 이상 /를
    구분자로 사용하지 않아야 한다.
    """

    result = split_ingredients(
        "정제수, 코코-카프릴레이트/카프레이트, 글리세린"
    )

    assert result == [
        "정제수",
        "코코-카프릴레이트/카프레이트",
        "글리세린",
    ]


def test_split_ingredients_still_splits_on_comma() -> None:
    result = split_ingredients("정제수, 글리세린, 나이아신아마이드")

    assert result == ["정제수", "글리세린", "나이아신아마이드"]


def test_split_ingredients_handles_none_and_empty() -> None:
    assert split_ingredients(None) == []
    assert split_ingredients("") == []


def test_normalize_ingredient_name_collapses_whitespace() -> None:
    assert normalize_ingredient_name("  정제수   ") == "정제수"


def test_deduplicate_ingredient_names_keeps_first_occurrence_order() -> None:
    result = deduplicate_ingredient_names(
        ["정제수", "글리세린", "정제수", "향료"]
    )

    assert result == ["정제수", "글리세린", "향료"]

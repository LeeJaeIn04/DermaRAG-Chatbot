from app.products.ingredient_extractors.oliveyoung_browser import (
    split_raw_ingredient_text,
)


def test_splits_plain_comma_separated_list() -> None:
    result = split_raw_ingredient_text(
        "정제수, 글리세린, 나이아신아마이드"
    )

    assert result == ["정제수", "글리세린", "나이아신아마이드"]


def test_preserves_numeric_comma_inside_ingredient_name() -> None:
    """
    "1,2-헥산다이올"처럼 숫자 사이의 쉼표는 구분자가 아니다.
    """

    result = split_raw_ingredient_text(
        "정제수, 1,2-헥산다이올, 글리세린"
    )

    assert result == ["정제수", "1,2-헥산다이올", "글리세린"]


def test_preserves_comma_inside_parentheses() -> None:
    """
    "자작나무수액(1,425ppm)"처럼 괄호 안의 쉼표는 구분자가 아니다.
    """

    result = split_raw_ingredient_text(
        "정제수, 자작나무수액(1,425ppm), 글리세린"
    )

    assert result == [
        "정제수",
        "자작나무수액(1,425ppm)",
        "글리세린",
    ]


def test_preserves_slash_inside_ingredient_name() -> None:
    result = split_raw_ingredient_text(
        "정제수, 코코-카프릴레이트/카프레이트, 글리세린"
    )

    assert result == [
        "정제수",
        "코코-카프릴레이트/카프레이트",
        "글리세린",
    ]


def test_handles_empty_string() -> None:
    assert split_raw_ingredient_text("") == []

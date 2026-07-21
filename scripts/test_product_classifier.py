from app.products.classifier import (
    classify_product_category,
    get_next_action,
    normalize_product_text,
)


def test_normalize_product_text() -> None:
    result = normalize_product_text(
        "  Glow   Cushion  "
    )

    assert result == "glow cushion"


def test_classifies_sunscreen_as_skincare() -> None:
    result = classify_product_category(
        "자작나무 수분 선크림 50ml"
    )

    assert result == "skincare"


def test_classifies_serum_as_skincare() -> None:
    result = classify_product_category(
        "나이아신아마이드 세럼 30ml"
    )

    assert result == "skincare"


def test_classifies_cushion_as_color_makeup() -> None:
    result = classify_product_category(
        "글로우 쿠션 15g"
    )

    assert result == "color_makeup"


def test_classifies_lip_tint_as_color_makeup() -> None:
    result = classify_product_category(
        "벨벳 립 틴트"
    )

    assert result == "color_makeup"


def test_color_keyword_has_priority() -> None:
    result = classify_product_category(
        "컬러 글로우 립 세럼"
    )

    assert result == "color_makeup"


def test_classifies_shampoo_as_other() -> None:
    result = classify_product_category(
        "데미지 케어 샴푸 500ml"
    )

    assert result == "other"


def test_returns_unknown_for_ambiguous_product() -> None:
    result = classify_product_category(
        "스페셜 기획세트"
    )

    assert result == "unknown"


def test_category_path_has_priority() -> None:
    result = classify_product_category(
        product_name="글로우 컬렉션",
        category_path=(
            "메이크업 > 베이스메이크업 > 쿠션"
        ),
    )

    assert result == "color_makeup"


def test_skincare_next_action() -> None:
    assert (
        get_next_action("skincare")
        == "extract_ingredients"
    )


def test_color_makeup_next_action() -> None:
    assert (
        get_next_action("color_makeup")
        == "select_product_option"
    )


def test_unknown_next_action() -> None:
    assert (
        get_next_action("unknown")
        == "manual_review"
    )
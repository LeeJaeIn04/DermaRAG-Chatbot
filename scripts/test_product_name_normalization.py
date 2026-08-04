from app.products.product_name_normalization import normalize_product_name
from app.products.service import normalize_product_search_query


def test_removes_only_complete_leading_bracket_blocks() -> None:
    cases = {
        "[기획]틴트": "틴트",
        "[NEW] 롬앤 틴트": "롬앤 틴트",
        "[NEW두유코어/1등틴트] 롬앤 더 쥬시 래스팅 틴트": (
            "롬앤 더 쥬시 래스팅 틴트"
        ),
        "[기획][단독] 롬앤 틴트": "롬앤 틴트",
        "  [기획]  롬앤   틴트  ": "롬앤 틴트",
    }

    for value, expected in cases.items():
        assert normalize_product_name(value) == expected


def test_keeps_non_leading_or_unclosed_brackets() -> None:
    assert normalize_product_name("롬앤 [기획] 틴트") == "롬앤 [기획] 틴트"
    assert normalize_product_name("롬앤 틴트 [23호]") == "롬앤 틴트 [23호]"
    assert normalize_product_name("[기획 롬앤 틴트") == "[기획 롬앤 틴트"


def test_bracket_only_name_falls_back_to_normalized_original() -> None:
    assert normalize_product_name(" [기획] ") == "[기획]"


def test_search_query_uses_same_product_name_normalization() -> None:
    assert normalize_product_search_query("[기획] 롬앤 틴트") == "롬앤 틴트"
    assert normalize_product_search_query("롬앤 틴트") == "롬앤 틴트"

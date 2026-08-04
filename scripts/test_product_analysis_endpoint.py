from datetime import datetime, timezone

import app.main as main
from app.products.ingredient_cache_service import (
    ProductIngredientResolution,
)
from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.rag_chain import resolve_ingredients
from app.schemas import UserSkinProfile
from app.skin_rule_schemas import (
    SkinCompatibilityNotice,
)


RESOLVED_INGREDIENTS = [
    "1,2-헥산다이올",
    "자작나무수액(1,425ppm)",
    "코코-카프릴레이트/카프레이트",
]


def make_product() -> ProductCandidate:
    return ProductCandidate(
        product_id="A000000149135",
        source="oliveyoung",
        brand_name="라운드랩",
        product_name="자작나무 수분 선크림 50ml",
        category="skincare",
        category_path="스킨케어 > 선케어 > 선크림",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000149135"
        ),
    )


def make_resolution() -> ProductIngredientResolution:
    result = ProductIngredientResult(
        product_id="A000000149135",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000149135"
        ),
        raw_ingredients=", ".join(RESOLVED_INGREDIENTS),
        ingredients=list(RESOLVED_INGREDIENTS),
        extraction_method="browser_dom",
        extraction_success=True,
        error_message=None,
    )

    return ProductIngredientResolution(
        result=result,
        cache_hit=True,
        cache_expired=False,
        extraction_performed=False,
    )


def test_analyze_product_passes_structured_ingredients(
    monkeypatch,
) -> None:
    """
    /products/analyze는 성분 목록을 문자열로 합치지 않고
    ChatRequest.ingredients에 구조화된 목록을 그대로 전달해야 한다.
    """

    captured_requests: list = []

    def fake_get_or_extract(**kwargs):
        return make_resolution()

    def fake_invoke_derma_rag(request, *, api_endpoint="/chat"):
        captured_requests.append(request)
        return {
            "answer": "테스트 답변",
            "sources": [],
            "metadata": {
                "ingredient_count": len(
                    resolve_ingredients(
                        ingredients=request.ingredients,
                        ingredient_list=request.ingredient_list,
                    )
                ),
            },
        }

    monkeypatch.setattr(
        main.ingredient_cache_service,
        "get_or_extract",
        fake_get_or_extract,
    )
    monkeypatch.setattr(
        main,
        "invoke_derma_rag",
        fake_invoke_derma_rag,
    )

    request = main.ProductAnalysisRequest(
        product=make_product(),
        question="이 성분 때문에 트러블이 났을까요?",
    )

    response = main.analyze_product(request)

    assert len(captured_requests) == 1
    rag_request = captured_requests[0]

    assert rag_request.ingredients == RESOLVED_INGREDIENTS
    assert rag_request.ingredient_list is None
    assert rag_request.skin_profile is None
    assert response.skin_compatibility == []

    # /products/analyze 응답의 ingredient_count와 LangGraph
    # metadata의 ingredient_count, 그리고 실제 RAG로 전달된
    # 성분 개수가 모두 일치해야 한다.
    assert response.ingredient_count == len(RESOLVED_INGREDIENTS)
    assert (
        response.metadata["ingredient_count"]
        == response.ingredient_count
    )
    assert len(rag_request.ingredients) == response.ingredient_count


def test_product_analysis_request_accepts_profile_without_skin_type() -> None:
    request = main.ProductAnalysisRequest(
        product=make_product(),
        question="민감 피부 기준으로 확인해 주세요.",
        skin_profile=UserSkinProfile(
            sensitive=True,
            concerns=["redness"],
        ),
    )

    assert request.skin_profile is not None
    assert request.skin_profile.skin_type is None
    assert request.skin_profile.sensitive is True


def test_analyze_product_uses_only_selected_option_ingredients(
    monkeypatch,
) -> None:
    selected_ingredients = [
        "정제수",
        "황색4호 (CI 19140)",
        "향료",
    ]
    captured: dict[str, object] = {}
    profile = UserSkinProfile(
        skin_type="oily",
        sensitive=True,
        concerns=["acne_prone"],
    )
    compatibility_notice = SkinCompatibilityNotice(
        ingredient_name="향료",
        rule_id="fragrance",
        category="향료",
        level="caution",
        matched_profiles=["sensitive"],
        possible_concerns=["자극 가능성"],
        reason="피부 상태에 따라 주의 요인이 될 수 있습니다.",
        condition="함량과 제형에 따라 달라질 수 있습니다.",
        evidence_level="reference",
    )

    def fake_get_cached_option(**kwargs):
        captured["option_key"] = kwargs["internal_option_key"]
        resolution = make_resolution()
        return ProductIngredientResolution(
            result=resolution.result.model_copy(
                update={
                    "raw_ingredients": ", ".join(selected_ingredients),
                    "ingredients": selected_ingredients,
                }
            ),
            cache_hit=True,
            cache_expired=False,
            extraction_performed=False,
        )

    class CapturingRepository:
        def __init__(self, key: str) -> None:
            self.key = key

        def find_for_ingredients(self, ingredients):
            captured[self.key] = list(ingredients)
            return []

    def fake_invoke(request, *, api_endpoint="/chat"):
        captured["rag"] = list(request.ingredients)
        captured["skin_profile"] = request.skin_profile
        return {
            "answer": "선택 옵션 답변",
            "sources": [],
            "metadata": {},
            "skin_compatibility": [
                compatibility_notice,
            ],
        }

    monkeypatch.setattr(
        main.ingredient_cache_service,
        "get_cached_option",
        fake_get_cached_option,
    )
    monkeypatch.setattr(
        main,
        "get_mfds_regulation_repository",
        lambda: CapturingRepository("regulation"),
    )
    monkeypatch.setattr(
        main,
        "get_mfds_fragrance_allergen_repository",
        lambda: CapturingRepository("allergen"),
    )
    monkeypatch.setattr(main, "invoke_derma_rag", fake_invoke)

    response = main.analyze_product(
        main.ProductAnalysisRequest(
            product=make_product(),
            question="19호 옵션을 분석해 주세요.",
            option_id="internal-key-19",
            internal_option_key="internal-key-19",
            option_name="19호",
            skin_profile=profile,
        )
    )

    assert captured["option_key"] == "internal-key-19"
    assert captured["regulation"] == selected_ingredients
    assert captured["allergen"] == selected_ingredients
    assert captured["rag"] == selected_ingredients
    assert captured["skin_profile"] == profile
    assert response.selected_option_key == "internal-key-19"
    assert response.selected_option_name == "19호"
    assert response.option_specific_ingredients is True
    assert response.skin_compatibility == [
        compatibility_notice
    ]

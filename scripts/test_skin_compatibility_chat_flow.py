import app.graph.nodes as nodes
import app.main as main
from app.schemas import (
    ChatRequest,
    UserSkinProfile,
)
from app.skin_rule_schemas import (
    SkinCompatibilityNotice,
)


def _profile() -> UserSkinProfile:
    return UserSkinProfile(
        skin_type="oily",
        sensitive=True,
        concerns=["acne_prone"],
    )


def _notice() -> SkinCompatibilityNotice:
    return SkinCompatibilityNotice(
        ingredient_name="향료",
        rule_id="fragrance",
        category="향료",
        level="caution",
        matched_profiles=["sensitive"],
        possible_concerns=["자극 가능성"],
        reason="민감 피부는 주의가 필요합니다.",
        condition="개인차가 있습니다.",
        evidence_level="reference",
    )


def test_structured_ingredients_are_evaluated_without_resplitting(
    monkeypatch,
) -> None:
    captured: list[list[str]] = []

    def fake_evaluate(ingredients, profile):
        captured.append(list(ingredients))
        assert profile == _profile()
        return [_notice()]

    monkeypatch.setattr(
        nodes,
        "evaluate_product_ingredients",
        fake_evaluate,
    )

    request = ChatRequest(
        question="이 제품이 맞을까요?",
        skin_profile=_profile(),
        ingredients=[
            "1,2-헥산다이올",
            "향료",
        ],
        ingredient_list="에탄올, 글리세린",
    )
    classified = nodes.classify_intent_node(
        {"request": request}
    )
    result = nodes.evaluate_skin_compatibility_node(
        {
            "request": request,
            **classified,
        }
    )

    assert captured == [["1,2-헥산다이올", "향료"]]
    assert result["skin_compatibility"] == [_notice()]


def test_chat_flow_contains_actual_caution_and_beneficial_rules() -> None:
    request = ChatRequest(
        question="피부 타입에 맞는 성분인지 확인해 주세요.",
        skin_profile=_profile(),
        ingredients=[
            "살리실릭애씨드",
            "에탄올",
            "향료",
            "글리세린",
        ],
    )
    classified = nodes.classify_intent_node(
        {"request": request}
    )
    result = nodes.evaluate_skin_compatibility_node(
        {
            "request": request,
            **classified,
        }
    )
    levels = {
        notice.ingredient_name: notice.level
        for notice in result["skin_compatibility"]
    }

    assert levels == {
        "살리실릭애씨드": "caution",
        "에탄올": "caution",
        "향료": "caution",
        "글리세린": "beneficial",
    }


def test_ingredient_list_uses_existing_split_fallback(
    monkeypatch,
) -> None:
    captured: list[list[str]] = []

    def fake_evaluate(ingredients, profile):
        captured.append(list(ingredients))
        return []

    monkeypatch.setattr(
        nodes,
        "evaluate_product_ingredients",
        fake_evaluate,
    )

    request = ChatRequest(
        question="성분을 확인해 주세요.",
        skin_profile=_profile(),
        ingredient_list="살리실릭애씨드, 에탄올, 향료",
    )
    classified = nodes.classify_intent_node(
        {"request": request}
    )
    nodes.evaluate_skin_compatibility_node(
        {
            "request": request,
            **classified,
        }
    )

    assert captured == [[
        "살리실릭애씨드",
        "에탄올",
        "향료",
    ]]


def test_evaluation_is_skipped_without_profile_or_ingredients(
    monkeypatch,
) -> None:
    def unexpected_call(*args, **kwargs):
        raise AssertionError(
            "피부 프로필과 성분이 모두 있을 때만 호출해야 합니다."
        )

    monkeypatch.setattr(
        nodes,
        "evaluate_product_ingredients",
        unexpected_call,
    )

    without_profile = ChatRequest(
        question="향료가 들어 있어요.",
        ingredients=["향료"],
    )
    without_ingredients = ChatRequest(
        question="제품을 봐 주세요.",
        skin_profile=_profile(),
    )

    assert nodes.evaluate_skin_compatibility_node(
        {
            "request": without_profile,
            "ingredient_names": ["향료"],
        }
    ) == {"skin_compatibility": []}
    assert nodes.evaluate_skin_compatibility_node(
        {
            "request": without_ingredients,
            "ingredient_names": [],
        }
    ) == {"skin_compatibility": []}


def test_chat_response_includes_skin_compatibility(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main,
        "invoke_derma_rag",
        lambda request: {
            "answer": "피부 맞춤 분석 결과입니다.",
            "sources": [],
            "metadata": {},
            "skin_compatibility": [_notice()],
        },
    )

    response = main.chat(
        ChatRequest(
            question="향료가 민감성 피부에 맞을까요?",
            skin_profile=_profile(),
            ingredients=["향료"],
        )
    )

    assert response.skin_compatibility == [_notice()]

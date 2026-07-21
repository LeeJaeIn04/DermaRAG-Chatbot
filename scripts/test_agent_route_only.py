from app.graph.nodes import classify_intent_node
from app.schemas import ChatRequest

def assert_route(request: ChatRequest, expected_route: str) -> None:
    result = classify_intent_node({"request": request})
    actual_route = result.get("route")

    print("EXPECTED: ", expected_route)
    print("ACTUAL: ", actual_route)

    if actual_route != expected_route :
        raise AssertionError(
            f"expected_route={expected_route}, actual_route={actual_route}"
        )
    

def main() -> None:
    assert_route(
        ChatRequest(
            question="로션을 바꾼 뒤 볼에 좁쌀이 올라오고 따가워요.",
            skin_type="수부지",
            ingredient_list="정제수, 부틸렌글라이콜, 프로판다이올",
            current_routine="이 로션 아침 저녁에 바름",
        ),
        "ingredient_rag",
    )

    assert_route(
        ChatRequest(
            question="얼굴이 붓고 진물이 나요.",
            skin_type="민감성",
            ingredient_list="정제수, 향료",
        ),
        "safety_warning",
    )

    assert_route(
        ChatRequest(
            question="비타민C랑 BHA 같이 써도 돼?",
            skin_type="수부지",
            current_routine="아침 비타민C, 저녁 BHA",
        ),
        "routine_check",
    )

    assert_route(
        ChatRequest(
            question="화장품 바꾸고 피부가 좀 안 좋아진 것 같아요.",
            skin_type="수부지",
        ),
        "general_answer",
    )

    print("route-only tests ok")


if __name__ == "__main__":
    main()
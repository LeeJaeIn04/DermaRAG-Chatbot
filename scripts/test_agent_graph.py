from app.graph.workflow import derma_rag_graph
from app.schemas import ChatRequest


TEST_CASES = [
    (
        "ingredient_rag",
        ChatRequest(
            question="새 쿠션을 바른 뒤 볼에 좁쌀이 올라오고 약간 따가워요.",
            skin_type="수부지, 민감성",
            ingredient_list="정제수, 티타늄디옥사이드, 글리세린, 나이아신아마이드, 향료, 판테놀",
            current_routine="아침에는 비타민C 세럼을 쓰고, 저녁에는 BHA 토너를 주 3회 사용 중입니다.",
        ),
    ),
    (
        "safety_warning",
        ChatRequest(
            question="새 화장품을 바른 뒤 얼굴이 붓고 진물이 나요.",
            skin_type="민감성",
            ingredient_list="정제수, 향료",
            current_routine="",
        ),
    ),
    (
        "routine_check",
        ChatRequest(
            question="비타민C 세럼이랑 BHA 토너를 같이 써도 괜찮나요?",
            skin_type="민감성",
            ingredient_list="",
            current_routine="아침 비타민C 세럼, 저녁 BHA 토너",
        ),
    ),
    (
        "general_answer",
        ChatRequest(
            question="새 제품 쓰고 좁쌀이 올라왔는데 어떻게 확인하면 좋을까요?",
            skin_type="수부지",
            ingredient_list="",
            current_routine="",
        ),
    ),
]


def assert_answer_has_required_sections(answer: str) -> None:
    section_groups = [
        ["요약"],
        ["가능성 있는 원인 후보", "원인 후보", "가능성"],
        ["루틴/사용 상황", "루틴", "사용 상황", "함께 볼 점"],
        ["안전한 대응", "대응", "지금 할 수 있는"],
        ["주의 문구", "주의", "상담"],
    ]

    for candidates in section_groups:
        assert any(candidate in answer for candidate in candidates), (
            f"missing section candidates: {candidates}"
        )


def main():
    for expected_route, request in TEST_CASES:
        result = derma_rag_graph.invoke(
            {
                "request": request,
            }
        )

        actual_route = result.get("route")
        answer = result.get("answer", "")
        sources = result.get("sources", [])
        warnings = result.get("warnings", [])

        print("\n" + "=" * 80)
        print(f"STATE KEYS:      {list(result.keys())}")
        print(f"EXPECTED ROUTE:  {expected_route}")
        print(f"ACTUAL ROUTE:    {actual_route}")
        print(f"WARNINGS:        {warnings}")
        print(f"SOURCES COUNT:   {len(sources)}")
        print("-" * 80)
        print(answer[:1000])

        assert actual_route == expected_route, (
            f"route mismatch: expected={expected_route}, actual={actual_route}"
        )

        assert answer.strip(), "answer is empty"

        assert_answer_has_required_sections(answer)

        if expected_route == "ingredient_rag":
            assert len(sources) > 0, "ingredient_rag route should return sources"
        else:
            assert len(sources) == 0, (
                f"{expected_route} route should not return sources"
            )

    print("\n모든 Agent route 테스트 통과")


if __name__ == "__main__":
    main()
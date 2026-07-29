from app.rag_chain import build_agent_prompt, build_prompt
from app.schemas import ChatRequest
from app.services.langsmith_trace import invoke_derma_rag


REGULATION_CONTEXT = (
    "[식약처 화장품 규제 정보]\n"
    "아래 정보는 제품 전성분과 식약처 규제 원료 목록을 exact match한 결과이다.\n\n"
    "1. 성분명: 에칠헥실트리아존\n"
    "- 규제 유형: restricted\n"
    "- 규제 분류: uv_filter\n"
    "- 최대 사용한도: 5%"
)


def make_request(regulation_context: str | None) -> ChatRequest:
    return ChatRequest(
        question="선크림을 바른 뒤 따가움이 있어요.",
        skin_type="민감성",
        ingredients=["에칠헥실트리아존"],
        regulation_context=regulation_context,
    )


def test_build_prompt_without_regulation_context_stays_unaffected() -> None:
    """regulation_context가 없는 일반 /chat 요청은 기존과 동일하게 동작해야 한다."""

    request = make_request(regulation_context=None)

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "[식약처 화장품 규제 정보]" not in prompt
    assert "검색된 성분 정보가 없습니다." in prompt


def test_build_prompt_includes_regulation_context_when_present() -> None:
    """상품 분석 요청처럼 regulation_context가 있으면 프롬프트 본문에 포함돼야 한다."""

    request = make_request(regulation_context=REGULATION_CONTEXT)

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "에칠헥실트리아존" in prompt
    assert "최대 사용한도: 5%" in prompt


def test_build_prompt_states_restricted_interpretation_rules() -> None:
    """restricted를 위험/위반으로 단정하지 않도록 하는 규칙이 프롬프트에 있어야 한다."""

    request = make_request(regulation_context=REGULATION_CONTEXT)

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "restricted는 무조건 위험하거나 사용할 수 없는 성분이라는 뜻이 아니" in prompt
    assert "prohibited exact match가 있을 때만" in prompt
    assert "사용한도 초과나 법규 위반 여부를 판단하지" in prompt


def test_build_agent_prompt_also_carries_regulation_context() -> None:
    """safety_warning 등 agent 경로로 빠져도 regulation_context가 유지돼야 한다."""

    request = make_request(regulation_context=REGULATION_CONTEXT)

    prompt = build_agent_prompt(request=request, route="safety_warning")

    assert "에칠헥실트리아존" in prompt


def test_invoke_derma_rag_forwards_api_endpoint_to_langsmith_metadata(
    monkeypatch,
) -> None:
    """/products/analyze 호출 시 api_endpoint가 LangSmith config metadata에 전달돼야 한다."""

    captured_configs: list = []

    def fake_invoke(state, config):
        captured_configs.append(config)
        return {"answer": "테스트 답변", "sources": [], "metadata": {}}

    import app.services.langsmith_trace as langsmith_trace

    monkeypatch.setattr(
        langsmith_trace.derma_rag_graph,
        "invoke",
        fake_invoke,
    )

    request = make_request(regulation_context=REGULATION_CONTEXT)

    result = invoke_derma_rag(request, api_endpoint="/products/analyze")

    assert result["answer"] == "테스트 답변"
    assert len(captured_configs) == 1
    assert (
        captured_configs[0]["metadata"]["api_endpoint"]
        == "/products/analyze"
    )


def test_invoke_derma_rag_defaults_api_endpoint_for_chat(
    monkeypatch,
) -> None:
    """기존 /chat 호출은 api_endpoint를 넘기지 않아도 기본값으로 정상 동작해야 한다."""

    captured_configs: list = []

    def fake_invoke(state, config):
        captured_configs.append(config)
        return {"answer": "테스트 답변", "sources": [], "metadata": {}}

    import app.services.langsmith_trace as langsmith_trace

    monkeypatch.setattr(
        langsmith_trace.derma_rag_graph,
        "invoke",
        fake_invoke,
    )

    request = make_request(regulation_context=None)

    result = invoke_derma_rag(request)

    assert result["answer"] == "테스트 답변"
    assert captured_configs[0]["metadata"]["api_endpoint"] == "/chat"

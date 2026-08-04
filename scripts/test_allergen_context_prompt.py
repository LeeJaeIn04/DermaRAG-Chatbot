from app.rag_chain import build_agent_prompt, build_prompt
from app.schemas import ChatRequest


REGULATION_CONTEXT = (
    "[식약처 화장품 규제 정보]\n"
    "아래 정보는 제품 전성분과 식약처 규제 원료 목록을 exact match한 결과이다.\n\n"
    "1. 성분명: 에칠헥실트리아존\n"
    "- 규제 유형: restricted\n"
    "- 규제 분류: uv_filter\n"
    "- 최대 사용한도: 5%"
)

ALLERGEN_CONTEXT = (
    "[식약처 향료 알레르기 표시 대상 정보]\n"
    "아래 정보는 제품 전성분과 식약처 향료 알레르기 유발성분 표시 대상 목록을 "
    "exact match한 결과이다.\n\n"
    "1. 성분명: 리모넨\n"
    "- 공식 한글명: 리모넨\n"
    "- 법적 상태: 표시 대상\n"
    "- 사용 후 씻어내는 제품 표시 기준: 0.01% 초과"
)


def make_request(
    *,
    regulation_context: str | None = None,
    allergen_context: str | None = None,
) -> ChatRequest:
    return ChatRequest(
        question="새 샴푸를 쓴 뒤 두피가 따가워요.",
        skin_type="민감성",
        ingredients=["리모넨", "리날룰"],
        regulation_context=regulation_context,
        allergen_context=allergen_context,
    )


def test_build_prompt_without_allergen_context_has_no_allergen_section() -> None:
    """allergen_context가 없으면 기존 /chat 프롬프트에 알레르겐 섹션이 없어야 한다."""

    request = make_request()

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "[식약처 향료 알레르기 표시 대상 정보]" not in prompt
    assert "검색된 성분 정보가 없습니다." in prompt


def test_build_prompt_includes_allergen_context_when_present() -> None:
    """allergen_context가 있으면 build_prompt() 결과에 리모넨과 표시 대상 정보가 포함돼야 한다."""

    request = make_request(allergen_context=ALLERGEN_CONTEXT)

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "리모넨" in prompt
    assert "식약처 향료 알레르기 표시 대상 정보" in prompt


def test_build_agent_prompt_carries_allergen_context() -> None:
    """safety_warning 등 agent 경로에서도 allergen_context가 유실되지 않아야 한다."""

    request = make_request(allergen_context=ALLERGEN_CONTEXT)

    prompt = build_agent_prompt(request=request, route="safety_warning")

    assert "리모넨" in prompt
    assert "식약처 향료 알레르기 표시 대상 정보" in prompt


def test_build_prompt_states_allergen_interpretation_rules() -> None:
    """표시 대상과 실제 알레르기 원인 확정을 구분하는 규칙이 프롬프트에 있어야 한다."""

    request = make_request(allergen_context=ALLERGEN_CONTEXT)

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "향료 알레르기 표시 대상이라는 사실만으로" in prompt
    assert "단정하지" in prompt


def test_build_prompt_states_threshold_judgement_rule() -> None:
    """0.01%, 0.001% 표시 기준 초과 여부를 전성분표만으로 판단하지 않는 규칙이 있어야 한다."""

    request = make_request(allergen_context=ALLERGEN_CONTEXT)

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "0.01%" in prompt
    assert "0.001%" in prompt
    assert "독성·안전 기준이 아니라 법적 표시 기준" in prompt
    assert "[필수 근거 전달]" in prompt
    assert "표시 기준 수치를 답변에 그대로 포함" in prompt


def test_build_prompt_includes_both_regulation_and_allergen_context() -> None:
    """regulation_context와 allergen_context가 동시에 있으면 둘 다 프롬프트에 포함돼야 한다."""

    request = make_request(
        regulation_context=REGULATION_CONTEXT,
        allergen_context=ALLERGEN_CONTEXT,
    )

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "에칠헥실트리아존" in prompt
    assert "리모넨" in prompt
    assert "식약처 화장품 규제 정보" in prompt
    assert "식약처 향료 알레르기 표시 대상 정보" in prompt


def test_build_prompt_without_any_context_generates_normal_prompt() -> None:
    """regulation_context, allergen_context가 모두 없어도 기존 /chat 프롬프트가 정상 생성돼야 한다."""

    request = ChatRequest(
        question="쿠션을 바꾼 뒤 볼에 좁쌀이 올라와요.",
        skin_type="복합성",
    )

    prompt = build_prompt(request=request, context="검색된 성분 정보가 없습니다.")

    assert "쿠션을 바꾼 뒤 볼에 좁쌀이 올라와요." in prompt
    assert "[답변 형식]" in prompt
    assert "[식약처 화장품 규제 정보]" not in prompt
    assert "[식약처 향료 알레르기 표시 대상 정보]" not in prompt

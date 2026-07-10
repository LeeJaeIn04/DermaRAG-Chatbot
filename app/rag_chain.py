from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings
from app.retriever import search_documents
from app.schemas import ChatRequest, ChatResponse, Source
from typing import Any


def validate_environment() -> None:
    if not settings.google_api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY가 설정되어 있지 않습니다. "
            ".env 파일에 Gemini API Key를 추가해 주세요."
        )


def build_search_query(request: ChatRequest) -> str:
    if request.ingredient_list:
        return request.ingredient_list

    return request.question


def split_ingredients(ingredient_list: str | None) -> list[str]:
    if not ingredient_list:
        return []

    normalized = ingredient_list.replace("，", ",").replace("/", ",")

    ingredients = []

    for item in normalized.split(","):
        name = item.strip()

        if name:
            ingredients.append(name)

    return ingredients


def deduplicate_docs(docs) -> list:
    unique_docs = []
    seen_keys = set()

    for doc in docs:
        key = (
            doc.metadata.get("ingredient_kor_name")
            or doc.metadata.get("ingredient_eng_name")
            or doc.page_content[:100]
        )

        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_docs.append(doc)

    return unique_docs


def retrieve_documents(
        request: ChatRequest, 
        ingredient_names: list[str] | None = None,
)  -> list[Any]:
    ingredient_names = split_ingredients(request.ingredient_list)

    if ingredient_names:
        docs = []

        for ingredient_name in ingredient_names:
            docs.extend(search_documents(ingredient_name, search_k=2))
    
    else:
        search_query = build_search_query(request)
        docs = search_documents(search_query, search_k=8)

    docs = deduplicate_docs(docs)
    return docs[:10]


def build_context(docs) -> str:
    if not docs:
        return "검색된 성분 정보가 없습니다."

    formatted_docs = []

    for index, doc in enumerate(docs, start=1):
        source = doc.metadata.get("source", "unknown")
        eng_name = doc.metadata.get("ingredient_eng_name")
        kor_name = doc.metadata.get("ingredient_kor_name")
        content = doc.page_content

        formatted_docs.append(
            f"[근거 문서 {index}]\n"
            f"출처: {source}\n"
            f"성분명: {kor_name or '정보 없음'}\n"
            f"영문명: {eng_name or '정보 없음'}\n"
            f"{content}"
        )

    return "\n\n".join(formatted_docs)


def build_prompt(request: ChatRequest, context: str) -> str:

    return f"""
    당신은 화장품 성분 기반 피부 반응 원인 후보를 분석하는 RAG 챗봇입니다.

    반드시 지켜야 할 원칙:
    1. 특정 성분이 피부 반응의 원인이라고 단정하지 마세요.
    2. 검색된 근거 문서와 사용자 입력을 바탕으로 가능성 있는 후보를 설명하세요.
    3. 식약처 원료성분 정보는 성분의 기본 정보이지, 피부 반응의 직접적인 인과관계 데이터가 아님을 반영하세요.
    4. 증상이 심하거나 오래 지속되거나 통증, 진물, 부종이 있으면 피부과 전문의 상담을 권장하세요.
    5. 답변은 한국어로 작성하세요.
    6. 과장된 표현, 공포를 유발하는 표현, 치료 지시 표현은 피하세요.
    7. 검색된 근거 문서에 없는 성분 정보를 근거가 있는 것처럼 설명하지 마세요.
    8. 사용자 전성분표에는 있지만 검색 결과에 없는 성분은 "현재 구축된 성분 DB에서 직접 근거를 찾지 못했습니다"라고 표현하세요.
    9. 검색된 식약처 원료성분 정보는 성분의 정의, 기원, 구조, 표시명에 대한 정보입니다. 해당 문서만으로 특정 성분의 자극성, 안전성, 여드름 유발 가능성을 단정하지 마세요.
    10. 검색 문서에 직접 없는 효능/위험성/자극 가능성은 일반적인 가능성으로만 표현하고, 근거 문서에서 확인된 사실과 분리해서 설명하세요.

    [사용자 입력]
    질문/피부 반응:
    {request.question}

    피부 타입:
    {request.skin_type or "입력 없음"}

    전성분표:
    {request.ingredient_list or "입력 없음"}

    현재 루틴:
    {request.current_routine or "입력 없음"}

    [검색된 성분 근거]
    {context}

    [답변 형식]
    1. 요약
    2. 가능성 있는 원인 후보
    3. 루틴/사용 상황에서 함께 볼 점
    4. 지금 할 수 있는 안전한 대응
    5. 주의 문구

    위 형식에 맞춰 답변하세요.
    """.strip()

def build_agent_prompt(
        request: ChatRequest,
        route: str,
        context: str = "검색된 성분 정보가 없습니다.",
        warnings: list[str] | None = None,
) -> str:
    warnings = warnings or []

    route_guidance = {
        "safety_warning" : """현재 입력에는 부종, 진물, 물집, 심한 통증, 호흡곤란, 전신 두드러기 등 주의가 필요한 증상 표현이 포함되었을 수 있습니다.
        이 경우 성분 후보 분석보다 안전 안내를 우선하세요.
        특정 성분이 원인이라고 단저앟지 마록, 증상 악화나 위험 증상이 있으면 피부과 전문의 또는 의료기관 상담을 권장하세요.""",

        "routine_check" : """전성분표가 제공되지 않았거나 부족하므로 성분 DB 기반 원인 후보를 단정하지 마세요.
         대신 현재 루틴, 사용 빈도, 활성 성분 병행 가능성, 새 제품 추가 여부를 중심으로 설명하세요.
          비타민 C, AHA/BHA, 레티놀, 필링, 스크럽 등은 일반적으로 자극감을 느낄 수 있는 사용 상황으로 조심스럽게 언급할 수 있습니다. """,

        "general_answer" : """전성분표와 루틴 정보가 부족하므로 성분 DB 기반 원인 후보를 구체적으로 제시하지 마세요.
        사용자에게 전성분표를 입력하면 더 구체적은 RAG 분석이 가능하다고 안내하세요.
        현재 정보로 할 수 있는 안전한 확인 바업을 중심으로 답변하세요.""",
    }

    guidance = route_guidance.get(route, route_guidance["general_answer"])

    return f"""
    당신은 화장품 성분 기반 피부 반응 원인 후보를 안전하게 분석하는 DermaRAG Agent입니다.

    [현재 route]
    {route}

    [route별 답변 지침]
    {guidance}

    [공통 안전 원친]
    1. 특정 성분이 피부 반응의 원인이라고 단정하지 마세요.
    2. 검색 근거가 없는 성분 정보는 근거가 있는 것처럼 말하지 마세요.
    3. 식약처 원료성분 정보만으로 자극성, 안전성, 여드름 유발 가능성을 단정하지 마세요.
    4. 과장된 표현, 공포를 유발하는 표현, 치료 지시 표현은 피하세요.
    5. 증상이 심하거나 오래 지속되거나 통증, 진물, 부종이 있으면 피부과 전문의 상담을 권장하세요.
    6. 답변은 한국어로 작성하세요.
    7. 반드시 아래 1~5번 형식을 유지하세요.

    [사용자 입력]
    질문/피부 반응:
    {request.question}

    피부 타입:
    {request.skin_type or "입력 없음"}

    현재 루틴:
    {request.current_routine or "입력 없음"}

    [검색된 성분 근거]
    {context}

    [감지된 주의 정보]
    {", ".join(warnings) if warnings else "없음"}

    [답변 형식]
    1. 요약
    2. 가능성 있는 원인 후보
    3. 루틴/사용 사오항에서 함께 볼 점
    4. 지금 할 수 있는 안전한 대응
    5. 주의 문구

    위 형식에 맞춰 답변하세요.
    """.strip()


def get_llm() -> ChatGoogleGenerativeAI:
    validate_environment()

    return ChatGoogleGenerativeAI(
        model=settings.gemini_chat_model,
        google_api_key=settings.google_api_key,
        temperature=0.3,
    )


def generate_answer(request: ChatRequest, context: str) -> ChatResponse:
    prompt = build_prompt(request=request, context=context)
    llm = get_llm()
    response = llm.invoke(prompt)
    return response.content


def _content_to_text(content: Any) -> str :
    if isinstance(content, str):
        return content
    
    return str(content)


def generate_agent_answer(
    request: ChatRequest,
    route: str,
    context: str = "검색된 성분 정보가 없습니다.",
    warnings: list[str] | None = None,
) -> str :
    prompt = build_agent_prompt(
        request=request,
        route=route,
        context=context,
        warnings=warnings,
    )

    llm = get_llm()
    response = llm.invoke(prompt)
    return _content_to_text(response.content)


def build_sources(docs: list[Any]) -> list[Source]:
    return [
        Source(
            source = doc.metadata.get("source", "unknown"),
            content = doc.page_content[:500]
        )
        for doc in docs
    ]


# 기존 방식
def build_answer(request: ChatRequest) -> ChatResponse:
    ingredient_names = split_ingredients(request.ingredient_list)

    if ingredient_names:
        docs = []

        for ingredient_name in ingredient_names:
            docs.extend(search_documents(ingredient_name, search_k=2))
    else:
        search_query = build_search_query(request)
        docs = search_documents(search_query, search_k=8)

    docs = deduplicate_docs(docs)
    docs = docs[:10]

    context = build_context(docs)

    prompt = build_prompt(request=request, context=context)

    llm = get_llm()

    response = llm.invoke(prompt)

    sources = [
        Source(
            source=doc.metadata.get("source", "unknown"),
            content=doc.page_content[:500],
        )
        for doc in docs
    ]

    return ChatResponse(
        answer=response.content,
        sources=sources,
    )

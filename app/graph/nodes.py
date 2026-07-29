from app.graph.state import DermaRagState
from app.rag_chain import (
    resolve_ingredients,
    retrieve_documents,
    build_context,
    generate_answer,
    generate_agent_answer,
    build_sources,
)
from app.trace_metadata import (
    count_retrieval_types,
    merge_metadata,
)
from app.skin_compatibility import (
    evaluate_product_ingredients,
)

from typing import Any

def classify_intent_node(
    state: DermaRagState,
) -> dict[str, Any]:
    request = state["request"]

    ingredient_names = resolve_ingredients(
        ingredients=request.ingredients,
        ingredient_list=request.ingredient_list,
    )

    question = request.question or ""
    current_routine = request.current_routine or ""

    text = (
        f"{question} {' '.join(ingredient_names)} {current_routine}"
    ).lower()

    danger_keywords = [
        "호흡곤란",
        "숨이 안",
        "숨쉬기",
        "숨 쉬기",
        "얼굴이 부",
        "부종",
        "진물",
        "물집",
        "심한 통증",
        "통증이 심",
        "눈 주변",
        "전신 두드러기",
        "두드러기",
        "피부가 벗겨",
        "피부 벗겨",
    ]

    routine_keywords = [
        "비타민c",
        "비타민 c",
        "bha",
        "aha",
        "레티놀",
        "트레티노인",
        "아다팔렌",
        "필링",
        "스크럽",
        "토너",
        "세럼",
        "루틴",
        "같이 써",
        "함께 써",
        "병행",
    ]

    if any(
        keyword in text
        for keyword in danger_keywords
    ):
        route = "safety_warning"
        warnings = [
            "위험 증상 가능성이 있으므로 안전 안내를 우선합니다."
        ]

    elif ingredient_names:
        route = "ingredient_rag"
        warnings = []

    elif any(
        keyword in text
        for keyword in routine_keywords
    ):
        route = "routine_check"
        warnings = []

    else:
        route = "general_answer"
        warnings = []

    metadata = merge_metadata(
        state.get("metadata"),
        route=route,
        warnings=warnings,
    )

    return {
        "route": route,
        "warnings": warnings,
        "ingredient_names": ingredient_names,
        "metadata": metadata,
    }


def route_after_classification(state: DermaRagState) -> str:
    return state.get("route", "general_answer")


def evaluate_skin_compatibility_node(
    state: DermaRagState,
) -> dict[str, Any]:
    request = state["request"]
    ingredient_names = state.get(
        "ingredient_names",
        [],
    )

    if (
        request.skin_profile is None
        or not ingredient_names
    ):
        return {
            "skin_compatibility": [],
        }

    return {
        "skin_compatibility": (
            evaluate_product_ingredients(
                ingredient_names,
                request.skin_profile,
            )
        ),
    }


def parse_ingredient_node(state: DermaRagState) -> dict[str, Any]:
    # classify_intent_node가 이미 resolve_ingredients()로 최종 목록을
    # 계산해 두었으므로 여기서는 재사용만 하고 다시 파싱하지 않는다.
    ingredient_names = state.get("ingredient_names", [])

    metadata = merge_metadata(
        state.get("metadata"),
        ingredient_count = len(ingredient_names),
    )

    return {
        "ingredient_names": ingredient_names,
        "metadata": metadata,
    }

def retrieve_documents_node(state: DermaRagState) -> dict[str, Any]:
    request = state["request"]
    ingredient_names = state.get("ingredient_names", [])
    docs = retrieve_documents(request, ingredient_names=ingredient_names)
    retrieval_counts = count_retrieval_types(docs)
    metadata = merge_metadata(
        state.get("metadata"),
        retrieved_doc_count = len(docs),

        exact_match_count = (
            retrieval_counts["exact_match_count"]
        ),
        vector_fallback_count=(
            retrieval_counts["vector_fallback_count"]
        ),
    )
    return {
        "docs" : docs,
        "metadata": metadata,
    }

def build_context_node(state: DermaRagState) -> dict[str, Any]:
    docs = state.get("docs", [])
    context = build_context(docs).strip()

    metadata = merge_metadata(
        state.get("metadata"),
        context_char_count = len(context),
        context_empty = not bool(docs),
    )
    return {
        "context": context,
        "metadata": metadata,
    }


def generate_answer_node(state: DermaRagState) -> dict[str, Any]:
    request = state["request"]
    context = state.get("context", "")
    context_empty = state.get("metadata", {}).get("context_empty", True)
    
    answer = generate_answer(request=request, context=context)
    
    metadata = merge_metadata(
        state.get("metadata"),
        used_rag_context=not context_empty,
    )
    return {"answer": answer, "metadata": metadata}


def build_sources_node(state: DermaRagState) -> dict[str, Any]:
    docs = state.get("docs", [])
    sources = build_sources(docs)
    return {
        "sources": sources,
    }

def safety_warning_node(state: DermaRagState) -> dict[str, Any]:
    request = state["request"]
    warnings = state.get("warnings", [])

    answer = generate_agent_answer(
        request = request,
        route = "safety_warning",
        warnings = warnings,
    )

    metadata = merge_metadata(
        state.get("metadata"),
        used_rag_context=False,
    )

    return {
        "answer" : answer,
        "sources" : [],
        "metadata": metadata,
    }

def routine_check_node(state: DermaRagState) -> dict[str, Any]:
    request = state["request"]
    warnings = state.get("warnings", [])

    answer = generate_agent_answer(
        request = request,
        route = "routine_check",
        warnings = warnings,
    )

    metadata = merge_metadata(
        state.get("metadata"),
        used_rag_context=False,
    )

    return {
        "answer" : answer,
        "sources" : [],
        "metadata": metadata,
    }

def generate_agent_answer_node(state: DermaRagState) -> dict[str, Any]:
    request = state["request"]
    warnings = state.get("warnings", [])

    answer = generate_agent_answer(
        request = request,
        route = "general_answer",
        warnings = warnings,
    )

    metadata = merge_metadata(
        state.get("metadata"),
        used_rag_context=False,
    )

    return {
        "answer" : answer,
        "sources" : [],
        "metadata": metadata,
    }

from app.graph.state import DermaRagState
from app.rag_chain import (
    split_ingredients,
    retrieve_documents,
    build_context,
    generate_answer,
    generate_agent_answer,
    build_sources,
)

def classify_intent_node(state: DermaRagState) -> DermaRagState:
    request = state["request"]

    question = request.question or ""
    ingredient_list = request.ingredient_list or ""
    current_routine = request.current_routine or ""
    
    text = f"{question} {ingredient_list} {current_routine}".lower()

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

    if any(keyword in text for keyword in danger_keywords):
        return {
            "route": "safety_warning",
            "warnings": ["위험 증상 가능성이 있으므로 안전 안내를 우선합니다."],
        }
    
    if ingredient_list.strip():
        return {
            "route": "ingredient_rag",
            "warnings": [],
        }

    if any(keyword in text for keyword in routine_keywords):
        return {
            "route": "routine_check",
            "warnings": [],
        }
    
    return {
        "route": "general_answer",
        "warnings": [],
    }
    

def route_after_classification(state: DermaRagState) -> str:
    return state.get("route", "general_answer")


def parse_ingredient_node(state: DermaRagState) -> DermaRagState:
    request = state["request"]

    ingredient_names = split_ingredients(request.ingredient_list)
    return {
        "ingredient_names": ingredient_names,
    }

def retrieve_documents_node(state: DermaRagState) -> DermaRagState:
    request = state["request"]
    docs = retrieve_documents(request)
    return {
        "docs" : docs,
    }

def build_context_node(state: DermaRagState) -> DermaRagState:
    docs = state.get("docs", [])
    context = build_context(docs)
    return {
        "context": context,
    }


def generate_answer_node(state: DermaRagState) -> str:
    request = state["request"]
    context = state.get("context", "")
    answer = generate_answer(request, context)
    return {
        "answer": answer,
    }


def build_sources_node(state: DermaRagState) -> DermaRagState:
    docs = state.get("docs", [])
    sources = build_sources(docs)
    return {
        "sources": sources,
    }

def safety_warning_node(state: DermaRagState) -> DermaRagState:
    request = state["request"]
    warnings = state.get("warnings", [])

    answer = generate_agent_answer(
        request = request,
        route = "safety_warning",
        warnings = warnings,
    )

    return {
        "answer" : answer,
        "sources" : [],
    }

def routine_check_node(state: DermaRagState) -> DermaRagState:
    request = state["request"]
    warnings = state.get("warnings", [])

    answer = generate_agent_answer(
        request = request,
        route = "routine_check",
        warnings = warnings,
    )

    return {
        "answer" : answer,
        "sources" : [],
    }

def generate_answer_node(state: DermaRagState) -> DermaRagState:
    request = state["request"]
    warnings = state.get("warnings", [])

    answer = generate_agent_answer(
        request = request,
        route = "general_answer",
        warnings = warnings,
    )

    return {
        "answer" : answer,
        "sources" : [],
    }
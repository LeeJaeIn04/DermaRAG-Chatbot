from app.graph.state import DermaRagState
from langgraph.graph import StateGraph, END, START
from app.graph.nodes import (
    classify_intent_node,
    route_after_classification,
    parse_ingredient_node,
    retrieve_documents_node,
    build_context_node,
    generate_answer_node,
    build_sources_node,
    safety_warning_node,
    routine_check_node,
    generate_agent_answer_node,
)


def create_derma_rag_graph():
    builder = StateGraph(DermaRagState)

    builder.add_node("classify_intent", classify_intent_node)

    builder.add_node("parse_ingredients", parse_ingredient_node)
    builder.add_node("retrieve_documents", retrieve_documents_node)
    builder.add_node("build_context", build_context_node)
    builder.add_node("generate_answer", generate_answer_node)
    builder.add_node("build_sources", build_sources_node)

    builder.add_node("safety_warning", safety_warning_node)
    builder.add_node("routine_check", routine_check_node)
    builder.add_node("generate_agent_answer", generate_agent_answer_node)

    builder.add_edge(START, "classify_intent")

    builder.add_conditional_edges(
        "classify_intent",
        route_after_classification,
        
        {
            "ingredient_rag" : "parse_ingredients",
            "safety_warning" : "safety_warning",
            "routine_check": "routine_check",
            "general_answer": "generate_agent_answer",
        },
    )

    builder.add_edge("parse_ingredients", "retrieve_documents")
    builder.add_edge("retrieve_documents", "build_context")
    builder.add_edge("build_context", "generate_answer")
    builder.add_edge("generate_answer", "build_sources")
    builder.add_edge("build_sources", END)

    builder.add_edge("safety_warning", END)
    builder.add_edge("routine_check", END)
    builder.add_edge("generate_agent_answer", END)

    return builder.compile()

derma_rag_graph = create_derma_rag_graph()

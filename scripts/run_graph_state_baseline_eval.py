from typing import Any

from langsmith import Client

from app.graph.workflow import derma_rag_graph
from app.schemas import ChatRequest


DATASET_NAME = "DermaRAG Graph State Baseline v1"


def graph_state_target(
    inputs: dict[str, Any],
) -> dict[str, Any]:
    request = ChatRequest(
        question=inputs.get("question", ""),
        ingredient_list=(
            inputs.get("ingredient_list") or None
        ),
        current_routine=(
            inputs.get("current_routine") or None
        ),
    )

    final_state = derma_rag_graph.invoke(
        {"request": request},
        config={
            "run_name": "derma_rag_graph_state_eval",
            "tags": [
                "baseline-evaluation",
                "graph-state",
            ],
            "metadata": {
                "evaluation_scope": "graph_state",
                "baseline_version": "v1",
            },
        },
    )

    metadata = final_state.get("metadata", {}) or {}

    return {
        "route": final_state.get("route"),
        "answer_exists": bool(
            str(final_state.get("answer", "")).strip()
        ),
        "source_count": len(
            final_state.get("sources", []) or []
        ),
        "ingredient_count": metadata.get(
            "ingredient_count"
        ),
        "retrieved_doc_count": metadata.get(
            "retrieved_doc_count"
        ),
        "exact_match_count": metadata.get(
            "exact_match_count"
        ),
        "vector_fallback_count": metadata.get(
            "vector_fallback_count"
        ),
        "context_char_count": metadata.get(
            "context_char_count"
        ),
        "context_empty": metadata.get(
            "context_empty"
        ),
        "used_rag_context": metadata.get(
            "used_rag_context"
        ),
    }


def route_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return (
        outputs.get("route")
        == reference_outputs.get("expected_route")
    )


def ingredient_count_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return (
        outputs.get("ingredient_count")
        == reference_outputs.get(
            "expected_ingredient_count"
        )
    )


def answer_exists(
    outputs: dict[str, Any],
) -> bool:
    return outputs.get("answer_exists") is True


def retrieval_counts_consistent(
    outputs: dict[str, Any],
) -> bool:
    route = outputs.get("route")

    retrieved_count = outputs.get(
        "retrieved_doc_count"
    )
    exact_count = outputs.get(
        "exact_match_count"
    )
    vector_count = outputs.get(
        "vector_fallback_count"
    )

    if route != "ingredient_rag":
        return (
            retrieved_count is None
            and exact_count is None
            and vector_count is None
        )

    if not all(
        isinstance(value, int)
        for value in [
            retrieved_count,
            exact_count,
            vector_count,
        ]
    ):
        return False

    return (
        exact_count + vector_count
        == retrieved_count
    )


def context_state_consistent(
    outputs: dict[str, Any],
) -> bool:
    route = outputs.get("route")

    context_empty = outputs.get("context_empty")
    context_char_count = outputs.get(
        "context_char_count"
    )
    used_rag_context = outputs.get(
        "used_rag_context"
    )

    if route != "ingredient_rag":
        return (
            context_empty is None
            and context_char_count is None
            and used_rag_context is False
        )

    if context_empty is True:
        return (
            context_char_count == 0
            and used_rag_context is False
        )

    if context_empty is False:
        return (
            isinstance(context_char_count, int)
            and context_char_count > 0
            and used_rag_context is True
        )

    return False


def rag_usage_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return (
        outputs.get("used_rag_context")
        == reference_outputs.get(
            "expected_uses_rag"
        )
    )


def graph_state_case_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return all(
        [
            route_correct(
                outputs,
                reference_outputs,
            ),
            ingredient_count_correct(
                outputs,
                reference_outputs,
            ),
            answer_exists(outputs),
            retrieval_counts_consistent(outputs),
            context_state_consistent(outputs),
            rag_usage_correct(
                outputs,
                reference_outputs,
            ),
        ]
    )


def main() -> None:
    client = Client()

    results = client.evaluate(
        graph_state_target,
        data=DATASET_NAME,
        evaluators=[
            route_correct,
            ingredient_count_correct,
            answer_exists,
            retrieval_counts_consistent,
            context_state_consistent,
            rag_usage_correct,
            graph_state_case_correct,
        ],
        experiment_prefix=(
            "derma-rag-graph-state-baseline-v1"
        ),
        metadata={
            "evaluation_scope": "graph_state",
            "uses_llm": True,
            "baseline_version": "v1",
        },
        max_concurrency=1,
    )

    print(results)


if __name__ == "__main__":
    main()
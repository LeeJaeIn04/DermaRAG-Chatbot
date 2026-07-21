from typing import Any

from langsmith import Client

from app.graph.nodes import classify_intent_node
from app.schemas import ChatRequest


DATASET_NAME = "DermaRAG Route Baseline v1"


def route_target(inputs: dict[str, Any]) -> dict[str, Any]:
    request = ChatRequest(
        question=inputs.get("question", ""),
        ingredient_list=(
            inputs.get("ingredient_list") or None
        ),
        current_routine=(
            inputs.get("current_routine") or None
        ),
    )

    result = classify_intent_node(
        {
            "request": request,
        }
    )

    warnings = result.get("warnings", [])

    return {
        "route": result.get("route"),
        "warnings": warnings,
        "has_warning": bool(warnings),
    }


def route_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return (
        outputs.get("route")
        == reference_outputs.get("expected_route")
    )


def warning_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return (
        outputs.get("has_warning")
        == reference_outputs.get(
            "expected_has_warning"
        )
    )


def route_and_warning_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    route_matches = (
        outputs.get("route")
        == reference_outputs.get("expected_route")
    )

    warning_matches = (
        outputs.get("has_warning")
        == reference_outputs.get(
            "expected_has_warning"
        )
    )

    return route_matches and warning_matches


def main() -> None:
    client = Client()

    results = client.evaluate(
        route_target,
        data=DATASET_NAME,
        evaluators=[
            route_correct,
            warning_correct,
            route_and_warning_correct,
        ],
        experiment_prefix=(
            "derma-rag-route-baseline-v1"
        ),
        metadata={
            "evaluation_scope": "route",
            "uses_llm": False,
            "baseline_version": "v1",
        },
    )

    print(results)


if __name__ == "__main__":
    main()
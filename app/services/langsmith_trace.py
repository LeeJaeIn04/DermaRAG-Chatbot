from typing import Any
from langsmith import get_current_run_tree, traceable
from app.graph.workflow import derma_rag_graph
from app.schemas import ChatRequest

@traceable(
    name="derma_rag_chat",
    run_type="chain",
    tags=["derma-rag", "langgraph"],
)
def invoke_derma_rag(
    request: ChatRequest,
) -> dict[str, Any]:
    final_state = derma_rag_graph.invoke(
        {"request": request},
        config={
            "run_name": "derma_rag_graph",
            "tags": ["graph-run"],
            "metadata": {
                "environment": "development",
                "api_endpoint": "/chat",
            },
        },
    )

    run = get_current_run_tree()

    if run is not None :
        run.add_metadata(
            final_state.get("metadata", {})
        )
    return final_state
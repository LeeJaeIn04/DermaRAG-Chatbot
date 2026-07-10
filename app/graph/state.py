from typing import Any, TypedDict, Literal
from app.rag_chain import ChatRequest, Source

DermaRoute = Literal[
    "ingredient_rag",
    "safety_warning",
    "routine_check",
    "general_answer",
]

class DermaRagState(TypedDict, total=False):
    request: ChatRequest
    ingredient_names: list[str]
    docs: list[Any]
    context: str
    answer: str
    sources: list[Source]
    
    route: DermaRoute
    warnings: list[str]

from typing import Any, Iterable

def merge_metadata(
        current: dict[str, Any] | None,
        **updates: Any,
) -> dict[str, Any]:
    metadata = dict(current or {})

    for key, value in updates.items():
        if value is not None :
            metadata[key] = value
    
    return metadata

def count_retrieval_types(
        docs: Iterable[Any],
) -> dict[str, int]:
    exact_match_count = 0
    vector_fallback_count = 0

    for doc in docs:
        doc_metadata = getattr(doc, "metadata", {}) or {}
        retrieval_type = doc_metadata.get("retrieval_type")

        if retrieval_type == "exact_match":
            exact_match_count += 1
        elif retrieval_type in {
            "vector_search",
            "vector_fallback",
        }:
            vector_fallback_count += 1
        
    return {
            "exact_match_count": exact_match_count,
            "vector_fallback_count": vector_fallback_count,
    }
    
def merge_warnings(
        current: list[str] | None,
        new_warnings: list[str] | None,
) -> list[str]:
    merged: list[str] = []

    for warning in [
        *(current or []),
        *(new_warnings or []),
    ]:
        if warning and warning not in merged :
            merged.append(warning)
        
    return merged
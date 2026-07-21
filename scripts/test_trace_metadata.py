from langchain_core.documents import Document

from app.trace_metadata import (
    count_retrieval_types,
    merge_metadata,
)


def test_merge_metadata() -> None:
    current = {
        "route": "ingredient_rag",
        "warnings": [],
    }

    result = merge_metadata(
        current,
        ingredient_count=3,
    )

    assert result["route"] == "ingredient_rag"
    assert result["warnings"] == []
    assert result["ingredient_count"] == 3


def test_merge_metadata_keeps_zero_and_false() -> None:
    result = merge_metadata(
        None,
        retrieved_doc_count=0,
        context_empty=True,
        used_rag_context=False,
    )

    assert result["retrieved_doc_count"] == 0
    assert result["context_empty"] is True
    assert result["used_rag_context"] is False


def test_count_retrieval_types() -> None:
    docs = [
        Document(
            page_content="정제수",
            metadata={
                "retrieval_type": "exact_match",
            },
        ),
        Document(
            page_content="나이아신아마이드",
            metadata={
                "retrieval_type": "exact_match",
            },
        ),
        Document(
            page_content="성분 후보",
            metadata={
                "retrieval_type": "vector_fallback",
            },
        ),
    ]

    result = count_retrieval_types(docs)

    assert result["exact_match_count"] == 2
    assert result["vector_fallback_count"] == 1


if __name__ == "__main__":
    test_merge_metadata()
    test_merge_metadata_keeps_zero_and_false()
    test_count_retrieval_types()

    print("trace metadata tests passed")
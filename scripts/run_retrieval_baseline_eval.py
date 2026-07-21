from typing import Any

from langsmith import Client

from app.retriever import search_documents


DATASET_NAME = "DermaRAG Retrieval Baseline v1"


def get_document_name(doc: Any) -> str:
    metadata = getattr(doc, "metadata", {}) or {}

    return str(
        metadata.get("ingredient_kor_name")
        or metadata.get("kor_name")
        or metadata.get("name")
        or ""
    ).strip()


def retrieval_target(
    inputs: dict[str, Any],
) -> dict[str, Any]:
    query = str(inputs["query"])
    search_k = int(inputs.get("search_k", 8))

    docs = search_documents(
        query=query,
        search_k=search_k,
    )

    document_names = [
        get_document_name(doc)
        for doc in docs
    ]

    retrieval_types = [
        (getattr(doc, "metadata", {}) or {}).get(
            "retrieval_type"
        )
        for doc in docs
    ]

    return {
        "query": query,
        "document_count": len(docs),
        "document_names": document_names,
        "retrieval_types": retrieval_types,
    }


def retrieval_type_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected = reference_outputs.get(
        "expected_retrieval_type"
    )

    retrieval_types = outputs.get(
        "retrieval_types",
        [],
    )

    return bool(retrieval_types) and all(
        retrieval_type == expected
        for retrieval_type in retrieval_types
    )


def expected_name_found(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_name = reference_outputs.get(
        "expected_name"
    )

    document_names = outputs.get(
        "document_names",
        [],
    )

    return expected_name in document_names


def forbidden_names_absent(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    forbidden_names = reference_outputs.get(
        "forbidden_names",
        [],
    )

    document_names = outputs.get(
        "document_names",
        [],
    )

    return not any(
        forbidden_name in document_names
        for forbidden_name in forbidden_names
    )


def retrieval_case_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return (
        retrieval_type_correct(
            outputs,
            reference_outputs,
        )
        and expected_name_found(
            outputs,
            reference_outputs,
        )
        and forbidden_names_absent(
            outputs,
            reference_outputs,
        )
    )


def main() -> None:
    client = Client()

    results = client.evaluate(
        retrieval_target,
        data=DATASET_NAME,
        evaluators=[
            retrieval_type_correct,
            expected_name_found,
            forbidden_names_absent,
            retrieval_case_correct,
        ],
        experiment_prefix=(
            "derma-rag-retrieval-baseline-v1"
        ),
        metadata={
            "evaluation_scope": "retrieval",
            "uses_llm": False,
            "baseline_version": "v1",
        },
    )

    print(results)


if __name__ == "__main__":
    main()
from app.langsmith_client import (
    create_langsmith_client,
    run_with_langsmith_auth_help,
)


DATASET_NAME = "DermaRAG Retrieval Baseline v1"


def main() -> None:
    client = create_langsmith_client()

    existing = list(
        client.list_datasets(
            dataset_name=DATASET_NAME,
        )
    )

    if existing:
        print(f"이미 dataset이 존재합니다: {DATASET_NAME}")
        return

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "DermaRAG retriever의 exact match 정확성과 "
            "vector fallback 동작을 검증하는 baseline dataset."
        ),
    )

    examples = [
        {
            "inputs": {
                "query": "프로판다이올",
                "search_k": 8,
            },
            "outputs": {
                "expected_retrieval_type": "exact_match",
                "expected_name": "프로판다이올",
                "forbidden_names": [
                    "프로판",
                    "메틸프로판다이올",
                    "멘톡시프로판다이올",
                ],
            },
            "metadata": {
                "case": "propanediol_exact",
                "category": "substring_regression",
            },
        },
        {
            "inputs": {
                "query": "부틸렌글라이콜",
                "search_k": 8,
            },
            "outputs": {
                "expected_retrieval_type": "exact_match",
                "expected_name": "부틸렌글라이콜",
                "forbidden_names": [
                    "글라이콜",
                ],
            },
            "metadata": {
                "case": "butylene_glycol_exact",
                "category": "substring_regression",
            },
        },
        {
            "inputs": {
                "query": "비닐다이메티콘",
                "search_k": 8,
            },
            "outputs": {
                "expected_retrieval_type": "exact_match",
                "expected_name": "비닐다이메티콘",
                "forbidden_names": [
                    "메티콘",
                ],
            },
            "metadata": {
                "case": "vinyl_dimethicone_exact",
                "category": "substring_regression",
            },
        },
        {
            "inputs": {
                "query": "나이아신아마이드",
                "search_k": 8,
            },
            "outputs": {
                "expected_retrieval_type": "exact_match",
                "expected_name": "나이아신아마이드",
                "forbidden_names": [],
            },
            "metadata": {
                "case": "niacinamide_korean",
                "category": "korean_exact",
            },
        },
        {
            "inputs": {
                "query": "Niacinamide",
                "search_k": 8,
            },
            "outputs": {
                "expected_retrieval_type": "exact_match",
                "expected_name": "나이아신아마이드",
                "forbidden_names": [],
            },
            "metadata": {
                "case": "niacinamide_english",
                "category": "english_exact",
            },
        },
        {
            "inputs": {
                "query": "정제수",
                "search_k": 8,
            },
            "outputs": {
                "expected_retrieval_type": "exact_match",
                "expected_name": "정제수",
                "forbidden_names": [],
            },
            "metadata": {
                "case": "water_exact",
                "category": "korean_exact",
            },
        },
    ]

    client.create_examples(
        dataset_id=dataset.id,
        examples=examples,
    )

    print(f"Dataset 생성 완료: {DATASET_NAME}")
    print(f"Example 개수: {len(examples)}")


if __name__ == "__main__":
    run_with_langsmith_auth_help(main)

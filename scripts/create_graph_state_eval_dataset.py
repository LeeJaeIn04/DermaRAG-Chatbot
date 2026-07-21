from langsmith import Client


DATASET_NAME = "DermaRAG Graph State Baseline v1"


def main() -> None:
    client = Client()

    existing_datasets = list(
        client.list_datasets(
            dataset_name=DATASET_NAME,
        )
    )

    if existing_datasets:
        print(f"이미 dataset이 존재합니다: {DATASET_NAME}")
        print("중복 생성을 방지하기 위해 종료합니다.")
        return

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "DermaRAG 전체 LangGraph 실행 후 route, retrieval, "
            "context, metadata 상태의 일관성을 검증하는 baseline."
        ),
    )

    examples = [
        {
            "inputs": {
                "question": "이 전성분을 분석해주세요.",
                "ingredient_list": (
                    "정제수, 글리세린, 나이아신아마이드"
                ),
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "ingredient_rag",
                "expected_ingredient_count": 3,
                "expected_uses_rag": True,
            },
            "metadata": {
                "case": "ingredient_exact_matches",
                "category": "ingredient_rag",
            },
        },
        {
            "inputs": {
                "question": (
                    "민감성 피부가 사용해도 괜찮은지 "
                    "성분을 분석해주세요."
                ),
                "ingredient_list": (
                    "프로판다이올, 부틸렌글라이콜"
                ),
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "ingredient_rag",
                "expected_ingredient_count": 2,
                "expected_uses_rag": True,
            },
            "metadata": {
                "case": "substring_regression_ingredients",
                "category": "ingredient_rag",
            },
        },
        {
            "inputs": {
                "question": (
                    "화장품 사용 후 얼굴이 붓고 "
                    "숨쉬기가 어려워요."
                ),
                "ingredient_list": "",
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "safety_warning",
                "expected_ingredient_count": None,
                "expected_uses_rag": False,
            },
            "metadata": {
                "case": "safety_non_rag",
                "category": "non_rag",
            },
        },
        {
            "inputs": {
                "question": (
                    "레티놀과 BHA를 같이 사용해도 되나요?"
                ),
                "ingredient_list": "",
                "current_routine": (
                    "저녁에 레티놀 세럼을 사용합니다."
                ),
            },
            "outputs": {
                "expected_route": "routine_check",
                "expected_ingredient_count": None,
                "expected_uses_rag": False,
            },
            "metadata": {
                "case": "routine_non_rag",
                "category": "non_rag",
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
    main()
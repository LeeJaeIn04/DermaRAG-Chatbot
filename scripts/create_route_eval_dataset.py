from app.langsmith_client import (
    create_langsmith_client,
    run_with_langsmith_auth_help,
)


DATASET_NAME = "DermaRAG Route Baseline v1"


def main() -> None:
    client = create_langsmith_client()

    existing_datasets = list(
        client.list_datasets(
            dataset_name=DATASET_NAME,
        )
    )

    if existing_datasets:
        print(
            f"이미 dataset이 존재합니다: {DATASET_NAME}"
        )
        print(
            "중복 생성을 방지하기 위해 종료합니다."
        )
        return

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "DermaRAG의 rule-based route 분류 baseline. "
            "Gemini를 호출하지 않고 classify_intent_node의 "
            "route와 warnings를 평가한다."
        ),
    )

    examples = [
        {
            "inputs": {
                "question": (
                    "화장품을 바른 뒤 얼굴이 붓고 "
                    "숨쉬기가 어려워요."
                ),
                "ingredient_list": "",
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "safety_warning",
                "expected_has_warning": True,
            },
            "metadata": {
                "case": "danger_breathing",
                "category": "safety",
            },
        },
        {
            "inputs": {
                "question": (
                    "크림을 바른 뒤 진물이 나고 "
                    "물집이 생겼어요."
                ),
                "ingredient_list": "",
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "safety_warning",
                "expected_has_warning": True,
            },
            "metadata": {
                "case": "danger_blister",
                "category": "safety",
            },
        },
        {
            "inputs": {
                "question": (
                    "이 제품의 성분을 분석해주세요."
                ),
                "ingredient_list": (
                    "정제수, 글리세린, "
                    "나이아신아마이드"
                ),
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "ingredient_rag",
                "expected_has_warning": False,
            },
            "metadata": {
                "case": "ingredient_list_present",
                "category": "ingredient",
            },
        },
        {
            "inputs": {
                "question": (
                    "민감성 피부가 사용해도 괜찮나요?"
                ),
                "ingredient_list": (
                    "프로판다이올, 부틸렌글라이콜"
                ),
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "ingredient_rag",
                "expected_has_warning": False,
            },
            "metadata": {
                "case": "ingredient_sensitive_skin",
                "category": "ingredient",
            },
        },
        {
            "inputs": {
                "question": (
                    "레티놀과 BHA를 같이 써도 되나요?"
                ),
                "ingredient_list": "",
                "current_routine": (
                    "저녁에 레티놀 세럼을 사용합니다."
                ),
            },
            "outputs": {
                "expected_route": "routine_check",
                "expected_has_warning": False,
            },
            "metadata": {
                "case": "retinol_bha",
                "category": "routine",
            },
        },
        {
            "inputs": {
                "question": (
                    "비타민C 세럼과 AHA 토너를 "
                    "함께 써도 되나요?"
                ),
                "ingredient_list": "",
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "routine_check",
                "expected_has_warning": False,
            },
            "metadata": {
                "case": "vitamin_c_aha",
                "category": "routine",
            },
        },
        {
            "inputs": {
                "question": (
                    "화장품 성분표는 어디서 확인할 수 있나요?"
                ),
                "ingredient_list": "",
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "general_answer",
                "expected_has_warning": False,
            },
            "metadata": {
                "case": "general_information",
                "category": "general",
            },
        },
        {
            "inputs": {
                "question": (
                    "피부 타입은 어떻게 구분하나요?"
                ),
                "ingredient_list": "",
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "general_answer",
                "expected_has_warning": False,
            },
            "metadata": {
                "case": "general_skin_type",
                "category": "general",
            },
        },
        {
            "inputs": {
                "question": (
                    "레티놀을 사용했는데 얼굴이 붓고 "
                    "두드러기가 생겼어요."
                ),
                "ingredient_list": "",
                "current_routine": "레티놀 사용",
            },
            "outputs": {
                "expected_route": "safety_warning",
                "expected_has_warning": True,
            },
            "metadata": {
                "case": "safety_priority_over_routine",
                "category": "priority",
            },
        },
        {
            "inputs": {
                "question": (
                    "이 전성분을 분석해주세요. "
                    "사용 후 물집도 생겼어요."
                ),
                "ingredient_list": (
                    "정제수, 글리세린, 향료"
                ),
                "current_routine": "",
            },
            "outputs": {
                "expected_route": "safety_warning",
                "expected_has_warning": True,
            },
            "metadata": {
                "case": "safety_priority_over_ingredient",
                "category": "priority",
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

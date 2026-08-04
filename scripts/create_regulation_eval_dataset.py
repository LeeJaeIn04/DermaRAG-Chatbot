from app.langsmith_client import (
    create_langsmith_client,
    run_with_langsmith_auth_help,
)


DATASET_NAME = "DermaRAG Regulation Baseline v1"


def main() -> None:
    client = create_langsmith_client()

    existing_datasets = list(
        client.list_datasets(
            dataset_name=DATASET_NAME,
        )
    )

    if existing_datasets:
        print(
            f"이미 dataset이 존재합니다: "
            f"{DATASET_NAME}"
        )
        print(
            "중복 생성을 방지하기 위해 종료합니다."
        )
        return

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "DermaRAG 식약처 화장품 규제 Repository의 "
            "exact match, 규제 유형, 판정 근거와 "
            "공식 출처 전달을 검증하는 baseline dataset."
        ),
    )

    examples = [
        {
            "inputs": {
                "ingredients": [
                    "글루타랄(펜탄-1,5-디알)",
                ],
            },
            "outputs": {
                "expected_match_count": 1,
                "expected_names": [
                    "글루타랄(펜탄-1,5-디알)",
                ],
                "expected_regulation_types": [
                    "restricted",
                ],
                "expected_source_id": (
                    "mfds-cosmetics-safety-2026-19"
                ),
                "expected_has_decision_basis": True,
            },
            "metadata": {
                "case": "restricted_korean_name",
                "category": "restricted",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    (
                        "(+/-)-테트라하이드로풀푸릴-(R)-2-"
                        "[4-(6-클로로퀴노살린-2-일옥시)"
                        "페닐옥시]프로피오네이트"
                    ),
                ],
            },
            "outputs": {
                "expected_match_count": 1,
                "expected_names": [
                    (
                        "(+/-)-테트라하이드로풀푸릴-(R)-2-"
                        "[4-(6-클로로퀴노살린-2-일옥시)"
                        "페닐옥시]프로피오네이트"
                    ),
                ],
                "expected_regulation_types": [
                    "prohibited",
                ],
                "expected_source_id": (
                    "mfds-cosmetics-safety-2026-19"
                ),
                "expected_has_decision_basis": True,
            },
            "metadata": {
                "case": "prohibited_korean_name",
                "category": "prohibited",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "111-30-8",
                ],
            },
            "outputs": {
                "expected_match_count": 1,
                "expected_names": [
                    "글루타랄(펜탄-1,5-디알)",
                ],
                "expected_regulation_types": [
                    "restricted",
                ],
                "expected_source_id": (
                    "mfds-cosmetics-safety-2026-19"
                ),
                "expected_has_decision_basis": True,
            },
            "metadata": {
                "case": "restricted_cas_match",
                "category": "cas_exact",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "정제수",
                    "글리세린",
                    "나이아신아마이드",
                ],
            },
            "outputs": {
                "expected_match_count": 0,
                "expected_names": [],
                "expected_regulation_types": [],
                "expected_source_id": (
                    "mfds-cosmetics-safety-2026-19"
                ),
                "expected_has_decision_basis": True,
            },
            "metadata": {
                "case": "normal_ingredients_no_match",
                "category": "negative",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "정제수",
                    "글루타랄(펜탄-1,5-디알)",
                    "글리세린",
                ],
            },
            "outputs": {
                "expected_match_count": 1,
                "expected_names": [
                    "글루타랄(펜탄-1,5-디알)",
                ],
                "expected_regulation_types": [
                    "restricted",
                ],
                "expected_source_id": (
                    "mfds-cosmetics-safety-2026-19"
                ),
                "expected_has_decision_basis": True,
            },
            "metadata": {
                "case": "mixed_normal_and_restricted",
                "category": "mixed",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "글루타랄",
                ],
            },
            "outputs": {
                "expected_match_count": 0,
                "expected_names": [],
                "expected_regulation_types": [],
                "expected_source_id": (
                    "mfds-cosmetics-safety-2026-19"
                ),
                "expected_has_decision_basis": True,
            },
            "metadata": {
                "case": "partial_name_false_positive",
                "category": "substring_regression",
            },
        },
    ]

    client.create_examples(
        dataset_id=dataset.id,
        examples=examples,
    )

    print(
        f"Dataset 생성 완료: {DATASET_NAME}"
    )
    print(
        f"Example 개수: {len(examples)}"
    )


if __name__ == "__main__":
    run_with_langsmith_auth_help(main)

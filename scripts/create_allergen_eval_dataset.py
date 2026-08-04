from app.langsmith_client import (
    create_langsmith_client,
    run_with_langsmith_auth_help,
)


DATASET_NAME = "DermaRAG Allergen Baseline v1"

SOURCE_ID = "mfds-fragrance-allergens-v2-2019"
RINSE_OFF_THRESHOLD = "0.01% 초과"
LEAVE_ON_THRESHOLD = "0.001% 초과"


def expected_outputs(
    names: list[str],
    match_types: list[str],
) -> dict[str, object]:
    match_count = len(names)

    return {
        "expected_match_count": match_count,
        "expected_names": names,
        "expected_match_types": match_types,
        "expected_source_id": SOURCE_ID,
        "expected_rinse_off_thresholds": [
            RINSE_OFF_THRESHOLD
        ] * match_count,
        "expected_leave_on_thresholds": [
            LEAVE_ON_THRESHOLD
        ] * match_count,
    }


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
            "DermaRAG 식약처 향료 알레르기 표시 대상 "
            "Repository의 exact match, false positive 방지, "
            "표시 기준 threshold와 공식 출처 전달을 검증하는 "
            "baseline dataset."
        ),
    )

    examples = [
        {
            "inputs": {
                "ingredients": [
                    "리모넨",
                ],
            },
            "outputs": expected_outputs(
                ["리모넨"],
                ["ingredient_kor_name"],
            ),
            "metadata": {
                "case": "limonene_korean_name",
                "category": "korean_exact",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "Limonene",
                ],
            },
            "outputs": expected_outputs([], []),
            "metadata": {
                "case": "english_name_not_in_source_data",
                "category": "unsupported_english_name",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "78-70-6",
                ],
            },
            "outputs": expected_outputs(
                ["리날룰"],
                ["cas_no"],
            ),
            "metadata": {
                "case": "linalool_cas_number",
                "category": "cas_exact",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "리모넨",
                    "리날룰",
                    "벤질알코올",
                ],
            },
            "outputs": expected_outputs(
                [
                    "리모넨",
                    "리날룰",
                    "벤질알코올",
                ],
                [
                    "ingredient_kor_name",
                    "ingredient_kor_name",
                    "ingredient_kor_name",
                ],
            ),
            "metadata": {
                "case": "multiple_allergens",
                "category": "multiple",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "정제수",
                    "글리세린",
                ],
            },
            "outputs": expected_outputs([], []),
            "metadata": {
                "case": "normal_ingredients_no_match",
                "category": "negative",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "정제수",
                    "리모넨",
                    "글리세린",
                ],
            },
            "outputs": expected_outputs(
                ["리모넨"],
                ["ingredient_kor_name"],
            ),
            "metadata": {
                "case": "mixed_normal_and_allergen",
                "category": "mixed",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "리모",
                    "알코올",
                ],
            },
            "outputs": expected_outputs([], []),
            "metadata": {
                "case": "partial_names_false_positive",
                "category": "substring_regression",
            },
        },
        {
            "inputs": {
                "ingredients": [
                    "알파–아이소메틸아이오논",
                ],
            },
            "outputs": expected_outputs(
                ["알파-아이소메틸아이오논"],
                ["ingredient_kor_name"],
            ),
            "metadata": {
                "case": "normalized_hyphen_exact_match",
                "category": "normalized_exact",
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

from typing import Any

from app.langsmith_client import (
    create_langsmith_client,
    run_with_langsmith_auth_help,
)


DATASET_NAME = "DermaRAG Product Analysis Baseline v1"

REGULATION_SOURCE_ID = "mfds-cosmetics-safety-2026-19"
ALLERGEN_SOURCE_ID = "mfds-fragrance-allergens-v2-2019"
RINSE_OFF_THRESHOLD = "0.01% 초과"
LEAVE_ON_THRESHOLD = "0.001% 초과"

RESTRICTED_NAME = "글루타랄(펜탄-1,5-디알)"
PROHIBITED_NAME = "2-니트로프로판"


def restricted_regulation() -> dict[str, Any]:
    return {
        "matched_name": RESTRICTED_NAME,
        "regulation_type": "restricted",
        "max_concentration": "0.1%",
        "product_scope": None,
        "use_conditions": (
            "에어로졸(스프레이에 한함) 제품에는 사용금지"
        ),
        "warning_text": None,
        "source_id": REGULATION_SOURCE_ID,
    }


def prohibited_regulation() -> dict[str, Any]:
    return {
        "matched_name": PROHIBITED_NAME,
        "regulation_type": "prohibited",
        "max_concentration": None,
        "product_scope": "all_cosmetics",
        "use_conditions": "화장품에 사용할 수 없음",
        "warning_text": None,
        "source_id": REGULATION_SOURCE_ID,
    }


def expected_allergen(
    ingredient_name: str,
) -> dict[str, str]:
    return {
        "ingredient_kor_name": ingredient_name,
        "source_id": ALLERGEN_SOURCE_ID,
    }


def expected_outputs(
    *,
    ingredient_count: int,
    regulations: list[dict[str, Any]],
    allergens: list[dict[str, str]],
) -> dict[str, Any]:
    empty_fields = []
    if not regulations:
        empty_fields.append("regulations")
    if not allergens:
        empty_fields.append("allergens")

    return {
        "expected_status_code": 200,
        "expected_ingredient_count": ingredient_count,
        "expected_regulation_count": len(regulations),
        "expected_allergen_count": len(allergens),
        "expected_regulations": regulations,
        "expected_allergens": allergens,
        "expected_allergen_thresholds": [
            {
                "rinse_off_threshold": RINSE_OFF_THRESHOLD,
                "leave_on_threshold": LEAVE_ON_THRESHOLD,
            }
            for _ in allergens
        ],
        "expected_empty_fields": empty_fields,
    }


def build_examples() -> list[dict[str, Any]]:
    return [
        {
            "inputs": {
                "case_id": "restricted_only",
                "ingredients": [RESTRICTED_NAME],
            },
            "outputs": expected_outputs(
                ingredient_count=1,
                regulations=[restricted_regulation()],
                allergens=[],
            ),
            "metadata": {
                "case": "restricted_regulation_only",
                "category": "regulation_restricted",
            },
        },
        {
            "inputs": {
                "case_id": "prohibited_only",
                "ingredients": [PROHIBITED_NAME],
            },
            "outputs": expected_outputs(
                ingredient_count=1,
                regulations=[prohibited_regulation()],
                allergens=[],
            ),
            "metadata": {
                "case": "prohibited_regulation_only",
                "category": "regulation_prohibited",
            },
        },
        {
            "inputs": {
                "case_id": "allergen_only",
                "ingredients": ["리모넨"],
            },
            "outputs": expected_outputs(
                ingredient_count=1,
                regulations=[],
                allergens=[
                    expected_allergen("리모넨")
                ],
            ),
            "metadata": {
                "case": "fragrance_allergen_only",
                "category": "allergen",
            },
        },
        {
            "inputs": {
                "case_id": "regulation_and_allergen",
                "ingredients": [
                    RESTRICTED_NAME,
                    "리모넨",
                ],
            },
            "outputs": expected_outputs(
                ingredient_count=2,
                regulations=[restricted_regulation()],
                allergens=[
                    expected_allergen("리모넨")
                ],
            ),
            "metadata": {
                "case": "regulation_and_allergen",
                "category": "combined",
            },
        },
        {
            "inputs": {
                "case_id": "no_matches",
                "ingredients": [
                    "정제수",
                    "글리세린",
                ],
            },
            "outputs": expected_outputs(
                ingredient_count=2,
                regulations=[],
                allergens=[],
            ),
            "metadata": {
                "case": "empty_regulation_and_allergen_arrays",
                "category": "negative",
            },
        },
        {
            "inputs": {
                "case_id": "mixed_ingredients",
                "ingredients": [
                    "정제수",
                    PROHIBITED_NAME,
                    "리날룰",
                    "글리세린",
                ],
            },
            "outputs": expected_outputs(
                ingredient_count=4,
                regulations=[prohibited_regulation()],
                allergens=[
                    expected_allergen("리날룰")
                ],
            ),
            "metadata": {
                "case": "mixed_normal_and_target_ingredients",
                "category": "mixed",
            },
        },
        {
            "inputs": {
                "case_id": "multiple_matches",
                "ingredients": [
                    RESTRICTED_NAME,
                    PROHIBITED_NAME,
                    "리모넨",
                    "리날룰",
                ],
            },
            "outputs": expected_outputs(
                ingredient_count=4,
                regulations=[
                    restricted_regulation(),
                    prohibited_regulation(),
                ],
                allergens=[
                    expected_allergen("리모넨"),
                    expected_allergen("리날룰"),
                ],
            ),
            "metadata": {
                "case": "multiple_regulations_and_allergens",
                "category": "multiple",
            },
        },
    ]


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
            "DermaRAG /products/analyze API의 Pydantic 응답 계약, "
            "규제·알레르겐 count와 배열 일관성, 판정 근거, "
            "threshold 및 공식 출처 전달을 검증하는 baseline dataset."
        ),
    )

    examples = build_examples()

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

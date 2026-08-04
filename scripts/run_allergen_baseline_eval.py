import re
from collections import Counter
from typing import Any

from app.allergens.mfds_repository import (
    get_mfds_fragrance_allergen_repository,
)
from app.langsmith_client import (
    create_langsmith_client,
    run_with_langsmith_auth_help,
)


DATASET_NAME = "DermaRAG Allergen Baseline v1"

CAS_PATTERN = re.compile(
    r"^\d{2,7}-\d{2}-\d$"
)


def allergen_target(
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Run the Repository's name or CAS exact-match policy."""

    repository = (
        get_mfds_fragrance_allergen_repository()
    )

    ingredients = [
        str(ingredient).strip()
        for ingredient in inputs.get(
            "ingredients",
            [],
        )
        if str(ingredient).strip()
    ]

    matches = []

    for ingredient in ingredients:
        if CAS_PATTERN.fullmatch(ingredient):
            current_matches = (
                repository.find_by_cas_no(
                    ingredient
                )
            )
        else:
            current_matches = (
                repository.find_by_name(
                    ingredient
                )
            )

        matches.extend(current_matches)

    return {
        "ingredients": ingredients,
        "match_count": len(matches),
        "matched_names": [
            match.allergen.ingredient_kor_name
            for match in matches
        ],
        "match_types": [
            match.match_type
            for match in matches
        ],
        "source_ids": [
            match.allergen.source_id
            for match in matches
        ],
        "rinse_off_thresholds": [
            match.allergen.rinse_off_threshold
            for match in matches
        ],
        "leave_on_thresholds": [
            match.allergen.leave_on_threshold
            for match in matches
        ],
        "cas_numbers": [
            match.allergen.cas_numbers
            for match in matches
        ],
    }


def match_count_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return int(
        outputs.get("match_count", 0)
    ) == int(
        reference_outputs.get(
            "expected_match_count",
            0,
        )
    )


def expected_names_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return Counter(
        outputs.get("matched_names", [])
    ) == Counter(
        reference_outputs.get(
            "expected_names",
            [],
        )
    )


def match_types_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return Counter(
        outputs.get("match_types", [])
    ) == Counter(
        reference_outputs.get(
            "expected_match_types",
            [],
        )
    )


def source_id_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    source_ids = outputs.get(
        "source_ids",
        [],
    )

    if not source_ids:
        return True

    expected_source_id = (
        reference_outputs.get(
            "expected_source_id"
        )
    )

    return all(
        source_id == expected_source_id
        for source_id in source_ids
    )


def thresholds_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    rinse_off_correct = Counter(
        outputs.get(
            "rinse_off_thresholds",
            [],
        )
    ) == Counter(
        reference_outputs.get(
            "expected_rinse_off_thresholds",
            [],
        )
    )

    leave_on_correct = Counter(
        outputs.get(
            "leave_on_thresholds",
            [],
        )
    ) == Counter(
        reference_outputs.get(
            "expected_leave_on_thresholds",
            [],
        )
    )

    return (
        rinse_off_correct
        and leave_on_correct
    )


def exact_match_type_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    del reference_outputs

    allowed_match_types = {
        "ingredient_kor_name",
        "ingredient_eng_name",
        "inci_name",
        "alias",
        "cas_no",
    }

    return all(
        match_type in allowed_match_types
        for match_type in outputs.get(
            "match_types",
            [],
        )
    )


def allergen_case_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    return (
        match_count_correct(
            outputs,
            reference_outputs,
        )
        and expected_names_correct(
            outputs,
            reference_outputs,
        )
        and match_types_correct(
            outputs,
            reference_outputs,
        )
        and source_id_correct(
            outputs,
            reference_outputs,
        )
        and thresholds_correct(
            outputs,
            reference_outputs,
        )
        and exact_match_type_correct(
            outputs,
            reference_outputs,
        )
    )


def run_evaluation() -> None:
    client = create_langsmith_client()

    results = client.evaluate(
        allergen_target,
        data=DATASET_NAME,
        evaluators=[
            match_count_correct,
            expected_names_correct,
            match_types_correct,
            source_id_correct,
            thresholds_correct,
            exact_match_type_correct,
            allergen_case_correct,
        ],
        experiment_prefix=(
            "derma-rag-allergen-baseline-v1"
        ),
        metadata={
            "evaluation_scope": (
                "mfds_fragrance_allergen"
            ),
            "uses_llm": False,
            "baseline_version": "v1",
            "matching_policy": (
                "exact_match_only"
            ),
        },
    )

    print(results)


def main() -> None:
    run_with_langsmith_auth_help(
        run_evaluation
    )


if __name__ == "__main__":
    main()

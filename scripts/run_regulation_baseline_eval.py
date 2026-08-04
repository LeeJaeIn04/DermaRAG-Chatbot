import re
from typing import Any

from app.langsmith_client import (
    create_langsmith_client,
    run_with_langsmith_auth_help,
)
from app.safety.mfds_repository import (
    get_mfds_regulation_repository,
)


DATASET_NAME = "DermaRAG Regulation Baseline v1"

CAS_PATTERN = re.compile(
    r"^\d{2,7}-\d{2}-\d$"
)


def regulation_target(
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """
    평가 입력에 포함된 성분을 식약처 규제 Repository와
    비교하고 평가 가능한 구조로 변환한다.

    일반 성분명은 이름 exact match를 사용하고,
    CAS 번호 형태의 입력은 CAS exact match를 사용한다.
    """
    repository = (
        get_mfds_regulation_repository()
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

    matched_names = [
        match.regulation.ingredient_kor_name
        for match in matches
    ]

    regulation_types = [
        match.regulation.regulation_type
        for match in matches
    ]

    source_ids = [
        match.regulation.source_id
        for match in matches
    ]

    match_types = [
        match.match_type
        for match in matches
    ]

    decision_basis_flags = [
        has_decision_basis(
            match.regulation
        )
        for match in matches
    ]

    return {
        "ingredients": ingredients,
        "match_count": len(matches),
        "matched_names": matched_names,
        "regulation_types": regulation_types,
        "source_ids": source_ids,
        "match_types": match_types,
        "decision_basis_flags": (
            decision_basis_flags
        ),
    }


def has_decision_basis(
    regulation: Any,
) -> bool:
    """
    규제 판정의 근거가 되는 필드가 존재하는지 확인한다.

    금지 성분은 보통 use_conditions 또는 product_scope로
    사용 금지 근거를 제공한다.

    제한 성분은 최대 함량, 사용 범위, 사용 조건,
    주의 문구 중 하나 이상이 있어야 한다.
    """
    basis_values = [
        regulation.max_concentration,
        regulation.product_scope,
        regulation.use_conditions,
        regulation.warning_text,
    ]

    return any(
        bool(str(value).strip())
        for value in basis_values
        if value is not None
    )


def match_count_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_count = int(
        reference_outputs.get(
            "expected_match_count",
            0,
        )
    )

    actual_count = int(
        outputs.get(
            "match_count",
            0,
        )
    )

    return actual_count == expected_count


def expected_names_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_names = set(
        reference_outputs.get(
            "expected_names",
            [],
        )
    )

    actual_names = set(
        outputs.get(
            "matched_names",
            [],
        )
    )

    return actual_names == expected_names


def regulation_types_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    expected_types = sorted(
        reference_outputs.get(
            "expected_regulation_types",
            [],
        )
    )

    actual_types = sorted(
        outputs.get(
            "regulation_types",
            [],
        )
    )

    return actual_types == expected_types


def source_id_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    """
    규제 매칭이 없는 음성 케이스에는 source_id를
    검사할 결과가 없으므로 통과로 처리한다.
    """
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


def decision_basis_present(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    """
    규제 매칭이 있는 경우 모든 결과에 판정 근거가
    존재하는지 확인한다.

    음성 케이스는 확인할 규제 결과가 없으므로 통과한다.
    """
    expected = bool(
        reference_outputs.get(
            "expected_has_decision_basis",
            True,
        )
    )

    flags = outputs.get(
        "decision_basis_flags",
        [],
    )

    if not flags:
        return True

    actual = all(flags)

    return actual == expected


def exact_match_type_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    """
    규제 검색은 유사도 검색을 사용하지 않고,
    허용된 exact match 유형만 반환하는지 확인한다.
    """
    match_types = outputs.get(
        "match_types",
        [],
    )

    allowed_match_types = {
        "ingredient_kor_name",
        "chemical_name",
        "cas_no",
    }

    return all(
        match_type in allowed_match_types
        for match_type in match_types
    )


def regulation_case_correct(
    outputs: dict[str, Any],
    reference_outputs: dict[str, Any],
) -> bool:
    """
    한 평가 케이스의 모든 지표가 통과했는지 확인한다.
    """
    return (
        match_count_correct(
            outputs,
            reference_outputs,
        )
        and expected_names_correct(
            outputs,
            reference_outputs,
        )
        and regulation_types_correct(
            outputs,
            reference_outputs,
        )
        and source_id_correct(
            outputs,
            reference_outputs,
        )
        and decision_basis_present(
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
        regulation_target,
        data=DATASET_NAME,
        evaluators=[
            match_count_correct,
            expected_names_correct,
            regulation_types_correct,
            source_id_correct,
            decision_basis_present,
            exact_match_type_correct,
            regulation_case_correct,
        ],
        experiment_prefix=(
            "derma-rag-regulation-baseline-v1"
        ),
        metadata={
            "evaluation_scope": (
                "mfds_regulation"
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
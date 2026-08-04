from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]

REGULATION_METADATA_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "raw"
    / "source_metadata.json"
)

ALLERGEN_METADATA_PATH = (
    BASE_DIR
    / "data"
    / "allergens"
    / "mfds"
    / "raw"
    / "source_metadata.json"
)

REGULATION_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "processed"
    / "mfds_cosmetic_regulations.jsonl"
)

PROHIBITED_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "processed"
    / "mfds_prohibited_ingredients.jsonl"
)

RESTRICTED_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "processed"
    / "mfds_restricted_ingredients.jsonl"
)

ALLERGEN_PATH = (
    BASE_DIR
    / "data"
    / "allergens"
    / "mfds"
    / "processed"
    / "mfds_fragrance_allergens.jsonl"
)


ALLOWED_REGULATION_TYPES = {
    "prohibited",
    "restricted",
}

REGULATION_REQUIRED_FIELDS = {
    "ingredient_kor_name",
    "regulation_type",
    "category",
    "source_id",
    "source_authority",
    "source_document",
    "notice_number",
    "notice_date",
    "source_section",
    "source_row",
}

ALLERGEN_REQUIRED_FIELDS = {
    "ingredient_kor_name",
    "allergen_type",
    "legal_status",
    "rinse_off_threshold",
    "leave_on_threshold",
    "source_id",
    "source_authority",
    "source_document",
    "source_document_version",
    "source_document_date",
    "source_section",
    "source_page",
    "source_row",
}


class ValidationError(Exception):
    """
    데이터 출처 또는 판정 근거 검증 실패를 나타낸다.
    """


def is_missing(value: Any) -> bool:
    """
    값이 실질적으로 비어 있는지 확인한다.
    """
    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, list):
        return len(value) == 0

    if isinstance(value, dict):
        return len(value) == 0

    return False


def load_json(path: Path) -> dict[str, Any]:
    """
    JSON 파일을 읽고 객체 형태인지 검증한다.
    """
    if not path.exists():
        raise ValidationError(
            f"JSON 파일이 없습니다: {path}"
        )

    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"JSON 파싱에 실패했습니다: {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValidationError(
            f"JSON 최상위 값이 객체가 아닙니다: {path}"
        )

    return data


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """
    JSONL 파일을 읽고 모든 행을 객체로 반환한다.
    """
    if not path.exists():
        raise ValidationError(
            f"JSONL 파일이 없습니다: {path}"
        )

    records: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            text = line.strip()

            if not text:
                continue

            try:
                record = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValidationError(
                    "JSONL 파싱에 실패했습니다: "
                    f"{path}:{line_number}: {exc}"
                ) from exc

            if not isinstance(record, dict):
                raise ValidationError(
                    "JSONL 레코드가 객체가 아닙니다: "
                    f"{path}:{line_number}"
                )

            records.append(record)

    return records


def validate_metadata(
    metadata: dict[str, Any],
    *,
    path: Path,
    required_fields: set[str],
) -> None:
    """
    source metadata의 필수 필드를 검증한다.
    """
    missing_fields = [
        field
        for field in sorted(required_fields)
        if field not in metadata
        or is_missing(metadata[field])
    ]

    if missing_fields:
        raise ValidationError(
            f"메타데이터 필드가 누락되었습니다: "
            f"{path}: {missing_fields}"
        )


def validate_required_fields(
    records: list[dict[str, Any]],
    *,
    path: Path,
    required_fields: set[str],
) -> None:
    """
    모든 레코드의 공통 필수 필드를 검증한다.
    """
    errors: list[str] = []

    for index, record in enumerate(
        records,
        start=1,
    ):
        missing_fields = [
            field
            for field in sorted(required_fields)
            if field not in record
            or is_missing(record[field])
        ]

        if missing_fields:
            errors.append(
                f"{path.name}:{index}: "
                f"{missing_fields}"
            )

    if errors:
        preview = "\n".join(errors[:20])

        raise ValidationError(
            "필수 필드가 누락된 레코드가 있습니다.\n"
            f"{preview}\n"
            f"전체 오류 수: {len(errors)}"
        )


def validate_source_ids(
    records: list[dict[str, Any]],
    *,
    path: Path,
    expected_source_id: str,
) -> None:
    """
    모든 레코드가 metadata의 source_id를 참조하는지 확인한다.
    """
    mismatches: list[str] = []

    for index, record in enumerate(
        records,
        start=1,
    ):
        source_id = record.get("source_id")

        if source_id != expected_source_id:
            mismatches.append(
                f"{path.name}:{index}: "
                f"{source_id!r}"
            )

    if mismatches:
        preview = "\n".join(mismatches[:20])

        raise ValidationError(
            "source_id가 metadata와 일치하지 않습니다.\n"
            f"기대값: {expected_source_id}\n"
            f"{preview}\n"
            f"전체 오류 수: {len(mismatches)}"
        )


def validate_regulation_records(
    records: list[dict[str, Any]],
    *,
    path: Path,
) -> None:
    """
    규제 유형과 판정 근거를 검증한다.
    """
    errors: list[str] = []

    for index, record in enumerate(
        records,
        start=1,
    ):
        regulation_type = record.get(
            "regulation_type"
        )

        if regulation_type not in (
            ALLOWED_REGULATION_TYPES
        ):
            errors.append(
                f"{path.name}:{index}: "
                "허용되지 않은 regulation_type="
                f"{regulation_type!r}"
            )
            continue

        if regulation_type == "prohibited":
            use_conditions = record.get(
                "use_conditions"
            )

            if is_missing(use_conditions):
                errors.append(
                    f"{path.name}:{index}: "
                    "금지 성분의 use_conditions 누락"
                )

        if regulation_type == "restricted":
            decision_fields = [
                record.get("max_concentration"),
                record.get("product_scope"),
                record.get("use_conditions"),
                record.get("warning_text"),
            ]

            if all(
                is_missing(value)
                for value in decision_fields
            ):
                errors.append(
                    f"{path.name}:{index}: "
                    "제한 판정 근거가 모두 누락"
                )

    if errors:
        preview = "\n".join(errors[:20])

        raise ValidationError(
            "규제 데이터 검증에 실패했습니다.\n"
            f"{preview}\n"
            f"전체 오류 수: {len(errors)}"
        )


def validate_allergen_records(
    records: list[dict[str, Any]],
    *,
    path: Path,
) -> None:
    """
    알레르겐 목록과 표시 기준을 검증한다.
    """
    errors: list[str] = []

    if len(records) != 25:
        errors.append(
            "향료 알레르겐 레코드는 "
            f"25개여야 하지만 {len(records)}개입니다."
        )

    source_rows = [
        record.get("source_row")
        for record in records
    ]

    if source_rows != list(range(1, 26)):
        errors.append(
            "알레르겐 source_row가 "
            "1부터 25까지 연속되지 않습니다."
        )

    for index, record in enumerate(
        records,
        start=1,
    ):
        if (
            record.get("legal_status")
            != "labeling_required"
        ):
            errors.append(
                f"{path.name}:{index}: "
                "legal_status가 "
                "labeling_required가 아님"
            )

        if (
            record.get("allergen_type")
            != "fragrance_allergen"
        ):
            errors.append(
                f"{path.name}:{index}: "
                "allergen_type이 "
                "fragrance_allergen이 아님"
            )

        cas_numbers = record.get(
            "cas_numbers"
        )

        if not isinstance(cas_numbers, list):
            errors.append(
                f"{path.name}:{index}: "
                "cas_numbers가 배열이 아님"
            )
        elif not cas_numbers:
            errors.append(
                f"{path.name}:{index}: "
                "cas_numbers가 비어 있음"
            )

    if errors:
        preview = "\n".join(errors[:20])

        raise ValidationError(
            "알레르겐 데이터 검증에 실패했습니다.\n"
            f"{preview}\n"
            f"전체 오류 수: {len(errors)}"
        )


def validate_record_counts(
    *,
    prohibited_records: list[dict[str, Any]],
    restricted_records: list[dict[str, Any]],
    merged_records: list[dict[str, Any]],
) -> None:
    """
    통합 데이터의 레코드 수 관계를 확인한다.

    통합 스크립트에서 중복 제거가 적용될 수 있으므로,
    단순 합계와 반드시 같아야 한다고 강제하지는 않는다.
    """
    source_total = (
        len(prohibited_records)
        + len(restricted_records)
    )

    merged_total = len(merged_records)

    if merged_total > source_total:
        raise ValidationError(
            "통합 레코드 수가 원본 합계보다 큽니다: "
            f"원본 합계={source_total}, "
            f"통합={merged_total}"
        )

    if not merged_records:
        raise ValidationError(
            "통합 규제 데이터가 비어 있습니다."
        )


def print_success(
    *,
    prohibited_records: list[dict[str, Any]],
    restricted_records: list[dict[str, Any]],
    merged_records: list[dict[str, Any]],
    allergen_records: list[dict[str, Any]],
) -> None:
    """
    검증 성공 결과를 출력한다.
    """
    print("MFDS 출처 및 판정 근거 검증 성공")
    print()
    print(
        "금지 성분:",
        len(prohibited_records),
    )
    print(
        "제한 성분:",
        len(restricted_records),
    )
    print(
        "통합 규제:",
        len(merged_records),
    )
    print(
        "향료 알레르겐:",
        len(allergen_records),
    )


def main() -> None:
    regulation_metadata = load_json(
        REGULATION_METADATA_PATH
    )
    allergen_metadata = load_json(
        ALLERGEN_METADATA_PATH
    )

    validate_metadata(
        regulation_metadata,
        path=REGULATION_METADATA_PATH,
        required_fields={
            "source_id",
            "dataset_version",
            "authority",
            "document_title",
            "notice_number",
            "notice_label",
            "notice_date",
        },
    )

    validate_metadata(
        allergen_metadata,
        path=ALLERGEN_METADATA_PATH,
        required_fields={
            "source_id",
            "dataset_version",
            "authority",
            "document_title",
            "document_version",
            "document_date",
        },
    )

    prohibited_records = load_jsonl(
        PROHIBITED_PATH
    )
    restricted_records = load_jsonl(
        RESTRICTED_PATH
    )
    merged_records = load_jsonl(
        REGULATION_PATH
    )
    allergen_records = load_jsonl(
        ALLERGEN_PATH
    )

    for path, records in [
        (
            PROHIBITED_PATH,
            prohibited_records,
        ),
        (
            RESTRICTED_PATH,
            restricted_records,
        ),
        (
            REGULATION_PATH,
            merged_records,
        ),
    ]:
        validate_required_fields(
            records,
            path=path,
            required_fields=(
                REGULATION_REQUIRED_FIELDS
            ),
        )

        validate_source_ids(
            records,
            path=path,
            expected_source_id=str(
                regulation_metadata[
                    "source_id"
                ]
            ),
        )

        validate_regulation_records(
            records,
            path=path,
        )

    validate_required_fields(
        allergen_records,
        path=ALLERGEN_PATH,
        required_fields=(
            ALLERGEN_REQUIRED_FIELDS
        ),
    )

    validate_source_ids(
        allergen_records,
        path=ALLERGEN_PATH,
        expected_source_id=str(
            allergen_metadata["source_id"]
        ),
    )

    validate_allergen_records(
        allergen_records,
        path=ALLERGEN_PATH,
    )

    validate_record_counts(
        prohibited_records=prohibited_records,
        restricted_records=restricted_records,
        merged_records=merged_records,
    )

    print_success(
        prohibited_records=prohibited_records,
        restricted_records=restricted_records,
        merged_records=merged_records,
        allergen_records=allergen_records,
    )


if __name__ == "__main__":
    try:
        main()
    except ValidationError as exc:
        print("MFDS 검증 실패")
        print(exc)
        raise SystemExit(1) from exc
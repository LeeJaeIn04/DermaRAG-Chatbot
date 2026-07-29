from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[1]

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

OUTPUT_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "processed"
    / "mfds_cosmetic_regulations.jsonl"
)


def read_jsonl(
    file_path: Path,
) -> list[dict[str, Any]]:
    """
    JSONL 파일을 읽어 dict 목록으로 반환한다.
    """
    if not file_path.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {file_path}"
        )

    records: list[dict[str, Any]] = []

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        for line_number, line in enumerate(
            file,
            start=1,
        ):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"JSON 파싱 실패: "
                    f"{file_path.name} "
                    f"{line_number}번째 줄"
                ) from error

            records.append(record)

    return records


def build_record_key(
    record: dict[str, Any],
) -> tuple[str, str, str, str]:
    """
    완전히 동일한 규제 레코드를 확인하기 위한 키를 만든다.

    같은 원료명이더라도 CAS 번호나 규제 유형,
    카테고리가 다르면 별도 레코드로 유지한다.
    """
    return (
        str(
            record.get(
                "ingredient_kor_name",
                "",
            )
        ).strip(),
        str(
            record.get(
                "cas_no",
                "",
            )
        ).strip(),
        str(
            record.get(
                "regulation_type",
                "",
            )
        ).strip(),
        str(
            record.get(
                "category",
                "",
            )
        ).strip(),
    )


def deduplicate_records(
    records: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    int,
]:
    """
    완전히 같은 식별 키를 가진 중복 레코드를 제거한다.
    """
    unique_records: list[
        dict[str, Any]
    ] = []

    seen_keys: set[
        tuple[str, str, str, str]
    ] = set()

    duplicate_count = 0

    for record in records:
        key = build_record_key(record)

        if key in seen_keys:
            duplicate_count += 1
            continue

        seen_keys.add(key)
        unique_records.append(record)

    return unique_records, duplicate_count


def sort_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    규제 유형, 카테고리, 원료명, CAS 번호 순으로 정렬한다.
    """
    regulation_order = {
        "prohibited": 0,
        "restricted": 1,
    }

    return sorted(
        records,
        key=lambda record: (
            regulation_order.get(
                str(
                    record.get(
                        "regulation_type",
                        "",
                    )
                ),
                99,
            ),
            str(
                record.get(
                    "category",
                    "",
                )
            ),
            str(
                record.get(
                    "ingredient_kor_name",
                    "",
                )
            ),
            str(
                record.get(
                    "cas_no",
                    "",
                )
            ),
        ),
    )


def write_jsonl(
    records: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """
    병합된 레코드를 JSONL 파일로 저장한다.
    """
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        for record in records:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
            )
            file.write("\n")


def print_summary(
    records: list[dict[str, Any]],
) -> None:
    """
    병합 결과를 규제 유형과 카테고리별로 출력한다.
    """
    regulation_counts = Counter(
        str(
            record.get(
                "regulation_type",
                "unknown",
            )
        )
        for record in records
    )

    category_counts = Counter(
        str(
            record.get(
                "category",
                "unknown",
            )
        )
        for record in records
    )

    print("규제 유형별 개수:")

    for regulation_type, count in (
        regulation_counts.items()
    ):
        print(
            f"- {regulation_type}: {count}"
        )

    print()
    print("카테고리별 개수:")

    for category, count in (
        category_counts.items()
    ):
        print(f"- {category}: {count}")


def main() -> None:
    prohibited_records = read_jsonl(
        PROHIBITED_PATH
    )

    restricted_records = read_jsonl(
        RESTRICTED_PATH
    )

    merged_records = (
        prohibited_records
        + restricted_records
    )

    unique_records, duplicate_count = (
        deduplicate_records(
            merged_records
        )
    )

    sorted_records = sort_records(
        unique_records
    )

    write_jsonl(
        records=sorted_records,
        output_path=OUTPUT_PATH,
    )

    print(
        f"사용금지 원료 레코드: "
        f"{len(prohibited_records)}"
    )
    print(
        f"사용제한 원료 레코드: "
        f"{len(restricted_records)}"
    )
    print(
        f"병합 전 전체 레코드: "
        f"{len(merged_records)}"
    )
    print(
        f"제거한 중복 레코드: "
        f"{duplicate_count}"
    )
    print(
        f"최종 레코드: "
        f"{len(sorted_records)}"
    )
    print(
        f"저장 위치: {OUTPUT_PATH}"
    )

    print()
    print_summary(sorted_records)


if __name__ == "__main__":
    main()
from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from lxml import etree


BASE_DIR = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "raw"
    / "mfds_restricted_ingredients_2026-19.hwpx"
)

OUTPUT_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "processed"
    / "mfds_restricted_ingredients.jsonl"
)


TABLE_CATEGORIES = {
    1: "preservative",
    2: "uv_filter",
    3: "hair_dye",
    4: "restricted_other",
}


def local_name(element: etree._Element) -> str:
    """
    XML namespace를 제외한 태그 이름만 반환한다.
    """
    return etree.QName(element).localname


def clean_text(value: str | None) -> str:
    """
    줄바꿈과 연속 공백을 하나의 공백으로 정리한다.
    """
    if not value:
        return ""

    return " ".join(value.split())


def extract_cell_text(
    cell: etree._Element,
) -> str:
    """
    표 셀 내부의 모든 텍스트를 추출한다.
    """
    texts: list[str] = []

    for element in cell.iter():
        if local_name(element) != "t":
            continue

        text = clean_text(element.text)

        if text:
            texts.append(text)

    return " ".join(texts)


def extract_tables(
    hwpx_path: Path,
) -> list[list[list[str]]]:
    """
    HWPX 파일 안의 모든 표를 읽는다.

    반환 형식:
    [
        [
            ["원료명", "사용한도", ...],
            ["글루타랄", "0.1%", ...],
        ],
        ...
    ]
    """
    with ZipFile(hwpx_path) as archive:
        section_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("Contents/section")
            and name.endswith(".xml")
        )

        if not section_names:
            raise RuntimeError(
                "HWPX에서 section XML을 찾지 못했습니다."
            )

        parser = etree.XMLParser(
            recover=True,
            remove_blank_text=True,
        )

        root = etree.fromstring(
            archive.read(section_names[0]),
            parser=parser,
        )

        table_elements = [
            element
            for element in root.iter()
            if local_name(element) == "tbl"
        ]

        tables: list[list[list[str]]] = []

        for table in table_elements:
            rows: list[list[str]] = []

            for row in table.iter():
                if local_name(row) != "tr":
                    continue

                cells = [
                    extract_cell_text(cell)
                    for cell in row
                    if local_name(cell) == "tc"
                ]

                if not cells:
                    cells = [
                        extract_cell_text(cell)
                        for cell in row.iter()
                        if local_name(cell) == "tc"
                    ]

                if cells:
                    rows.append(cells)

            tables.append(rows)

        return tables


def normalize_cas_no(value: str) -> str:
    """
    CAS 번호가 '-'인 경우 빈 문자열로 바꾼다.

    여러 CAS 번호가 있는 경우 원문을 유지한다.
    """
    value = clean_text(value)

    if value == "-":
        return ""

    return value


def build_record(
    *,
    ingredient_name: str,
    usage_limit: str,
    notes: str,
    cas_no: str,
    chemical_name: str,
    category: str,
    table_number: int,
    source_row: int,
) -> dict[str, object]:
    """
    한 행을 규제 JSON 레코드로 변환한다.
    """
    return {
        "ingredient_kor_name": ingredient_name,
        "ingredient_eng_name": None,
        "cas_no": normalize_cas_no(cas_no),
        "chemical_name": chemical_name or None,
        "regulation_type": "restricted",
        "category": category,
        "max_concentration": usage_limit or None,
        "product_scope": None,
        "use_conditions": notes or None,
        "warning_text": None,
        "source_authority": "MFDS",
        "source_document": (
            "화장품 안전기준 등에 관한 규정"
        ),
        "notice_number": "2026-19",
        "notice_label": (
            "식품의약품안전처 고시 제2026-19호"
        ),
        "notice_date": "2026-03-18",
        "source_section": "별표 2",
        "source_table": table_number,
        "source_row": source_row,
    }


def normalize_table(
    rows: list[list[str]],
    *,
    table_number: int,
    category: str,
) -> list[dict[str, object]]:
    """
    하나의 사용제한 표를 구조화한다.

    정상 행:
    [원료명, 사용한도, 비고, CAS No., 화학물질명]

    병합 후속 행:
    [CAS No., 화학물질명]

    병합 후속 행은 직전 원료명과
    사용한도·비고를 이어받는다.
    """
    records: list[dict[str, object]] = []

    current_ingredient_name = ""
    current_usage_limit = ""
    current_notes = ""

    # 첫 번째 행은 헤더이므로 제외한다.
    for source_row, cells in enumerate(
        rows[1:],
        start=2,
    ):
        cells = [
            clean_text(cell)
            for cell in cells
        ]

        ingredient_name = ""
        usage_limit = ""
        notes = ""
        cas_no = ""
        chemical_name = ""

        if len(cells) >= 5:
            ingredient_name = cells[0]
            usage_limit = cells[1]
            notes = cells[2]
            cas_no = cells[3]
            chemical_name = cells[4]

            if ingredient_name:
                current_ingredient_name = (
                    ingredient_name
                )
                current_usage_limit = usage_limit
                current_notes = notes

        elif len(cells) == 2:
            # 병합된 원료명·사용한도·비고 셀의
            # 후속 행이다.
            ingredient_name = (
                current_ingredient_name
            )
            usage_limit = current_usage_limit
            notes = current_notes
            cas_no = cells[0]
            chemical_name = cells[1]

        else:
            print(
                "[WARN] 예상하지 못한 행 구조:",
                {
                    "table": table_number,
                    "row": source_row,
                    "cells": cells,
                },
            )
            continue

        if not ingredient_name:
            print(
                "[WARN] 원료명이 없는 행:",
                {
                    "table": table_number,
                    "row": source_row,
                    "cells": cells,
                },
            )
            continue

        record = build_record(
            ingredient_name=ingredient_name,
            usage_limit=usage_limit,
            notes=notes,
            cas_no=cas_no,
            chemical_name=chemical_name,
            category=category,
            table_number=table_number,
            source_row=source_row,
        )

        records.append(record)

    return records


def write_jsonl(
    records: list[dict[str, object]],
    output_path: Path,
) -> None:
    """
    레코드를 JSONL로 저장한다.
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


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"입력 파일이 없습니다: {INPUT_PATH}"
        )

    tables = extract_tables(INPUT_PATH)

    if len(tables) != 4:
        raise RuntimeError(
            "사용제한 원료 HWPX에서 "
            f"표 4개를 기대했지만 {len(tables)}개를 찾았습니다."
        )

    all_records: list[dict[str, object]] = []

    for table_number, rows in enumerate(
        tables,
        start=1,
    ):
        category = TABLE_CATEGORIES[
            table_number
        ]

        table_records = normalize_table(
            rows,
            table_number=table_number,
            category=category,
        )

        print(
            f"TABLE {table_number} "
            f"({category}): "
            f"{len(table_records)}개 변환"
        )

        all_records.extend(
            table_records
        )

    write_jsonl(
        records=all_records,
        output_path=OUTPUT_PATH,
    )

    print()
    print(
        f"전체 변환 레코드 수: "
        f"{len(all_records)}"
    )
    print(
        f"저장 위치: {OUTPUT_PATH}"
    )

    print()
    print("카테고리별 개수:")

    for category in TABLE_CATEGORIES.values():
        count = sum(
            1
            for record in all_records
            if record["category"] == category
        )

        print(
            f"- {category}: {count}"
        )

    print()
    print("처음 5개 레코드:")

    for record in all_records[:5]:
        print(
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
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
    / "mfds_prohibited_ingredients_2026-19.hwpx"
)

OUTPUT_PATH = (
    BASE_DIR
    / "data"
    / "regulations"
    / "mfds"
    / "processed"
    / "mfds_prohibited_ingredients.jsonl"
)


def local_name(element: etree._Element) -> str:
    """
    XML namespace를 제외한 태그 이름만 반환한다.

    예:
    {namespace}tbl
    → tbl
    """
    return etree.QName(element).localname


def clean_text(value: str | None) -> str:
    """
    줄바꿈과 연속 공백을 하나의 공백으로 정리한다.
    """
    if not value:
        return ""

    return " ".join(value.split())


def extract_cell_text(cell: etree._Element) -> str:
    """
    표의 한 셀 안에 들어 있는 모든 텍스트를 추출한다.
    """
    texts: list[str] = []

    for element in cell.iter():
        if local_name(element) != "t":
            continue

        text = clean_text(element.text)

        if text:
            texts.append(text)

    return " ".join(texts)


def extract_rows(
    hwpx_path: Path,
) -> list[list[str]]:
    """
    HWPX 파일의 첫 번째 표를 행 단위로 읽는다.
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

        table = next(
            (
                element
                for element in root.iter()
                if local_name(element) == "tbl"
            ),
            None,
        )

        if table is None:
            raise RuntimeError(
                "HWPX에서 표를 찾지 못했습니다."
            )

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

        return rows


def normalize_rows(
    rows: list[list[str]],
) -> list[dict[str, object]]:
    """
    표의 병합 셀을 고려해 사용금지 원료 데이터를 구조화한다.

    정상 행:
    [원료명, CAS No., 화학물질명]

    병합된 후속 행:
    [CAS No., 화학물질명]

    두 칸짜리 행은 직전 원료명을 이어받는다.
    """
    records: list[dict[str, object]] = []

    current_ingredient_name = ""

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
        cas_no = ""
        chemical_name = ""

        if len(cells) >= 3:
            ingredient_name = cells[0]
            cas_no = cells[1]
            chemical_name = cells[2]

            if ingredient_name:
                current_ingredient_name = (
                    ingredient_name
                )

        elif len(cells) == 2:
            # 병합된 원료명 셀의 후속 행으로 판단한다.
            ingredient_name = (
                current_ingredient_name
            )
            cas_no = cells[0]
            chemical_name = cells[1]

        elif len(cells) == 1:
            # 예외 행은 우선 원료명으로 보관한다.
            ingredient_name = cells[0]
            current_ingredient_name = (
                ingredient_name
            )

        if not ingredient_name:
            continue

        record = {
            "ingredient_kor_name": (
                ingredient_name
            ),
            "ingredient_eng_name": None,
            "cas_no": (
                ""
                if cas_no == "-"
                else cas_no
            ),
            "chemical_name": (
                chemical_name or None
            ),
            "regulation_type": "prohibited",
            "category": "prohibited",
            "max_concentration": None,
            "product_scope": "all_cosmetics",
            "use_conditions": (
                "화장품에 사용할 수 없음"
            ),
            "warning_text": None,
            "source_authority": "MFDS",
            "source_document": (
                "화장품 안전기준 등에 관한 규정"
            ),
            "notice_number": "2026-19",
            "notice_label": (
                "식품의약품안전처 고시 "
                "제2026-19호"
            ),
            "notice_date": "2026-03-18",
            "source_section": "별표 1",
            "source_row": source_row,
        }

        records.append(record)

    return records


def write_jsonl(
    records: list[dict[str, object]],
    output_path: Path,
) -> None:
    """
    구조화한 레코드를 JSONL 파일로 저장한다.
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

    rows = extract_rows(INPUT_PATH)
    records = normalize_rows(rows)

    write_jsonl(
        records=records,
        output_path=OUTPUT_PATH,
    )

    print(f"원본 행 수: {len(rows)}")
    print(f"변환 레코드 수: {len(records)}")
    print(f"저장 위치: {OUTPUT_PATH}")

    print()
    print("처음 5개 레코드:")

    for record in records[:5]:
        print(
            json.dumps(
                record,
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
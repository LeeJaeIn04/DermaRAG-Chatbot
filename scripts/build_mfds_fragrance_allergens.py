from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import fitz


BASE_DIR = Path(__file__).resolve().parents[1]

DEFAULT_INPUT_PATH = (
    BASE_DIR
    / "data"
    / "allergens"
    / "mfds"
    / "raw"
    / "mfds_fragrance_allergen_labeling_guide.pdf"
)

DEFAULT_OUTPUT_PATH = (
    BASE_DIR
    / "data"
    / "allergens"
    / "mfds"
    / "processed"
    / "mfds_fragrance_allergens.jsonl"
)


# 6페이지에서 확인된 표의 행 구조:
#
# 1 아밀신남알 CAS No 122-40-7
# 2 벤질알코올 CAS No 100-51-6
#
# 성분명에는 숫자, 하이픈 등이 포함될 수 있으므로
# 다음 행 번호가 나오기 전까지를 성분명으로 본다.
ROW_PATTERN = re.compile(
    r"(?P<row_number>\d{1,2})\s+"
    r"(?P<ingredient_name>.+?)\s+"
    r"CAS\s+No\s+"
    r"(?P<cas_no>\d{2,7}-\d{2}-\d)"
    r"(?=\s+\d{1,2}\s+|\s*$)",
    re.IGNORECASE,
)


def clean_text(value: str) -> str:
    """
    줄바꿈, 탭, 연속 공백을 하나의 공백으로 정리한다.
    """
    return " ".join(value.split())


def extract_page_text(
    pdf_path: Path,
    page_number: int,
) -> str:
    """
    PDF에서 지정한 페이지의 텍스트를 추출한다.

    page_number는 사람이 보는 페이지 번호 기준으로
    1부터 시작한다.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(
            f"PDF 파일을 찾을 수 없습니다: {pdf_path}"
        )

    document = fitz.open(pdf_path)

    try:
        if page_number < 1:
            raise ValueError(
                "page_number는 1 이상이어야 합니다."
            )

        page_index = page_number - 1

        if page_index >= document.page_count:
            raise ValueError(
                f"PDF 전체 페이지는 {document.page_count}페이지인데 "
                f"{page_number}페이지를 요청했습니다."
            )

        page = document.load_page(page_index)
        return clean_text(page.get_text("text"))

    finally:
        document.close()


def isolate_allergen_table_text(
    page_text: str,
) -> str:
    """
    6페이지 전체 텍스트에서 알레르겐 표 부분만 분리한다.
    """
    header = "연번 성분명 CAS 등록번호"

    header_index = page_text.find(header)

    if header_index == -1:
        raise ValueError(
            "알레르겐 표 헤더를 찾지 못했습니다: "
            "'연번 성분명 CAS 등록번호'"
        )

    return page_text[
        header_index + len(header):
    ].strip()


def parse_allergen_rows(
    table_text: str,
) -> list[dict[str, object]]:
    """
    알레르겐 표 텍스트를 행 단위 레코드로 변환한다.
    """
    records: list[dict[str, object]] = []

    matches = list(
        ROW_PATTERN.finditer(table_text)
    )

    if not matches:
        raise ValueError(
            "알레르겐 행을 한 건도 파싱하지 못했습니다."
        )

    for match in matches:
        source_row = int(
            match.group("row_number")
        )

        ingredient_name = clean_text(
            match.group("ingredient_name")
        )

        cas_no = clean_text(
            match.group("cas_no")
        )

        record = {
            "ingredient_kor_name": ingredient_name,
            "ingredient_eng_name": None,
            "inci_name": None,
            "cas_numbers": [cas_no],
            "aliases": [],
            "allergen_type": "fragrance_allergen",
            "legal_status": "labeling_required",
            "jurisdiction": "KR",
            "evidence_scope": "fragrance_component",
            "reaction_types": [],
            "sensitization_note": None,
            "oxidation_note": None,
            "rinse_off_threshold": "0.01% 초과",
            "leave_on_threshold": "0.001% 초과",
            "source_authority": "MFDS",
            "source_document": (
                "화장품 향료 중 알레르기 유발물질 표시 지침"
            ),
            "source_document_version": "v2",
            "source_document_date": "2019-12-30",
            "source_section": (
                "참고 1 관련 법령 / 별표 2"
            ),
            "source_page": 6,
            "source_row": source_row,
        }

        records.append(record)

    return records


def validate_records(
    records: list[dict[str, object]],
) -> None:
    """
    변환된 데이터의 기본 구조를 검증한다.
    """
    if len(records) != 25:
        raise ValueError(
            "알레르겐 25개를 기대했지만 "
            f"{len(records)}개가 파싱됐습니다."
        )

    row_numbers = [
        int(record["source_row"])
        for record in records
    ]

    expected_rows = list(range(1, 26))

    if row_numbers != expected_rows:
        raise ValueError(
            "연번이 1부터 25까지 연속되지 않습니다: "
            f"{row_numbers}"
        )

    cas_numbers = [
        str(record["cas_numbers"][0])
        for record in records
    ]

    duplicate_cas_numbers = {
        cas_no
        for cas_no in cas_numbers
        if cas_numbers.count(cas_no) > 1
    }

    if duplicate_cas_numbers:
        raise ValueError(
            "중복 CAS 번호가 발견됐습니다: "
            f"{sorted(duplicate_cas_numbers)}"
        )


def write_jsonl(
    records: list[dict[str, object]],
    output_path: Path,
) -> None:
    """
    레코드를 JSONL 파일로 저장한다.
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
    parser = argparse.ArgumentParser(
        description=(
            "식약처 향료 알레르기 유발성분 "
            "25개 목록을 JSONL로 변환합니다."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
    )

    parser.add_argument(
        "--page",
        type=int,
        default=6,
        help="알레르겐 표가 있는 PDF 페이지 번호",
    )

    args = parser.parse_args()

    page_text = extract_page_text(
        pdf_path=args.input,
        page_number=args.page,
    )

    table_text = isolate_allergen_table_text(
        page_text
    )

    records = parse_allergen_rows(
        table_text
    )

    validate_records(records)

    write_jsonl(
        records=records,
        output_path=args.output,
    )

    print(
        f"입력 PDF: {args.input}"
    )
    print(
        f"추출 페이지: {args.page}"
    )
    print(
        f"변환 레코드 수: {len(records)}"
    )
    print(
        f"저장 위치: {args.output}"
    )

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
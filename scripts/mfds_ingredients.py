import json
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
import requests
from app.config import settings
from dotenv import load_dotenv
load_dotenv()


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

RAW_OUTPUT_PATH = DATA_DIR / "mfds_ingredients_raw.jsonl"
TEXT_OUTPUT_PATH = DATA_DIR / "mfds_ingredients.txt"

API_URL = (
    "https://apis.data.go.kr/1471000/"
    "CsmtcsIngdCpntInfoService01/"
    "getCsmtcsIngdCpntInfoService01"
)

def validate_environment() -> str:
    service_key = settings.data_go_kr_service_key

    if not service_key:
        raise RuntimeError(
            ".env 파일에 공공데이터포털 API 키를 추가해 주세요."
        )
    return service_key


def clean_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.replace("\r", " ").replace("\n", " ").split())


def normalized_item(item: dict[str, Any]) -> dict[str, str]:
    return {
        "ingredient_kor_name": clean_text(item.get("INGR_KOR_NAME")),
        "ingredient_eng_name": clean_text(item.get("INGR_ENG_NAME")),
        "cas_no": clean_text(item.get("CAS_NO")),
        "origin_description": clean_text(item.get("ORIGIN_MAJOR_KOR_NAME")),
        "synonym": clean_text(item.get("INGR_SYNONYM")),
    }


def extract_items_json(data: dict[str, Any]) -> list[dict[str, str]]:
    response = data.get("response", data)
    body = response.get("body", response)
    items = body.get("items", [])

    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        return []
    
    normalized_items: list[dict[str, str]] = []

    for item in items:
        if isinstance(item, dict):
            normalized_items.append(normalized_item(item))
    
    return normalized_items


def extract_items_xml(text: str) -> list[dict[str, str]]:
    root = ElementTree.fromstring(text)

    result_code = root.findtext(".//resultCode")
    result_msg = root.findtext(".//resultMsg")

    if result_code and result_code != "00":
        raise RuntimeError(
            f"공공데이터 API 오류: resultCode={result_code}, resultMsg={result_msg}"
        )
    
    items: list[dict[str, str]] = []

    for item_element in root.findall(".//items/item"):
        raw_item = {
            "INGR_KOR_NAME": item_element.findtext("INGR_KOR_NAME"),
            "INGR_ENG_NAME": item_element.findtext("INGR_ENG_NAME"),
            "CAS_NO": item_element.findtext("CAS_NO"),
            "ORIGIN_MAJOR_KOR_NAME": item_element.findtext("ORIGIN_MAJOR_KOR_NAME"),
            "INGR_SYNONYM": item_element.findtext("INGR_SYNONYM"),
        }

        items.append(normalized_item(raw_item))
    
    return items


def parse_items(response: requests.Response) -> list[dict[str, str]]:
    text = response.text.strip()

    if text.startswith("<"):
        return extract_items_xml(text)
    
    try:
        data = response.json()
        return extract_items_json(data)
    except json.JSONDecodeError:
        return extract_items_xml(text)
    

def fetch_page(
        service_key: str,
        page_no: int,
        num_of_rows: int = 100,
) -> list[dict[str, str]]:
    params = {
        "serviceKey": service_key,
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "type": "json",
        "_type": "json",
    }

    response = requests.get(API_URL, params=params, timeout=20)

    if response.status_code != 200:
        print("API 요청 실패")
        print(f"status_code: {response.status_code}")
        print(f"url: {response.url}")
        print("response text:")
        print(response.text[:1000])

        response.raise_for_status()

    return parse_items(response)


def item_to_text(item: dict[str, str]) -> str:
    kor_name = item.get("ingredient_kor_name", "")
    eng_name = item.get("ingredient_eng_name", "")
    cas_no = item.get("cas_no", "")
    origin_description = item.get("origin_description", "")
    synonym = item.get("synonym", "")

    lines = ["화장품 원료성분 정보"]

    if kor_name:
        lines.append(f"성분명: {kor_name}")

    if eng_name:
        lines.append(f"영문명: {eng_name}")

    if cas_no:
        lines.append(f"CAS 번호: {cas_no}")
    
    if origin_description:
        lines.append(f"원료 설명: {origin_description}")

    if synonym:
        lines.append(f"동의어: {synonym}")
    
    return "\n".join(lines)


def save_outputs(items: list[dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with RAW_OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    with TEXT_OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for index, item in enumerate(items, start=1):
            f.write(f"[성분 데이터 {index}]\n")
            f.write(item_to_text(item))
            f.write("\n\n")


def main() -> None:
    service_key = validate_environment()

    max_pages = 50
    num_of_rows = 100

    all_items: list[dict[str, str]] = []

    for page_no in range(1, max_pages + 1):
        print(f"{page_no} 페이지 수집 중...")

        items = fetch_page(
            service_key=service_key,
            page_no=page_no,
            num_of_rows=num_of_rows,
        )

        print(f"  가져온 item 수: {len(items)}")

        if not items:
            break

        all_items.extend(items)

        time.sleep(0.2)

    if not all_items:
        raise RuntimeError(
            "수집된 데이터가 없습니다. "
            "API 키, 활용신청 승인 여부, 요청 URL을 확인해 주세요."
        )

    save_outputs(all_items)

    print()
    print("수집 완료!")
    print(f"총 수집 item 수: {len(all_items)}")
    print(f"원본 저장: {RAW_OUTPUT_PATH}")
    print(f"RAG 텍스트 저장: {TEXT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any
from langchain_chroma import Chroma
from langchain_core.documents import Document
from app.embeddings import get_embeddings, get_embedding_model_name
from app.config import settings


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

RAW_INPUT_PATH = DATA_DIR / "mfds_ingredients_raw.jsonl"

PERSIST_DIR = BASE_DIR / "vectorstore" / "chroma"
COLLECTION_NAME = "derma_rag"

EMBEDDING_MODEL = getattr(
    settings,
    "gemini_embedding_model",
    "gemini-embedding-001",
)

def validate_environment() -> None:
    if not RAW_INPUT_PATH.exists():
        raise RuntimeError(
            f"{RAW_INPUT_PATH} 파일이 없습니다. "
            "먼저 아래 명령어를 실행해 주세요.\n"
            "python -m scripts.mfds_ingredients"
        )


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def make_document_id(item: dict[str, Any]) -> str:
    kor_name = clean_text(item.get("ingredient_kor_name"))
    eng_name = clean_text(item.get("ingredient_eng_name"))
    cas_no = clean_text(item.get("cas_no"))

    key = f"{kor_name}|{eng_name}|{cas_no}".lower()
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()

    return f"ingredient-{digest}"


def item_to_text(item: dict[str, Any]) -> str:
    kor_name = clean_text(item.get("ingredient_kor_name"))
    eng_name = clean_text(item.get("ingredient_eng_name"))
    cas_no = clean_text(item.get("cas_no"))
    origin_description = clean_text(item.get("origin_description"))
    synonym = clean_text(item.get("synonym"))

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


def load_documents() -> tuple[list[Document], list[str]]:
    documents: list[Document] = []
    ids: list[str] = []

    seen_ids: set[str] = set()

    with RAW_INPUT_PATH.open("r", encoding="utf-8") as f:
        for row_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            item = json.loads(line)

            kor_name = clean_text(item.get("ingredient_kor_name"))
            eng_name = clean_text(item.get("ingredient_eng_name"))
            cas_no = clean_text(item.get("cas_no"))

            if not kor_name and not eng_name:
                continue

            document_id = make_document_id(item)

            if document_id in seen_ids:
                continue

            seen_ids.add(document_id)

            content = item_to_text(item)

            document = Document(
                page_content=content,
                metadata={
                    "source": RAW_INPUT_PATH.name,
                    "row": row_number,
                    "ingredient_kor_name": kor_name,
                    "ingredient_eng_name": eng_name,
                    "cas_no": cas_no,
                },
            )

            documents.append(document)
            ids.append(document_id)

    return documents, ids


def reset_vectorstore() -> None:
    if PERSIST_DIR.exists():
        shutil.rmtree(PERSIST_DIR)


def create_vectorstore(documents: list[Document], ids: list[str]) -> Chroma:
    """
    성분 Document들을 embedding한 뒤 Chroma Vector DB에 저장합니다.
    """
    embeddings = get_embeddings()

    vectorstore = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        ids=ids,
        persist_directory=str(PERSIST_DIR),
        collection_name=COLLECTION_NAME,
    )

    return vectorstore


def main() -> None:
    validate_environment()

    print("1. 성분 단위 문서 로드 중...")
    documents, ids = load_documents()
    print(f"   로드된 성분 문서 수: {len(documents)}")

    if not documents:
        raise RuntimeError("로드된 성분 문서가 없습니다.")

    print("2. 기존 Chroma Vector DB 초기화 중...")
    reset_vectorstore()

    print("3. Chroma Vector DB 저장 중...")
    create_vectorstore(documents, ids)

    print()
    print("Ingest 완료!")
    print(f"저장 위치: {PERSIST_DIR}")
    print(f"Collection 이름: {COLLECTION_NAME}")
    print(f"Embedding 모델: {get_embedding_model_name()}")


if __name__ == "__main__":
    main()
import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from langchain_chroma import Chroma
from langchain_core.documents import Document
from app.embeddings import get_embeddings
import re

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
RAW_INPUT_PATH = DATA_DIR / "mfds_ingredients_raw.jsonl"
PERSIST_DIR = BASE_DIR / "vectorstore" / "chroma"
COLLECTION_NAME = "derma_rag"

def with_retrieval_type(
        doc: Document,
        retrieval_type: str,
) -> Document:
    return Document (
        page_content=doc.page_content,
        metadata={
            **(doc.metadata or {}),
            "retrieval_type": retrieval_type,
        },
    )


def clean_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def normalize_text(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[\s\-/·,()]+", "", text)
    return text


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


def item_to_document(item: dict[str, Any], row_number: int) -> Document:
    kor_name = clean_text(item.get("ingredient_kor_name"))
    eng_name = clean_text(item.get("ingredient_eng_name"))
    cas_no = clean_text(item.get("cas_no"))

    return Document(
        page_content=item_to_text(item),
        metadata={
            "source": RAW_INPUT_PATH.name,
            "row": row_number,
            "ingredient_kor_name": kor_name,
            "ingredient_eng_name": eng_name,
            "cas_no": cas_no,
            "retrieval_type": "exact_match",
        },
    )


@lru_cache(maxsize=1)
def load_raw_items() -> list[tuple[int, dict[str, Any]]]:
    if not RAW_INPUT_PATH.exists():
        raise RuntimeError(
            f"{RAW_INPUT_PATH} 파일이 없습니다. "
            "먼저 python -m scripts.mfds_ingredients 를 실행해 주세요."
        )

    items: list[tuple[int, dict[str, Any]]] = []

    with RAW_INPUT_PATH.open("r", encoding="utf-8") as f:
        for row_number, line in enumerate(f, start=1):
            line = line.strip()

            if not line:
                continue

            item = json.loads(line)
            items.append((row_number, item))

    return items


def exact_match_documents(query: str, limit: int = 8) -> list[Document]:
    query_norm = normalize_text(query)

    if not query_norm:
        return []

    scored_matches: list[tuple[int, Document]] = []

    for row_number, item in load_raw_items():
        kor_name = clean_text(item.get("ingredient_kor_name"))
        eng_name = clean_text(item.get("ingredient_eng_name"))
        cas_no = clean_text(item.get("cas_no"))
        synonym = clean_text(item.get("synonym"))

        kor_norm = normalize_text(kor_name)
        eng_norm = normalize_text(eng_name)
        cas_norm = normalize_text(cas_no)
        synonym_norm = normalize_text(synonym)

        score: int | None = None

        if kor_norm and kor_norm == query_norm:
            score = 100
        elif eng_norm and eng_norm == query_norm:
            score = 95
        elif synonym_norm and synonym_norm == query_norm:
            score = 90
        elif cas_norm and cas_norm == query_norm:
            score = 90

        if score is None:
            continue

        document = item_to_document(item, row_number)
        document.metadata["retrieval_type"] = "exact_match"
        document.metadata["match_score"] = score

        scored_matches.append((score, document))

    scored_matches.sort(
        key=lambda pair: pair[0],
        reverse=True,
    )

    return [document for _, document in scored_matches[:limit]]


def validate_vectorstore() -> None:
    if not PERSIST_DIR.exists():
        raise RuntimeError(
            f"Vector DB가 없습니다: {PERSIST_DIR}\n"
            "먼저 아래 명령어를 실행해 주세요.\n"
            "python -m scripts.ingest"
        )


def get_vectorstore() -> Chroma:
    validate_vectorstore()

    return Chroma(
        persist_directory=str(PERSIST_DIR),
        embedding_function=get_embeddings(),
        collection_name=COLLECTION_NAME,
    )


def get_retriever(search_k: int = 4):
    vectorstore = get_vectorstore()

    return vectorstore.as_retriever(
        search_kwargs={"k": search_k}
    )


def deduplicate_documents(docs: list[Document]) -> list[Document]:
    unique_docs: list[Document] = []
    seen_keys: set[str] = set()

    for doc in docs:
        key = "|".join(
            [
                str(doc.metadata.get("ingredient_kor_name", "")),
                str(doc.metadata.get("ingredient_eng_name", "")),
                str(doc.metadata.get("cas_no", "")),
                doc.page_content[:100],
            ]
        )

        if key in seen_keys:
            continue

        seen_keys.add(key)
        unique_docs.append(doc)

    return unique_docs


def search_documents(query: str, search_k: int = 8) -> list[Document]:
    exact_docs = exact_match_documents(query, limit=search_k)

    if exact_docs:
        return exact_docs[:search_k]

    retriever = get_retriever(search_k=search_k)
    vector_docs = retriever.invoke(query)

    for doc in vector_docs:
        doc.metadata["retrieval_type"] = "vector_search"

    return vector_docs[:search_k]
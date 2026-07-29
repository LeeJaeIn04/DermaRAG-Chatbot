from langchain_core.documents import Document

import app.rag_chain as rag_chain
from app.rag_chain import build_sources, retrieve_documents
from app.schemas import ChatRequest


def fake_search_documents(query: str, search_k: int = 1):
    return [
        Document(
            page_content=f"{query} 성분 정보",
            metadata={
                "ingredient_kor_name": query,
                "retrieval_type": "exact_match",
                "match_score": 100,
            },
        )
    ]


def test_retrieved_docs_and_sources_carry_query_ingredient(
    monkeypatch,
) -> None:
    """
    각 검색 문서와 최종 source에는 어떤 원본 성분을 검색하다
    반환됐는지 확인할 수 있는 query_ingredient가 있어야 한다.
    """

    monkeypatch.setattr(
        rag_chain,
        "search_documents",
        fake_search_documents,
    )

    request = ChatRequest(
        question="테스트 질문",
        ingredients=["1,2-헥산다이올", "자작나무수액(1,425ppm)"],
    )

    docs = retrieve_documents(request)

    assert {doc.metadata["query_ingredient"] for doc in docs} == {
        "1,2-헥산다이올",
        "자작나무수액(1,425ppm)",
    }

    sources = build_sources(docs)

    assert {source.query_ingredient for source in sources} == {
        "1,2-헥산다이올",
        "자작나무수액(1,425ppm)",
    }

    for source in sources:
        assert source.retrieval_type == "exact_match"
        assert source.match_score == 100

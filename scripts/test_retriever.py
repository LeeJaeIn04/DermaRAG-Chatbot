from app.retriever import search_documents

def main() -> None:
    query = "나이아신아마이드"

    docs = search_documents(query, search_k=4)

    print(f"검색어: {query}")
    print(f"검색된 문서 수: {len(docs)}")
    print()

    for index, doc in enumerate(docs, start=1):
        print("=" * 80)
        print(f"[검색 결과 {index}]")
        print(f"source: {doc.metadata.get('source', 'unknown')}")
        print(f"retrieval_type: {doc.metadata.get('retrieval_type', 'unknown')}")
        print(f"match_score: {doc.metadata.get('match_score', 'none')}")
        print()
        print(doc.page_content[:700])
        print()


if __name__ == "__main__":
    main()
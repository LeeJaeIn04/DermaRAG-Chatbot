from app.retriever import exact_match_documents


def assert_forbidden_partial_not_returned(
    query: str,
    forbidden_name: str,
) -> None:
    docs = exact_match_documents(query, limit=8)

    matched_names = [
        (doc.metadata or {}).get("ingredient_kor_name")
        for doc in docs
    ]

    print("QUERY:", query)
    print("MATCHED:", matched_names)

    if forbidden_name in matched_names:
        raise AssertionError(
            f"{query} 검색 결과에 부분 매칭 '{forbidden_name}'이 섞였습니다: "
            f"{matched_names}"
        )

    for doc in docs:
        retrieval_type = (doc.metadata or {}).get("retrieval_type")

        if retrieval_type != "exact_match":
            raise AssertionError(
                f"exact_match_documents 결과의 retrieval_type이 이상합니다: "
                f"{retrieval_type}"
            )


def main() -> None:
    assert_forbidden_partial_not_returned("프로판다이올", "프로판")
    assert_forbidden_partial_not_returned("부틸렌글라이콜", "글라이콜")
    assert_forbidden_partial_not_returned("비닐다이메티콘", "메티콘")

    print("retriever exact match tests ok")


if __name__ == "__main__":
    main()
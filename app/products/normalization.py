import re


def normalize_ingredient_name(
    ingredient_name: str,
) -> str:
    """
    상품 성분 역검색에 사용할 성분명을 정규화한다.

    현재 규칙:
    - 앞뒤 공백 제거
    - 영문은 소문자로 변경
    - 문자열 내부의 모든 공백 제거

    예:
        " 나이아신아마이드 "
        → "나이아신아마이드"

        "Niacinamide"
        → "niacinamide"

        "부틸렌 글라이콜"
        → "부틸렌글라이콜"

    주의:
        이 함수는 상품 DB 검색을 위한 최소 정규화다.
        식약처 RAG의 성분 정규화 정책과는 별도로 시작하고,
        나중에 같은 규칙으로 통합할 수 있다.
    """

    normalized = ingredient_name.strip().lower()

    return re.sub(
        r"\s+",
        "",
        normalized,
    )
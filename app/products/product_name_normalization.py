import re
import unicodedata


_LEADING_BRACKET_BLOCKS_PATTERN = re.compile(
    r"^(?:\s*\[[^\[\]]*\])+\s*"
)


def normalize_product_name(value: str) -> str:
    """검색·비교용 상품명을 정규화하되 표시용 원문은 변경하지 않는다."""

    normalized_original = " ".join(
        unicodedata.normalize("NFKC", value).casefold().split()
    )
    if not normalized_original:
        return ""

    without_leading_blocks = _LEADING_BRACKET_BLOCKS_PATTERN.sub(
        "", normalized_original, count=1
    )
    normalized = " ".join(without_leading_blocks.split())

    # 상품명이 선두 대괄호 블록만으로 구성된 경우에는 검색 키가
    # 사라지지 않도록 정규화된 원문을 fallback으로 사용한다.
    return normalized or normalized_original

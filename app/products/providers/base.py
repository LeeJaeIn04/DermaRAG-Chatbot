from typing import Protocol
from app.products.models import ProductCandidate


class ProductSearchProviderError(RuntimeError):
    """
    외부 상품 검색 Provider 처리 중 발생한 기본 예외.
    """


class ProductSearchNetworkError(
    ProductSearchProviderError
):
    """
    브라우저 실행, 페이지 이동, 네트워크 응답 실패.
    """


class ProductSearchParsingError(
    ProductSearchProviderError
):
    """
    외부 검색 결과의 필수 필드를 읽지 못한 경우.
    """


class ProductSearchProvider(Protocol):
    provider_name: str

    def search_products(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ProductCandidate]:
        ...

from typing import Protocol
from app.products.models import ProductCandidate


class ProductSearchProvider(Protocol):
    provider_name: str

    def search_products(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ProductCandidate]:
        ...
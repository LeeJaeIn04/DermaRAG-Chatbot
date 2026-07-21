from typing import Protocol
from app.products.models import (
    ProductIngredientResult,
)

class IngredientExtractor(Protocol):
    def extract(
        self,
        product_id: str,
        product_url: str,
    ) -> ProductIngredientResult:

        ...
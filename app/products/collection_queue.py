from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel

from app.products.option_service import ProductOptionService
from app.products.repositories import ProductIngredientRepository


class CollectionQueueRunSummary(BaseModel):
    selected: int
    complete: int
    failed: int


class ProductCollectionQueueService:
    """eligible 상품과 stale lease를 기본 직렬 방식으로 처리한다."""

    def __init__(
        self,
        repository: ProductIngredientRepository,
        option_service: ProductOptionService,
        *,
        max_per_run: int = 10,
        clock: Callable[[], datetime],
    ) -> None:
        if max_per_run <= 0:
            raise ValueError("max_per_run은 1 이상이어야 합니다.")
        self.repository = repository
        self.option_service = option_service
        self.max_per_run = max_per_run
        self.clock = clock

    def run_pending(
        self,
        *,
        max_products: int | None = None,
    ) -> CollectionQueueRunSummary:
        requested = self.max_per_run if max_products is None else max_products
        if requested <= 0:
            raise ValueError("max_products는 1 이상이어야 합니다.")
        limit = min(requested, self.max_per_run)
        items = self.repository.list_collection_queue(
            now=self.clock(),
            limit=limit,
            collecting_lease_timeout_seconds=(
                self.option_service.collecting_lease_timeout_seconds
            ),
        )
        statuses: list[str] = []
        for item in items:
            try:
                result = self.option_service.prepare_product(item.product)
                statuses.append("complete" if result.can_analyze else "failed")
            except Exception:
                statuses.append("failed")
        counts = Counter(statuses)
        return CollectionQueueRunSummary(
            selected=len(items),
            complete=counts["complete"],
            failed=counts["failed"],
        )

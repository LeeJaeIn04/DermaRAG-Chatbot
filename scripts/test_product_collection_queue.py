from datetime import datetime

from app.products.collection_queue import ProductCollectionQueueService
from app.products.models import ProductCandidate
from app.products.option_models import ProductOptionPreparationResult
from app.products.repositories import ProductCollectionQueueItem


NOW = datetime(2026, 8, 4, 12, 0)


def product(index: int) -> ProductCandidate:
    return ProductCandidate(
        product_id=f"QUEUE-{index}",
        product_name=f"합성 큐 상품 {index}",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            f"getGoodsDetail.do?goodsNo=QUEUE-{index}"
        ),
    )


class FakeQueueRepository:
    def __init__(self) -> None:
        self.requested_limit = None

    def list_collection_queue(
        self, *, now, limit, collecting_lease_timeout_seconds
    ):
        self.requested_limit = limit
        return [
            ProductCollectionQueueItem(
                product=product(index),
                status="pending",
                attempt_count=0,
                last_attempt_at=None,
                next_retry_at=None,
            )
            for index in range(limit)
        ]


class FakeOptionService:
    def __init__(self) -> None:
        self.calls = []
        self.collecting_lease_timeout_seconds = 90

    def prepare_product(self, product):
        self.calls.append(product.product_id)
        return ProductOptionPreparationResult(
            requires_option_selection=False,
            can_analyze=True,
            status="not_applicable",
        )


def test_queue_worker_is_serial_and_caps_each_run() -> None:
    repository = FakeQueueRepository()
    option_service = FakeOptionService()
    service = ProductCollectionQueueService(
        repository,
        option_service,
        max_per_run=2,
        clock=lambda: NOW,
    )

    summary = service.run_pending(max_products=10)

    assert repository.requested_limit == 2
    assert option_service.calls == ["QUEUE-0", "QUEUE-1"]
    assert summary.selected == 2
    assert summary.complete == 2

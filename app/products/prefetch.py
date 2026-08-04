from __future__ import annotations

from collections import Counter
from collections.abc import Callable
import time
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, Field, model_validator

from app.products.models import ProductCandidate
from app.products.option_service import ProductOptionService
from app.products.repositories import ProductIngredientRepository


def oliveyoung_product_id(product_url: str) -> str:
    parsed = urlparse(product_url.strip())
    hostname = (parsed.hostname or "").lower()
    ids = parse_qs(parsed.query).get("goodsNo", [])
    if (
        parsed.scheme not in {"http", "https"}
        or not (
            hostname == "oliveyoung.co.kr"
            or hostname.endswith(".oliveyoung.co.kr")
        )
        or not parsed.path.endswith("/store/goods/getGoodsDetail.do")
        or not ids
        or not ids[0].strip()
    ):
        raise ValueError("지원하지 않는 상품 URL입니다.")
    return ids[0].strip()


class PrefetchProductEntry(BaseModel):
    source: str = "oliveyoung"
    external_product_id: str
    product_url: str
    label: str | None = None
    product_name: str | None = None
    brand_name: str | None = None
    category: str | None = None
    category_path: str | None = None
    image_url: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> "PrefetchProductEntry":
        if self.source.strip() != "oliveyoung":
            raise ValueError("source는 oliveyoung만 지원합니다.")
        parsed_id = oliveyoung_product_id(self.product_url)
        if parsed_id != self.external_product_id.strip():
            raise ValueError("URL의 goodsNo와 external_product_id가 다릅니다.")
        return self


class PrefetchResult(BaseModel):
    product_id: str
    status: str
    option_count: int = 0
    error_type: str | None = None


class PrefetchSummary(BaseModel):
    total: int
    collected: int = 0
    cache_hit: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[PrefetchResult] = Field(default_factory=list)


def validate_manifest_entries(
    entries: list[PrefetchProductEntry],
) -> None:
    if not entries:
        raise ValueError("manifest가 비어 있습니다.")
    identities = [
        (entry.source.strip(), entry.external_product_id.strip())
        for entry in entries
    ]
    duplicates = [key for key, count in Counter(identities).items() if count > 1]
    if duplicates:
        raise ValueError("manifest에 중복 상품이 있습니다.")


class ProductPrefetchService:
    def __init__(
        self,
        repository: ProductIngredientRepository,
        option_service: ProductOptionService,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.repository = repository
        self.option_service = option_service
        self.sleeper = sleeper

    def prefetch(
        self,
        entries: list[PrefetchProductEntry],
        *,
        force_refresh: bool = False,
        dry_run: bool = False,
        continue_on_error: bool = False,
        delay_seconds: float = 0.0,
    ) -> PrefetchSummary:
        validate_manifest_entries(entries)
        results: list[PrefetchResult] = []

        for index, entry in enumerate(entries):
            try:
                product = self._candidate(entry)
                cached = self.option_service.cache_service.get_cached_preparation(
                    product
                )
                if dry_run:
                    results.append(
                        PrefetchResult(
                            product_id=product.product_id,
                            status="cache_hit" if cached else "skipped",
                        )
                    )
                    continue
                if cached is not None and not force_refresh:
                    results.append(
                        PrefetchResult(
                            product_id=product.product_id,
                            status="cache_hit",
                            option_count=len(cached.options),
                        )
                    )
                    continue

                prepared = self.option_service.prepare_product(
                    product,
                    force_refresh=force_refresh,
                )
                if not prepared.can_analyze:
                    raise RuntimeError(prepared.status)
                results.append(
                    PrefetchResult(
                        product_id=product.product_id,
                        status="collected",
                        option_count=len(prepared.options),
                    )
                )
            except Exception as error:
                results.append(
                    PrefetchResult(
                        product_id=entry.external_product_id,
                        status="failed",
                        error_type=type(error).__name__,
                    )
                )
                if not continue_on_error:
                    break
            finally:
                if delay_seconds > 0 and index < len(entries) - 1:
                    self.sleeper(delay_seconds)

        counts = Counter(result.status for result in results)
        return PrefetchSummary(
            total=len(entries),
            collected=counts["collected"],
            cache_hit=counts["cache_hit"],
            skipped=counts["skipped"],
            failed=counts["failed"],
            results=results,
        )

    def _candidate(self, entry: PrefetchProductEntry) -> ProductCandidate:
        existing = self.repository.get_product_candidate(
            entry.source, entry.external_product_id
        )
        product_name = (
            entry.product_name
            or entry.label
            or (existing.product_name if existing else None)
        )
        if not product_name:
            raise ValueError(
                "신규 상품에는 product_name 또는 label이 필요합니다."
            )
        return ProductCandidate(
            product_id=entry.external_product_id.strip(),
            source=entry.source.strip(),
            brand_name=entry.brand_name or (existing.brand_name if existing else None),
            product_name=product_name,
            category=entry.category or (existing.category if existing else "unknown"),
            category_path=entry.category_path or (
                existing.category_path if existing else None
            ),
            product_url=entry.product_url.strip(),
            image_url=entry.image_url or (existing.image_url if existing else None),
        )

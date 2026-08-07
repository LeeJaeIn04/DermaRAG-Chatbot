"""인기·실제 수요 상품을 소량 수집하는 선택적 최적화 CLI."""

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from app.config import settings
from app.database import SessionLocal, create_database_tables
from app.products.ingredient_cache_service import ProductIngredientCacheService
from app.products.ingredient_extractors import (
    OliveYoungIngredientExtractor,
    OliveYoungProductOptionExtractor,
)
from app.products.option_service import ProductOptionService
from app.products.prefetch import (
    PrefetchProductEntry,
    ProductPrefetchService,
    oliveyoung_product_id,
    validate_manifest_entries,
)
from app.products.repositories import SQLiteProductIngredientRepository


def load_manifest(path: Path) -> list[PrefetchProductEntry]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("manifest 최상위 값은 배열이어야 합니다.")
    return [PrefetchProductEntry.model_validate(item) for item in data]


def build_service(*, create_tables: bool = True) -> ProductPrefetchService:
    if create_tables:
        create_database_tables()
    repository = SQLiteProductIngredientRepository(SessionLocal)
    ingredient_extractor = OliveYoungIngredientExtractor(
        headless=settings.playwright_headless,
        timeout_ms=settings.product_playwright_timeout_ms,
        deadline_ms=settings.product_playwright_deadline_ms,
        max_attempts=settings.product_playwright_max_attempts,
    )
    cache_service = ProductIngredientCacheService(
        repository,
        ingredient_extractor,
        ttl_days=settings.product_ingredient_ttl_days,
        cache_only_mode=False,
        live_collection_enabled=True,
    )
    option_extractor = OliveYoungProductOptionExtractor(
        ingredient_extractor,
        headless=settings.playwright_headless,
        timeout_ms=settings.product_playwright_timeout_ms,
        deadline_ms=settings.product_playwright_deadline_ms,
        max_attempts=settings.product_playwright_max_attempts,
    )
    return ProductPrefetchService(
        repository,
        ProductOptionService(
            option_extractor,
            cache_service,
            retry_base_seconds=settings.product_collection_retry_base_seconds,
            retry_max_seconds=settings.product_collection_retry_max_seconds,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="인기 또는 실제 검색된 상품만 소량 사전 수집합니다."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--url", action="append")
    parser.add_argument("--label")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument(
        "--max-products",
        type=int,
        default=settings.product_collection_max_per_run,
    )
    parser.add_argument("--delay-seconds", type=float, default=1.0)
    args = parser.parse_args()

    try:
        if not 1 <= args.max_products <= settings.product_collection_max_per_run:
            raise ValueError(
                "max-products가 설정된 실행당 수집 상한을 초과했습니다."
            )
        if args.delay_seconds < 0 or args.delay_seconds > 30:
            raise ValueError("delay-seconds는 0 이상 30 이하여야 합니다.")
        if args.manifest:
            entries = load_manifest(args.manifest)
        else:
            urls = args.url or []
            if len(urls) > 1 and args.label:
                raise ValueError("label은 URL 하나에만 사용할 수 있습니다.")
            entries = [
                PrefetchProductEntry(
                    external_product_id=oliveyoung_product_id(url),
                    product_url=url,
                    label=args.label,
                )
                for url in urls
            ]
        validate_manifest_entries(entries)
        entries = entries[: args.max_products]
        service = build_service(create_tables=not args.dry_run)
        summary = service.prefetch(
            entries,
            force_refresh=args.force_refresh,
            dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
            delay_seconds=0.0 if args.dry_run else args.delay_seconds,
        )
    except (OSError, ValueError, json.JSONDecodeError, ValidationError) as error:
        print(f"[INVALID] error={type(error).__name__}")
        return 2

    for result in summary.results:
        label = result.status.upper().replace("_", " ")
        suffix = (
            f" options={result.option_count}"
            if result.status == "collected"
            else ""
        )
        if result.error_type:
            suffix = f" error={result.error_type}"
        print(f"[{label}] product_id={result.product_id}{suffix}")

    print(
        "SUMMARY "
        f"total={summary.total} collected={summary.collected} "
        f"cache_hit={summary.cache_hit} skipped={summary.skipped} "
        f"failed={summary.failed}"
    )
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Headless 상품 검색/상세/전성분/옵션 수집 1회 smoke test."""

import argparse
import os

from app.config import settings
from app.products.ingredient_extractors import (
    OliveYoungIngredientExtractor,
    OliveYoungProductOptionExtractor,
)
from app.products.providers import OliveYoungProductSearchProvider
from app.products.models import ProductCandidate
from app.products.prefetch import oliveyoung_product_id


def external_smoke_enabled() -> bool:
    return os.getenv("RUN_EXTERNAL_SMOKE_TESTS", "").strip() == "1"


def main() -> int:
    if not external_smoke_enabled():
        print("REFUSED: set RUN_EXTERNAL_SMOKE_TESTS=1")
        return 2

    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--query")
    source.add_argument("--url")
    args = parser.parse_args()

    if args.query:
        provider = OliveYoungProductSearchProvider(
            headless=False,
            timeout_ms=settings.product_playwright_timeout_ms,
            deadline_ms=settings.product_playwright_deadline_ms,
            max_attempts=min(settings.product_playwright_max_attempts, 2),
        )
        try:
            products = provider.search_products(args.query, limit=1)
        except Exception as error:
            print(f"FAIL search: {type(error).__name__}")
            return 1
        if not products:
            print("FAIL search: no_product")
            return 1
        product = products[0]
        print("PASS search")
    else:
        try:
            product_id = oliveyoung_product_id(args.url)
        except ValueError:
            print("FAIL input: invalid_url")
            return 2
        product = ProductCandidate(
            product_id=product_id,
            product_name="headless-smoke",
            product_url=args.url,
        )
    ingredient_extractor = OliveYoungIngredientExtractor(
        headless=False,
        timeout_ms=settings.product_playwright_timeout_ms,
        deadline_ms=settings.product_playwright_deadline_ms,
        max_attempts=min(settings.product_playwright_max_attempts, 2),
    )
    option_extractor = OliveYoungProductOptionExtractor(
        ingredient_extractor=ingredient_extractor,
        headless=False,
        timeout_ms=settings.product_playwright_timeout_ms,
        deadline_ms=settings.product_playwright_deadline_ms,
        max_attempts=min(settings.product_playwright_max_attempts, 2),
    )
    result = option_extractor.extract(
        product.product_id,
        product.product_url,
    )
    if result.status == "failed":
        print("FAIL detail_ingredients_options: collection_failed")
        return 1

    print("PASS detail_ingredients")
    print(f"PASS options: {result.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

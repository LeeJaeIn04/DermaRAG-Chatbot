from __future__ import annotations

import time
import logging
from datetime import datetime, timezone

from playwright.sync_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from app.products.ingredient_extractors.oliveyoung_browser import (
    OliveYoungIngredientExtractor,
)
from app.products.option_models import (
    ProductIngredientRawDocument,
    ProductOption,
    ProductOptionExtractionResult,
)
from app.products.option_parser import (
    PARSER_VERSION,
    make_product_option,
)
from app.products.playwright_runtime import (
    CollectionDeadline,
    CollectionDeadlineExceeded,
    run_browser_operation,
)


logger = logging.getLogger(__name__)


class OliveYoungProductOptionExtractor:
    """리뷰 필터의 옵션명과 상품 고시의 전체 전성분을 수집한다."""

    def __init__(
        self,
        ingredient_extractor: OliveYoungIngredientExtractor,
        *,
        headless: bool = False,
        timeout_ms: int = 60_000,
        deadline_ms: int = 90_000,
        max_attempts: int = 2,
    ) -> None:
        self.ingredient_extractor = ingredient_extractor
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.deadline_ms = deadline_ms
        self.max_attempts = max_attempts

    def extract(
        self,
        product_id: str,
        product_url: str,
    ) -> ProductOptionExtractionResult:
        started_at = time.monotonic()
        ingredient_result = self.ingredient_extractor.extract(
            product_id=product_id,
            product_url=product_url,
        )
        if not ingredient_result.extraction_success:
            return ProductOptionExtractionResult(
                status="failed",
                error_message=(
                    ingredient_result.error_message
                    or "전성분 원문을 찾지 못했습니다."
                ),
            )

        raw_document = ProductIngredientRawDocument(
            source="oliveyoung",
            product_id=product_id,
            raw_text=ingredient_result.raw_ingredients,
            fetched_at=datetime.now(timezone.utc),
            parser_version=PARSER_VERSION,
        )
        remaining_deadline_ms = int(
            self.deadline_ms
            - (time.monotonic() - started_at) * 1_000
        )
        if remaining_deadline_ms <= 0:
            return ProductOptionExtractionResult(
                status="failed",
                raw_document=raw_document,
                error_message="상품 수집 전체 제한 시간이 초과되었습니다.",
            )

        def collect_options(page: Page, deadline: CollectionDeadline):
            stage_timeout = deadline.remaining_ms(self.timeout_ms)
            page.goto(
                product_url,
                wait_until="domcontentloaded",
                timeout=stage_timeout,
            )
            self.ingredient_extractor._dismiss_blocking_layers(page)
            return self._collect_review_options(
                page,
                timeout_ms=deadline.remaining_ms(stage_timeout),
            )

        try:
            options = run_browser_operation(
                collect_options,
                headless=self.headless,
                deadline_ms=remaining_deadline_ms,
                max_attempts=self.max_attempts,
            )
        except (PlaywrightTimeoutError, CollectionDeadlineExceeded) as error:
            logger.warning(
                "Olive Young option collection timed out (%s, headless=%s): %s",
                product_id,
                self.headless,
                error,
            )
            return ProductOptionExtractionResult(
                status="failed",
                raw_document=raw_document,
                error_message=(
                    "올리브영 리뷰 옵션을 제한 시간 안에 수집하지 못했습니다."
                ),
            )
        except Exception as error:
            logger.warning(
                "Olive Young option collection failed (%s, headless=%s): %s",
                product_id,
                self.headless,
                error,
            )
            return ProductOptionExtractionResult(
                status="failed",
                raw_document=raw_document,
                error_message=(
                    "올리브영 리뷰 옵션 DOM을 처리하지 못했습니다."
                ),
            )

        if options is None:
            return ProductOptionExtractionResult(
                status="no_options",
                raw_document=raw_document,
            )
        if not options:
            return ProductOptionExtractionResult(
                status="failed",
                raw_document=raw_document,
                error_message=(
                    "리뷰 상품 옵션 UI는 찾았지만 "
                    "옵션 목록이 비어 있습니다."
                ),
            )

        return ProductOptionExtractionResult(
            status="collected",
            options=options,
            option_count=len(options),
            raw_document=raw_document,
        )

    def _collect_review_options(
        self,
        page: Page,
        timeout_ms: int | None = None,
    ) -> list[ProductOption] | None:
        effective_timeout = timeout_ms or self.timeout_ms
        review_button = self._find_review_button(page, effective_timeout)

        review_button.scroll_into_view_if_needed()
        review_button.click(timeout=effective_timeout)

        review_area = page.locator(
            "oy-review-option-filter"
        ).first
        try:
            review_area.wait_for(
                state="attached",
                timeout=min(effective_timeout, 15_000),
            )
        except PlaywrightTimeoutError:
            # 옵션이 없는 상품은 리뷰 자체는 표시되지만
            # 상품 옵션 필터 custom element가 생성되지 않는다.
            review_option_text = page.locator(
                ".goods-option"
            ).filter(has_text="[옵션]")
            if review_option_text.count() > 0:
                raise RuntimeError(
                    "리뷰에는 옵션 정보가 있지만 상품 옵션 "
                    "필터 UI를 찾지 못했습니다."
                )
            return None

        option_filter_button = page.get_by_text(
            "상품 옵션",
            exact=True,
        ).first
        try:
            option_filter_button.wait_for(
                state="visible",
                timeout=min(effective_timeout, 15_000),
            )
        except PlaywrightTimeoutError:
            review_option_text = page.locator(
                ".goods-option"
            ).filter(has_text="[옵션]")
            if review_option_text.count() > 0:
                raise RuntimeError(
                    "리뷰 옵션 필터의 DOM 구조가 변경되었습니다."
                )
            return None

        option_filter_button.click(timeout=effective_timeout)

        sheet = page.locator(
            "oy-review-goods-option-sheet"
        ).first
        sheet.wait_for(
            state="attached",
            timeout=effective_timeout,
        )

        option_rows = sheet.locator(
            ".goods-option-list li.option"
        )
        option_rows.first.wait_for(
            state="attached",
            timeout=effective_timeout,
        )

        collected: list[ProductOption] = []
        for index in range(option_rows.count()):
            row = option_rows.nth(index)
            option_name = row.locator(
                ".option-name"
            ).inner_text().strip()
            if not option_name:
                continue

            source_option_id = self._source_option_id(row)
            image_url = self._option_image_url(row)
            option = make_product_option(
                option_name,
                source_option_id=source_option_id,
                image_url=image_url,
            )
            collected.append(option)

        return collected

    def _find_review_button(
        self,
        page: Page,
        timeout_ms: int | None = None,
    ) -> Locator:
        review_area_selector = (
            "button[class*='ReviewArea_btn-review']"
        )
        tab_clicked = False

        effective_timeout = timeout_ms or self.timeout_ms
        max_attempts = max(1, min(30, effective_timeout // 500))
        for _ in range(max_attempts):
            candidates = page.locator(review_area_selector)
            for index in range(candidates.count()):
                candidate = candidates.nth(index)
                if candidate.is_visible():
                    return candidate

            if not tab_clicked:
                review_tab = page.locator(
                    "button:has-text('리뷰&셔터')"
                ).first
                if (
                    review_tab.count() > 0
                    and review_tab.is_visible()
                ):
                    review_tab.click(timeout=min(5_000, effective_timeout))
                    tab_clicked = True

            page.evaluate(
                """
                window.scrollBy(
                    0,
                    Math.floor(window.innerHeight * 0.75)
                )
                """
            )
            page.wait_for_timeout(500)

        raise RuntimeError(
            "상품 상세 페이지에서 리뷰 탭을 찾지 못했습니다. "
            "올리브영 DOM 구조가 변경되었을 수 있습니다."
        )

    @staticmethod
    def _source_option_id(row: Locator) -> str | None:
        for attribute in (
            "data-option-id",
            "data-goods-option-id",
            "data-value",
            "value",
        ):
            value = row.get_attribute(attribute)
            if value and value.strip():
                return value.strip()

        nested = row.locator(
            "[data-option-id], [data-goods-option-id], [data-value]"
        ).first
        if nested.count() > 0:
            for attribute in (
                "data-option-id",
                "data-goods-option-id",
                "data-value",
            ):
                value = nested.get_attribute(attribute)
                if value and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _option_image_url(row: Locator) -> str | None:
        image = row.locator(
            "oy-review-optimized-image, img"
        ).first
        if image.count() == 0:
            return None
        for attribute in ("src", "data-src"):
            value = image.get_attribute(attribute)
            if value and value.strip():
                return value.strip()
        return None

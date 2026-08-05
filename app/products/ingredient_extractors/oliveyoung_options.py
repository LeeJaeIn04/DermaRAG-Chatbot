from __future__ import annotations

import logging
from copy import copy
from datetime import datetime, timezone

from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from app.products.ingredient_extractors.oliveyoung_browser import (
    OliveYoungIngredientExtractor,
    _ExistingPageBrowser,
)
from app.products.ingredient_extractors.oliveyoung_option_metadata import (
    DomOptionSnapshot,
    FlightOptionParseResult,
    parse_flight_option_metadata,
    reconcile_dom_and_flight_options,
)
from app.products.option_models import (
    OptionExtractionFailureStage,
    ProductIngredientRawDocument,
    ProductOption,
    ProductOptionExtractionResult,
)
from app.products.option_parser import (
    PARSER_VERSION,
    make_product_option,
    normalize_option_label,
)
from app.products.playwright_runtime import (
    CollectionDeadline,
    CollectionDeadlineExceeded,
    run_browser_operation,
)


logger = logging.getLogger(__name__)

OPTION_BUTTON_SELECTOR = "button[class*='OptionSelector_btn-option']"
OPTION_LIST_SELECTOR = "ul[class*='OptionSelector_option-list']"
OPTION_ROW_SELECTOR = "li[class*='OptionSelector_option-item']"
OPTION_ROW_BUTTON_SELECTOR = (
    "button[class*='OptionSelector_option-item-btn']"
)
OPTION_NAME_SELECTOR = "span[class*='OptionSelector_option-item-tit']"
OPTION_SOLD_OUT_LABEL_SELECTOR = "span[class*='OptionSelector_soldout']"
OPTION_BUTTON_TEXT = "옵션을 선택해 주세요"
SOLD_OUT_CLASS_MARKER = "OptionSelector_is-soldout"


class _OptionCollectionError(RuntimeError):
    def __init__(
        self,
        stage: OptionExtractionFailureStage,
        message: str,
    ) -> None:
        super().__init__(message)
        self.stage = stage


class OliveYoungProductOptionExtractor:
    """상품 선택 UI 옵션과 상품 고시 전성분을 한 세션에서 수집한다."""

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
        normalized_product_id = product_id.strip()
        normalized_product_url = product_url.strip()

        def collect(page: Page, deadline: CollectionDeadline):
            stage_timeout = deadline.remaining_ms(self.timeout_ms)
            page.goto(
                normalized_product_url,
                wait_until="domcontentloaded",
                timeout=stage_timeout,
            )
            self.ingredient_extractor._dismiss_blocking_layers(page)

            script_texts = page.locator("script").all_inner_texts()
            flight_result = parse_flight_option_metadata(
                script_texts,
                product_id=normalized_product_id,
            )
            options, metadata_status = self._collect_product_options(
                page,
                product_id=normalized_product_id,
                flight_result=flight_result,
                timeout_ms=deadline.remaining_ms(stage_timeout),
            )
            self._close_option_list(page)

            bounded_ingredient_extractor = copy(self.ingredient_extractor)
            bounded_ingredient_extractor.timeout_ms = deadline.remaining_ms(
                self.timeout_ms
            )
            ingredient_result = (
                bounded_ingredient_extractor._extract_with_browser(
                    browser=_ExistingPageBrowser(page),
                    product_id=normalized_product_id,
                    product_url=normalized_product_url,
                )
            )
            deadline.remaining_ms(1)
            return options, metadata_status, ingredient_result

        try:
            options, metadata_status, ingredient_result = (
                run_browser_operation(
                    collect,
                    headless=self.headless,
                    deadline_ms=self.deadline_ms,
                    max_attempts=self.max_attempts,
                )
            )
        except _OptionCollectionError as error:
            logger.warning(
                "Olive Young product option collection failed "
                "(%s, stage=%s): %s",
                normalized_product_id,
                error.stage,
                error,
            )
            return ProductOptionExtractionResult(
                status="failed",
                error_message=(
                    "상품 옵션 정보를 정확히 확인하지 못했습니다."
                ),
                failure_stage=error.stage,
                metadata_match_status=(
                    "mismatch"
                    if error.stage == "option_dom_flight_mismatch"
                    else "not_applicable"
                ),
            )
        except (PlaywrightTimeoutError, CollectionDeadlineExceeded) as error:
            logger.warning(
                "Olive Young product collection timed out (%s): %s",
                normalized_product_id,
                error,
            )
            return ProductOptionExtractionResult(
                status="failed",
                error_message=(
                    "상품 정보를 제한 시간 안에 확인하지 못했습니다."
                ),
                failure_stage="ingredient_disclosure_failed",
            )
        except Exception as error:
            logger.warning(
                "Olive Young product collection failed (%s): %s",
                normalized_product_id,
                error,
            )
            return ProductOptionExtractionResult(
                status="failed",
                error_message="상품 정보를 확인하지 못했습니다.",
                failure_stage="ingredient_disclosure_failed",
            )

        if not ingredient_result.extraction_success:
            return ProductOptionExtractionResult(
                status="failed",
                error_message=(
                    ingredient_result.error_message
                    or "전성분 원문을 찾지 못했습니다."
                ),
                metadata_match_status=metadata_status,
                failure_stage="ingredient_disclosure_failed",
            )
        if not ingredient_result.raw_ingredients.strip():
            return ProductOptionExtractionResult(
                status="failed",
                error_message="전성분 항목의 내용이 비어 있습니다.",
                metadata_match_status=metadata_status,
                failure_stage="ingredient_text_empty",
            )

        raw_document = ProductIngredientRawDocument(
            source="oliveyoung",
            product_id=normalized_product_id,
            raw_text=ingredient_result.raw_ingredients,
            fetched_at=datetime.now(timezone.utc),
            parser_version=PARSER_VERSION,
        )
        if options is None:
            return ProductOptionExtractionResult(
                status="no_options",
                raw_document=raw_document,
                metadata_match_status="not_applicable",
            )
        return ProductOptionExtractionResult(
            status="collected",
            options=options,
            option_count=len(options),
            raw_document=raw_document,
            metadata_match_status=metadata_status,
            failure_stage=(
                "flight_parse_failed"
                if metadata_status == "partial_metadata_enrichment"
                else None
            ),
        )

    def _collect_product_options(
        self,
        page: Page,
        *,
        product_id: str,
        flight_result: FlightOptionParseResult,
        timeout_ms: int,
    ) -> tuple[list[ProductOption] | None, str]:
        button = self._visible_option_button(page, timeout_ms=timeout_ms)
        if button is None:
            named_flight_options = [
                option
                for option in flight_result.options
                if normalize_option_label(option.option_name)
            ]
            if len(named_flight_options) > 1:
                raise _OptionCollectionError(
                    "option_button_not_found",
                    "Flight에는 복수 옵션이 있지만 선택 버튼이 없습니다.",
                )
            return None, "not_applicable"

        button_text = button.inner_text().strip()
        if OPTION_BUTTON_TEXT not in button_text:
            raise _OptionCollectionError(
                "option_button_not_found",
                "상품 옵션 선택 버튼의 의미 확인 문구가 다릅니다.",
            )
        button.scroll_into_view_if_needed()
        button.click(timeout=timeout_ms)

        option_list = page.locator(OPTION_LIST_SELECTOR).first
        try:
            option_list.wait_for(state="visible", timeout=timeout_ms)
            rows = option_list.locator(OPTION_ROW_SELECTOR)
            rows.first.wait_for(state="attached", timeout=timeout_ms)
        except PlaywrightTimeoutError as error:
            raise _OptionCollectionError(
                "option_list_render_timeout",
                "상품 옵션 목록의 lazy rendering이 완료되지 않았습니다.",
            ) from error

        dom_options: list[DomOptionSnapshot] = []
        for index in range(rows.count()):
            row = rows.nth(index)
            name = row.locator(OPTION_NAME_SELECTOR).first
            if name.count() == 0:
                raise _OptionCollectionError(
                    "option_dom_parse_failed",
                    "상품 옵션명 요소를 찾지 못했습니다.",
                )
            raw_name = name.inner_text().strip()
            if not raw_name or not normalize_option_label(raw_name):
                raise _OptionCollectionError(
                    "option_dom_parse_failed",
                    "상품 옵션명이 비어 있습니다.",
                )
            row_button = row.locator(OPTION_ROW_BUTTON_SELECTOR).first
            disabled = (
                row_button.is_disabled()
                if row_button.count() > 0
                else None
            )
            row_class = row.get_attribute("class") or ""
            sold_out_label = row.locator(
                OPTION_SOLD_OUT_LABEL_SELECTOR
            ).first
            sold_out_text = (
                sold_out_label.inner_text().strip()
                if sold_out_label.count() > 0
                else None
            )
            dom_options.append(
                DomOptionSnapshot(
                    raw_option_name=raw_name,
                    disabled=disabled,
                    has_sold_out_class=(
                        SOLD_OUT_CLASS_MARKER in row_class
                    ),
                    sold_out_label=sold_out_text,
                    sort_order=index + 1,
                )
            )

        reconciliation = reconcile_dom_and_flight_options(
            dom_options,
            flight_result,
        )
        if reconciliation.status == "mismatch":
            raise _OptionCollectionError(
                "option_dom_flight_mismatch",
                "상품 옵션 DOM과 Flight metadata가 일치하지 않습니다.",
            )

        options: list[ProductOption] = []
        for reconciled in reconciliation.options:
            dom = reconciled.dom
            flight = reconciled.flight
            option_number = flight.option_number if flight else None
            sold_out_flag = (
                flight.sold_out_flag if flight else dom.sold_out
            )
            if dom.sold_out:
                availability = "temporarily_sold_out"
            elif dom.disabled is False:
                availability = "available"
            else:
                availability = "unknown"
            option = make_product_option(
                dom.raw_option_name,
                source_option_id=option_number,
                image_url=flight.image_url if flight else None,
            ).model_copy(
                update={
                    "product_id": product_id,
                    "option_number": option_number,
                    "standard_code": (
                        flight.standard_code if flight else None
                    ),
                    "normalized_option_name": normalize_option_label(
                        dom.raw_option_name
                    ),
                    "availability": availability,
                    "sold_out_flag": sold_out_flag,
                    "dom_disabled": dom.disabled,
                    "sort_order": (
                        flight.sort_order
                        if flight and flight.sort_order is not None
                        else dom.sort_order
                    ),
                    "representative": (
                        flight.representative if flight else None
                    ),
                    "group_path": (
                        list(flight.group_path) if flight else []
                    ),
                    "combination_option_flag": (
                        flight_result.combination_option_flag
                    ),
                }
            )
            options.append(option)
        return options, reconciliation.status

    @staticmethod
    def _visible_option_button(page: Page, *, timeout_ms: int):
        candidates = page.locator(OPTION_BUTTON_SELECTOR)
        try:
            candidates.first.wait_for(
                state="visible",
                timeout=min(timeout_ms, 10_000),
            )
        except PlaywrightTimeoutError:
            pass
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            if candidate.is_visible():
                return candidate
        return None

    @staticmethod
    def _close_option_list(page: Page) -> None:
        try:
            option_list = page.locator(OPTION_LIST_SELECTOR).first
            if option_list.count() > 0 and option_list.is_visible():
                page.keyboard.press("Escape")
                page.wait_for_timeout(100)
        except Exception:
            # 다음 전성분 단계는 같은 페이지를 다시 탐색하므로 닫기 실패가
            # 수집 전체 실패로 이어지지 않게 한다.
            return

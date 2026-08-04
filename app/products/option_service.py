import logging
import math

from app.products.ingredient_cache_service import (
    ProductIngredientCacheService,
)
from app.products.ingredient_parsing import (
    split_raw_ingredient_text,
)
from app.products.ingredient_extractors.oliveyoung_options import (
    OliveYoungProductOptionExtractor,
)
from app.products.models import (
    ProductCandidate,
    ProductIngredientResult,
)
from app.products.option_models import (
    OptionMappingDiagnostics,
    ProductOptionPreparationResult,
)
from app.products.option_parser import (
    PARSER_VERSION,
    canonicalize_product_options,
    split_option_ingredient_sections,
)
from app.products.concurrency import KeyedLockPool
from app.products.repositories import ProductCollectionEntry
from app.products.errors import ProductCollectionRetryLaterError


logger = logging.getLogger(__name__)
_MAX_LOGGED_FAILED_OPTIONS = 5
_MAX_LOGGED_OPTION_NAME_LENGTH = 80


class ProductOptionService:
    def __init__(
        self,
        extractor: OliveYoungProductOptionExtractor,
        cache_service: ProductIngredientCacheService,
        retry_base_seconds: int = 300,
        retry_max_seconds: int = 21_600,
        collecting_lease_timeout_seconds: int | None = None,
    ) -> None:
        if retry_base_seconds <= 0:
            raise ValueError("retry_base_seconds는 1 이상이어야 합니다.")
        if retry_max_seconds < retry_base_seconds:
            raise ValueError(
                "retry_max_seconds는 retry_base_seconds 이상이어야 합니다."
            )
        self.extractor = extractor
        self.cache_service = cache_service
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        extractor_deadline_ms = getattr(extractor, "deadline_ms", 90_000)
        self.collecting_lease_timeout_seconds = (
            collecting_lease_timeout_seconds
            if collecting_lease_timeout_seconds is not None
            else max(1, math.ceil(extractor_deadline_ms / 1_000))
        )
        if self.collecting_lease_timeout_seconds <= 0:
            raise ValueError(
                "collecting lease timeout은 1초 이상이어야 합니다."
            )
        self._collection_locks = KeyedLockPool()

    def prepare_product(
        self,
        product: ProductCandidate,
        *,
        force_refresh: bool = False,
    ) -> ProductOptionPreparationResult:
        if not force_refresh:
            cached = self.cache_service.get_cached_preparation(product)
            if cached is not None:
                return cached

        self.cache_service.ensure_live_collection_allowed()

        collection_key = f"{product.source}:{product.product_id}"
        with self._collection_locks.acquire(collection_key):
            if not force_refresh:
                cached = self.cache_service.get_cached_preparation(product)
                if cached is not None:
                    return cached
            queue = self._start_attempt(product, force=force_refresh)
            if queue is not None and not queue.attempt_started:
                raise ProductCollectionRetryLaterError()
            try:
                result = self._collect_product(product)
            except Exception:
                self._finish_attempt(product, success=False)
                raise
            self._finish_attempt(product, success=result.can_analyze)
            return result

    def _start_attempt(self, product: ProductCandidate, *, force: bool):
        repository = getattr(self.cache_service, "repository", None)
        method = getattr(repository, "start_collection_attempt", None)
        if method is None:
            return None
        return method(
            product,
            now=self.cache_service.current_time(),
            force=force,
            collecting_lease_timeout_seconds=(
                self.collecting_lease_timeout_seconds
            ),
        )

    def _finish_attempt(
        self,
        product: ProductCandidate,
        *,
        success: bool,
    ) -> None:
        repository = getattr(self.cache_service, "repository", None)
        method = getattr(repository, "finish_collection_attempt", None)
        if method is None:
            return
        method(
            product,
            success=success,
            now=self.cache_service.current_time(),
            retry_base_seconds=self.retry_base_seconds,
            retry_max_seconds=self.retry_max_seconds,
        )

    def _collect_product(
        self,
        product: ProductCandidate,
    ) -> ProductOptionPreparationResult:
        extraction = self.extractor.extract(
            product_id=product.product_id,
            product_url=product.product_url,
        )

        if extraction.status == "failed":
            return ProductOptionPreparationResult(
                requires_option_selection=False,
                can_analyze=False,
                status="extraction_failed",
                error_message=extraction.error_message,
            )

        raw_document = extraction.raw_document
        if raw_document is None or not raw_document.raw_text.strip():
            return ProductOptionPreparationResult(
                requires_option_selection=False,
                can_analyze=False,
                status="extraction_failed",
                error_message="전성분 전체 원문을 찾지 못했습니다.",
            )

        if extraction.status == "no_options":
            ingredients = split_raw_ingredient_text(
                raw_document.raw_text
            )
            if not ingredients:
                return ProductOptionPreparationResult(
                    requires_option_selection=False,
                    can_analyze=False,
                    status="extraction_failed",
                    error_message="상품의 전성분 목록이 비어 있습니다.",
                )

            result = ProductIngredientResult(
                    product_id=product.product_id,
                    product_url=product.product_url,
                    raw_ingredients=raw_document.raw_text,
                    ingredients=ingredients,
                    extraction_method=(
                        f"browser_dom:{PARSER_VERSION}:common"
                    ),
                    extraction_success=True,
                )
            self.cache_service.store_collection(
                product,
                entries=[ProductCollectionEntry(result=result)],
                status="not_applicable",
                options=[],
                parser_version=PARSER_VERSION,
            )
            return ProductOptionPreparationResult(
                requires_option_selection=False,
                can_analyze=True,
                status="not_applicable",
            )

        canonical_options = canonicalize_product_options(
            extraction.options
        )
        sections = split_option_ingredient_sections(
            raw_document.raw_text,
            canonical_options,
        )
        sections_by_key = {
            section.internal_option_key: section
            for section in sections
        }
        matched_options = []
        collection_entries: list[ProductCollectionEntry] = []

        status_counts = {
            "matched": 0,
            "unmatched": 0,
            "ambiguous": 0,
            "unsupported": 0,
        }
        for section in sections:
            status_counts[section.mapping_status] += 1
        diagnostics = OptionMappingDiagnostics(
            collected_option_count=len(extraction.options),
            matched_count=status_counts["matched"],
            unmatched_count=status_counts["unmatched"],
            ambiguous_count=status_counts["ambiguous"],
            unsupported_count=status_counts["unsupported"],
            collected_raw_option_count=len(extraction.options),
            canonical_option_count=len(canonical_options),
            merged_duplicate_count=(
                len(extraction.options) - len(canonical_options)
            ),
            matched_canonical_count=status_counts["matched"],
            unmatched_canonical_count=status_counts["unmatched"],
            duplicate_header_count=sum(
                section.duplicate_header_count
                for section in sections
            ),
        )

        for option in canonical_options:
            section = sections_by_key[option.internal_option_key]
            if (
                section.mapping_status != "matched"
                or not section.ingredients
            ):
                continue

            mapped_option = option.model_copy(
                update={
                    "mapping_status": "matched",
                    "mapping_confidence": (
                        section.mapping_confidence
                    ),
                }
            )
            matched_options.append(mapped_option)
            collection_entries.append(
                ProductCollectionEntry(
                    result=ProductIngredientResult(
                        product_id=product.product_id,
                        product_url=product.product_url,
                        raw_ingredients=(
                            section.raw_ingredient_text
                        ),
                        ingredients=section.ingredients,
                        extraction_method=(
                            f"browser_dom:{PARSER_VERSION}:"
                            f"{section.mapping_method}"
                        ),
                        extraction_success=True,
                    ),
                    option_id=option.internal_option_key,
                    option_name=option.option_name,
                )
            )

        if (
            not matched_options
            or len(matched_options) != len(canonical_options)
        ):
            failed_names = [
                " ".join(section.option_name.split())[
                    :_MAX_LOGGED_OPTION_NAME_LENGTH
                ]
                for section in sections
                if section.mapping_status != "matched"
            ][:_MAX_LOGGED_FAILED_OPTIONS]
            logger.warning(
                "Product option mapping incomplete "
                "(source=%s, product_id=%s, raw=%d, canonical=%d, "
                "merged=%d, matched=%d, unmatched=%d, ambiguous=%d, "
                "unsupported=%d, duplicate_headers=%d, "
                "failed_options=%r)",
                product.source,
                product.product_id,
                diagnostics.collected_raw_option_count,
                diagnostics.canonical_option_count,
                diagnostics.merged_duplicate_count,
                diagnostics.matched_canonical_count,
                diagnostics.unmatched_canonical_count,
                diagnostics.ambiguous_count,
                diagnostics.unsupported_count,
                diagnostics.duplicate_header_count,
                failed_names,
            )
            return ProductOptionPreparationResult(
                requires_option_selection=False,
                can_analyze=False,
                status="mapping_failed",
                error_message=(
                    "이 상품의 모든 옵션별 전성분을 정확히 "
                    "구분하지 못했습니다. 현재는 옵션별 "
                    "분석을 진행할 수 없습니다."
                ),
                mapping_diagnostics=diagnostics,
            )

        logger.info(
            "Product option mapping complete "
            "(source=%s, product_id=%s, raw=%d, canonical=%d, "
            "merged=%d, matched=%d, unmatched=%d, ambiguous=%d, "
            "unsupported=%d, duplicate_headers=%d)",
            product.source,
            product.product_id,
            diagnostics.collected_raw_option_count,
            diagnostics.canonical_option_count,
            diagnostics.merged_duplicate_count,
            diagnostics.matched_canonical_count,
            diagnostics.unmatched_canonical_count,
            diagnostics.ambiguous_count,
            diagnostics.unsupported_count,
            diagnostics.duplicate_header_count,
        )
        self.cache_service.store_collection(
            product,
            entries=collection_entries,
            status="ready",
            options=matched_options,
            parser_version=PARSER_VERSION,
        )

        return ProductOptionPreparationResult(
            requires_option_selection=True,
            options=matched_options,
            can_analyze=True,
            status="ready",
            mapping_diagnostics=diagnostics,
        )

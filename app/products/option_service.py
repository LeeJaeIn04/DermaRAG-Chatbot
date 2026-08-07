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
    ProductOption,
    ProductOptionPreparationResult,
)
from app.products.option_parser import (
    PARSER_VERSION,
    OptionFullSectionParseResult,
    OptionIngredientSection,
    ShadowParseResult,
    canonicalize_product_options,
    parse_option_full_sections,
    shadow_parse_option_ingredient_sections,
)
from app.products.parser_state import (
    ParserResult,
    ParserSelectionResult,
    build_option_level_result,
    build_parser_result,
    select_safe_parser_result,
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
        shadow_observation_enabled: bool = False,
        selected_parser_result_enabled: bool = False,
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
        self.shadow_observation_enabled = shadow_observation_enabled
        # Step 6: true면 selector가 고른 결과(production 또는 shadow)를
        # effective result로 써서 응답/저장에 그대로 반영한다. 이
        # flag가 켜지면 production이 partial/failed일 때 shadow_
        # observation_enabled가 꺼져 있어도 shadow를 실행한다(선택
        # 판단 자체에 필요하기 때문).
        self.selected_parser_result_enabled = (
            selected_parser_result_enabled
        )
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

    def _run_shadow_parser(
        self,
        product: ProductCandidate,
        raw_text: str,
        canonical_options: list,
    ) -> ShadowParseResult | None:
        try:
            return shadow_parse_option_ingredient_sections(
                raw_text,
                canonical_options,
            )
        except Exception:
            logger.warning(
                "Shadow option parser failed "
                "(source=%s, product_id=%s)",
                product.source,
                product.product_id,
                exc_info=True,
            )
            return None

    def _log_shadow_comparison(
        self,
        product: ProductCandidate,
        parse_result: OptionFullSectionParseResult,
        production_status_counts: dict[str, int],
        shadow_result: ShadowParseResult,
    ) -> None:
        shadow_status_counts = {
            "matched": shadow_result.matched_count,
            "unmatched": shadow_result.unmatched_count,
            "ambiguous": shadow_result.ambiguous_count,
            "unsupported": shadow_result.unsupported_count,
        }
        status_diff = {
            status: (
                production_status_counts[status]
                - shadow_status_counts[status]
            )
            for status in production_status_counts
            if production_status_counts[status]
            != shadow_status_counts[status]
        }
        format_diff = parse_result.document_format != (
            shadow_result.document_format
        )
        # 상세 진단(옵션별/format 단위)은 DEBUG로만 남긴다 - 상품당
        # INFO 로그는 _log_selector_observation 1건으로 제한한다.
        logger.debug(
            "Shadow option parser diagnostics "
            "(product_id=%s, production_format=%s, "
            "production_status_counts=%s, shadow_format=%s, "
            "shadow_section_count=%d, shadow_status_counts=%s, "
            "shadow_orphan_count=%d, format_diff=%s, "
            "status_diff=%s)",
            product.product_id,
            parse_result.document_format,
            production_status_counts,
            shadow_result.document_format,
            len(shadow_result.sections),
            shadow_status_counts,
            shadow_result.orphan_section_count,
            format_diff,
            status_diff,
        )

    def _build_production_parser_result(
        self,
        canonical_options: list[ProductOption],
        sections_by_key: dict[str, OptionIngredientSection],
    ) -> ParserResult:
        """production 결과를 Step 1 공통 형식으로 변환한다. option_id는
        production/shadow가 동일한 canonical_options 목록에서 얻은
        internal_option_key(정규화된 옵션명의 결정적 해시)를 그대로
        쓴다 - 두 parser가 같은 실제 옵션에 항상 같은 id를 매기는
        전제 조건이다."""

        option_results = [
            build_option_level_result(
                option_id=option.internal_option_key,
                option_name=option.option_name,
                mapping_status=(
                    sections_by_key[option.internal_option_key].mapping_status
                ),
                ingredients=(
                    sections_by_key[option.internal_option_key].ingredients
                ),
            )
            for option in canonical_options
        ]
        return build_parser_result("production", option_results)

    def _build_shadow_parser_result(
        self,
        canonical_options: list[ProductOption],
        shadow_result: ShadowParseResult,
    ) -> ParserResult:
        """shadow 결과를 Step 1 공통 형식으로 변환한다. production과
        동일한 canonical_options을 순회하므로 option_id도 동일하다."""

        mapping_by_key = {
            mapping.internal_option_key: mapping
            for mapping in shadow_result.mappings
        }

        option_results = []
        for option in canonical_options:
            mapping = mapping_by_key.get(option.internal_option_key)
            if mapping is None:
                option_results.append(
                    build_option_level_result(
                        option_id=option.internal_option_key,
                        option_name=option.option_name,
                        mapping_status="unmatched",
                        ingredients=(),
                    )
                )
                continue

            ingredients: tuple[str, ...] = ()
            if (
                mapping.mapping_status == "matched"
                and mapping.section_index is not None
            ):
                ingredients = tuple(
                    shadow_result.sections[
                        mapping.section_index
                    ].ingredients
                )

            option_results.append(
                build_option_level_result(
                    option_id=option.internal_option_key,
                    option_name=option.option_name,
                    mapping_status=mapping.mapping_status,
                    ingredients=ingredients,
                )
            )
        return build_parser_result("shadow", option_results)

    def _build_effective_collection_entries(
        self,
        product: ProductCandidate,
        canonical_options: list[ProductOption],
        effective_result: ParserResult,
    ) -> tuple[list[ProductOption], list[ProductCollectionEntry]]:
        """Step 6: selector가 고른 effective result(선택된 shadow)의
        ready 옵션만으로 API 응답 옵션 목록과 cache 저장용 entries를
        만든다. production 경로가 이미 만든 matched_options/
        collection_entries를 대체하는 용도로만 쓰며, parser를 다시
        실행하지 않고 이미 계산된 OptionLevelResult.ingredients만
        읽는다."""

        result_by_id = {
            option_result.option_id: option_result
            for option_result in effective_result.options
        }
        matched_options: list[ProductOption] = []
        collection_entries: list[ProductCollectionEntry] = []
        for option in canonical_options:
            option_result = result_by_id.get(option.internal_option_key)
            if option_result is None or option_result.status != "ready":
                continue

            ingredients = list(option_result.ingredients)
            mapped_option = option.model_copy(
                update={
                    "mapping_status": "matched",
                    "mapping_confidence": 1.0,
                    "status": "ready",
                    "analysis_available": True,
                }
            )
            matched_options.append(mapped_option)
            collection_entries.append(
                ProductCollectionEntry(
                    result=ProductIngredientResult(
                        product_id=product.product_id,
                        product_url=product.product_url,
                        raw_ingredients=", ".join(ingredients),
                        ingredients=ingredients,
                        extraction_method=(
                            f"browser_dom:{PARSER_VERSION}:"
                            "selected_shadow"
                        ),
                        extraction_success=True,
                    ),
                    option_id=option.internal_option_key,
                    option_name=option.option_name,
                )
            )
        return matched_options, collection_entries

    def _log_selector_observation(
        self,
        product: ProductCandidate,
        selection: ParserSelectionResult,
    ) -> None:
        """production/shadow 상태, ready 수, 선택된 parser, 이유만
        로그에 남긴다. 옵션명/전성분 목록은 남기지 않는다(대량 로그
        금지)."""

        production_ready = sum(
            1
            for option in selection.production.options
            if option.status == "ready"
        )
        shadow_ready = (
            sum(
                1
                for option in selection.shadow.options
                if option.status == "ready"
            )
            if selection.shadow is not None
            else None
        )
        logger.info(
            "Shadow selector observation "
            "(source=%s, product_id=%s, production_status=%s, "
            "production_option_count=%d, production_ready=%d, "
            "shadow_status=%s, shadow_ready=%s, selected=%s, "
            "reason=%s)",
            product.source,
            product.product_id,
            selection.production.collection_status,
            len(selection.production.options),
            production_ready,
            selection.shadow.collection_status if selection.shadow else None,
            shadow_ready,
            selection.selected,
            selection.reason,
        )

    def _log_selector_observation_detail(
        self,
        product: ProductCandidate,
        production: ParserResult,
        shadow: ParserResult,
    ) -> None:
        """옵션별 상세는 DEBUG에만 남긴다. option_id와 상태값만
        기록하고, 옵션명·성분·원문 HTML은 절대 남기지 않는다."""

        shadow_status_by_id = {
            option.option_id: option.status for option in shadow.options
        }
        detail = [
            {
                "option_id": option.option_id,
                "production_status": option.status,
                "shadow_status": shadow_status_by_id.get(option.option_id),
            }
            for option in production.options
        ]
        logger.debug(
            "Shadow selector observation detail "
            "(source=%s, product_id=%s, options=%s)",
            product.source,
            product.product_id,
            detail,
        )

    def _observe_shadow_selection(
        self,
        product: ProductCandidate,
        raw_text: str,
        canonical_options: list[ProductOption],
        parse_result: OptionFullSectionParseResult,
        production_status_counts: dict[str, int],
        production_parser_result: ParserResult,
    ) -> ParserSelectionResult | None:
        """shadow를 실행하고 selector 판단을 로그에 남긴다.

        Step 2 관찰 모드에서는 이 반환값을 쓰지 않는다(cache 저장이나
        API 응답에 절대 반영하지 않는다). Step 6에서
        selected_parser_result_enabled가 켜져 있을 때만 호출부가 이
        반환값을 읽어 effective result를 고른다 - selector 정책
        (select_safe_parser_result)은 그대로이며 여기서 다시
        계산하지 않는다. shadow 실행이나 selector 판단 중 어떤
        예외가 나도 production 흐름을 막지 않도록 여기서 흡수하고
        None을 반환한다(= production으로 자동 fallback).
        """

        shadow_result = self._run_shadow_parser(
            product, raw_text, canonical_options
        )
        if shadow_result is None:
            return None

        self._log_shadow_comparison(
            product,
            parse_result,
            production_status_counts,
            shadow_result,
        )

        try:
            shadow_parser_result = self._build_shadow_parser_result(
                canonical_options, shadow_result
            )
            selection = select_safe_parser_result(
                production_parser_result, shadow_parser_result
            )
            self._log_selector_observation(product, selection)
            self._log_selector_observation_detail(
                product, production_parser_result, shadow_parser_result
            )
            return selection
        except Exception:
            logger.warning(
                "Shadow selector observation failed "
                "(source=%s, product_id=%s)",
                product.source,
                product.product_id,
                exc_info=True,
            )
            return None

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
        parse_result = parse_option_full_sections(
            raw_document.raw_text,
            canonical_options,
        )
        sections = list(parse_result.sections)

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

        # production 결과를 Step 1 공통 형식으로 한 번만 만들어
        # shadow 관찰과 Step 3 option-level cache 저장에서 함께
        # 재사용한다(재계산하지 않는다). 이 값을 만드는 것 자체가
        # 실패해도 production 흐름은 막지 않는다.
        try:
            production_parser_result = self._build_production_parser_result(
                canonical_options, sections_by_key
            )
        except Exception:
            production_parser_result = None
            logger.warning(
                "Building production ParserResult failed "
                "(source=%s, product_id=%s)",
                product.source,
                product.product_id,
                exc_info=True,
            )

        # Shadow parser + Step 1 selector: production이 이미 ready
        # (모든 옵션 매핑 성공)면 shadow를 실행하지 않는다. 그 외에는
        # shadow_observation_enabled(관찰만) 또는
        # selected_parser_result_enabled(effective result 선택에
        # 필요) 둘 중 하나만 켜져 있어도 실행한다. 실행/판단 중
        # 예외가 나면 여기서 전부 흡수해 production 흐름을 막지
        # 않는다 - selection은 None으로 남아 아래에서 자동으로
        # production으로 fallback한다.
        selection: ParserSelectionResult | None = None
        if (
            (
                self.shadow_observation_enabled
                or self.selected_parser_result_enabled
            )
            and production_parser_result is not None
            and production_parser_result.collection_status != "ready"
        ):
            try:
                selection = self._observe_shadow_selection(
                    product,
                    raw_document.raw_text,
                    canonical_options,
                    parse_result,
                    status_counts,
                    production_parser_result,
                )
            except Exception:
                selection = None
                logger.warning(
                    "Shadow observation setup failed "
                    "(source=%s, product_id=%s)",
                    product.source,
                    product.product_id,
                    exc_info=True,
                )

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
            orphan_document_section_count=(
                parse_result.orphan_document_section_count
            ),
            malformed_header_count=parse_result.malformed_header_count,
            ambiguous_header_count=parse_result.ambiguous_header_count,
            document_format=parse_result.document_format,
            structure_reason=parse_result.structure_reason,
            top_level_header_count=parse_result.top_level_header_count,
            nested_header_count=parse_result.nested_header_count,
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
                    "status": "ready",
                    "analysis_available": True,
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

        # Step 6: selected_parser_result_enabled가 켜져 있고 selector가
        # shadow를 선택했을 때만 effective result를 shadow로 바꾼다.
        # selector 정책(select_safe_parser_result)은 다시 계산하지
        # 않고 위에서 이미 만든 selection을 그대로 읽기만 한다. 위에서
        # production 기준으로 채운 matched_options/collection_entries를
        # 여기서 완전히 교체해야(추가가 아니라 대체) 아래의 기존
        # ready/partial 분기·cache 저장 로직이 수정 없이 그대로
        # effective result를 따라간다.
        #
        # selection.shadow(Step 1이 이미 만든 ParserResult)를 재포장
        # 없이 그대로 effective result로 쓴다 - source="shadow"인
        # provenance를 잃지 않는다. repository/cache_service는
        # source가 "production" 또는 "shadow"인 결과만 저장을
        # 허용하며, 선택되지 않은 raw shadow가 이 분기 밖에서 여기로
        # 들어올 수는 없다(이 분기 자체가 selector가 승인한 경우에만
        # 진입하는 통제된 경로다).
        effective_parser_result = production_parser_result
        if (
            self.selected_parser_result_enabled
            and selection is not None
            and selection.selected == "shadow"
        ):
            matched_options, collection_entries = (
                self._build_effective_collection_entries(
                    product, canonical_options, selection.shadow
                )
            )
            effective_parser_result = selection.shadow

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
                "unsupported=%d, duplicate_headers=%d, orphans=%d, "
                "malformed_headers=%d, ambiguous_headers=%d, "
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
                diagnostics.orphan_document_section_count,
                diagnostics.malformed_header_count,
                diagnostics.ambiguous_header_count,
                failed_names,
            )
            is_partial = (
                effective_parser_result is not None
                and effective_parser_result.collection_status == "partial"
            )
            # Step 3 option-level cache: 일부만 ready인 partial
            # 결과도 신규 컬럼에는 저장한다(legacy 저장은 그대로
            # mapping_failed다 - 기존 실패 캐시 정책은 바꾸지 않는다).
            # collection_status가 완전 failed(ready 0개)면 저장하지
            # 않는다 - 기존에도 완전 실패는 캐시하지 않았다. Step 6에서
            # selector가 shadow를 골랐다면 effective_parser_result는
            # selection.shadow(source="shadow") 그 자체이므로, 여기서
            # 저장되는 값도 항상 selector가 승인한 결과이며
            # provenance도 그대로 보존된다(선택되지 않은 raw shadow는
            # 저장되지 않는다). 저장 자체가 실패해도 이 응답에는
            # 영향을 주지 않는다.
            if is_partial:
                try:
                    self.cache_service.store_option_cache_snapshot(
                        product,
                        production_parser_result=effective_parser_result,
                        parser_version=PARSER_VERSION,
                    )
                except Exception:
                    logger.warning(
                        "Option-level cache partial snapshot save failed "
                        "(source=%s, product_id=%s)",
                        product.source,
                        product.product_id,
                        exc_info=True,
                    )

            # Step 4: partial이면 ready/non-ready 옵션을 전부 응답에
            # 담아 ready 옵션만 분석에 쓸 수 있게 한다. 완전 실패
            # (ready 0개)는 기존과 동일하게 빈 목록/분석 불가로
            # 남긴다. Step 6에서 shadow가 effective면 ready 판정도
            # shadow 기준이다.
            using_shadow_effective = (
                effective_parser_result is not None
                and effective_parser_result is not production_parser_result
            )
            partial_options: list[ProductOption] = []
            if is_partial:
                status_by_key = {
                    option.option_id: option.status
                    for option in effective_parser_result.options
                }
                for option in canonical_options:
                    section = sections_by_key[option.internal_option_key]
                    option_status = status_by_key.get(
                        option.internal_option_key, "error"
                    )
                    if option_status == "ready":
                        confidence = (
                            1.0
                            if using_shadow_effective
                            else section.mapping_confidence
                        )
                        partial_options.append(
                            option.model_copy(
                                update={
                                    "mapping_status": "matched",
                                    "mapping_confidence": confidence,
                                    "status": "ready",
                                    "analysis_available": True,
                                }
                            )
                        )
                    else:
                        partial_options.append(
                            option.model_copy(
                                update={
                                    "status": option_status,
                                    "analysis_available": False,
                                }
                            )
                        )

            return ProductOptionPreparationResult(
                requires_option_selection=is_partial,
                options=partial_options,
                can_analyze=is_partial,
                status="mapping_failed",
                error_message=(
                    None
                    if is_partial
                    else (
                        "이 상품의 모든 옵션별 전성분을 정확히 "
                        "구분하지 못했습니다. 현재는 옵션별 "
                        "분석을 진행할 수 없습니다."
                    )
                ),
                collection_status=(
                    effective_parser_result.collection_status
                    if effective_parser_result is not None
                    else None
                ),
                mapping_diagnostics=diagnostics,
            )

        logger.info(
            "Product option mapping complete "
            "(source=%s, product_id=%s, raw=%d, canonical=%d, "
            "merged=%d, matched=%d, unmatched=%d, ambiguous=%d, "
            "unsupported=%d, duplicate_headers=%d, orphans=%d, "
            "malformed_headers=%d, ambiguous_headers=%d)",
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
            diagnostics.orphan_document_section_count,
            diagnostics.malformed_header_count,
            diagnostics.ambiguous_header_count,
        )
        # Step 3/6 option-level cache: effective_parser_result만
        # 넘긴다 - flag가 꺼져 있거나 selector가 production을
        # 골랐으면 production 그대로이고, selector가 shadow를
        # 골랐을 때만(Step 6, controlled path) selection.shadow
        # 그 자체(source="shadow", 재포장 없음)다. 선택되지 않은
        # raw shadow 결과는 여기 절대 들어오지 않는다. cache_service가
        # option_level_cache_enabled를 보고 실제로 저장할지 최종
        # 결정한다.
        self.cache_service.store_collection(
            product,
            entries=collection_entries,
            status="ready",
            options=matched_options,
            parser_version=PARSER_VERSION,
            production_parser_result=effective_parser_result,
        )

        return ProductOptionPreparationResult(
            requires_option_selection=True,
            options=matched_options,
            can_analyze=True,
            status="ready",
            collection_status=(
                effective_parser_result.collection_status
                if effective_parser_result is not None
                else None
            ),
            mapping_diagnostics=diagnostics,
        )

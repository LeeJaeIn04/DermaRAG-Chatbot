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
    ProductOptionPreparationResult,
)
from app.products.option_parser import (
    PARSER_VERSION,
    split_option_ingredient_sections,
)


class ProductOptionService:
    def __init__(
        self,
        extractor: OliveYoungProductOptionExtractor,
        cache_service: ProductIngredientCacheService,
    ) -> None:
        self.extractor = extractor
        self.cache_service = cache_service

    def prepare_product(
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

            self.cache_service.store_extracted(
                product,
                ProductIngredientResult(
                    product_id=product.product_id,
                    product_url=product.product_url,
                    raw_ingredients=raw_document.raw_text,
                    ingredients=ingredients,
                    extraction_method=(
                        f"browser_dom:{PARSER_VERSION}:common"
                    ),
                    extraction_success=True,
                ),
            )
            return ProductOptionPreparationResult(
                requires_option_selection=False,
                can_analyze=True,
                status="not_applicable",
            )

        sections = split_option_ingredient_sections(
            raw_document.raw_text,
            extraction.options,
        )
        sections_by_key = {
            section.internal_option_key: section
            for section in sections
        }
        matched_options = []

        for option in extraction.options:
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
            self.cache_service.store_extracted(
                product,
                ProductIngredientResult(
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

        if not matched_options:
            return ProductOptionPreparationResult(
                requires_option_selection=False,
                can_analyze=False,
                status="mapping_failed",
                error_message=(
                    "이 상품의 옵션별 전성분을 정확히 "
                    "구분하지 못했습니다. 현재는 옵션별 "
                    "분석을 진행할 수 없습니다."
                ),
            )

        return ProductOptionPreparationResult(
            requires_option_selection=True,
            options=matched_options,
            can_analyze=True,
            status="ready",
        )

from app.products.models import ProductCandidate
from app.products.option_models import (
    ProductIngredientRawDocument,
    ProductOptionExtractionResult,
)
from app.products.option_parser import (
    PARSER_VERSION,
    make_product_option,
)
from app.products.option_service import ProductOptionService


def _product() -> ProductCandidate:
    return ProductCandidate(
        product_id="A000000000001",
        source="oliveyoung",
        product_name="옵션 테스트 상품",
        category="color_makeup",
        product_url=(
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000000001"
        ),
    )


class FakeOptionExtractor:
    def __init__(self, result: ProductOptionExtractionResult) -> None:
        self.result = result

    def extract(self, product_id: str, product_url: str):
        return self.result


class FakeCacheService:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    def store_extracted(self, product, result, **kwargs):
        self.saved.append(
            {
                "product": product,
                "result": result,
                **kwargs,
            }
        )


def _raw_document(raw_text: str) -> ProductIngredientRawDocument:
    return ProductIngredientRawDocument(
        source="oliveyoung",
        product_id="A000000000001",
        raw_text=raw_text,
        parser_version=PARSER_VERSION,
    )


def test_optionless_product_keeps_common_ingredient_flow() -> None:
    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="no_options",
                raw_document=_raw_document(
                    "정제수, 글리세린, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.status == "not_applicable"
    assert result.requires_option_selection is False
    assert result.can_analyze is True
    assert cache.saved[0].get("option_id", "") == ""


def test_romand_no_option_product_keeps_common_ingredient_flow() -> None:
    """롬앤 등 옵션 필터가 없는 상품은 기존 공통 전성분 흐름을 유지해야 한다."""

    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="no_options",
                raw_document=_raw_document(
                    "정제수, 다이메티콘, 글리세린, 나이아신아마이드, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.status == "not_applicable"
    assert result.requires_option_selection is False
    assert result.can_analyze is True
    assert cache.saved[0].get("option_id", "") == ""
    assert cache.saved[0]["result"].ingredients == [
        "정제수",
        "다이메티콘",
        "글리세린",
        "나이아신아마이드",
        "향료",
    ]


def test_only_matched_options_are_returned_and_cached() -> None:
    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[
                    make_product_option("19호"),
                    make_product_option("21호"),
                ],
                raw_document=_raw_document(
                    "[19호] 정제수, 글리세린, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.requires_option_selection is True
    assert [option.option_name for option in result.options] == ["19호"]
    assert len(cache.saved) == 1
    assert (
        cache.saved[0]["option_id"]
        == result.options[0].internal_option_key
    )


def test_all_mapping_failures_block_analysis() -> None:
    cache = FakeCacheService()
    service = ProductOptionService(
        extractor=FakeOptionExtractor(
            ProductOptionExtractionResult(
                status="collected",
                options=[make_product_option("21호")],
                raw_document=_raw_document(
                    "[19호] 정제수, 글리세린, 향료"
                ),
            )
        ),
        cache_service=cache,
    )

    result = service.prepare_product(_product())

    assert result.status == "mapping_failed"
    assert result.can_analyze is False
    assert result.options == []
    assert cache.saved == []

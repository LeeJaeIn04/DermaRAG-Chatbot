import sys

from app.products.option_models import (
    ProductIngredientRawDocument,
    ProductOptionExtractionResult,
)
from scripts import smoke_product_collection_headless as smoke


def test_external_smoke_refuses_without_opt_in(monkeypatch) -> None:
    monkeypatch.delenv("RUN_EXTERNAL_SMOKE_TESTS", raising=False)
    assert smoke.main() == 2


def test_external_smoke_opt_in_enters_mocked_collection(monkeypatch) -> None:
    monkeypatch.setenv("RUN_EXTERNAL_SMOKE_TESTS", "1")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smoke",
            "--url",
            "https://www.oliveyoung.co.kr/store/goods/"
            "getGoodsDetail.do?goodsNo=A000000000001",
        ],
    )

    modes = []

    class FakeIngredientExtractor:
        def __init__(self, **kwargs) -> None:
            modes.append(kwargs["headless"])

    class FakeOptionExtractor:
        def __init__(self, ingredient_extractor, **kwargs) -> None:
            pass

        def extract(self, product_id, product_url):
            return ProductOptionExtractionResult(
                status="no_options",
                raw_document=ProductIngredientRawDocument(
                    source="oliveyoung",
                    product_id=product_id,
                    raw_text="정제수, 글리세린",
                    parser_version="test",
                ),
            )

    monkeypatch.setattr(smoke, "OliveYoungIngredientExtractor", FakeIngredientExtractor)
    monkeypatch.setattr(smoke, "OliveYoungProductOptionExtractor", FakeOptionExtractor)
    assert smoke.main() == 0
    assert modes == [True]

from app.products.ingredient_extractors import (
    OliveYoungIngredientExtractor,
)


PRODUCT_ID = "A000000149135"

PRODUCT_URL = (
    "https://www.oliveyoung.co.kr/store/goods/"
    "getGoodsDetail.do?goodsNo=A000000149135"
)


def test_rejects_non_oliveyoung_url() -> None:
    """
    올리브영이 아닌 URL은 브라우저를 열기 전에 거부해야 한다.
    """

    extractor = OliveYoungIngredientExtractor(
        headless=True,
    )

    result = extractor.extract(
        product_id="TEST-001",
        product_url="https://example.com/product",
    )

    assert result.extraction_success is False
    assert result.raw_ingredients == ""
    assert result.ingredients == []
    assert result.error_message is not None


def test_extracts_oliveyoung_ingredients() -> None:
    """
    실제 올리브영 상품 페이지에서 전성분을 추출한다.

    외부 사이트 상태에 영향을 받는 통합 테스트이므로
    일반 단위 테스트보다 실행 시간이 길 수 있다.
    """

    extractor = OliveYoungIngredientExtractor(
        # 처음에는 브라우저 동작을 확인하기 위해
        # 창이 보이도록 False로 둔다.
        headless=False,
    )

    result = extractor.extract(
        product_id=PRODUCT_ID,
        product_url=PRODUCT_URL,
    )

    # 문제가 생겼을 때 터미널에서 원인을 확인한다.
    print()
    print("추출 성공:", result.extraction_success)
    print("오류:", result.error_message)
    print("성분 개수:", len(result.ingredients))
    print("전성분:", result.raw_ingredients)

    assert result.extraction_success is True
    assert result.raw_ingredients
    assert result.ingredients
    assert "정제수" in result.ingredients
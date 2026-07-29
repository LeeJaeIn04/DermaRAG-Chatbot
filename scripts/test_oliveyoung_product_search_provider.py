from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.products.providers.base import (
    ProductSearchParsingError,
)
from app.products.providers.oliveyoung import (
    OliveYoungProductSearchProvider,
)


PRODUCT_CARD_HTML = """
<li class="flag li_result">
  <div class="prd_info">
    <a class="prd_thumb"
       href="https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo=A000000172128&amp;dispCatNo=1000001000200060001&amp;trackingCd=Result_3">
      <img src="https://image.oliveyoung.co.kr/products/lip-balm.jpg"
           alt="이미지 썸네일">
    </a>
    <div class="prd_name">
      <a href="javascript:void(0)">
        <span class="tx_brand">에뛰드</span>
        <p class="tx_name">에뛰드 진저슈가 립밤 스틱 3.7g</p>
      </a>
    </div>
    <button data-ref-goodscategory="색조화장품 > 립 메이크업 > 립케어">
      찜하기
    </button>
    <p class="prd_price">
      <span class="tx_org">
        <span class="tx_num">8,000</span>원
      </span>
      <span class="tx_cur">
        <span class="tx_num">7,200</span>원
      </span>
    </p>
  </div>
</li>
"""


def test_build_search_url_encodes_korean_query() -> None:
    url = (
        OliveYoungProductSearchProvider
        .build_search_url(
            "에뛰드 진저슈가 립밤"
        )
    )

    parsed = urlparse(url)

    assert parsed.hostname == "www.oliveyoung.co.kr"
    assert parse_qs(parsed.query)["query"] == [
        "에뛰드 진저슈가 립밤"
    ]
    assert " " not in url


def test_parse_product_card_builds_complete_candidate() -> None:
    fetched_at = datetime(
        2026,
        7,
        28,
        tzinfo=timezone.utc,
    )

    product = (
        OliveYoungProductSearchProvider
        .parse_product_card(
            card_html=PRODUCT_CARD_HTML,
            rank=1,
            search_query="에뛰드 진저슈가 립밤",
            fetched_at=fetched_at,
        )
    )

    assert product.product_id == "A000000172128"
    assert product.source == "oliveyoung"
    assert product.brand_name == "에뛰드"
    assert (
        product.product_name
        == "에뛰드 진저슈가 립밤 스틱 3.7g"
    )
    assert product.product_url.startswith(
        "https://www.oliveyoung.co.kr/"
        "store/goods/getGoodsDetail.do?"
    )
    assert (
        "goodsNo=A000000172128"
        in product.product_url
    )
    assert product.image_url == (
        "https://image.oliveyoung.co.kr/"
        "products/lip-balm.jpg"
    )
    assert product.original_price == 8000
    assert product.sale_price == 7200
    assert product.rank == 1
    assert (
        product.search_query
        == "에뛰드 진저슈가 립밤"
    )
    assert product.fetched_at == fetched_at


def test_parse_product_card_rejects_non_oliveyoung_url() -> None:
    invalid_html = PRODUCT_CARD_HTML.replace(
        "https://www.oliveyoung.co.kr/"
        "store/goods/getGoodsDetail.do",
        "https://example.com/product",
    )

    with pytest.raises(
        ProductSearchParsingError
    ):
        (
            OliveYoungProductSearchProvider
            .parse_product_card(
                card_html=invalid_html,
                rank=1,
                search_query="에뛰드",
            )
        )


def test_parse_product_card_rejects_missing_product_name() -> None:
    invalid_html = PRODUCT_CARD_HTML.replace(
        "tx_name",
        "missing_name",
    )

    with pytest.raises(
        ProductSearchParsingError
    ):
        (
            OliveYoungProductSearchProvider
            .parse_product_card(
                card_html=invalid_html,
                rank=1,
                search_query="에뛰드",
            )
        )

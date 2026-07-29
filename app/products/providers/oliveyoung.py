import re
import time
from datetime import datetime, timezone
from urllib.parse import (
    parse_qs,
    urlencode,
    urljoin,
    urlparse,
)

from lxml import etree, html
from playwright.sync_api import (
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from app.products.models import ProductCandidate
from app.products.providers.base import (
    ProductSearchNetworkError,
    ProductSearchParsingError,
)


OLIVEYOUNG_ORIGIN = "https://www.oliveyoung.co.kr"
OLIVEYOUNG_SEARCH_URL = (
    f"{OLIVEYOUNG_ORIGIN}/store/search/getSearchMain.do"
)
PRODUCT_CARD_SELECTOR = "ul.cate_prd_list > li"
NO_RESULT_TEXT = "검색 결과가 없어요"


def _class_xpath(class_name: str) -> str:
    return (
        "contains(concat(' ', normalize-space(@class), ' '), "
        f"' {class_name} ')"
    )


def _first_text(
    document: html.HtmlElement,
    xpath: str,
) -> str | None:
    values = document.xpath(xpath)
    if not values:
        return None

    value = values[0]
    if isinstance(value, html.HtmlElement):
        text = value.text_content()
    else:
        text = str(value)

    normalized = " ".join(text.split())
    return normalized or None


def _parse_price(value: str | None) -> int | None:
    if not value:
        return None

    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None


class OliveYoungProductSearchProvider:
    """
    실제 Chrome으로 올리브영 통합검색 페이지를 열어 상품 후보를
    만드는 Provider.

    올리브영은 일반 HTTP 클라이언트와 headless Chrome 요청을
    Cloudflare 확인 페이지로 전환한다. 전성분 추출기와 동일하게
    사용자가 보는 Chrome 세션(headless=False)을 기본으로 사용한다.
    """

    provider_name = "oliveyoung"

    def __init__(
        self,
        headless: bool = False,
        timeout_ms: int = 60_000,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms

    @staticmethod
    def build_search_url(query: str) -> str:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError(
                "상품 검색어는 비어 있을 수 없습니다."
            )

        encoded_query = urlencode(
            {"query": normalized_query},
            encoding="utf-8",
            errors="strict",
        )
        return f"{OLIVEYOUNG_SEARCH_URL}?{encoded_query}"

    def search_products(
        self,
        query: str,
        limit: int = 5,
    ) -> list[ProductCandidate]:
        normalized_query = query.strip()
        search_url = self.build_search_url(
            normalized_query
        )
        normalized_limit = max(1, min(limit, 10))
        fetched_at = datetime.now(timezone.utc)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    channel="chrome",
                    headless=self.headless,
                )

                try:
                    context = browser.new_context(
                        locale="ko-KR",
                        viewport={
                            "width": 1440,
                            "height": 1000,
                        },
                    )

                    try:
                        page = context.new_page()
                        page.goto(
                            search_url,
                            wait_until="domcontentloaded",
                            timeout=self.timeout_ms,
                        )

                        cards = page.locator(
                            PRODUCT_CARD_SELECTOR
                        )
                        self._wait_for_search_result(
                            cards=cards,
                            page=page,
                        )

                        if cards.count() == 0:
                            return []

                        products: list[
                            ProductCandidate
                        ] = []

                        for index in range(cards.count()):
                            if len(products) >= normalized_limit:
                                break

                            card_html = cards.nth(
                                index
                            ).evaluate(
                                "element => element.outerHTML"
                            )

                            products.append(
                                self.parse_product_card(
                                    card_html=card_html,
                                    rank=index + 1,
                                    search_query=(
                                        normalized_query
                                    ),
                                    fetched_at=fetched_at,
                                )
                            )

                        return products
                    finally:
                        context.close()
                finally:
                    browser.close()

        except (
            ProductSearchParsingError,
            ValueError,
        ):
            raise
        except PlaywrightTimeoutError as error:
            raise ProductSearchNetworkError(
                "올리브영 상품 검색 요청 시간이 "
                "초과되었습니다."
            ) from error
        except PlaywrightError as error:
            raise ProductSearchNetworkError(
                "올리브영 상품 검색용 Chrome을 "
                f"실행하지 못했습니다: {error}"
            ) from error
        except OSError as error:
            raise ProductSearchNetworkError(
                "올리브영 상품 검색 중 네트워크 또는 "
                f"실행 환경 오류가 발생했습니다: {error}"
            ) from error

    def _wait_for_search_result(
        self,
        cards: Locator,
        page: Page,
    ) -> None:
        deadline = (
            time.monotonic()
            + self.timeout_ms / 1000
        )
        last_body_text = ""

        while time.monotonic() < deadline:
            if cards.count() > 0:
                return

            try:
                last_body_text = (
                    page.locator("body").inner_text(
                        timeout=2_000
                    )
                )
            except PlaywrightTimeoutError:
                last_body_text = ""

            if NO_RESULT_TEXT in last_body_text:
                return

            page.wait_for_timeout(250)

        if (
            "Enable JavaScript and cookies"
            in last_body_text
            or "잠시만 기다려 주세요"
            in last_body_text
        ):
            raise ProductSearchNetworkError(
                "올리브영의 브라우저 확인 화면을 "
                "통과하지 못했습니다."
            )

        raise ProductSearchParsingError(
            "올리브영 검색 페이지에서 상품 목록 또는 "
            "빈 검색 결과를 확인하지 못했습니다."
        )

    @staticmethod
    def parse_product_card(
        card_html: str,
        rank: int,
        search_query: str,
        fetched_at: datetime | None = None,
    ) -> ProductCandidate:
        try:
            document = html.fromstring(card_html)
        except (
            etree.ParserError,
            ValueError,
            TypeError,
        ) as error:
            raise ProductSearchParsingError(
                "올리브영 상품 카드 HTML을 읽지 "
                "못했습니다."
            ) from error

        thumb_xpath = (
            f".//a[{_class_xpath('prd_thumb')}]"
        )
        product_url_value = _first_text(
            document,
            f"{thumb_xpath}/@href",
        )
        product_name = _first_text(
            document,
            f".//*[{_class_xpath('tx_name')}]",
        )

        if not product_url_value or not product_name:
            raise ProductSearchParsingError(
                "올리브영 상품 카드에 상세 URL 또는 "
                "상품명이 없습니다."
            )

        product_url = urljoin(
            OLIVEYOUNG_ORIGIN,
            product_url_value,
        )
        parsed_url = urlparse(product_url)
        hostname = (parsed_url.hostname or "").lower()
        product_ids = parse_qs(
            parsed_url.query
        ).get("goodsNo", [])
        product_id = (
            product_ids[0].strip()
            if product_ids
            else ""
        )

        is_oliveyoung_url = (
            parsed_url.scheme in {"http", "https"}
            and (
                hostname == "oliveyoung.co.kr"
                or hostname.endswith(
                    ".oliveyoung.co.kr"
                )
            )
            and parsed_url.path.endswith(
                "/store/goods/getGoodsDetail.do"
            )
        )

        if not is_oliveyoung_url or not product_id:
            raise ProductSearchParsingError(
                "올리브영 상품 카드의 실제 상세 URL이나 "
                "goodsNo를 확인하지 못했습니다."
            )

        brand_name = _first_text(
            document,
            f".//*[{_class_xpath('tx_brand')}]",
        )
        image_url_value = _first_text(
            document,
            f"{thumb_xpath}//img[1]/@src",
        )
        image_url = (
            urljoin(
                OLIVEYOUNG_ORIGIN,
                image_url_value,
            )
            if image_url_value
            else None
        )
        category_path = _first_text(
            document,
            ".//*[@data-ref-goodscategory][1]"
            "/@data-ref-goodscategory",
        )

        original_price_text = _first_text(
            document,
            (
                f".//*[{_class_xpath('prd_price')}]"
                f"//*[{_class_xpath('tx_org')}]"
                f"//*[{_class_xpath('tx_num')}]"
            ),
        )
        current_price_text = _first_text(
            document,
            (
                f".//*[{_class_xpath('prd_price')}]"
                f"//*[{_class_xpath('tx_cur')}]"
                f"//*[{_class_xpath('tx_num')}]"
            ),
        )
        current_price = _parse_price(
            current_price_text
        )
        original_price = (
            _parse_price(original_price_text)
            or current_price
        )

        return ProductCandidate(
            product_id=product_id,
            source="oliveyoung",
            brand_name=brand_name,
            product_name=product_name,
            category="unknown",
            category_path=category_path,
            product_url=product_url,
            image_url=image_url,
            original_price=original_price,
            sale_price=current_price,
            rank=rank,
            search_query=search_query,
            fetched_at=(
                fetched_at
                or datetime.now(timezone.utc)
            ),
        )

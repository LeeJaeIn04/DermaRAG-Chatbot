from urllib.parse import urlparse
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)
from app.products.models import (
    ProductIngredientResult,
)


# 올리브영 상품정보 제공고시에서 찾을 전성분 항목 제목
INGREDIENT_LABEL = (
    "화장품법에 따라 기재해야 하는 모든 성분"
)

# 접었다 펼칠 수 있는 상품정보 제공고시 제목
PRODUCT_NOTICE_LABEL = "상품정보 제공고시"


class OliveYoungIngredientExtractor:
    """
    Playwright와 Chrome을 이용해 올리브영 상품 페이지에서
    전성분 문자열을 추출한다.

    현재 확인된 전성분 HTML 구조:

    <tr>
        <th>
            화장품법에 따라 기재해야 하는 모든 성분
        </th>
        <td>
            정제수, 글리세린, ...
        </td>
    </tr>
    """

    def __init__(
        self,
        headless: bool = False,
        timeout_ms: int = 60_000,
    ) -> None:
        """
        추출기 실행 옵션을 저장한다.

        Parameters
        ----------
        headless:
            False이면 Chrome 창을 화면에 보여준다.
            개발 중에는 False가 디버깅하기 쉽다.

        timeout_ms:
            페이지와 DOM 요소를 기다릴 최대 시간.
            60_000은 60초다.
        """

        self.headless = headless
        self.timeout_ms = timeout_ms

    def extract(
        self,
        product_id: str,
        product_url: str,
    ) -> ProductIngredientResult:
        """
        상품 URL에서 전성분을 추출한다.

        성공:
            extraction_success=True
            raw_ingredients와 ingredients를 반환한다.

        실패:
            extraction_success=False
            error_message에 실패 원인을 기록한다.
        """

        # 입력값 앞뒤의 불필요한 공백을 제거한다.
        normalized_product_id = product_id.strip()
        normalized_url = product_url.strip()

        # 잘못된 입력은 브라우저를 실행하기 전에 거부한다.
        if not normalized_product_id:
            return self._failure_result(
                product_id=product_id,
                product_url=product_url,
                message="product_id가 비어 있습니다.",
            )

        if not normalized_url:
            return self._failure_result(
                product_id=normalized_product_id,
                product_url=product_url,
                message="product_url이 비어 있습니다.",
            )

        # 올리브영이 아닌 URL이 추출기로 들어오는 것을 막는다.
        if not self._is_oliveyoung_url(normalized_url):
            return self._failure_result(
                product_id=normalized_product_id,
                product_url=normalized_url,
                message="올리브영 상품 URL이 아닙니다.",
            )

        try:
            # Playwright 실행 환경을 시작한다.
            with sync_playwright() as playwright:
                # 현재 컴퓨터에 설치된 Google Chrome을 사용한다.
                browser = playwright.chromium.launch(
                    channel="chrome",
                    headless=self.headless,
                )

                try:
                    return self._extract_with_browser(
                        browser=browser,
                        product_id=normalized_product_id,
                        product_url=normalized_url,
                    )
                finally:
                    # 성공과 실패 여부에 관계없이
                    # Chrome 프로세스를 종료한다.
                    browser.close()

        except PlaywrightTimeoutError as error:
            # 페이지나 전성분 영역을 제한 시간 안에
            # 찾지 못했을 때의 실패 결과다.
            return self._failure_result(
                product_id=normalized_product_id,
                product_url=normalized_url,
                message=(
                    "제한 시간 안에 전성분 영역을 "
                    f"찾지 못했습니다: {error}"
                ),
            )

        except Exception as error:
            # 예상하지 못한 오류도 프로그램 전체로 전파하지 않고
            # 일정한 실패 결과 형태로 반환한다.
            return self._failure_result(
                product_id=normalized_product_id,
                product_url=normalized_url,
                message=(
                    "전성분 추출 중 오류가 발생했습니다: "
                    f"{error}"
                ),
            )
    
    @staticmethod
    def _ingredient_label(
        page: Page,
    ) -> Locator:
        """
        상품정보 제공고시 내부의 전성분 제목 TH를 찾는다.

        전체 문장 대신 '모든 성분'을 사용해
        공백이나 줄바꿈 차이를 허용한다.
        """

        return (
            page.locator("th")
            .filter(has_text="모든 성분")
            .first
        )

    def _extract_with_browser(
        self,
        browser: Browser,
        product_id: str,
        product_url: str,
    ) -> ProductIngredientResult:
        """
        새 브라우저 탭을 열고 실제 전성분 DOM을 읽는다.

        이 메서드는 extract() 내부에서만 호출한다.
        """

        # 독립된 브라우저 세션을 만든다.
        context: BrowserContext = browser.new_context(
            locale="ko-KR",
        )

        try:
            # 새로운 Chrome 탭을 연다.
            page: Page = context.new_page()

            # 올리브영 상품 상세 페이지로 이동한다.
            page.goto(
                product_url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )

            # 상품정보 제공고시가 있는 위치까지
            # Playwright가 자동으로 스크롤한다.
            notice_title = self._scroll_until_product_notice(
                page
            )

            # 상품정보 제공고시가 접혀 있다면 클릭해서 연다.
            self._open_product_information_notice(
                page=page,
                notice_title=notice_title,
            )

            # 펼쳐진 표에서 전성분 제목 TH를 찾는다.
            ingredient_label = self._ingredient_label(
                page
            )

            # 전성분 행이 실제 화면에 표시될 때까지 기다린다.
            ingredient_label.wait_for(
                state="visible",
                timeout=self.timeout_ms,
            )

            # 필요한 경우 전성분 행이 보이는 위치까지
            # Playwright가 자동으로 스크롤한다.
            ingredient_label.scroll_into_view_if_needed()

            # 확인한 HTML 구조에서 TH의 바로 다음 TD가
            # 실제 전성분 문자열을 가지고 있다.
            ingredient_value = ingredient_label.locator(
                "xpath=following-sibling::td[1]"
            )

            # TD가 나타날 때까지 기다린다.
            ingredient_value.wait_for(
                state="visible",
                timeout=self.timeout_ms,
            )

            # TD의 화면 표시 텍스트를 읽고
            # 앞뒤 공백을 제거한다.
            raw_ingredients = (
                ingredient_value.inner_text().strip()
            )

            if not raw_ingredients:
                return self._failure_result(
                    product_id=product_id,
                    product_url=product_url,
                    message=(
                        "전성분 항목은 찾았지만 "
                        "내용이 비어 있습니다."
                    ),
                )

            # 전성분 문자열을 쉼표 기준으로 분리한다.
            #
            # 예:
            # "정제수, 글리세린, 나이아신아마이드"
            #
            # 결과:
            # ["정제수", "글리세린", "나이아신아마이드"]
            ingredients = [
                ingredient.strip()
                for ingredient
                in raw_ingredients.split(",")
                if ingredient.strip()
            ]

            return ProductIngredientResult(
                product_id=product_id,
                product_url=product_url,
                raw_ingredients=raw_ingredients,
                ingredients=ingredients,
                extraction_method="browser_dom",
                extraction_success=True,
                error_message=None,
            )

        finally:
            # 탭을 포함하는 브라우저 세션을 정리한다.
            context.close()

    def _scroll_until_product_notice(
        self,
        page: Page,
    ) -> Locator:
        
        """
        화면에 보이는 상품정보 제공고시 제목을 찾을 때까지
        페이지를 단계적으로 자동 스크롤한다.

        Returns
        -------
        Locator
            실제 화면에 표시된 상품정보 제공고시 제목.
        """

        max_scroll_attempts = 30

        for _ in range(max_scroll_attempts):
            # PC용·모바일용 DOM이 함께 있을 수 있으므로
            # 같은 문구를 가진 모든 요소를 먼저 찾는다.
            candidates = page.get_by_text(
                PRODUCT_NOTICE_LABEL,
                exact=True,
            )

            # 찾아낸 요소 중 실제 화면에 보이는 것을 선택한다.
            for index in range(candidates.count()):
                candidate = candidates.nth(index)

                if candidate.is_visible():
                    candidate.scroll_into_view_if_needed()
                    page.wait_for_timeout(500)
                    return candidate

            # 아직 제목이 없거나 모두 숨겨져 있다면
            # 현재 화면 높이의 80%만큼 아래로 이동한다.
            page.evaluate(
                """
                window.scrollBy(
                    0,
                    Math.floor(window.innerHeight * 0.8)
                )
                """
            )

            # 스크롤 후 지연 콘텐츠가 로드될 시간을 준다.
            page.wait_for_timeout(500)

        raise PlaywrightTimeoutError(
            "화면에 표시된 상품정보 제공고시 영역을 "
            "찾지 못했습니다."
        )

    def _open_product_information_notice(
        self,
        page: Page,
        notice_title: Locator,
    ) -> None:
        """
        상품정보 제공고시를 펼친다.

        제목 자체 또는 가장 가까운 클릭 가능한 부모 요소를
        눌러 전성분 표가 나타나도록 한다.
        """

        ingredient_label = self._ingredient_label(page)

        # 전성분 행이 이미 보이면 제공고시가 열린 상태다.
        # 다시 클릭하면 닫힐 수 있으므로 바로 종료한다.
        if (
            ingredient_label.count() > 0
            and ingredient_label.is_visible()
        ):
            return

        notice_title.scroll_into_view_if_needed()
        page.wait_for_timeout(500)

        # 제목을 감싸는 가장 가까운 클릭 가능 요소를 찾는다.
        clickable_ancestor = notice_title.locator(
            (
                "xpath=ancestor-or-self::*["
                "self::button "
                "or @role='button' "
                "or self::a "
                "or @onclick"
                "][1]"
            )
        )

        if clickable_ancestor.count() > 0:
            click_target = clickable_ancestor
        else:
            # 명시적인 button이나 링크가 없다면
            # 제목의 바로 위 부모 영역을 클릭한다.
            parent = notice_title.locator(
                "xpath=parent::*"
            )

            click_target = (
                parent if parent.count() > 0 else notice_title
            )

        # 올리브영 페이지는 스크롤 직후에도 지연 콘텐츠로
        # 레이아웃이 계속 움직여, 첫 클릭이 목표 지점을
        # 벗어나 아무 효과 없이 소비될 수 있다.
        # 그래서 실제로 펼쳐졌는지(전성분 행이 보이는지)를
        # 짧은 대기로 확인하고, 열리지 않았다면 다시 클릭한다.
        # aria-expanded가 이미 true라면 다시 클릭하지 않는다.
        # (다시 누르면 접힐 수 있기 때문이다.)
        max_click_attempts = 5
        per_attempt_timeout_ms = 3_000

        for attempt in range(max_click_attempts):
            if click_target.get_attribute("aria-expanded") != "true":
                click_target.click()

            try:
                ingredient_label.wait_for(
                    state="visible",
                    timeout=per_attempt_timeout_ms,
                )
                return
            except PlaywrightTimeoutError:
                if attempt == max_click_attempts - 1:
                    raise
                continue


    @staticmethod
    def _is_oliveyoung_url(
        product_url: str,
    ) -> bool:
        """
        상품 URL의 hostname이 올리브영 도메인인지 검사한다.

        URL 전체 문자열에 oliveyoung.co.kr이 들어가는지만
        확인하면 가짜 URL도 통과할 수 있으므로
        파싱된 hostname을 기준으로 판단한다.
        """

        hostname = (
            urlparse(product_url).hostname or ""
        ).lower()

        return (
            hostname == "oliveyoung.co.kr"
            or hostname.endswith(
                ".oliveyoung.co.kr"
            )
        )

    @staticmethod
    def _failure_result(
        product_id: str,
        product_url: str,
        message: str,
    ) -> ProductIngredientResult:
        """
        전성분 추출 실패 결과를 일정한 형태로 생성한다.
        """

        return ProductIngredientResult(
            product_id=product_id.strip(),
            product_url=product_url.strip(),
            raw_ingredients="",
            ingredients=[],
            extraction_method="browser_dom",
            extraction_success=False,
            error_message=message,
        )
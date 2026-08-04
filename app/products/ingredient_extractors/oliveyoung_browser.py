import re
import logging
from copy import copy
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)
from app.products.models import (
    ProductIngredientResult,
)
from app.products.ingredient_parsing import (
    split_raw_ingredient_text,
)
from app.products.playwright_runtime import (
    CollectionDeadline,
    CollectionDeadlineExceeded,
    run_browser_operation,
)


logger = logging.getLogger(__name__)


class _ExistingPageContext:
    """공통 runtime이 생성한 page를 기존 추출 로직에 연결한다."""

    def __init__(self, page: Page) -> None:
        self.page = page

    def new_page(self) -> Page:
        return self.page

    def close(self) -> None:
        return None


class _ExistingPageBrowser:
    def __init__(self, page: Page) -> None:
        self.page = page

    def new_context(self, **_kwargs) -> _ExistingPageContext:
        return _ExistingPageContext(self.page)


# 올리브영 상품정보 제공고시에서 찾을 전성분 항목 제목.
#
# 상품 카테고리에 따라 문구가 조금씩 다를 수 있어
# 우선순위가 높은 순서대로 후보를 나열한다.
INGREDIENT_LABEL_CANDIDATES = (
    "모든 성분",
    "전성분",
)

# 하위 호환을 위해 기존 이름도 유지한다.
INGREDIENT_LABEL = INGREDIENT_LABEL_CANDIDATES[0]

# 접었다 펼칠 수 있는 상품정보 제공고시 제목
PRODUCT_NOTICE_LABEL = "상품정보 제공고시"

# 정확한 문구가 바뀌었을 때를 대비한 느슨한 대체 문구.
# "제공고시"만 포함하면 되므로 공백이나 줄바꿈 차이,
# 일부 단어 변경에도 견딜 수 있다.
PRODUCT_NOTICE_LABEL_FALLBACK = "제공고시"

# 실패 시 스크린샷과 HTML을 저장할 위치.
# 상품 ID별로 파일을 남겨 재현 없이도 원인을 확인할 수 있다.
DEBUG_ARTIFACT_DIR = Path("debug_artifacts/ingredient_extraction")

# 실패 메시지에 포함할 본문 텍스트의 최대 길이.
# 페이지 전체 텍스트나 개인정보를 그대로 남기지 않기 위해
# 앞부분 일부만 잘라서 사용한다.
MAX_BODY_TEXT_EXCERPT = 300

# 방해 요소로 흔히 쓰이는 닫기 버튼 selector 후보.
# 하나라도 화면에 보이면 클릭해서 닫는다.
BLOCKING_LAYER_CLOSE_SELECTORS = (
    "[role='dialog'] button[aria-label*='닫기']",
    "[role='dialog'] button[class*='close' i]",
    ".layer-popup button[class*='close' i]",
    "button[class*='cookie' i][class*='close' i]",
    "button:has-text('오늘 하루 보지 않기')",
    "button:has-text('닫기')",
)


@dataclass
class ExtractionDebugInfo:
    """
    전성분 추출 실패 시 원인 파악에 필요한 최소한의 진단 정보.

    페이지 전체 HTML이나 개인정보를 그대로 남기지 않고
    디버깅에 필요한 범위만 담는다.
    """

    current_url: str = ""
    page_title: str = ""
    notice_locator_count: int = 0
    ingredient_locator_count: int = 0
    notice_tab_clicked: bool = False
    scroll_performed: bool = False
    body_text_excerpt: str = ""
    screenshot_path: str | None = None
    html_path: str | None = None

    def as_message(self) -> str:
        return (
            "[디버그 정보] "
            f"현재 URL={self.current_url} | "
            f"페이지 title={self.page_title!r} | "
            f"상품정보 관련 locator 개수={self.notice_locator_count} | "
            f"전성분 관련 locator 개수={self.ingredient_locator_count} | "
            f"상품정보 탭 클릭 성공={self.notice_tab_clicked} | "
            f"스크롤 수행={self.scroll_performed} | "
            f"body 텍스트 일부={self.body_text_excerpt!r} | "
            f"screenshot={self.screenshot_path} | "
            f"html={self.html_path}"
        )


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

    headless 여부는 환경별 smoke test 결과에 따라 설정한다.
    차단 시 CAPTCHA 우회나 stealth 기법을 사용하지 않으며,
    운영 요청에서 headed 모드로 자동 fallback하지 않는다.
    """

    def __init__(
        self,
        headless: bool = False,
        timeout_ms: int = 60_000,
        deadline_ms: int = 90_000,
        max_attempts: int = 2,
    ) -> None:
        """
        추출기 실행 옵션을 저장한다.

        Parameters
        ----------
        headless:
            운영 목표는 True이며, 환경별 smoke test 통과 후
            설정한다. False는 개발/진단 환경에서만 명시한다.

        timeout_ms:
            페이지와 DOM 요소를 기다릴 최대 시간.
            60_000은 60초다.
        """

        self.headless = headless
        self.timeout_ms = timeout_ms
        self.deadline_ms = deadline_ms
        self.max_attempts = max_attempts

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
            error_message에 실패 원인과 디버그 정보를 기록한다.
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

        def collect(page: Page, deadline: CollectionDeadline):
            bounded_extractor = copy(self)
            bounded_extractor.timeout_ms = deadline.remaining_ms(
                self.timeout_ms
            )
            result = bounded_extractor._extract_with_browser(
                browser=_ExistingPageBrowser(page),
                product_id=normalized_product_id,
                product_url=normalized_url,
            )
            deadline.remaining_ms(1)
            return result

        try:
            return run_browser_operation(
                collect,
                headless=self.headless,
                deadline_ms=self.deadline_ms,
                max_attempts=self.max_attempts,
            )

        except (
            PlaywrightTimeoutError,
            CollectionDeadlineExceeded,
        ) as error:
            # 페이지나 전성분 영역을 제한 시간 안에
            # 찾지 못했을 때의 실패 결과다.
            # 이 시점에는 이미 page/context가 정리된 뒤이므로
            # 디버그 정보는 _extract_with_browser 내부에서
            # 메시지에 미리 포함시켜 전달한다.
            logger.warning(
                "Olive Young ingredient extraction timed out (%s, headless=%s): %s",
                normalized_product_id,
                self.headless,
                error,
            )
            return self._failure_result(
                product_id=normalized_product_id,
                product_url=normalized_url,
                message=(
                    "제한 시간 안에 전성분 영역을 찾지 못했습니다. "
                    "headless smoke test와 외부 사이트 상태를 확인해 주세요."
                ),
            )

        except Exception as error:
            # 예상하지 못한 오류도 프로그램 전체로 전파하지 않고
            # 일정한 실패 결과 형태로 반환한다.
            logger.warning(
                "Olive Young ingredient extraction failed (%s, headless=%s): %s",
                normalized_product_id,
                self.headless,
                error,
            )
            return self._failure_result(
                product_id=normalized_product_id,
                product_url=normalized_url,
                message=(
                    "전성분 추출 중 브라우저 또는 페이지 오류가 발생했습니다."
                ),
            )

    @staticmethod
    def _ingredient_label(
        page: Page,
    ) -> Locator:
        """
        상품정보 제공고시 내부의 전성분 제목 TH를 찾는다.

        하나의 문구에만 의존하면 카테고리별 문구 차이나
        사이트 개편에 취약하므로, 후보 문구를 순서대로
        시도해 가장 먼저 매칭되는 locator를 사용한다.
        """

        for candidate_text in INGREDIENT_LABEL_CANDIDATES:
            candidate_locator = (
                page.locator("th").filter(has_text=candidate_text)
            )

            if candidate_locator.count() > 0:
                return candidate_locator.first

        # 후보를 모두 찾지 못했다면 첫 번째 후보 기준의
        # (비어 있는) locator를 반환해 이후 wait_for가
        # 실패 사유를 명확히 드러내도록 한다.
        return (
            page.locator("th")
            .filter(has_text=INGREDIENT_LABEL_CANDIDATES[0])
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
        page: Page | None = None

        try:
            # 새로운 Chrome 탭을 연다.
            page = context.new_page()

            try:
                # 올리브영 상품 상세 페이지로 이동한다.
                page.goto(
                    product_url,
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )

                # 쿠키 배너나 팝업 레이어가 이후 클릭을
                # 가로채지 않도록 먼저 정리한다.
                self._dismiss_blocking_layers(page)

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

                # 전성분 행이 DOM에 존재할 때까지 기다린다.
                #
                # state="visible"만 사용하면 뷰포트 밖에 있거나
                # 애니메이션 중인 요소를 잘못된 실패로 처리할 수
                # 있으므로, 먼저 DOM에 붙었는지(attached)를 확인한
                # 뒤 scroll_into_view로 실제로 보이게 만든다.
                ingredient_label.wait_for(
                    state="attached",
                    timeout=self.timeout_ms,
                )

                ingredient_label.scroll_into_view_if_needed()

                ingredient_label.wait_for(
                    state="visible",
                    timeout=self.timeout_ms,
                )

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
                    debug_info = self._gather_failure_diagnostics(
                        page=page,
                        product_id=product_id,
                    )
                    logger.warning(
                        "Olive Young ingredient text was empty (%s): %s",
                        product_id,
                        debug_info.as_message(),
                    )
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
                ingredients = split_raw_ingredient_text(
                    raw_ingredients
                )

                return ProductIngredientResult(
                    product_id=product_id,
                    product_url=product_url,
                    raw_ingredients=raw_ingredients,
                    ingredients=ingredients,
                    extraction_method="browser_dom",
                    extraction_success=True,
                    error_message=None,
                )

            except PlaywrightTimeoutError as error:
                debug_info = self._gather_failure_diagnostics(
                    page=page,
                    product_id=product_id,
                )

                raise PlaywrightTimeoutError(
                    f"{error} {debug_info.as_message()}"
                ) from error

            except Exception as error:
                debug_info = self._gather_failure_diagnostics(
                    page=page,
                    product_id=product_id,
                )

                raise RuntimeError(
                    f"{error} {debug_info.as_message()}"
                ) from error

        finally:
            if page is not None:
                with suppress(Exception):
                    page.close()
            context.close()

    def _dismiss_blocking_layers(
        self,
        page: Page,
    ) -> None:
        """
        쿠키 배너, 오늘 하루 보지 않기 팝업 등
        이후 클릭을 가로챌 수 있는 레이어를 최선을 다해 닫는다.

        후보 selector 중 실제로 화면에 보이는 것이 있으면
        클릭해서 닫고, 없으면 조용히 넘어간다.
        이 단계에서 발생하는 오류는 추출 자체를 막지
        않도록 무시한다.
        """

        for selector in BLOCKING_LAYER_CLOSE_SELECTORS:
            try:
                close_button = page.locator(selector).first

                if close_button.count() > 0 and close_button.is_visible():
                    close_button.click(timeout=2_000)
                    page.wait_for_timeout(300)
            except Exception:
                # 팝업 처리 실패는 추출 실패로 이어지지 않아야
                # 하므로 다음 후보로 넘어간다.
                continue

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

            # 정확한 문구를 찾지 못했다면 느슨한 문구로도
            # 시도한다. 사이트 개편으로 정확한 문구가 조금
            # 바뀌어도 완전히 실패하지 않도록 하기 위함이다.
            if candidates.count() == 0:
                candidates = page.get_by_text(
                    PRODUCT_NOTICE_LABEL_FALLBACK,
                    exact=False,
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

        # 올리브영 페이지는 상품정보 제공고시 영역의 실제 내용을
        # 별도 비동기 요청으로 지연 로딩한다. 이 요청이 끝나기
        # 전에는 아코디언 버튼을 눌러도 화면상 반응이 없을 수
        # 있다. 짧게 한 번 안정화 시간을 준 뒤 클릭하고, 그래도
        # 열리지 않으면 반복해서 다시 클릭한다.
        #
        # 시도 횟수와 시도당 대기 시간을 고정값 대신 생성자에서
        # 받은 timeout_ms를 기준으로 계산해, 느린 네트워크에서도
        # 전체 대기 시간이 자연스럽게 늘어나도록 한다. 단순히
        # per_attempt 시간만 늘리면 클릭 자체가 필요한 순간을
        # 놓쳤을 때 그대로 낭비되므로, 시도 횟수를 함께 늘려
        # "재시도"라는 근본적인 해결 방식을 유지한다.
        max_click_attempts = 8
        per_attempt_timeout_ms = max(
            3_000,
            self.timeout_ms // max_click_attempts,
        )

        # 지연 로딩이 막 끝난 시점에 클릭이 몰리면 아코디언이
        # 열렸다 즉시 닫히는 것처럼 보일 수 있으므로, 첫 클릭
        # 전에 네트워크가 잦아들 때까지 짧게 기다린다.
        # 이 사이트는 추천 상품 영역이 계속 요청을 보내
        # networkidle이 끝까지 도달하지 않을 수 있으므로
        # 실패해도 무시하고 진행한다.
        try:
            page.wait_for_load_state(
                "networkidle",
                timeout=2_000,
            )
        except PlaywrightTimeoutError:
            pass

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

    def _gather_failure_diagnostics(
        self,
        page: Page,
        product_id: str,
    ) -> ExtractionDebugInfo:
        """
        실패 원인을 파악하는 데 필요한 최소한의 진단 정보를 모은다.

        이 메서드는 실패 상황에서 호출되므로 진단 정보를
        수집하는 과정 자체에서 오류가 나더라도 원래 실패를
        가리지 않도록 각 단계를 개별적으로 방어한다.
        """

        info = ExtractionDebugInfo()

        try:
            info.current_url = page.url
        except Exception:
            pass

        try:
            info.page_title = page.title()
        except Exception:
            pass

        try:
            notice_candidates = page.get_by_text(
                PRODUCT_NOTICE_LABEL_FALLBACK,
                exact=False,
            )
            info.notice_locator_count = notice_candidates.count()
        except Exception:
            pass

        try:
            ingredient_candidates = page.locator("th").filter(
                has_text="성분"
            )
            info.ingredient_locator_count = (
                ingredient_candidates.count()
            )
        except Exception:
            pass

        try:
            accordion_buttons = page.locator(
                "button[aria-expanded]"
            ).filter(has_text=PRODUCT_NOTICE_LABEL)
            info.notice_tab_clicked = (
                accordion_buttons.count() > 0
                and accordion_buttons.first.get_attribute(
                    "aria-expanded"
                )
                == "true"
            )
        except Exception:
            pass

        try:
            info.scroll_performed = bool(
                page.evaluate("window.scrollY > 0")
            )
        except Exception:
            pass

        try:
            body_text = page.inner_text("body")
            info.body_text_excerpt = (
                body_text[:MAX_BODY_TEXT_EXCERPT]
                .replace("\n", " ")
                .strip()
            )
        except Exception:
            pass

        (
            info.screenshot_path,
            info.html_path,
        ) = self._save_failure_artifacts(
            page=page,
            product_id=product_id,
        )

        return info

    @staticmethod
    def _save_failure_artifacts(
        page: Page,
        product_id: str,
    ) -> tuple[str | None, str | None]:
        """
        실패 시점의 스크린샷과 HTML을 파일로 저장한다.

        전체 HTML을 로그로 남기지 않고 파일로만 남겨,
        필요할 때만 열어보고 평소 로그는 짧게 유지한다.
        저장 자체가 실패해도 추출 실패 처리를 막지 않는다.
        """

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        safe_product_id = (
            re.sub(r"[^0-9A-Za-z_-]", "_", product_id)
            or "unknown"
        )
        base_name = f"{safe_product_id}_{timestamp}"

        screenshot_path: str | None = None
        html_path: str | None = None

        try:
            DEBUG_ARTIFACT_DIR.mkdir(
                parents=True, exist_ok=True
            )

            screenshot_file = (
                DEBUG_ARTIFACT_DIR / f"{base_name}.png"
            )
            page.screenshot(
                path=str(screenshot_file),
                full_page=True,
            )
            screenshot_path = str(screenshot_file)
        except Exception:
            pass

        try:
            DEBUG_ARTIFACT_DIR.mkdir(
                parents=True, exist_ok=True
            )

            html_file = (
                DEBUG_ARTIFACT_DIR / f"{base_name}.html"
            )
            html_file.write_text(
                page.content(),
                encoding="utf-8",
            )
            html_path = str(html_file)
        except Exception:
            pass

        return screenshot_path, html_path

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

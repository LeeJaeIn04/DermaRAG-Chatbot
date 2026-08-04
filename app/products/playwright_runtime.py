from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import Iterator, TypeVar

from playwright.sync_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


T = TypeVar("T")


class CollectionDeadlineExceeded(TimeoutError):
    """상품 수집의 전체 허용 시간이 소진된 경우."""


@dataclass(frozen=True)
class CollectionDeadline:
    expires_at: float

    @classmethod
    def start(cls, deadline_ms: int) -> "CollectionDeadline":
        if deadline_ms <= 0:
            raise ValueError("deadline_ms는 1 이상이어야 합니다.")
        return cls(time.monotonic() + deadline_ms / 1_000)

    def remaining_ms(self, stage_timeout_ms: int) -> int:
        remaining = int((self.expires_at - time.monotonic()) * 1_000)
        if remaining <= 0:
            raise CollectionDeadlineExceeded(
                "상품 수집 전체 제한 시간이 초과되었습니다."
            )
        return max(1, min(stage_timeout_ms, remaining))


@contextmanager
def managed_chromium_page(
    *,
    headless: bool,
    viewport: dict[str, int] | None = None,
) -> Iterator[Page]:
    """page/context/browser를 역순으로 항상 종료한다."""

    with sync_playwright() as playwright:
        browser = None
        context = None
        page = None
        try:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=headless,
            )
            context_kwargs: dict[str, object] = {"locale": "ko-KR"}
            if viewport is not None:
                context_kwargs["viewport"] = viewport
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            yield page
        finally:
            if page is not None:
                with suppress(Exception):
                    page.close()
            if context is not None:
                with suppress(Exception):
                    context.close()
            if browser is not None:
                with suppress(Exception):
                    browser.close()


def run_browser_operation(
    operation: Callable[[Page, CollectionDeadline], T],
    *,
    headless: bool,
    deadline_ms: int,
    max_attempts: int,
    viewport: dict[str, int] | None = None,
) -> T:
    """전체 deadline 안에서 일시적 Playwright 오류만 제한 재시도한다."""

    if max_attempts <= 0:
        raise ValueError("max_attempts는 1 이상이어야 합니다.")

    deadline = CollectionDeadline.start(deadline_ms)
    for attempt in range(1, max_attempts + 1):
        try:
            with managed_chromium_page(
                headless=headless,
                viewport=viewport,
            ) as page:
                return operation(page, deadline)
        except CollectionDeadlineExceeded:
            raise
        except (PlaywrightTimeoutError, PlaywrightError, OSError):
            if attempt >= max_attempts:
                raise
            backoff_ms = deadline.remaining_ms(250)
            time.sleep(backoff_ms / 1_000)

    raise RuntimeError("도달할 수 없는 재시도 상태입니다.")

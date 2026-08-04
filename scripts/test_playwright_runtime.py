from contextlib import contextmanager

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.products import playwright_runtime
from app.products.playwright_runtime import (
    CollectionDeadline,
    CollectionDeadlineExceeded,
    managed_chromium_page,
    run_browser_operation,
)


class CloseTracker:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeContext(CloseTracker):
    def __init__(self, page: CloseTracker) -> None:
        super().__init__()
        self.page = page

    def new_page(self):
        return self.page


class FakeBrowser(CloseTracker):
    def __init__(self, context: FakeContext) -> None:
        super().__init__()
        self.context = context

    def new_context(self, **kwargs):
        return self.context


def test_managed_page_closes_every_resource_on_error(monkeypatch) -> None:
    page = CloseTracker()
    context = FakeContext(page)
    browser = FakeBrowser(context)

    class Chromium:
        def launch(self, **kwargs):
            return browser

    class Playwright:
        chromium = Chromium()

    @contextmanager
    def fake_sync_playwright():
        yield Playwright()

    monkeypatch.setattr(
        playwright_runtime, "sync_playwright", fake_sync_playwright
    )
    with pytest.raises(RuntimeError):
        with managed_chromium_page(headless=False):
            raise RuntimeError("test")

    assert page.closed and context.closed and browser.closed


def test_browser_operation_retries_only_to_limit(monkeypatch) -> None:
    attempts = 0

    @contextmanager
    def fake_page(**kwargs):
        yield object()

    monkeypatch.setattr(playwright_runtime, "managed_chromium_page", fake_page)

    def fail(_page, _deadline):
        nonlocal attempts
        attempts += 1
        raise PlaywrightTimeoutError("temporary")

    with pytest.raises(PlaywrightTimeoutError):
        run_browser_operation(
            fail, headless=False, deadline_ms=1_000, max_attempts=2
        )
    assert attempts == 2


def test_deadline_rejects_expired_operation() -> None:
    deadline = CollectionDeadline(expires_at=0)
    with pytest.raises(CollectionDeadlineExceeded):
        deadline.remaining_ms(1_000)

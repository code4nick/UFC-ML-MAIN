from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import Browser, Error as PlaywrightError, Page, sync_playwright

_TRANSIENT_NETWORK_MARKERS = (
    "ERR_NETWORK_IO_SUSPENDED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_NETWORK_CHANGED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_ABORTED",
    "NS_ERROR_NET_INTERRUPT",
    "Timeout",
)


@contextmanager
def browser_session(headless: bool = True) -> Iterator[tuple[Browser, Page]]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            yield browser, page
        finally:
            browser.close()


def fetch_html(
    page: Page,
    url: str,
    timeout_ms: int = 60_000,
    retries: int = 4,
    wait_selector: str | None = None,
) -> str:
    last_err: PlaywrightError | None = None
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until="load", timeout=timeout_ms)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=min(timeout_ms, 30_000))
            return page.content()
        except PlaywrightError as exc:
            last_err = exc
            msg = str(exc)
            transient = any(marker in msg for marker in _TRANSIENT_NETWORK_MARKERS)
            if attempt < retries and transient:
                wait_s = 5 * attempt
                print(f"  Network hiccup on {url} — retry {attempt}/{retries - 1} in {wait_s}s")
                time.sleep(wait_s)
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError(f"fetch_html failed for {url}")

from __future__ import annotations

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from fetch import USER_AGENT, validate_url


def fetch_dynamic_html(url: str, timeout: int = 30_000) -> str:
    """Render a JavaScript page with the system Edge browser."""
    url = validate_url(url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            context = browser.new_context(user_agent=USER_AGENT, locale="zh-CN")
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout, 15_000))
            except PlaywrightTimeoutError:
                # Analytics and long polling often prevent networkidle indefinitely.
                page.wait_for_timeout(2_000)
            return page.content()
        finally:
            browser.close()

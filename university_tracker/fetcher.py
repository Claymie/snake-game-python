"""Загрузка страниц конкурсных списков через headless-браузер.

Часть сайтов приёмных комиссий рисует таблицы через JavaScript, поэтому
обычный requests.get() может вернуть пустую страницу. Playwright рендерит
страницу как настоящий браузер и отдаёт готовый HTML.
"""

from __future__ import annotations

from playwright.sync_api import Browser, sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class PageFetcher:
    """Держит один браузер открытым на всё время прогона, чтобы не
    перезапускать Chromium под каждое направление."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None

    def __enter__(self) -> "PageFetcher":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def get_html(self, url: str, timeout_ms: int = 45000) -> str:
        assert self._browser is not None
        page = self._browser.new_page(user_agent=USER_AGENT)
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            return page.content()
        finally:
            page.close()

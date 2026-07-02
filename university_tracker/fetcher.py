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

    def get_html(
        self,
        url: str,
        click_sequence: list[str] | None = None,
        autoscroll: bool = False,
        timeout_ms: int = 45000,
    ) -> tuple[str, str | None]:
        """click_sequence — список текстов, по которым нужно кликнуть по
        очереди перед чтением страницы (например: открыть выпадающий
        список -> выбрать значение -> открыть следующий список -> выбрать
        -> нажать кнопку отправки формы). Каждый клик ищет первый элемент,
        текст которого СОДЕРЖИТ нужную строку (без учёта регистра), и после
        клика немного ждёт (анимация выпадашки, возможный сетевой запрос).
        Если какой-то шаг не удался — последовательность прерывается, но
        уже загруженная страница всё равно возвращается, а не роняет прогон.

        Возвращает (html, click_error) — click_error не None, если один из
        шагов click_sequence не удался (с текстом, на котором споткнулись),
        чтобы это можно было залогировать и понять, что поправить."""
        assert self._browser is not None
        page = self._browser.new_page(user_agent=USER_AGENT, locale="ru-RU")
        click_error: str | None = None
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            for text in click_sequence or []:
                try:
                    page.get_by_text(text, exact=False).first.click(timeout=10000)
                    page.wait_for_timeout(500)
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                except Exception as exc:
                    snippet = self._body_text_snippet(page)
                    click_error = (
                        f"не удалось кликнуть '{text}': {exc}\n"
                        f"    Текст на странице на момент сбоя (первые 400 символов): {snippet!r}"
                    )
                    break
            if autoscroll:
                self._autoscroll(page)
            return page.content(), click_error
        finally:
            page.close()

    @staticmethod
    def _body_text_snippet(page, length: int = 400) -> str:
        """Короткий кусок видимого текста страницы для диагностики: если
        клик не удался, это показывает, что реально отрендерилось (баннер
        cookie, экран загрузки, капча, другая формулировка и т.д.), а не
        просто "не нашли текст"."""
        try:
            text = page.inner_text("body")
            return " ".join(text.split())[:length]
        except Exception:
            return "<не удалось прочитать текст страницы>"

    @staticmethod
    def _autoscroll(page, max_rounds: int = 25, pause_ms: int = 400) -> None:
        """Некоторые списки подгружают карточки по мере прокрутки страницы
        (бесконечный скролл) — прокручиваем вниз, пока высота страницы
        перестанет расти."""
        last_height = -1
        stable_rounds = 0
        for _ in range(max_rounds):
            height = page.evaluate("document.body.scrollHeight")
            if height == last_height:
                stable_rounds += 1
                if stable_rounds >= 2:
                    break
            else:
                stable_rounds = 0
            last_height = height
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(pause_ms)

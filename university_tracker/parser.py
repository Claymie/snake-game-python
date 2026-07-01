"""Универсальный парсер конкурсных списков вузов.

Списки на разных сайтах вёрстаются по-разному, поэтому парсер не привязан
к конкретной структуре одного сайта. Есть два режима:

- find_applicant(html, code) — ищет код абитуриента по всей странице
  (первая попавшаяся таблица со совпадением, либо текстовый фолбэк).
- find_applicant_by_context(html, code, context_terms) — используется,
  когда на одной странице сразу несколько таблиц (например, по одному
  направлению подготовки на каждую) и нужно найти таблицу, которая
  относится именно к нужному направлению. Для этого ищется заголовок
  (h1-h6, caption, strong, b), в котором встречаются ВСЕ строки из
  context_terms (например, код направления "09.03.01"), и из него берётся
  ближайшая следующая по документу таблица.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6", "caption", "strong", "b", "summary"]

# Список НГТУ выводит каждого абитуриента отдельной карточкой (не таблицей)
# с явной подписью "ID профиля ЕПГУ: <код>" — по ней и ищем, порядок карточек
# в документе соответствует месту в конкурсном списке.
ID_EPGU_PATTERN = re.compile(r"ID\s*профиля\s*ЕПГУ\s*:?\s*([0-9]+)", re.IGNORECASE)

# "Всего мест" — это квота (сколько реально зачислят на платное по этому
# направлению), а не число участников конкурса. Именно с этим числом нужно
# сравнивать место абитуриента, чтобы понять, проходит он или нет.
QUOTA_PATTERN = re.compile(r"всего\s*мест\D{0,10}?([0-9]+)", re.IGNORECASE)


@dataclass
class LookupResult:
    found: bool
    rank: int | None = None
    total: int | None = None
    row: list[str] = field(default_factory=list)
    # True, если find_applicant_by_context нашёл заголовок, подходящий под
    # match_all, и искал именно в таблице под ним (а не откатился на поиск
    # по всей странице). Помогает отличить "код не найден в списке" от
    # "не нашли даже подходящую таблицу — проверь click_text/match_all".
    matched_context: bool = False
    # Квота ("Всего мест") — сколько мест реально выделено на направление,
    # если её удалось найти на странице.
    quota: int | None = None


def _rows_from_table(table) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows


def _looks_like_header(cells: list[str]) -> bool:
    if not cells:
        return True
    joined = " ".join(cells).lower()
    header_markers = ("№", "фио", "снилс", "код", "балл", "приоритет", "место")
    return any(marker in joined for marker in header_markers) and not any(
        c.strip().isdigit() for c in cells
    )


def _first_column_is_rank_number(header_cells: list[str]) -> bool:
    if not header_cells or not header_cells[0]:
        return False
    first = header_cells[0].lower()
    return any(marker in first for marker in ("№", "ном", "место", "п/п"))


def _scan_table(table, code: str) -> LookupResult | None:
    rows = _rows_from_table(table)
    if not rows:
        return None

    header_cells = None
    data_rows = rows
    if _looks_like_header(rows[0]):
        header_cells = rows[0]
        data_rows = rows[1:]
    if not data_rows:
        return None

    has_rank_column = _first_column_is_rank_number(header_cells or [])

    for idx, cells in enumerate(data_rows, start=1):
        if any(code in cell for cell in cells):
            rank = idx
            # Используем число из первой колонки только если по заголовку видно,
            # что это явно колонка номера/места, а не сам код абитуриента
            # (иначе код вида "1339447" примут за место 1339447).
            if has_rank_column and cells[0].strip().isdigit():
                rank = int(cells[0].strip())
            return LookupResult(found=True, rank=rank, total=len(data_rows), row=cells)

    return LookupResult(found=False, total=len(data_rows))


def find_applicant(html: str, code: str) -> LookupResult:
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        result = _scan_table(table, code)
        if result and result.found:
            return result

    # Фолбэк: код может лежать вне <table> (div-based вёрстка, карточки и т.д.)
    text = soup.get_text("\n")
    for line in text.splitlines():
        line = line.strip()
        if line and code in line:
            return LookupResult(found=True, rank=None, total=None, row=[line])

    return LookupResult(found=False)


def find_applicant_by_context(html: str, code: str, context_terms: list[str]) -> LookupResult:
    """Ищет таблицу, относящуюся к конкретному направлению/разделу, по
    заголовку над таблицей, а не по первой попавшейся таблице на странице.
    Если ни один заголовок не подошёл — откатывается на find_applicant."""

    if context_terms:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(HEADING_TAGS):
            text = tag.get_text(" ", strip=True)
            if not text or len(text) > 200:
                continue
            if all(term.lower() in text.lower() for term in context_terms):
                table = tag.find_next("table")
                if table:
                    result = _scan_table(table, code)
                    if result:
                        result.matched_context = True
                        return result

    return find_applicant(html, code)


def find_applicant_by_id_epgu(html: str, code: str) -> LookupResult:
    """Парсер под конкурсные списки НГТУ: каждая запись — карточка с текстом
    вида "ID профиля ЕПГУ: 1339447", без <table>. Порядок карточек в
    документе = место в конкурсном списке (список уже отсортирован по
    баллам сайтом)."""

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    matches = ID_EPGU_PATTERN.findall(text)

    quota_match = QUOTA_PATTERN.search(text)
    quota = int(quota_match.group(1)) if quota_match else None

    if not matches:
        return LookupResult(found=False, quota=quota)

    total = len(matches)
    for idx, applicant_code in enumerate(matches, start=1):
        if applicant_code == code:
            return LookupResult(
                found=True, rank=idx, total=total, row=[applicant_code], matched_context=True, quota=quota
            )

    return LookupResult(found=False, total=total, matched_context=True, quota=quota)

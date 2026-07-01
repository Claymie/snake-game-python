"""Универсальный парсер конкурсных списков вузов.

Списки на разных сайтах вёрстаются по-разному, поэтому парсер не привязан
к конкретной структуре одного сайта, а ищет код абитуриента по всей
странице: сначала пытается найти строку в HTML-таблице (самый частый
случай), а если таблиц нет или совпадение не найдено — ищет код в тексте
страницы построчно.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass
class LookupResult:
    found: bool
    rank: int | None = None
    total: int | None = None
    row: list[str] = field(default_factory=list)


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


def find_applicant(html: str, code: str) -> LookupResult:
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        rows = _rows_from_table(table)
        if not rows:
            continue

        header_cells = None
        data_rows = rows
        if _looks_like_header(rows[0]):
            header_cells = rows[0]
            data_rows = rows[1:]
        if not data_rows:
            continue

        has_rank_column = _first_column_is_rank_number(header_cells or [])

        for idx, cells in enumerate(data_rows, start=1):
            if any(code in cell for cell in cells):
                rank = idx
                # Используем число из первой колонки только если по заголовку
                # видно, что это явно колонка номера/места, а не сам код
                # абитуриента (иначе код вида "1339447" примут за место 1339447).
                if has_rank_column and cells[0].strip().isdigit():
                    rank = int(cells[0].strip())
                return LookupResult(found=True, rank=rank, total=len(data_rows), row=cells)

    # Фолбэк: код может лежать вне <table> (div-based вёрстка, карточки и т.д.)
    text = soup.get_text("\n")
    for line in text.splitlines():
        line = line.strip()
        if line and code in line:
            return LookupResult(found=True, rank=None, total=None, row=[line])

    return LookupResult(found=False)

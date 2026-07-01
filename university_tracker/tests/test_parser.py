"""Проверка парсера на синтетических HTML-примерах.

Реальные сайты вузов недоступны из этого окружения (сетевая политика
блокирует sibsutis.ru, abiturient.nsu.ru, nstu.ru, nsuem.ru), поэтому здесь
проверяется только логика разбора HTML — на двух типичных вариантах
вёрстки конкурсных списков: обычная таблица и div-вёрстка без таблицы.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser import find_applicant, find_applicant_by_context

TABLE_HTML = """
<html><body>
<table>
  <tr><th>№</th><th>СНИЛС/код</th><th>Сумма баллов</th></tr>
  <tr><td>1</td><td>2210001</td><td>290</td></tr>
  <tr><td>2</td><td>1339447</td><td>275</td></tr>
  <tr><td>3</td><td>4455123</td><td>260</td></tr>
</table>
</body></html>
"""

TABLE_HTML_NO_LEADING_NUMBER = """
<html><body>
<table>
  <tr><th>Код</th><th>Баллы</th></tr>
  <tr><td>2210001</td><td>290</td></tr>
  <tr><td>1339447</td><td>275</td></tr>
</table>
</body></html>
"""

DIV_HTML = """
<html><body>
<div class="row">Код 2210001, баллы 290</div>
<div class="row">Код 1339447, баллы 275</div>
</body></html>
"""

NOT_FOUND_HTML = """
<html><body>
<table>
  <tr><th>№</th><th>Код</th></tr>
  <tr><td>1</td><td>9999999</td></tr>
</table>
</body></html>
"""

MULTI_TABLE_HTML = """
<html><body>
<h3>09.03.01 Информатика и вычислительная техника (платное)</h3>
<table>
  <tr><th>№</th><th>Код</th><th>Баллы</th></tr>
  <tr><td>1</td><td>7777777</td><td>270</td></tr>
  <tr><td>2</td><td>1339447</td><td>260</td></tr>
</table>
<h3>09.03.02 Информационные системы и технологии (платное)</h3>
<table>
  <tr><th>№</th><th>Код</th><th>Баллы</th></tr>
  <tr><td>1</td><td>1339447</td><td>250</td></tr>
  <tr><td>2</td><td>8888888</td><td>240</td></tr>
  <tr><td>3</td><td>9999999</td><td>230</td></tr>
</table>
</body></html>
"""


def test_finds_rank_from_leading_numeric_column():
    result = find_applicant(TABLE_HTML, "1339447")
    assert result.found
    assert result.rank == 2
    assert result.total == 3


def test_finds_rank_by_row_position_when_no_numeric_column():
    result = find_applicant(TABLE_HTML_NO_LEADING_NUMBER, "1339447")
    assert result.found
    assert result.rank == 2
    assert result.total == 2


def test_falls_back_to_plain_text_search():
    result = find_applicant(DIV_HTML, "1339447")
    assert result.found
    assert result.rank is None
    assert "1339447" in result.row[0]


def test_not_found_returns_false():
    result = find_applicant(NOT_FOUND_HTML, "1339447")
    assert not result.found
    assert result.rank is None


def test_context_picks_correct_table_among_several():
    result_01 = find_applicant_by_context(MULTI_TABLE_HTML, "1339447", ["09.03.01"])
    assert result_01.found
    assert result_01.rank == 2
    assert result_01.total == 2

    result_02 = find_applicant_by_context(MULTI_TABLE_HTML, "1339447", ["09.03.02"])
    assert result_02.found
    assert result_02.rank == 1
    assert result_02.total == 3


def test_context_falls_back_when_heading_not_found():
    result = find_applicant_by_context(TABLE_HTML, "1339447", ["09.03.09"])
    assert result.found
    assert result.rank == 2


if __name__ == "__main__":
    test_finds_rank_from_leading_numeric_column()
    test_finds_rank_by_row_position_when_no_numeric_column()
    test_falls_back_to_plain_text_search()
    test_not_found_returns_false()
    test_context_picks_correct_table_among_several()
    test_context_falls_back_when_heading_not_found()
    print("OK: все тесты парсера прошли")

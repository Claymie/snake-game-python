"""Тесты чистой логики определения команды из апдейтов Telegram, без
реальных сетевых вызовов."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from check_telegram_trigger import evaluate_updates


def _msg(update_id, text, chat_id=111):
    return {"update_id": update_id, "message": {"text": text, "chat": {"id": chat_id}}}


def test_no_updates_keeps_offset():
    triggered, new_offset, chat_id = evaluate_updates([], offset=5)
    assert not triggered
    assert new_offset == 5
    assert chat_id is None


def test_unrelated_messages_do_not_trigger_but_advance_offset():
    updates = [_msg(10, "привет"), _msg(11, "как дела")]
    triggered, new_offset, chat_id = evaluate_updates(updates, offset=10)
    assert not triggered
    assert new_offset == 12
    assert chat_id is None


def test_start_command_triggers_and_returns_chat_id():
    updates = [_msg(10, "какой-то мусор"), _msg(11, "/start", chat_id=999)]
    triggered, new_offset, chat_id = evaluate_updates(updates, offset=10)
    assert triggered
    assert new_offset == 12
    assert chat_id == 999


def test_case_insensitive_and_trims_whitespace():
    updates = [_msg(1, "  /START  ")]
    triggered, new_offset, chat_id = evaluate_updates(updates, offset=0)
    assert triggered


if __name__ == "__main__":
    test_no_updates_keeps_offset()
    test_unrelated_messages_do_not_trigger_but_advance_offset()
    test_start_command_triggers_and_returns_chat_id()
    test_case_insensitive_and_trims_whitespace()
    print("OK: все тесты триггера Telegram прошли")

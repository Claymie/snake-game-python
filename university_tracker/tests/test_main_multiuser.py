"""Проверка мультипользовательской логики main.py: без явного персонального
запроса (плановый прогон, ручной запуск, --force-notify) полный статус
получают все пользователи; а если кто-то один явно спросил через Telegram
(TRIGGERED_CHAT_ID) — только ему, остальные молчат, если у них ничего не
изменилось. Сеть и Playwright подменяются, реально ничего не открывается.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402
from parser import LookupResult  # noqa: E402

CONFIG = {
    "users": [
        {"name": "A", "applicant_code": "111", "chat_id": "1001"},
        {"name": "B", "applicant_code": "222", "chat_id": "2002"},
    ],
    "programs": [
        {
            "university": "U",
            "specialty": "S1",
            "form": "платное",
            "url": "http://example.test/1",
            "mode": "id_epgu",
        }
    ],
}


def _run(config, initial_state, fake_results, env, monkeypatch_send):
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.yaml"
        state_path = Path(tmp) / "state.json"
        state_path.write_text(json.dumps(initial_state), encoding="utf-8")

        import yaml

        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

        orig_config_path, orig_state_path = main.CONFIG_PATH, main.STATE_PATH
        orig_fetch, orig_send = main.fetch_program_results, main.send_message
        main.CONFIG_PATH = config_path
        main.STATE_PATH = state_path
        main.fetch_program_results = lambda cfg, users, errors: fake_results
        sent = []
        main.send_message = lambda token, chat_id, text: sent.append((chat_id, text))

        old_env = {k: os.environ.get(k) for k in env}
        os.environ.update({k: v for k, v in env.items() if v is not None})
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)

        try:
            main.main()
        finally:
            main.CONFIG_PATH, main.STATE_PATH = orig_config_path, orig_state_path
            main.fetch_program_results, main.send_message = orig_fetch, orig_send
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        return sent, json.loads(state_path.read_text(encoding="utf-8"))


def test_background_run_sends_full_status_to_everyone():
    """Плановый прогон (нет TRIGGERED_CHAT_ID — это не чей-то персональный
    запрос) шлёт полный статус всем зарегистрированным, а не только тем,
    у кого что-то изменилось с прошлого раза."""
    key = main.program_key(CONFIG["programs"][0])
    fake_results = {key: {"A": LookupResult(found=True, rank=5, total=10), "B": LookupResult(found=False)}}
    sent, _ = _run(
        CONFIG,
        initial_state={},
        fake_results=fake_results,
        env={"TELEGRAM_BOT_TOKEN": "tok", "TRIGGERED_CHAT_ID": None, "GITHUB_EVENT_NAME": None},
        monkeypatch_send=None,
    )
    chat_ids_notified = sorted(c for c, _ in sent)
    assert chat_ids_notified == ["1001", "2002"], sent


def test_triggered_user_gets_full_report_even_without_change():
    key = main.program_key(CONFIG["programs"][0])
    fake_results = {key: {"A": LookupResult(found=True, rank=5, total=10), "B": LookupResult(found=False)}}
    initial_state = {"A": {key: {"found": True, "rank": 5, "total": 10, "row": [], "url": "x", "checked_at": "t"}}}
    sent, _ = _run(
        CONFIG,
        initial_state=initial_state,
        fake_results=fake_results,
        env={"TELEGRAM_BOT_TOKEN": "tok", "TRIGGERED_CHAT_ID": "2002", "GITHUB_EVENT_NAME": None},
        monkeypatch_send=None,
    )
    chat_ids_notified = [c for c, _ in sent]
    assert chat_ids_notified == ["2002"], sent


def test_unknown_chat_id_gets_not_registered_reply_and_skips_check():
    sent, state_after = _run(
        CONFIG,
        initial_state={},
        fake_results={},  # не должно даже понадобиться
        env={"TELEGRAM_BOT_TOKEN": "tok", "TRIGGERED_CHAT_ID": "9999999", "GITHUB_EVENT_NAME": None},
        monkeypatch_send=None,
    )
    assert sent == [("9999999", main.NOT_REGISTERED_TEXT)]
    assert state_after == {}


if __name__ == "__main__":
    test_background_run_sends_full_status_to_everyone()
    test_triggered_user_gets_full_report_even_without_change()
    test_unknown_chat_id_gets_not_registered_reply_and_skips_check()
    print("OK: все тесты мультипользовательской логики прошли")

"""Лёгкий скрипт без внешних зависимостей (только стандартная библиотека),
чтобы часто (раз в несколько минут) проверять, не написал ли пользователь
боту команду вроде /start — и если да, сигнализировать об этом workflow'у,
чтобы тот запустил уже полноценную (тяжёлую, с Playwright) проверку списков.

Специально не использует requests/pip install, чтобы частый опрос был
максимально дешёвым по времени выполнения в GitHub Actions.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

TRIGGER_TEXTS = {"/start", "/check", "/status", "/report", "проверить"}
OFFSET_PATH = Path(__file__).parent / "data" / "telegram_offset.json"

# Кнопка внизу чата шлёт обычный текст ("Проверить статус"), поэтому триггер
# ищем подстрокой без учёта регистра, а не точным совпадением всего текста —
# так сработает и голая команда, и кнопка, и "/start@ИмяБота" в общих чатах.
STATUS_KEYBOARD = {
    "keyboard": [[{"text": "Проверить статус"}]],
    "resize_keyboard": True,
}

BOT_COMMANDS = [
    {"command": "start", "description": "Проверить моё место в конкурсных списках"},
    {"command": "check", "description": "Проверить моё место в конкурсных списках"},
    {"command": "status", "description": "Показать текущий статус"},
]


def _get(url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, data: dict) -> None:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=body)
    urllib.request.urlopen(request, timeout=20)


def _load_offset() -> int:
    if not OFFSET_PATH.exists():
        return 0
    try:
        return int(json.loads(OFFSET_PATH.read_text(encoding="utf-8")).get("offset", 0))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0


def _save_offset(offset: int) -> None:
    OFFSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def evaluate_updates(updates: list, offset: int) -> tuple:
    """Чистая функция (без сети/файлов) для лёгкого тестирования: по списку
    апдейтов от Telegram и текущему offset решает, была ли команда, какой у
    неё chat_id, и каким должен стать новый offset."""

    triggered = False
    chat_id = None
    max_update_id = offset - 1
    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        message = update.get("message") or {}
        text = (message.get("text") or "").strip().lower()
        if any(trigger in text for trigger in TRIGGER_TEXTS):
            triggered = True
            chat_id = message.get("chat", {}).get("id")

    return triggered, max_update_id + 1, chat_id


def _ensure_commands_registered(token: str) -> None:
    """Регистрирует /start, /check, /status в меню бота (значок "/" в
    Telegram). Вызывается на каждом опросе — это дешёвый идемпотентный
    вызов, Telegram просто перезаписывает тот же список команд."""
    try:
        _post(
            f"https://api.telegram.org/bot{token}/setMyCommands",
            {"commands": json.dumps(BOT_COMMANDS)},
        )
    except Exception:
        pass


def main() -> int:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    _ensure_commands_registered(token)
    offset = _load_offset()

    data = _get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        {"offset": offset, "timeout": 0},
    )
    updates = data.get("result", [])

    triggered, new_offset, chat_id = evaluate_updates(updates, offset)
    if new_offset != offset:
        _save_offset(new_offset)

    if triggered and chat_id:
        try:
            _post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                {
                    "chat_id": chat_id,
                    "text": "🔎 Проверяю конкурсные списки, подожди примерно минуту...",
                    "reply_markup": json.dumps(STATUS_KEYBOARD),
                },
            )
        except Exception:
            # Не критично, если это уведомление не ушло — основной отчёт всё
            # равно придёт из шага respond.
            pass

    # Первая строка вывода — triggered (true/false), вторая — chat_id того,
    # кто написал команду (или пусто), чтобы main.py знал, кому персонально
    # отвечать, а не слать полный отчёт всем зарегистрированным пользователям.
    print("true" if triggered else "false")
    print(chat_id if chat_id is not None else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

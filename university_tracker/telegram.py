"""Отправка уведомлений через Telegram Bot API."""

from __future__ import annotations

import json

import requests

# Кнопка внизу чата вместо ручного набора текста. Подпись специально без
# эмодзи/лишних слов в начале — check_telegram_trigger.py ищет одну из
# TRIGGER_TEXTS подстрокой в тексте сообщения без учёта регистра, так что
# "Проверить статус" совпадёт с триггером "проверить".
STATUS_KEYBOARD = {
    "keyboard": [[{"text": "Проверить статус"}]],
    "resize_keyboard": True,
}


def send_message(token: str, chat_id: str, text: str, with_keyboard: bool = True) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if with_keyboard:
        data["reply_markup"] = json.dumps(STATUS_KEYBOARD)
    resp = requests.post(url, data=data, timeout=15)
    resp.raise_for_status()

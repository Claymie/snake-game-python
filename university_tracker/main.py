"""Точка входа: проверяет место абитуриента во всех сконфигурированных
конкурсных списках и шлёт уведомление в Telegram, если что-то изменилось.

Запуск:
    APPLICANT_CODE=1339447 \
    TELEGRAM_BOT_TOKEN=... \
    TELEGRAM_CHAT_ID=... \
    python main.py [--force-notify]
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from fetcher import PageFetcher
from parser import find_applicant_by_context
from telegram import send_message

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
STATE_PATH = BASE_DIR / "data" / "state.json"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def program_key(entry: dict) -> str:
    return f'{entry["university"]} — {entry["specialty"]} ({entry.get("form", "?")})'


def describe_change(key: str, prev: dict | None, curr: dict) -> str | None:
    was_found = bool(prev and prev.get("found"))
    now_found = curr["found"]

    if now_found and not was_found:
        if curr["rank"] is not None and curr["total"] is not None:
            return f"✅ {key}\n   Появился в списке: место {curr['rank']} из {curr['total']}"
        return f"✅ {key}\n   Появился в списке (место определить не удалось, см. лог)"

    if now_found and was_found and prev.get("rank") != curr["rank"]:
        return (
            f"🔄 {key}\n   Место изменилось: {prev.get('rank')} → {curr['rank']} "
            f"(из {curr['total']})"
        )

    if was_found and not now_found:
        return f"⚠️ {key}\n   Пропал из списка (был на месте {prev.get('rank')})"

    return None


def main() -> int:
    config = load_config()
    code = os.environ.get("APPLICANT_CODE") or str(config.get("applicant_code", "")).strip()
    if not code:
        print("Не задан код абитуриента (APPLICANT_CODE или applicant_code в config.yaml)")
        return 1

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    force_notify = "--force-notify" in sys.argv

    state = load_state()
    changes: list[str] = []
    errors: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    programs = config.get("programs", [])

    # Несколько направлений могут находиться на одной и той же странице
    # (например, все программы одного факультета показываются после клика
    # по вкладке факультета). Группируем по (url, click_text), чтобы не
    # открывать и не кликать по одной и той же странице повторно.
    groups: dict[tuple[str, str | None], list[dict]] = defaultdict(list)
    for entry in programs:
        url = entry.get("url")
        if not url:
            errors.append(f"{program_key(entry)}: не указан url в config.yaml")
            continue
        groups[(url, entry.get("click_text"))].append(entry)

    with PageFetcher() as fetcher:
        for (url, click_text), entries in groups.items():
            try:
                html = fetcher.get_html(url, click_text=click_text)
            except Exception as exc:  # noqa: BLE001 - хотим залогировать любую ошибку сети
                for entry in entries:
                    errors.append(f"{program_key(entry)}: ошибка загрузки страницы — {exc}")
                continue

            for entry in entries:
                key = program_key(entry)
                result = find_applicant_by_context(html, code, entry.get("match_all", []))
                prev = state.get(key)
                curr = {
                    "found": result.found,
                    "rank": result.rank,
                    "total": result.total,
                    "row": result.row,
                    "url": url,
                    "checked_at": now,
                }
                state[key] = curr

                change_text = describe_change(key, prev, curr)
                if change_text:
                    changes.append(change_text)

    save_state(state)

    print(f"Проверено направлений: {len(programs)}")
    print(f"Изменения: {len(changes)}")
    for c in changes:
        print(c)
    if errors:
        print("Ошибки:")
        for e in errors:
            print(" -", e)

    should_notify = bool(changes) or force_notify
    if should_notify and token and chat_id:
        lines = ["📋 Обновление по конкурсным спискам"]
        if changes:
            lines.append("")
            lines.extend(changes)
        else:
            lines.append("\nБез изменений с прошлой проверки.")
        if errors:
            lines.append("\nОшибки при проверке:")
            lines.extend(f"- {e}" for e in errors)
        send_message(token, chat_id, "\n".join(lines))
    elif should_notify:
        print("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID не заданы — уведомление не отправлено")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

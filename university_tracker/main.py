"""Точка входа: проверяет место каждого зарегистрированного пользователя
(config.yaml -> users) во всех сконфигурированных конкурсных списках и
шлёт каждому уведомление в Telegram при изменениях.

Запуск:
    TELEGRAM_BOT_TOKEN=... \
    python main.py [--force-notify]

Переменная окружения TRIGGERED_CHAT_ID (её проставляет workflow при
срабатывании на команду из Telegram) заставляет отправить полный отчёт
только этому чату, даже без изменений — остальные пользователи в этом
случае получают уведомление, только если у них реально что-то изменилось.
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
from parser import LookupResult, find_applicant_by_context, find_applicant_by_id_epgu
from telegram import send_message

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
STATE_PATH = BASE_DIR / "data" / "state.json"

NOT_REGISTERED_TEXT = (
    "Этот чат не привязан ни к одному отслеживаемому профилю. "
    "Попроси владельца бота добавить твой код и chat_id в config.yaml."
)


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_users(config: dict) -> list[dict]:
    users = config.get("users") or []
    if users:
        return users
    # Обратная совместимость со старой схемой на одного пользователя.
    code = os.environ.get("APPLICANT_CODE") or str(config.get("applicant_code", "")).strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if code and chat_id:
        return [{"name": "default", "applicant_code": code, "chat_id": chat_id}]
    return []


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


def _place_text(rank: int | None, total: int | None, quota: int | None) -> str:
    """Квота ("Всего мест") — это реальный потолок зачисления на платное,
    а не число участников конкурса, поэтому именно с ней сравниваем место,
    если она нашлась на странице. Число участников показываем отдельно,
    для справки."""
    if quota is not None:
        passing = " ✅ проходит" if rank is not None and rank <= quota else " ⚠️ пока не проходит"
        extra = f", всего заявок: {total}" if total is not None else ""
        return f"место {rank} из {quota} мест{extra}{passing}"
    return f"место {rank}/{total}"


def status_line(key: str, mode: str, entry: dict, result: LookupResult) -> str:
    if result.found:
        return f"✅ {key}: {_place_text(result.rank, result.total, result.quota)}"
    if result.matched_context:
        quota_text = f", мест: {result.quota}" if result.quota is not None else ""
        return f"➖ {key}: список найден ({result.total} чел.{quota_text}), кода в нём нет"
    if mode == "id_epgu":
        return f"❔ {key}: не нашли на странице ни одной записи 'ID профиля ЕПГУ'"
    return (
        f"❔ {key}: не нашли таблицу по match_all={entry.get('match_all')} "
        f"— проверь click_text/match_all"
    )


def describe_change(key: str, prev: dict | None, curr: dict) -> str | None:
    was_found = bool(prev and prev.get("found"))
    now_found = curr["found"]

    if now_found and not was_found:
        if curr["rank"] is not None:
            place = _place_text(curr["rank"], curr["total"], curr.get("quota"))
            return f"✅ {key}\n   Появился в списке: {place}"
        return f"✅ {key}\n   Появился в списке (место определить не удалось, см. лог)"

    if now_found and was_found and prev.get("rank") != curr["rank"]:
        place = _place_text(curr["rank"], curr["total"], curr.get("quota"))
        return f"🔄 {key}\n   Место изменилось: {prev.get('rank')} → {curr['rank']} ({place})"

    if was_found and not now_found:
        return f"⚠️ {key}\n   Пропал из списка (был на месте {prev.get('rank')})"

    return None


def fetch_program_results(config: dict, users: list[dict], errors: list[str]) -> dict[str, dict[str, LookupResult]]:
    """Возвращает {program_key: {user_name: LookupResult}}. Каждая страница
    открывается ровно один раз за прогон, даже если пользователей и/или
    направлений на этой странице несколько — код каждого пользователя
    ищется в уже загруженном HTML, это не стоит лишних запросов."""

    programs = config.get("programs", [])

    groups: dict[tuple[str, tuple[str, ...]], list[dict]] = defaultdict(list)
    for entry in programs:
        url = entry.get("url")
        if not url:
            errors.append(f"{program_key(entry)}: не указан url в config.yaml")
            continue
        groups[(url, tuple(entry.get("click_sequence") or []))].append(entry)

    results: dict[str, dict[str, LookupResult]] = {}

    with PageFetcher() as fetcher:
        for (url, click_sequence), entries in groups.items():
            autoscroll = any(entry.get("autoscroll") for entry in entries)
            try:
                html = fetcher.get_html(url, click_sequence=list(click_sequence), autoscroll=autoscroll)
            except Exception as exc:  # noqa: BLE001 - хотим залогировать любую ошибку сети
                for entry in entries:
                    errors.append(f"{program_key(entry)}: ошибка загрузки страницы — {exc}")
                continue

            for entry in entries:
                key = program_key(entry)
                mode = entry.get("mode", "context")
                per_user: dict[str, LookupResult] = {}
                for user in users:
                    code = str(user["applicant_code"])
                    if mode == "id_epgu":
                        per_user[user["name"]] = find_applicant_by_id_epgu(html, code)
                    else:
                        per_user[user["name"]] = find_applicant_by_context(
                            html, code, entry.get("match_all", [])
                        )
                results[key] = per_user

    return results


def main() -> int:
    config = load_config()
    users = load_users(config)
    if not users:
        print("Не настроено ни одного пользователя (добавь users в config.yaml)")
        return 1

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    triggered_chat_id = os.environ.get("TRIGGERED_CHAT_ID") or None
    manual_run = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    force_notify_flag = "--force-notify" in sys.argv

    if triggered_chat_id and not any(str(u["chat_id"]) == str(triggered_chat_id) for u in users):
        print(f"Неизвестный chat_id {triggered_chat_id} — команду игнорирую.")
        if token:
            send_message(token, triggered_chat_id, NOT_REGISTERED_TEXT)
        return 0

    errors: list[str] = []
    program_results = fetch_program_results(config, users, errors)
    programs = config.get("programs", [])

    state = load_state()
    now = datetime.now(timezone.utc).isoformat()

    print(f"Проверено направлений: {len(programs)} для {len(users)} пользователь(ей)")
    if errors:
        print("Ошибки:")
        for e in errors:
            print(" -", e)

    for user in users:
        user_name = user["name"]
        user_chat_id = str(user["chat_id"])
        user_state = state.setdefault(user_name, {})

        status_lines: list[str] = []
        changes: list[str] = []

        for entry in programs:
            key = program_key(entry)
            per_user = program_results.get(key)
            if per_user is None:
                continue
            result = per_user[user_name]
            mode = entry.get("mode", "context")
            # Квота на сайте не всегда парсится надёжно (или её вообще нет на
            # странице), а число мест фиксировано на всю приёмную кампанию —
            # значение из config.yaml приоритетнее того, что нашли на странице.
            if entry.get("quota") is not None:
                result.quota = entry["quota"]

            curr = {
                "found": result.found,
                "rank": result.rank,
                "total": result.total,
                "quota": result.quota,
                "row": result.row,
                "url": entry.get("url"),
                "checked_at": now,
            }
            prev = user_state.get(key)
            user_state[key] = curr

            status_lines.append(status_line(key, mode, entry, result))
            change_text = describe_change(key, prev, curr)
            if change_text:
                changes.append(change_text)

        print(f"\n[{user_name}] изменений: {len(changes)}")
        for s in status_lines:
            print(" -", s)

        wants_full_report = (
            user_chat_id == str(triggered_chat_id)
            or (manual_run and not triggered_chat_id)
            or force_notify_flag
        )

        if not token:
            continue

        if changes:
            lines = ["📋 Обновление по конкурсным спискам", ""]
            lines.extend(changes)
            if errors:
                lines.append("\nОшибки при проверке:")
                lines.extend(f"- {e}" for e in errors)
            send_message(token, user_chat_id, "\n".join(lines))
        elif wants_full_report:
            lines = ["📋 Без изменений с прошлой проверки. Текущий статус:", ""]
            lines.extend(status_lines)
            if errors:
                lines.append("\nОшибки при проверке:")
                lines.extend(f"- {e}" for e in errors)
            send_message(token, user_chat_id, "\n".join(lines))

    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

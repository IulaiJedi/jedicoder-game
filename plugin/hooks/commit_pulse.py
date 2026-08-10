#!/usr/bin/env python3
"""PostToolUse-хук: серия коммитов и напоминание сохраниться.

Коммит-напоминание — не геймификация, а защита от потери работы (§9.2),
и оно же кормит ось соревнования «серия дней» (§9.5).

Закон хуков: любая ошибка — молчаливый выход. Этот хук вообще ничего не
блокирует, он только считает и напоминает.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

_PLUGIN_ROOT = Path(
    os.environ.get("CLAUDE_PLUGIN_ROOT")
    or Path(__file__).resolve().parents[1]
)
sys.path.insert(0, str(_PLUGIN_ROOT / "lib"))

import _shared  # noqa: E402
import bash_guard  # noqa: E402
from jedicoder import state as st  # noqa: E402

DATE_FORMAT = "%Y-%m-%d"

# Порог напоминания: столько изменённых файлов без коммита. Метрика —
# файлы, а не время: часы у падавана идут по-своему, а «сколько всего
# накопилось несохранённым» понятно любому.
DIRTY_THRESHOLD = 8

# Окно молчания, в срабатываниях хука: напомнили — дальше не бубним,
# пока падаван не сделает коммит или не пройдёт столько инструментов.
QUIET_CALLS = 20

# Глобальные опции git, забирающие следующий токен как значение: без их
# пропуска `git -C /путь commit` не опознаётся коммитом вовсе.
_GIT_VALUE_OPTS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace")

# Опции, при которых `git commit` ничего не сохраняет. Считать их
# коммитом — значит накрутить серию и снять напоминание «сохранись» за
# работу, которой не было.
_NOT_A_COMMIT = ("--dry-run", "--help", "-h")


def is_commit(tokens):
    """Команда действительно создаёт коммит?

    Проверка идёт по подкоманде, а не по второму слову: у git бывают
    глобальные опции перед подкомандой. И отсеиваются прогоны вхолостую
    («--dry-run», «--help») — они не сохраняют ничего, а серия и окно
    напоминания обязаны отражать сохранённую работу.
    """
    if not tokens or tokens[0] != "git":
        return False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in _GIT_VALUE_OPTS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        break
    if index >= len(tokens) or tokens[index] != "commit":
        return False
    return not any(arg in _NOT_A_COMMIT for arg in tokens[index + 1:])


def _parse_date(value):
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except (TypeError, ValueError):
        return None


def bump_streak(streak, today):
    """Обновить серию по дате коммита. Чистая функция: дата приходит
    параметром, чтобы границы суток проверялись тестом, а не часами.
    """
    result = dict(streak or {})
    last = _parse_date(result.get("last_commit_date"))
    now = _parse_date(today)
    if now is None:
        return result
    if last == now:
        return result
    if last is not None and now - last == timedelta(days=1):
        current = int(result.get("current", 0) or 0) + 1
    else:
        current = 1
    result["current"] = current
    result["best"] = max(int(result.get("best", 0) or 0), current)
    result["last_commit_date"] = today
    return result


def today_utc():
    return datetime.now(timezone.utc).strftime(DATE_FORMAT)


def dirty_count(project_dir):
    """Сколько файлов изменено с последнего коммита. Только чтение."""
    try:
        done = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_dir), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if done.returncode != 0:
        return 0
    return len([line for line in done.stdout.splitlines() if line.strip()])


def _committed_today(project_dir, today):
    """Последний коммит в проекте — сегодняшний по UTC? Только чтение.

    `cwd` — всегда папка проекта, а не cwd команды: `git commit -C
    /другой/репо` иначе засчитал бы чужой проект. Та же обработка ошибок,
    что у `dirty_count` — нет git, нет коммитов вовсе (`returncode != 0`)
    — не бумим, ничего не ломаем.

    Формат — `%cI` (строгий ISO 8601 со своим офсетом), а не `%cs`: `%cs`
    отдаёт дату в таймзоне самого коммита, а `today` здесь всегда UTC
    (`today_utc()`). На машине, чей локальный офсет отличается от UTC,
    коммит у полуночи разъезжается с `%cs` на сутки в любую сторону —
    серия не растёт за настоящий сегодняшний коммит. `%cI` переводится в
    UTC в питоне, и сравнение честное независимо от локального времени.
    """
    try:
        done = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            cwd=str(project_dir), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if done.returncode != 0:
        return False
    try:
        committed = datetime.fromisoformat(done.stdout.strip())
    except ValueError:
        return False
    return committed.astimezone(timezone.utc).strftime(DATE_FORMAT) == today


def react(payload):
    """Ответ на завершившийся вызов Bash или None, если сказать нечего."""
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    # Разведка не под блокировкой: нужно только узнать project_dir и текущее
    # commit_nag_left, чтобы решить, будет ли вообще мутация. Настоящий
    # read-modify-write — ниже, отдельным `update_state()` на каждую ветку,
    # где состояние действительно меняется.
    state = _shared.load_state()
    project_dir = (state.get("project") or {}).get("path")
    if not project_dir or not Path(project_dir).is_dir():
        # Папка проекта неизвестна: считать нечего, а угадывать по cwd
        # нельзя — падаван мог зайти куда угодно.
        return None

    # Разбор по простым командам, а не плоский shlex.split: `git add -A
    # && git commit -m x` — самая частая форма коммита, и без разбора по
    # операторам она никогда не опознаётся как коммит вовсе.
    saw_commit = any(
        is_commit(tokens) for tokens in bash_guard.simple_commands(command)
    )
    if saw_commit:
        # «Успешный commit в проекте» — это и дата HEAD сегодня (не другой
        # репозиторий, не мимо), и чистое рабочее дерево прямо сейчас: одной
        # даты мало — тот же HEAD остаётся «сегодняшним» и после провала
        # следующего коммита, и после команды, которая вообще ничего не
        # сделала (симулированный вызов хука без реального git). Рабочее
        # дерево пустеет только тогда, когда `git commit` действительно
        # забрал в индекс то, что было изменено.
        if dirty_count(project_dir) != 0 or not _committed_today(
            project_dir, today_utc()
        ):
            # git не смог ответить, коммитов вовсе нет, последний — не
            # сегодняшний, либо в рабочем дереве осталось несохранённое:
            # увиденный `git commit` либо провалился, либо относится к
            # другому репозиторию, либо ничего не закоммитил на самом деле.
            # Спецификация («увидели успешный git commit в проекте») не
            # выполнена — ни серии, ни снятого окна молчания.
            return None
        # Мутация — под блокировкой, на свежепрочитанном состоянии: между
        # разведкой выше и этим окном могла успеть записаться чужая правка
        # (другой терминал, параллельный субагент, cli.py) — перечитываем,
        # а не берём в работу устаревший `state`.
        with _shared.update_state() as fresh:
            old_streak = fresh.get("streak") or {}
            streak = bump_streak(old_streak, today_utc())
            fresh["streak"] = streak
            if streak != old_streak:
                # Второй и последующий коммиты того же UTC-дня возвращают
                # тот же streak (bump_streak — no-op на same-day): событие
                # только когда серия действительно изменилась, иначе очередь
                # росла бы на каждый коммит без новой информации для бота.
                st.enqueue_event(fresh, "streak_updated", payload={
                    "current": int(streak.get("current", 0)),
                    "best": int(streak.get("best", 0)),
                })
            # Коммит закрывает окно молчания: следующая порция правок снова
            # имеет право на напоминание.
            fresh.pop("commit_nag_left", None)
        return {"systemMessage": "Серия коммитов: {} (лучшая {}).".format(
            streak.get("current", 0), streak.get("best", 0)
        )}

    left = int(state.get("commit_nag_left", 0) or 0)
    if left > 0:
        with _shared.update_state() as fresh:
            current_left = int(fresh.get("commit_nag_left", 0) or 0)
            if current_left > 0:
                fresh["commit_nag_left"] = current_left - 1
        return None
    if dirty_count(project_dir) < DIRTY_THRESHOLD:
        return None
    with _shared.update_state() as fresh:
        fresh["commit_nag_left"] = QUIET_CALLS
    return {"systemMessage": (
        "Ты давно не сохранялся: изменённых файлов уже много, а откатиться "
        "будет некуда. Сделай коммит — это точка возврата, а не отчётность."
    )}


def main():
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        out = react(payload)
        if out:
            print(json.dumps(out, ensure_ascii=False))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

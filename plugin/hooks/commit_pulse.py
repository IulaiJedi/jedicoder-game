#!/usr/bin/env python3
"""PostToolUse-хук: серия коммитов и напоминание сохраниться.

Коммит-напоминание — не геймификация, а защита от потери работы (§9.2),
и оно же кормит ось соревнования «серия дней» (§9.5).

Закон хуков: любая ошибка — молчаливый выход. Этот хук вообще ничего не
блокирует, он только считает и напоминает.

Серия от сессии не зависит: считается сдвиг HEAD записанной папки проекта,
из какого бы окна человек ни сохранил. Напоминание сохраниться — слова
игры, и звучит оно только в игровой сессии (#97).
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


def grew(before, after):
    """Выросло ли число серии. Чистая функция: мусор в сохранении — нуль."""
    def current(streak):
        try:
            return int((streak or {}).get("current", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            return 0
    return current(after) > current(before)


def today_utc():
    """Календарная дата UTC. Часы одни на игру — те же, что у журнала
    Тёмной стороны: две реализации разошлись бы молча, а даты серии и
    даты журнала стоят в Разборе рядом.
    """
    return st.today_utc()


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


def head_sha(project_dir):
    """Отпечаток последнего коммита проекта. Только чтение.

    Пустая строка — коммитов нет (репозиторий пуст или папка ещё не
    репозиторий): это тоже знание, и с ним первый в жизни коммит
    читается сдвигом, как любой другой. None — git не ответил вовсе:
    сравнивать не с чем.
    """
    try:
        done = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
            cwd=str(project_dir), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return ""
    return done.stdout.strip()


def seen_head(state, project_dir):
    """Отпечаток, который хук видел в этой папке в прошлый раз, или None.

    Хук зовётся ПОСЛЕ команды, и «до» ему взять неоткуда, кроме
    собственной записи с прошлого вызова. Запись привязана к папке
    проекта: отпечаток прежней папки — не «было» для новой, иначе после
    `project path` любой текст `git commit` читался бы сдвигом.
    """
    seen = state.get("commit_head")
    if not isinstance(seen, dict) or seen.get("path") != str(project_dir):
        return None
    sha = seen.get("sha")
    return sha if isinstance(sha, str) else None


def _remember_head(state, project_dir, sha):
    state["commit_head"] = {"path": str(project_dir), "sha": sha}


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
    game = _shared.is_game_session(payload)
    if game:
        state = _shared.load_state()
    else:
        # Чужая сессия: сохранение только читается. `load` на пустом месте
        # берёт замок, испорченный файл уносит в сторону, прежнюю игру — в
        # архив; ничего из этого чужой запрос в Claude Code делать не вправе.
        state = st.peek(_shared.state_path())
        if state is None:
            return None
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
    head = head_sha(project_dir)
    before = seen_head(state, project_dir)
    if not saw_commit and head is not None and head != before:
        # HEAD сдвинулся без нашего участия (pull, checkout, коммит из
        # другого окна): запоминаем как новое «было», серию не трогаем.
        with _shared.update_state() as fresh:
            _remember_head(fresh, project_dir, head)
    if saw_commit:
        # «Успешный commit в проекте» — это HEAD проекта, который сдвинулся
        # за эту команду, и сдвинулся на сегодняшний коммит. Текст команды
        # ничего не доказывает: коммит мог провалиться, уйти в другой
        # репозиторий (`git -C`) или не найти, что сохранять.
        #
        # Чистоты рабочего дерева больше не требуется: «один файл сохранил,
        # второй ещё правится» — обычный день, и раньше он серию не растил.
        if before is not None:
            happened = bool(head) and head != before
        else:
            # Первый вызов в этой папке: сравнивать не с чем. Тогда —
            # прежняя, строгая примета: дерево опустело, значит коммит
            # забрал изменённое. Недосчёт здесь безопаснее приписки.
            happened = bool(head) and dirty_count(project_dir) == 0
        if not happened or not _committed_today(project_dir, today_utc()):
            # Ни серии, ни снятого окна молчания. Но сдвиг запоминаем:
            # вчерашний коммит, подтянутый этой же командой, — уже «было».
            if head is not None and head != before:
                with _shared.update_state() as fresh:
                    _remember_head(fresh, project_dir, head)
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
            _remember_head(fresh, project_dir, head)
        if not grew(old_streak, streak):
            # «Серия сохранений: 1» после каждого сохранения за день — шум
            # (живая приёмка 0.11.0, #122). Строка звучит, только когда число
            # выросло: первое сохранение дня после вчерашнего — или первое
            # вообще. Серия, начатая заново после перерыва, молчит: число
            # стало меньше, и хвалить не за что, а упрекать игра не будет.
            return None
        return {"systemMessage": st.streak_line(
            streak.get("current", 0), streak.get("best", 0)
        ) + "."}

    if not game:
        # Напоминание и его окно молчания — только в игровой сессии: в чужом
        # проекте человек не играет, и слова игры ему там не нужны.
        return None
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
        "Изменённых файлов уже много, а сохранения давно не было. Попроси "
        "Claude сохранить сделанное: будет куда вернуться, если что-то "
        "сломается."
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

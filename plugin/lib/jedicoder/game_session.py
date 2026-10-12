"""Игровая сессия: одно правило на Лицо и на хуки (#97).

Плагин ставится на всю машину, и всё, что он зовёт сам — снимок Лица после
каждого хода, хуки на каждом запросе и каждой команде, — срабатывает в любой
сессии Claude Code, в том числе в чужих проектах человека. Игра действует
только в игровой сессии. Признаков три, и хватает любого:

1. сессию запустил Голокрон — переменная запуска `JEDICODER_GOLOKRON`;
2. папка сессии — записанная папка проекта или папка внутри неё;
3. в этой сессии человек позвал команду игры. Модуль Лица помнит это сам и
   передаёт флагом (`called`); хук запроса записывает идентификатор сессии в
   сохранение (`note`), остальные хуки сверяют с записанным свой.

Модуль не пишет на диск и не берёт замок: `is_game` получает уже прочитанное
сохранение (или None — показать нечего), запись списка делает вызывающий
под замком.
"""
import os
from pathlib import Path

#: Метка, которую ставит десктопный Голокрон, запуская Claude Code у себя в
#: Верстаке (golokron/src/main/workbench/launch.ts, GOLOKRON_MARK).
GOLOKRON_MARK = "JEDICODER_GOLOKRON"

#: С этого начинается запрос, которым человек зовёт команду игры. То же
#: слово у модуля Лица (`GAME_COMMAND` в face.tsx).
COMMAND_PREFIX = "/jedicoder:"

#: Ключ сохранения: идентификаторы последних игровых сессий, свежая — в
#: конце. Ключ необязательный: нет его или в нём мусор — список пуст.
SESSIONS_KEY = "game_sessions"

#: Сколько сессий помнит сохранение; старые вытесняются. Вытесненная сессия
#: снова станет игровой на следующей команде игры.
SESSIONS_CAP = 20

#: Идентификатор длиннее — не идентификатор: в сохранение не пишется.
_ID_MAX = 200


def launched_by_golokron(environ=None):
    """Запущена ли сессия Голокроном — по переменной запуска."""
    environ = os.environ if environ is None else environ
    return bool(environ.get(GOLOKRON_MARK))


def is_game_command(text):
    """Запрос человека зовёт команду игры?"""
    return isinstance(text, str) and text.lstrip().startswith(COMMAND_PREFIX)


def is_session_id(value):
    """Годится ли значение из данных хука в идентификаторы сессии."""
    return isinstance(value, str) and 0 < len(value) <= _ID_MAX


def sessions(state):
    """Записанные игровые сессии, свежая — последней. Мусор — пустой список.

    Мусор не разбирается по частям: список, где хоть что-то не идентификатор,
    правили руками, и верить остальному в нём нечем.
    """
    if not isinstance(state, dict):
        return []
    value = state.get(SESSIONS_KEY)
    if not isinstance(value, list) or not all(is_session_id(item) for item in value):
        return []
    return list(value)


def note(state, session_id):
    """Записать сессию игровой. True — сохранение изменилось.

    Сессия, позвавшая игру снова, уходит в свежий конец: вытесняются те, где
    игру не звали дольше всего. Уже последняя — писать нечего.
    """
    if not is_session_id(session_id):
        return False
    known = sessions(state)
    if known and known[-1] == session_id:
        return False
    fresh = [item for item in known if item != session_id] + [session_id]
    state[SESSIONS_KEY] = fresh[-SESSIONS_CAP:]
    return True


def inside_project(state, cwd):
    """Открыта ли сессия в записанной папке проекта или внутри неё."""
    project = state.get("project") if isinstance(state, dict) else None
    project = project.get("path") if isinstance(project, dict) else None
    if not isinstance(project, str) or not project:
        return False
    if not isinstance(cwd, str) or not cwd:
        return False
    # Относительный путь в сохранении — правка руками: от какой папки его
    # считать, неизвестно, и совпал бы он с любой сессией.
    if not Path(project).is_absolute():
        return False
    try:
        # Обе стороны раскрываются: папку проекта записал `project path`
        # уже раскрытой, а сессию могли открыть по ссылке на неё.
        here = Path(cwd).resolve()
        root = Path(project).resolve()
        wide = root == Path(root.anchor) or root == Path.home().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    if here == root:
        return True
    # Проектом назвали домашнюю папку или корень диска: «внутри» оказался бы
    # любой проект человека, и игра встала бы в каждом. Там — только сама папка.
    return not wide and root in here.parents


def is_game(state, cwd=None, session_id=None, golokron=False, called=False):
    """Игровая ли сессия. Только чтение, диск не трогает (кроме `resolve`).

    `state` — сохранение или None, когда его нет (`state.peek`): тогда
    говорят только признаки, которым сохранение не нужно. `cwd` — папка
    сессии, `session_id` — её идентификатор из данных хука; того и другого
    может не быть, и признак тогда просто молчит. `golokron` — сессию
    запустил Голокрон (`launched_by_golokron`). `called` — третий признак
    для того, кто идентификатора не знает, но помнит сам: модуль Лица.
    """
    if golokron or called:
        return True
    if not isinstance(state, dict):
        return False
    if inside_project(state, cwd):
        return True
    return is_session_id(session_id) and session_id in sessions(state)

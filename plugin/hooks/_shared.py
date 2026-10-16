#!/usr/bin/env python3
"""Общее для хуков штрафов (dark_side): состояние, счётчик, катсцены.

Закон хуков (действует с session_start.py): любая ошибка — молчаливый
выход без блокировки. Поэтому здесь только простые функции без побочных
эффектов сверх записи состояния, а всё рискованное ловит вызывающий.
"""
import contextlib
import os
import sys
from pathlib import Path

PLUGIN_ROOT = Path(
    os.environ.get("CLAUDE_PLUGIN_ROOT")
    or Path(__file__).resolve().parents[1]
)
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

from jedicoder import content  # noqa: E402
from jedicoder import game_session  # noqa: E402
from jedicoder import state as st  # noqa: E402

# Порог из §9.2: на пятом нарушении приходит Магистр. Не наказание —
# повод для разговора.
MAGISTR_THRESHOLD = 5

# Первое падаван-видимое употребление слова «Магистр» — значит здесь и
# глосса (D-04: имя роли остаётся, но объясняется при первой встрече).
# Правка строго текстовая: ни одной новой ветки и ни одного нового вызова,
# закон хуков в силе. Тесты ссылаются на константу, а не на её содержимое.
#
# Зовут Магистра словами, а не командой: команду человек не набирает
# (живой проход 2026-10-09), её знает модель.
MAGISTR_INVITE = (
    "Штрафов набралось пять. Магистр — наставник: он смотрит на работу "
    "свежим взглядом и говорит, что поменять. Скажи Claude: «позови "
    "Магистра»."
)


def penalty_line(amount, kind):
    """«Штраф: +1 — запрос без подробностей.» — первая фраза сообщения хука.

    Слово «штраф» обязано прозвучать в момент начисления: иначе число на
    первом экране появляется без истории (живой проход 2026-10-09). Слова
    типа — те же, что под счётом на первом экране (state.DARK_SIDE_WORDS).
    """
    return "Штраф: +{} — {}.".format(
        int(amount), st.DARK_SIDE_WORDS.get(kind, kind)
    )


def plugin_root():
    return PLUGIN_ROOT


def state_path():
    """Куда пишет хук — считает движок, тем же кодом, что и для себя.

    Своя копия этой строки тут уже была, и ровно она давала расщеплённое
    состояние: хук раскрывал значение переменной по одним правилам,
    движок по другим (долг №0). Источник правды один — state.state_path().
    """
    return st.state_path()


def load_state():
    return st.load(state_path())


def save_state(state, path=None):
    st.save(state, path or state_path())


@contextlib.contextmanager
def update_state(path=None):
    """Делегат state.update_state с резолвом пути из окружения хука."""
    with st.update_state(path or state_path()) as state:
        yield state


class _Unchanged(Exception):
    """Выход из окна записи без сохранения: менять нечего."""


def is_game_session(payload):
    """Игровая ли сессия, в которой сработал хук (#97).

    Плагин стоит на всей машине, и хук зовётся в любой сессии Claude Code.
    Вне игровой он молчит и сохранение не трогает; исключений два, и оба
    не про сессию: катастрофу сторож блокирует везде, а серию сохранений
    хук считает по папке проекта, из какого бы окна ни сохранили.
    Признаки считает движок,
    той же функцией, что и для Лица (`game_session.is_game`); хук приносит
    своё: папку сессии и её идентификатор из данных Claude Code (`cwd`,
    `session_id`) и переменную запуска Голокрона.

    Сохранение читается через `state.peek`: без замка, без починки, без
    архива — в чужой сессии диск не трогается вовсе. Никогда не бросает:
    не смогли понять — сессия не игровая, хук молчит (закон хуков).
    """
    try:
        return bool(game_session.is_game(
            st.peek(state_path()),
            cwd=payload.get("cwd"),
            session_id=payload.get("session_id"),
            golokron=game_session.launched_by_golokron(),
        ))
    except Exception:
        return False


def note_game_command(payload):
    """Запрос зовёт команду игры — записать сессию игровой (#97).

    Третий признак игровой сессии для хуков. Зовёт его один хук запроса:
    только он видит, что набрал человек. Остальные сверяют свой
    `session_id` с записанным.

    Сохранения ещё нет — заводится здесь: в голом терминале первая команда
    игры приходит раньше, чем её скилл позовёт движок, и без записи хуки
    первого вечера молчали бы до второй команды. Человек игру позвал сам,
    и то же сохранение через секунду завела бы она; прежнюю игру по той же
    причине уносит в архив та же дверь (`state.load`). Паспорт (`padawan_id`)
    хук не ставит и здесь: по нему приложение держит шаг «Первый запуск», и
    ставит его команда игры.

    Никогда не бросает: запись — справка для хуков, её сбой запрос человека
    не задевает. Файл переписывается, только когда список изменился.
    """
    try:
        text = payload.get("prompt") or payload.get("user_prompt")
        if not game_session.is_game_command(text):
            return
        session_id = payload.get("session_id")
        if not game_session.is_session_id(session_id):
            return  # идентификатора нет — писать нечего и заводить нечего
        path = state_path()
        if game_session.sessions(st.peek(path))[-1:] == [session_id]:
            return
        with update_state(path) as state:
            if not game_session.note(state, session_id):
                raise _Unchanged()
    except _Unchanged:
        return
    except Exception:
        return


def record_permission_mode(payload):
    """Записать в сохранение режим разрешений из данных хука.

    Claude Code кладёт его в поле `permission_mode` (у UserPromptSubmit и
    PreToolUse оно есть, у SessionStart — нет). По нему первый квест говорит
    человеку правду о режиме, а не просит искать строку внизу окна (#87).

    Режим у каждой сессии свой, а поле в сохранении одно. Свежим его
    держит PreToolUse: он срабатывает перед каждой командой игры в той же
    сессии, поэтому контракт читает режим своего окна, а не соседнего.

    Пишется только из игровой сессии (#97): режим чужого окна игре не
    нужен, а назвать его человеку она бы могла.

    Никогда не бросает: режим — справка, и её сбой не должен задеть ни
    запрос падавана, ни решение сторожа о команде. Файл переписывается,
    только когда режим сменился: хук срабатывает на каждой команде. Тому,
    кто ещё не играет, сохранение не заводится: его создаёт первая команда
    игры, а не чужой запрос в Claude Code.
    """
    try:
        if not is_game_session(payload):
            return
        reported = payload.get("permission_mode")
        path = state_path()
        if not Path(path).exists():
            # Игру ещё не начинали: и замок не берётся — он оставил бы на
            # диске папку игры и свой файл.
            return
        with update_state(path) as state:
            # Под замком, после чтения: испорченный файл `load` к этому
            # моменту уже унёс в сторону, и писать поверх пустоты нечего.
            if not Path(path).exists():
                raise _Unchanged()
            if not st.note_permission_mode(state, reported):
                raise _Unchanged()
    except _Unchanged:
        return
    except Exception:
        return


def add_dark_side(state, amount, kind):
    """Прибавить к счёту штрафов (dark_side) и вернуть новое значение.

    XP не трогается никогда (§9.2): счётчик учит, а не штрафует.
    Мусор в поле (правка руками) считается нулём — падать тут нельзя.

    Тип нарушения (`kind` из state.DARK_SIDE_KINDS) — обязательный
    параметр, а не удобство: журнал пишется здесь же, тем же проходом по
    состоянию, что и счётчик. Начислить очко и не оставить записи должно
    быть нельзя — иначе Разбор посчитает не то, что видит падаван.
    """
    try:
        current = int(state.get("dark_side", 0))
    except (TypeError, ValueError):
        current = 0
    current += int(amount)
    state["dark_side"] = current
    st.record_dark_side(state, kind, count=int(amount))
    st.enqueue_event(state, "dark_side", payload={
        "amount": int(amount), "total": current,
    })
    return current


def magistr_invite(state):
    """Строка приглашения, если счёт только что достиг порога.

    Один раз за прохождение: флаг в состоянии. Иначе одно и то же
    приглашение прилетало бы на каждом следующем нарушении.
    """
    try:
        current = int(state.get("dark_side", 0))
    except (TypeError, ValueError):
        return ""
    if current < MAGISTR_THRESHOLD or state.get("magistr_called"):
        return ""
    state["magistr_called"] = True
    return MAGISTR_INVITE


def rule_text(plugin_dir, rule_id):
    """Катсцена — текст правила Кодекса, а не строка в питоне.

    Слова игры живут в контент-ядре: то же правило потом читается
    падаваном через Кодекс. Правило не нашлось — пустая строка, хук
    промолчит, но действие всё равно обработает.
    """
    try:
        rules = content.load_rules(Path(plugin_dir) / "content" / "ru")
    except Exception:
        return ""
    for rule in rules:
        if rule.rule == rule_id:
            return "{}\n\n{}".format(rule.title, rule.body.strip())
    return ""

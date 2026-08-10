#!/usr/bin/env python3
"""Общее для хуков Тёмной стороны: состояние, счётчик ТС, катсцены.

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
from jedicoder import state as st  # noqa: E402

# Порог из §9.2: на пятом нарушении приходит Магистр. Не наказание —
# повод для разговора.
MAGISTR_THRESHOLD = 5

# Первое падаван-видимое употребление слова «Магистр» — значит здесь и
# глосса (D-04: имя роли остаётся, но объясняется при первой встрече).
# Правка строго текстовая: ни одной новой ветки и ни одного нового вызова,
# закон хуков в силе. Тесты ссылаются на константу, а не на её содержимое.
MAGISTR_INVITE = (
    "Тёмная сторона копится. Магистр — наставник, который приходит со "
    "свежим взглядом, когда своё решение перестало быть видно. Позови "
    "его: /magistr"
)


def plugin_root():
    return PLUGIN_ROOT


def state_path():
    return Path(os.environ.get("JEDICODER_STATE_PATH") or st.STATE_PATH)


def load_state():
    return st.load(state_path())


def save_state(state, path=None):
    st.save(state, path or state_path())


@contextlib.contextmanager
def update_state(path=None):
    """Делегат state.update_state с резолвом пути из окружения хука."""
    with st.update_state(path or state_path()) as state:
        yield state


def add_dark_side(state, amount):
    """Прибавить к счёту Тёмной стороны и вернуть новое значение.

    XP не трогается никогда (§9.2): счётчик учит, а не штрафует.
    Мусор в поле (правка руками) считается нулём — падать тут нельзя.
    """
    try:
        current = int(state.get("dark_side", 0))
    except (TypeError, ValueError):
        current = 0
    current += int(amount)
    state["dark_side"] = current
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

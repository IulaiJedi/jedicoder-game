"""Общий модуль хуков: состояние, счётчик ТС, порог Магистра, катсцены."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))

import _shared  # noqa: E402

from jedicoder import state as st  # noqa: E402

CONTENT_ROOT = ROOT / "plugin"


def test_state_path_honours_env(monkeypatch, tmp_path):
    target = tmp_path / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(target))
    assert _shared.state_path() == target


def test_state_path_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("JEDICODER_STATE_PATH", raising=False)
    assert _shared.state_path() == Path(st.STATE_PATH)


def test_add_dark_side_accumulates():
    state = {"dark_side": 0}
    assert _shared.add_dark_side(state, 2, "env_staged") == 2
    assert _shared.add_dark_side(state, 1, "root_login") == 3
    assert state["dark_side"] == 3


def test_add_dark_side_never_touches_xp():
    state = {"dark_side": 0, "xp": 40}
    _shared.add_dark_side(state, 2, "env_staged")
    assert state["xp"] == 40, "ТС не отнимает XP (§9.2)"


def test_add_dark_side_survives_garbage_counter():
    state = {"dark_side": "три"}
    assert _shared.add_dark_side(state, 1, "vague_prompt") == 1


def test_add_dark_side_enqueues_event():
    state = st.default_state()
    _shared.add_dark_side(state, 2, "env_staged")
    (event,) = [e for e in state["pending_sync"] if e["type"] == "dark_side"]
    assert event["payload"] == {"amount": 2, "total": 2}


def test_magistr_invite_fires_once_at_threshold():
    state = {"dark_side": 4}
    assert _shared.magistr_invite(state) == ""
    state["dark_side"] = 5
    first = _shared.magistr_invite(state)
    assert "/magistr" in first
    assert state["magistr_called"] is True
    state["dark_side"] = 9
    assert _shared.magistr_invite(state) == "", "приглашение не повторяется"


def test_rule_text_returns_title_and_body():
    text = _shared.rule_text(CONTENT_ROOT, "one-task-one-chat")
    assert "Одна задача — один чат" in text
    assert "Что делать вместо" in text


def test_rule_text_on_unknown_rule_is_empty():
    assert _shared.rule_text(CONTENT_ROOT, "нет-такого-правила") == ""


def test_update_state_composes_two_sequential_updates(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
    with _shared.update_state() as state:
        _shared.add_dark_side(state, 1, "root_login")
    with _shared.update_state() as state:
        _shared.add_dark_side(state, 1, "vague_prompt")
    assert st.load(path)["dark_side"] == 2


def test_update_state_falls_back_when_locking_is_unavailable(
    tmp_path, monkeypatch
):
    # «Платформа без fcntl» симулирована прямо: работа обязана пройти
    # так же, только без взаимного исключения.
    path = tmp_path / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
    # Блокировка теперь берётся в state.py — гварда fcntl там, не в _shared.
    monkeypatch.setattr(st, "fcntl", None)
    with _shared.update_state() as state:
        _shared.add_dark_side(state, 3, "rm_outside_project")
    assert st.load(path)["dark_side"] == 3


def test_update_state_survives_concurrent_writers(tmp_path, monkeypatch):
    # Без блокировки это ровно тот баг из чарты state.py: последний
    # записавший побеждает молча, и часть инкрементов от других потоков
    # теряется. Настоящий, а не последовательный, race — параллельные
    # потоки на общем файле состояния. Журнал пишется тем же проходом,
    # поэтому теряться ему тоже нельзя.
    import threading

    path = tmp_path / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
    st.save(st.default_state("local-test"), path)

    writers, per_writer = 6, 15

    def bump():
        for _ in range(per_writer):
            with _shared.update_state() as state:
                _shared.add_dark_side(state, 1, st.DARK_VAGUE_PROMPT)

    threads = [threading.Thread(target=bump) for _ in range(writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    saved = st.load(path)
    assert saved["dark_side"] == writers * per_writer
    assert len(st.dark_side_entries(saved)) == writers * per_writer


def test_add_dark_side_records_the_kind_and_the_day():
    state = st.default_state()
    _shared.add_dark_side(state, 2, "env_staged")
    entries = st.dark_side_entries(state)
    assert [e["type"] for e in entries] == ["env_staged", "env_staged"]
    for entry in entries:
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", entry["date"]), entry


def test_counter_and_log_agree_after_every_kind():
    state = st.default_state()
    for amount, kind in ((2, "env_staged"), (1, "rm_outside_project"),
                         (1, "root_login"), (1, "vague_prompt")):
        _shared.add_dark_side(state, amount, kind)
    assert state["dark_side"] == 5
    assert len(st.dark_side_entries(state)) == 5


def test_two_points_in_one_day_are_two_entries():
    # Разбор считает записи, а не дни: два нарушения за сутки — две строки.
    state = st.default_state()
    _shared.add_dark_side(state, 1, "root_login")
    _shared.add_dark_side(state, 1, "vague_prompt")
    first, second = st.dark_side_entries(state)
    assert first["date"] == second["date"], "один день — одна дата"
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", first["date"])


def test_add_dark_side_never_stores_the_command():
    # ADR-0011: в записи только тип и дата, больше ничего.
    state = st.default_state()
    _shared.add_dark_side(state, 1, "rm_outside_project")
    (entry,) = state["dark_side_log"]
    assert sorted(entry) == ["date", "type"]


def test_hooks_take_their_kinds_from_the_single_list():
    """Имя типа приходит из state.DARK_SIDE_KINDS, а не литералом на месте.

    Второй перечень имён — ровно тот дефект, из-за которого Разбор молча
    посчитал бы не то. Разбираем исходники хуков синтаксически (ast, не
    грепом): перенос вызова на две строки не должен ронять этот тест не по
    той причине, ради которой он написан.
    """
    import ast

    used, literals = set(), []
    for path in sorted((ROOT / "plugin" / "hooks").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            if name != "add_dark_side" or len(node.args) < 3:
                continue
            kind = node.args[2]
            if isinstance(kind, ast.Attribute):
                used.add(getattr(st, kind.attr))
            else:
                literals.append("{}:{}".format(path.name, node.lineno))
    assert not literals, "имя типа задано мимо перечня: {}".format(literals)
    assert used == set(st.DARK_SIDE_KINDS), "перечень и хуки разошлись"


# --- Один файл на движок и хуки (долг №0) --------------------------------


def test_hooks_and_engine_resolve_the_same_path(monkeypatch, tmp_path):
    """Сторож против второй копии: у хуков она уже была и разъехалась.

    Сегодня равенство держится само собой — `_shared.state_path()`
    делегирует движку. Тест сторожит тот день, когда кто-нибудь вернёт
    хукам собственный разбор значения; настоящая же проверка «один файл на
    двоих» — сквозная, процессами, ниже.
    """
    values = [
        str(tmp_path / "state.json"),          # обычный абсолютный
        "~/.jedicoder-песочница/state.json",   # тильда без оболочки
        "относительный/state.json",            # относительно текущей папки
        "",                                    # пусто — как если бы не было
    ]
    for value in values:
        monkeypatch.setenv("JEDICODER_STATE_PATH", value)
        assert _shared.state_path() == st.state_path(), value


CLI_PY = ROOT / "plugin" / "lib" / "jedicoder" / "cli.py"
HOOK_PY = ROOT / "plugin" / "hooks" / "lexicon_loot.py"


def _sandbox_env(home, value=None):
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["CLAUDE_PLUGIN_ROOT"] = str(ROOT / "plugin")
    if value is None:
        env.pop("JEDICODER_STATE_PATH", None)
    else:
        env["JEDICODER_STATE_PATH"] = value
    return env


@pytest.mark.parametrize("form", ["абсолютный", "тильда"])
def test_engine_and_hook_write_the_same_file(tmp_path, form):
    """Сквозная проверка, ради которой всё затевалось.

    Движок и хук — разные процессы, и запускаются они из РАЗНЫХ текущих
    папок: движок из проекта падавана, хук из того места, откуда запущен
    Claude Code. Значение с тильдой проверяется отдельно именно поэтому:
    нераскрытая тильда — путь относительный, и два процесса разошлись бы
    по двум файлам, каждый со своим прогрессом.
    """
    home = tmp_path / "домашняя"
    home.mkdir()
    if form == "абсолютный":
        value = str(tmp_path / "общая" / "state.json")
        target = Path(value)
    else:
        value = "~/своё/state.json"
        target = home / "своё" / "state.json"
    env = _sandbox_env(home, value)
    откуда_движок = tmp_path / "папка-движка"
    откуда_хук = tmp_path / "папка-хука"
    откуда_движок.mkdir()
    откуда_хук.mkdir()

    engine = subprocess.run(
        [sys.executable, str(CLI_PY), "track", "craftsman"],
        capture_output=True, text=True, timeout=60, env=env,
        cwd=str(откуда_движок),
    )
    assert engine.returncode == 0, engine.stderr
    assert target.exists(), "движок не увидел JEDICODER_STATE_PATH"

    hook = subprocess.run(
        [sys.executable, str(HOOK_PY)],
        input=json.dumps(
            {"last_assistant_message": "Начнём с MVP: одна кнопка."}
        ),
        capture_output=True, text=True, timeout=60, env=env,
        cwd=str(откуда_хук),
    )
    assert hook.returncode == 0, hook.stderr

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["passport"]["track"] == "craftsman", "правка движка потерялась"
    assert data["lexicon_unlocked"], "правка хука ушла в другой файл"
    assert not (home / ".jedicoder" / "state.json").exists(), (
        "кто-то из двоих всё-таки сходил в ~/.jedicoder"
    )
    осталось = sorted(
        p.name for p in list(откуда_движок.iterdir()) + list(откуда_хук.iterdir())
    )
    assert осталось == [], "путь посчитан от текущей папки: {}".format(осталось)


def test_without_the_variable_both_write_to_the_home_folder(tmp_path):
    """Переменной нет — поведение прежнее, до байта: ~/.jedicoder.

    Проверяется той же дверью, что и остальное: настоящими процессами, а
    не чтением константы.
    """
    home = tmp_path / "домашняя"
    home.mkdir()
    env = _sandbox_env(home)
    прежний = home / ".jedicoder" / "state.json"

    engine = subprocess.run(
        [sys.executable, str(CLI_PY), "track", "craftsman"],
        capture_output=True, text=True, timeout=60, env=env, cwd=str(tmp_path),
    )
    assert engine.returncode == 0, engine.stderr
    assert прежний.exists(), "без переменной путь обязан остаться прежним"

    hook = subprocess.run(
        [sys.executable, str(HOOK_PY)],
        input=json.dumps(
            {"last_assistant_message": "Начнём с MVP: одна кнопка."}
        ),
        capture_output=True, text=True, timeout=60, env=env, cwd=str(tmp_path),
    )
    assert hook.returncode == 0, hook.stderr

    data = json.loads(прежний.read_text(encoding="utf-8"))
    assert data["passport"]["track"] == "craftsman"
    assert data["lexicon_unlocked"], "хук ушёл не в тот же файл"

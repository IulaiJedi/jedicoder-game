"""Общий модуль хуков: состояние, счётчик ТС, порог Магистра, катсцены."""
import sys
from pathlib import Path

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
    assert _shared.add_dark_side(state, 2) == 2
    assert _shared.add_dark_side(state, 1) == 3
    assert state["dark_side"] == 3


def test_add_dark_side_never_touches_xp():
    state = {"dark_side": 0, "xp": 40}
    _shared.add_dark_side(state, 2)
    assert state["xp"] == 40, "ТС не отнимает XP (§9.2)"


def test_add_dark_side_survives_garbage_counter():
    state = {"dark_side": "три"}
    assert _shared.add_dark_side(state, 1) == 1


def test_add_dark_side_enqueues_event():
    state = st.default_state()
    _shared.add_dark_side(state, 2)
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
        _shared.add_dark_side(state, 1)
    with _shared.update_state() as state:
        _shared.add_dark_side(state, 1)
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
        _shared.add_dark_side(state, 3)
    assert st.load(path)["dark_side"] == 3


def test_update_state_survives_concurrent_writers(tmp_path, monkeypatch):
    # Без блокировки это ровно тот баг из чарты state.py: последний
    # записавший побеждает молча, и часть инкрементов от других потоков
    # теряется. Настоящий, а не последовательный, race — параллельные
    # потоки на общем файле состояния.
    import threading

    path = tmp_path / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
    st.save(st.default_state("local-test"), path)

    writers, per_writer = 6, 15

    def bump():
        for _ in range(per_writer):
            with _shared.update_state() as state:
                state["dark_side"] = int(state.get("dark_side", 0) or 0) + 1

    threads = [threading.Thread(target=bump) for _ in range(writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert st.load(path)["dark_side"] == writers * per_writer

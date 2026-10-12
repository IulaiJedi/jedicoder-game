"""Игровая сессия — одно правило на Лицо и на хуки (#97).

Плагин стоит на всей машине, и его хуки зовутся в любой сессии Claude Code.
Игровой сессию делает один из трёх признаков: её запустил Голокрон, она
открыта в папке проекта или в ней позвана команда игры. Считает их одна
функция — `game_session.is_game`; здесь её случаи и то, что `face` и хуки
на одних входах отвечают одинаково.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))

import _shared  # noqa: E402

from jedicoder import cli, game_session  # noqa: E402
from jedicoder import state as st  # noqa: E402


def save_with(project=None, sessions=None):
    data = st.default_state("local-test")
    if project is not None:
        data["project"]["path"] = str(project)
    if sessions is not None:
        data[game_session.SESSIONS_KEY] = sessions
    return data


# --- три признака -----------------------------------------------------------

def test_a_session_with_no_sign_is_not_a_game(tmp_path):
    project, other = tmp_path / "proj", tmp_path / "other"
    project.mkdir(), other.mkdir()
    data = save_with(project=project, sessions=["S1"])
    assert game_session.is_game(data, cwd=str(other), session_id="S2") is False


def test_golokron_makes_the_session_a_game_even_without_a_save():
    assert game_session.is_game(None, golokron=True) is True


def test_the_project_folder_and_folders_inside_it_are_a_game(tmp_path):
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    data = save_with(project=project)
    assert game_session.is_game(data, cwd=str(project)) is True
    assert game_session.is_game(data, cwd=str(project / "src")) is True
    assert game_session.is_game(data, cwd=str(tmp_path)) is False


def test_without_a_session_folder_the_second_sign_is_silent(tmp_path):
    data = save_with(project=tmp_path)
    assert game_session.is_game(data, cwd=None) is False
    assert game_session.is_game(data, cwd="") is False


def test_home_as_the_project_does_not_make_every_folder_a_game(
        tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "work").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    data = save_with(project=home)
    assert game_session.is_game(data, cwd=str(home)) is True
    assert game_session.is_game(data, cwd=str(home / "work")) is False


def test_a_relative_project_path_matches_no_session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = save_with(project=".")
    assert game_session.is_game(data, cwd=str(tmp_path)) is False


def test_a_recorded_session_is_a_game_anywhere(tmp_path):
    data = save_with(sessions=["S1", "S2"])
    assert game_session.is_game(data, cwd=str(tmp_path), session_id="S1") is True
    assert game_session.is_game(data, cwd=str(tmp_path), session_id="S3") is False


def test_without_a_session_id_the_third_sign_is_silent():
    data = save_with(sessions=["S1"])
    assert game_session.is_game(data, session_id=None) is False
    assert game_session.is_game(data, session_id="") is False


def test_called_is_the_third_sign_for_the_one_who_has_no_session_id():
    assert game_session.is_game(None, called=True) is True


# --- список игровых сессий ----------------------------------------------------

@pytest.mark.parametrize("garbage", [
    None, "S1", 7, {"S1": True}, [["S1"]], [None, 5, ""],
])
def test_garbage_in_the_key_reads_as_an_empty_list(garbage):
    data = save_with(sessions=garbage)
    assert game_session.sessions(data) == []
    assert game_session.is_game(data, session_id="S1") is False


def test_a_missing_key_reads_as_an_empty_list():
    data = st.default_state("local-test")
    data.pop(game_session.SESSIONS_KEY, None)
    assert game_session.sessions(data) == []
    assert game_session.sessions(None) == []


def test_note_adds_the_session_once():
    data = save_with()
    assert game_session.note(data, "S1") is True
    assert game_session.note(data, "S1") is False
    assert game_session.sessions(data) == ["S1"]


def test_note_over_garbage_starts_a_clean_list():
    data = save_with(sessions="мусор")
    assert game_session.note(data, "S1") is True
    assert data[game_session.SESSIONS_KEY] == ["S1"]


@pytest.mark.parametrize("bad", [None, "", 5, ["S"], "x" * 500])
def test_note_refuses_what_is_not_a_session_id(bad):
    data = save_with(sessions=["S1"])
    assert game_session.note(data, bad) is False
    assert game_session.sessions(data) == ["S1"]


def test_the_list_never_grows_past_the_cap_and_drops_the_oldest():
    data = save_with()
    total = game_session.SESSIONS_CAP + 5
    for number in range(total):
        game_session.note(data, "S{}".format(number))
    kept = game_session.sessions(data)
    assert len(kept) == game_session.SESSIONS_CAP == 20
    assert kept[0] == "S5" and kept[-1] == "S{}".format(total - 1)
    assert game_session.is_game(data, session_id="S0") is False


def test_a_session_called_again_moves_to_the_fresh_end():
    data = save_with(sessions=["S1", "S2"])
    assert game_session.note(data, "S1") is True
    assert game_session.sessions(data) == ["S2", "S1"]


def test_the_new_key_does_not_raise_the_schema_version():
    assert st.SCHEMA_VERSION == 4
    assert game_session.SESSIONS_KEY not in st.default_state("local-test")


# --- команда игры -------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "/jedicoder:start", "  /jedicoder:start", "/jedicoder:magistr помоги",
])
def test_a_request_starting_with_the_game_prefix_is_a_game_command(text):
    assert game_session.is_game_command(text) is True


@pytest.mark.parametrize("text", [
    "", None, 5, "сделай мне сайт", "набери /jedicoder:start", "/jedicoder",
    "/other:start",
])
def test_anything_else_is_not_a_game_command(text):
    assert game_session.is_game_command(text) is False


# --- Лицо и хуки не расходятся --------------------------------------------------

def face(save, cwd, capsys, called=False):
    args = ["face", "--cwd", str(cwd)] + (["--called"] if called else [])
    assert cli.main(args, state_path=save) == 0
    return json.loads(capsys.readouterr().out)["is_game"]


@pytest.mark.parametrize("golokron", [False, True])
@pytest.mark.parametrize("where", ["proj", "proj/src", "other"])
@pytest.mark.parametrize("has_save", [False, True])
def test_face_and_hooks_agree_on_the_same_inputs(
        tmp_path, monkeypatch, capsys, golokron, where, has_save):
    (tmp_path / "proj" / "src").mkdir(parents=True)
    (tmp_path / "other").mkdir()
    save = tmp_path / "state.json"
    if has_save:
        st.save(save_with(project=tmp_path / "proj"), save)
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(save))
    if golokron:
        monkeypatch.setenv(game_session.GOLOKRON_MARK, "1")
    cwd = tmp_path / where

    hook = _shared.is_game_session({"cwd": str(cwd), "session_id": "S9"})

    assert hook == face(save, cwd, capsys)
    assert hook == (golokron or (has_save and where != "other"))


def test_a_called_game_is_a_game_for_face_and_for_hooks(
        tmp_path, monkeypatch, capsys):
    """Третий признак у каждого свой носитель: у модуля — флаг, у хука —
    записанный идентификатор. Исход один."""
    save = tmp_path / "state.json"
    st.save(save_with(sessions=["S9"]), save)
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(save))

    assert face(save, tmp_path, capsys, called=True) is True
    assert _shared.is_game_session(
        {"cwd": str(tmp_path), "session_id": "S9"}
    ) is True
    assert face(save, tmp_path, capsys) is False
    assert _shared.is_game_session(
        {"cwd": str(tmp_path), "session_id": "S8"}
    ) is False


def test_asking_whether_the_session_is_a_game_never_touches_the_disk(
        tmp_path, monkeypatch):
    save = tmp_path / "jc" / "state.json"
    save.parent.mkdir()
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(save))
    assert _shared.is_game_session({"cwd": str(tmp_path)}) is False
    assert list(save.parent.iterdir()) == [], "ни сохранения, ни замка"


def test_a_broken_answer_reads_as_not_a_game(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("сломано")

    monkeypatch.setattr(game_session, "is_game", boom)
    assert _shared.is_game_session({"cwd": "/x", "session_id": "S"}) is False

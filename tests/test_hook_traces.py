"""След квеста «Хук»: слово «чистка» при записанном хуке (#110).

Швы те же, что у `tests/test_traces.py`: хук игры — процессом, на данных формы
из живого замера (`docs/research/2026-10-13-act3-skills-hooks-mods.md`, «Замеры
#110», Claude Code 2.1.296). Настройки с хуком кладутся так, как их пишет
Claude: `hooks.UserPromptSubmit` в `.claude/settings.json` папки проекта.

Сквозной проход квеста — в `tests/test_act3_walkthrough.py`; здесь — что
считается словом, что считается записанным хуком и чего хук игры не делает.
"""
import json
import os
import time
from pathlib import Path

import pytest

from jedicoder import acts, game_session, ranks
from jedicoder import state as st
from test_act3_checks import hook_settings
from test_show_traces import asked
from test_traces import GAME, clear_end, fire, untouched

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "plugin" / "hooks"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: хук читает настройки пользователя из `HOME`."""
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def played(tmp_path, project):
    """Сохранение играющего: папка проекта названа, сессия GAME — игровая.

    Акт 3 не начат: пометку акта след получает только в тестах, которые в
    него входят (`in_act3`).
    """
    proj = project()
    path = tmp_path / "state.json"
    data = st.default_state("local-test")
    data[game_session.SESSIONS_KEY] = [GAME]
    data["project"]["path"] = str(proj)
    st.save(data, path)
    return path, proj


def in_act3(save):
    """Человек вошёл в Акт 3 — той же функцией, что команда игры."""
    data = st.load(save)
    for act in (1, 2):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    ranks.enter_act(data, 3)
    st.save(data, save)


def word_trace(save):
    return st.trace(st.load(save), st.TRACE_HOOK_WORD)


# --- что считается словом -----------------------------------------------------

@pytest.mark.parametrize("prompt", [
    "чистка", "Чистка", "ЧИСТКА", "Всё, чистка!", "«чистка»",
    "давай: чистка.", "чистка\n", "ну что, Чистка?",
])
def test_the_word_with_a_recorded_hook_leaves_the_trace(played, prompt):
    save, proj = played
    hook_settings(proj)
    fire(save, asked(prompt, proj))
    entry = word_trace(save)
    assert entry is not None and entry["date"] == st.today_utc()
    assert abs(entry[st.TRACE_AT] - time.time()) < 60


@pytest.mark.parametrize("prompt", [
    "очистка", "чистками займёмся потом", "чистку сделай", "зачистка",
    "чистка_данных", "почисти код", "", "clear",
])
def test_other_words_leave_no_trace(played, prompt):
    save, proj = played
    hook_settings(proj)
    before = untouched(save)
    fire(save, asked(prompt, proj))
    assert untouched(save) == before


# --- что считается записанным хуком -------------------------------------------

def test_without_a_recorded_hook_the_word_is_just_a_word(played):
    save, proj = played
    before = untouched(save)
    fire(save, asked("чистка", proj))
    assert untouched(save) == before


def test_a_hook_in_the_user_settings_counts(played, home):
    save, proj = played
    hook_settings(home)
    fire(save, asked("чистка", proj))
    assert word_trace(save) is not None


@pytest.mark.parametrize("event", ["Stop", "PreToolUse", "PreCompact"])
def test_hooks_on_other_events_do_not_make_the_word_count(played, home, event):
    save, proj = played
    hook_settings(home, event=event)
    hook_settings(proj, event=event)
    before = untouched(save)
    fire(save, asked("чистка", proj))
    assert untouched(save) == before


@pytest.mark.parametrize("raw", ["{ не json", "[]", ""])
def test_unreadable_settings_leave_no_trace_and_no_noise(played, raw):
    """Не уверен, что опознал, — следа нет. Хук при этом молчит."""
    save, proj = played
    hook_settings(proj, raw=raw)
    before = untouched(save)
    fire(save, asked("чистка", proj))
    assert untouched(save) == before


def test_the_folder_of_the_session_is_not_the_project_folder(played, tmp_path):
    """Настройки читаются из названной папки проекта, а не из папки сессии."""
    save, proj = played
    elsewhere = tmp_path / "чужая"
    elsewhere.mkdir()
    hook_settings(elsewhere)
    before = untouched(save)
    fire(save, asked("чистка", elsewhere))
    assert untouched(save) == before
    hook_settings(proj)
    fire(save, asked("чистка", elsewhere))
    assert word_trace(save) is not None


def test_without_a_named_project_folder_there_is_no_trace(played, home):
    save, proj = played
    hook_settings(home)
    data = st.load(save)
    data["project"]["path"] = None
    st.save(data, save)
    before = untouched(save)
    fire(save, asked("чистка", proj))
    assert untouched(save) == before


# --- только в игровой сессии ---------------------------------------------------

def test_outside_a_game_session_the_word_is_not_seen(played, tmp_path):
    save, proj = played
    hook_settings(proj)
    before = untouched(save)
    fire(save, asked("чистка", tmp_path, session_id="chuzhaya-sessiya"))
    assert untouched(save) == before


def test_the_hook_does_not_start_a_game_by_the_word(tmp_path, project):
    save = tmp_path / "нет" / "state.json"
    proj = project()
    hook_settings(proj)
    fire(save, asked("чистка", proj), JEDICODER_GOLOKRON="1")
    assert not save.exists() and not save.parent.exists()


def test_the_words_of_the_request_never_reach_the_save(played):
    save, proj = played
    hook_settings(proj)
    fire(save, asked("чистка и ещё тайна-человека", proj))
    raw = save.read_text(encoding="utf-8")
    assert "тайна-человека" not in raw
    assert sorted(word_trace(save)) == ["at", "date"]


# --- пометка акта и момент -----------------------------------------------------

def test_the_trace_belongs_to_act3_and_the_others_to_act2():
    assert acts.TRACE_ACTS == {
        st.TRACE_PLAN_APPROVED: 2, st.TRACE_FILE_SHOWN: 2,
        st.TRACE_IMAGE_SHOWN: 2, st.TRACE_HOOK_WORD: 3,
    }
    assert st.TRACE_MARK[st.TRACE_HOOK_WORD] == st.TRACE_IN_ACT
    # У каждого следа с пометкой акта назван акт — и наоборот.
    marked = {k for k, mark in st.TRACE_MARK.items() if mark == st.TRACE_IN_ACT}
    assert marked == set(acts.TRACE_ACTS)


def test_the_word_said_before_act3_is_not_marked_and_is_marked_when_repeated(played):
    save, proj = played
    hook_settings(proj)
    fire(save, asked("чистка", proj))
    assert st.TRACE_IN_ACT not in word_trace(save)
    in_act3(save)
    fire(save, asked("чистка", proj))
    assert word_trace(save)[st.TRACE_IN_ACT] is True


def test_a_file_shown_in_act3_is_not_marked_for_act2(played):
    """Пометка акта — по своему акту у каждого следа."""
    save, proj = played
    (proj / "notes.txt").write_text("молоко\n", encoding="utf-8")
    in_act3(save)
    fire(save, asked("что в @notes.txt?", proj))
    entry = st.trace(st.load(save), st.TRACE_FILE_SHOWN)
    assert entry is not None and st.TRACE_IN_ACT not in entry


def _age_the_word(save, seconds):
    """Отодвинуть момент следа в прошлое: в тесте всё происходит в ту же
    секунду, у человека между словом и следующим словом проходят минуты."""
    data = st.load(save)
    moment = st.trace_moment(data, st.TRACE_HOOK_WORD) - seconds
    st.record_trace(data, st.TRACE_HOOK_WORD, at=moment)
    st.save(data, save)
    return moment


def test_the_moment_moves_while_no_handoff_answers_the_word(played):
    save, proj = played
    hook_settings(proj)
    in_act3(save)
    fire(save, asked("чистка", proj))
    old = _age_the_word(save, 600)
    fire(save, asked("чистка", proj))
    assert word_trace(save)[st.TRACE_AT] > old


def test_the_moment_stays_once_a_handoff_is_written_after_the_word(played):
    save, proj = played
    hook_settings(proj)
    in_act3(save)
    fire(save, asked("чистка", proj))
    old = _age_the_word(save, 600)
    (proj / "HANDOFF.md").write_text("# Передача\n", encoding="utf-8")
    before = untouched(save)
    fire(save, asked("я сказал: чистка", proj))
    assert untouched(save) == before
    assert word_trace(save)[st.TRACE_AT] == old


def test_a_handoff_older_than_the_word_does_not_hold_the_moment(played):
    save, proj = played
    hook_settings(proj)
    in_act3(save)
    path = proj / "HANDOFF.md"
    path.write_text("# Передача\n", encoding="utf-8")
    long_ago = time.time() - 7200
    os.utime(str(path), (long_ago, long_ago))
    fire(save, asked("чистка", proj))
    old = _age_the_word(save, 600)
    fire(save, asked("чистка", proj))
    assert word_trace(save)[st.TRACE_AT] > old


def test_a_moment_edited_by_hand_reads_as_no_moment():
    for junk in ("вчера", -1, 1.5, True, None, [1]):
        state = {st.TRACES_KEY: {st.TRACE_HOOK_WORD: {"date": "2026-10-13", "at": junk}}}
        assert st.trace_moment(state, st.TRACE_HOOK_WORD) is None
    with pytest.raises(ValueError):
        st.record_trace(st.default_state(), st.TRACE_HOOK_WORD, at="сейчас")


# --- чужие концы сессии ---------------------------------------------------------

def test_plugin_commands_from_a_session_leave_no_trace(played):
    """`claude plugin …`, запущенные Claude из сессии, шлют хукам `SessionEnd`
    с причиной `other` (замер #109). Это не `/clear`: хук следов не зовётся
    вовсе, а позванный — ничего не пишет."""
    save, proj = played
    before = untouched(save)
    fire(save, dict(clear_end(cwd=proj), reason="other"))
    assert untouched(save) == before
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    for entry in config["hooks"]["SessionEnd"]:
        if any("traces.py" in item["command"] for item in entry["hooks"]):
            assert entry["matcher"] == "clear"


def test_a_bad_moment_leaves_the_trace_untouched():
    """Ошибка вызывающего не оставляет след записанным наполовину."""
    state = st.default_state()
    with pytest.raises(ValueError):
        st.record_trace(state, st.TRACE_HOOK_WORD, {st.TRACE_IN_ACT: True}, at=1.5)
    assert st.trace(state, st.TRACE_HOOK_WORD) is None

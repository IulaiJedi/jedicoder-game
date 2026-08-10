"""PostToolUse-хук: серия коммитов и напоминание сохраниться.

Даты подставляются параметром, а не мокаются часы: логика серии — чистая
функция, и проверять её надо на границах суток, а не на «сегодня».
"""
import sys
from pathlib import Path

import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))

import commit_pulse  # noqa: E402

from jedicoder import state as st  # noqa: E402
from conftest import _git  # noqa: E402


def test_commit_detected_in_various_forms():
    assert commit_pulse.is_commit(["git", "commit", "-m", "фикс"]) is True
    assert commit_pulse.is_commit(["git", "commit", "--amend"]) is True
    assert commit_pulse.is_commit(["git", "status"]) is False
    assert commit_pulse.is_commit(["echo", "git", "commit"]) is False


def test_dry_run_and_help_are_not_commits():
    # Ничего не сохранено — значит ни серии, ни снятого напоминания.
    assert commit_pulse.is_commit(["git", "commit", "--dry-run"]) is False
    assert commit_pulse.is_commit(["git", "commit", "--help"]) is False
    assert commit_pulse.is_commit(["git", "commit", "-h"]) is False
    assert commit_pulse.is_commit(
        ["git", "commit", "-m", "фикс", "--dry-run"]
    ) is False


def test_global_options_do_not_hide_commit():
    assert commit_pulse.is_commit(
        ["git", "-C", "/путь", "commit", "-m", "шаг"]
    ) is True
    assert commit_pulse.is_commit(
        ["git", "--git-dir", "/путь/.git", "commit"]
    ) is True


def fresh():
    return {"current": 0, "best": 0, "last_commit_date": None}


def test_first_commit_starts_streak():
    streak = commit_pulse.bump_streak(fresh(), "2026-07-27")
    assert streak["current"] == 1
    assert streak["best"] == 1
    assert streak["last_commit_date"] == "2026-07-27"


def test_same_day_does_not_grow_streak():
    streak = {"current": 3, "best": 5, "last_commit_date": "2026-07-27"}
    after = commit_pulse.bump_streak(streak, "2026-07-27")
    assert after["current"] == 3
    assert after["best"] == 5


def test_next_day_grows_streak_and_best():
    streak = {"current": 5, "best": 5, "last_commit_date": "2026-07-27"}
    after = commit_pulse.bump_streak(streak, "2026-07-28")
    assert after["current"] == 6
    assert after["best"] == 6


def test_gap_resets_streak_but_keeps_best():
    streak = {"current": 9, "best": 9, "last_commit_date": "2026-07-20"}
    after = commit_pulse.bump_streak(streak, "2026-07-27")
    assert after["current"] == 1
    assert after["best"] == 9, "рекорд не отбирают за перерыв"


def test_month_boundary_is_a_next_day():
    streak = {"current": 2, "best": 2, "last_commit_date": "2026-07-31"}
    after = commit_pulse.bump_streak(streak, "2026-08-01")
    assert after["current"] == 3


def test_garbage_date_starts_over():
    streak = {"current": 4, "best": 4, "last_commit_date": "вчера"}
    after = commit_pulse.bump_streak(streak, "2026-07-27")
    assert after["current"] == 1
    assert after["best"] == 4


@pytest.fixture
def hook_state(tmp_path, monkeypatch):
    path = tmp_path / "state.json"

    def seed(**fields):
        data = st.default_state("local-test")
        data.update(fields)
        st.save(data, path)
        monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
        return path

    return seed


def payload(command, cwd):
    return {
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }


def test_dirty_count_counts_working_tree(project):
    proj = project(git=True, commits=1)
    assert commit_pulse.dirty_count(proj) == 0
    for i in range(3):
        (proj / "f{}.txt".format(i)).write_text("x", encoding="utf-8")
    assert commit_pulse.dirty_count(proj) == 3


def test_dirty_count_outside_repo_is_zero(tmp_path):
    assert commit_pulse.dirty_count(tmp_path) == 0


def test_commit_updates_streak_in_state(project, hook_state):
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    out = commit_pulse.react(payload("git commit -m 'шаг'", proj))
    assert out is not None
    assert "Серия" in out["systemMessage"]
    streak = st.load(path)["streak"]
    assert streak["current"] == 1
    assert streak["best"] == 1
    state = st.load(path)
    events = [e for e in state["pending_sync"] if e["type"] == "streak_updated"]
    assert events and events[-1]["payload"] == {
        "current": state["streak"]["current"], "best": state["streak"]["best"],
    }


def test_second_commit_same_day_does_not_repeat_streak_event(project, hook_state):
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    first = commit_pulse.react(payload("git commit -m 'первый'", proj))
    assert first is not None
    # Второй настоящий коммит в тот же UTC-день: серия не растёт (bump_streak
    # — no-op на same-day), поэтому очередь не должна получить второе событие
    # без новой информации для бота.
    _git(proj, "commit", "--allow-empty", "-q", "-m", "второй")
    second = commit_pulse.react(payload("git commit -m 'второй'", proj))
    assert second is not None
    events = [
        e for e in st.load(path)["pending_sync"] if e["type"] == "streak_updated"
    ]
    assert len(events) == 1, "второй коммит того же дня не дублирует событие"


def test_reminder_fires_over_threshold(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    for i in range(commit_pulse.DIRTY_THRESHOLD):
        (proj / "f{}.txt".format(i)).write_text("x", encoding="utf-8")
    out = commit_pulse.react(payload("ls", proj))
    assert out is not None
    assert "коммит" in out["systemMessage"].lower()


def test_reminder_silent_under_threshold(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    for i in range(commit_pulse.DIRTY_THRESHOLD - 1):
        (proj / "f{}.txt".format(i)).write_text("x", encoding="utf-8")
    assert commit_pulse.react(payload("ls", proj)) is None


def test_reminder_does_not_nag(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    for i in range(commit_pulse.DIRTY_THRESHOLD):
        (proj / "f{}.txt".format(i)).write_text("x", encoding="utf-8")
    assert commit_pulse.react(payload("ls", proj)) is not None
    assert commit_pulse.react(payload("ls", proj)) is None, "второй раз молчим"


def test_commit_resets_nag_window(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    for i in range(commit_pulse.DIRTY_THRESHOLD):
        (proj / "f{}.txt".format(i)).write_text("x", encoding="utf-8")
    commit_pulse.react(payload("ls", proj))
    # Коммит должен произойти по-настоящему: react() теперь проверяет
    # исход по git, а не верит одному тексту команды (иначе не отличить
    # от провалившегося commit — ровно то, что чинит 2b).
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "сохранился")
    commit_pulse.react(payload("git commit -m 'сохранился'", proj))
    # Новые несохранённые файлы после коммита: дереву, только что
    # очищенному настоящим коммитом, иначе не о чем напоминать.
    for i in range(commit_pulse.DIRTY_THRESHOLD):
        (proj / "g{}.txt".format(i)).write_text("y", encoding="utf-8")
    assert commit_pulse.react(payload("ls", proj)) is not None, \
        "после коммита напоминание снова доступно"


def test_dry_run_does_not_reset_the_nag_window(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    for i in range(commit_pulse.DIRTY_THRESHOLD):
        (proj / "f{}.txt".format(i)).write_text("x", encoding="utf-8")
    assert commit_pulse.react(payload("ls", proj)) is not None
    commit_pulse.react(payload("git commit --dry-run", proj))
    assert commit_pulse.react(payload("ls", proj)) is None, \
        "холостой прогон не снимает окно молчания"


def test_without_project_path_stays_silent(tmp_path, hook_state):
    hook_state()
    assert commit_pulse.react(payload("ls", tmp_path)) is None


def test_chained_add_and_commit_counts(project, hook_state):
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    (proj / "new.txt").write_text("x", encoding="utf-8")
    out = commit_pulse.react(payload("git add -A && git commit -m 'шаг'", proj))
    assert out is None, "сам хук ничего не коммитит — коммита ещё не было"
    # а теперь коммит действительно сделан
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "шаг")
    out = commit_pulse.react(payload("git add -A && git commit -m 'шаг'", proj))
    assert out is not None
    assert st.load(path)["streak"]["current"] == 1


def test_failed_commit_does_not_count(project, hook_state):
    # Коммита не было (git его отверг) — серия не растёт.
    proj = project(git=True, commits=0)
    path = hook_state(project={"path": str(proj)})
    assert commit_pulse.react(payload("git commit -m 'пусто'", proj)) is None
    assert st.load(path)["streak"]["current"] == 0

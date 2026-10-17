"""PostToolUse-хук: серия коммитов и напоминание сохраниться.

Даты подставляются параметром, а не мокаются часы: логика серии — чистая
функция, и проверять её надо на границах суток, а не на «сегодня».
"""
import sys
from datetime import datetime, timedelta
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
    # Число не выросло — строки нет (#122); коммит при этом увиден.
    assert second is None
    assert st.load(path)["commit_head"]["sha"] == commit_pulse.head_sha(proj)
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
    assert "сохранить сделанное" in out["systemMessage"]


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


# --- Долг №6: коммит опознаётся по сдвигу HEAD, а не по чистоте дерева -----


def test_partial_commit_grows_the_streak(project, hook_state):
    # Обычный день: один файл готов и сохранён, второй ещё правится.
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    assert commit_pulse.react(payload("ls", proj)) is None
    (proj / "done.txt").write_text("готово", encoding="utf-8")
    (proj / "draft.txt").write_text("в работе", encoding="utf-8")
    _git(proj, "add", "done.txt")
    _git(proj, "commit", "-q", "-m", "готовая часть")
    out = commit_pulse.react(
        payload("git add done.txt && git commit -m 'готовая часть'", proj)
    )
    assert out is not None and "Серия" in out["systemMessage"]
    assert st.load(path)["streak"]["current"] == 1
    assert commit_pulse.dirty_count(proj) == 1, "черновик остался несохранённым"


def test_first_ever_commit_counts_with_work_left_over(project, hook_state):
    # Первый коммит новичка: папка только что стала репозиторием, один
    # файл сохранён, второй нет. «Было» здесь — «коммитов ещё нет».
    proj = project(git=True, commits=0)
    path = hook_state(project={"path": str(proj)})
    assert commit_pulse.react(payload("ls", proj)) is None
    (proj / "done.txt").write_text("готово", encoding="utf-8")
    (proj / "draft.txt").write_text("в работе", encoding="utf-8")
    _git(proj, "add", "done.txt")
    _git(proj, "commit", "-q", "-m", "первый")
    out = commit_pulse.react(payload("git commit -m 'первый'", proj))
    assert out is not None
    assert st.load(path)["streak"]["current"] == 1


def test_first_commit_counts_when_the_repo_is_born_in_the_same_command(
        tmp_path, hook_state):
    proj = tmp_path / "newborn"
    proj.mkdir()
    path = hook_state(project={"path": str(proj)})
    assert commit_pulse.react(payload("ls", proj)) is None
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "padawan@example.test")
    _git(proj, "config", "user.name", "Padawan")
    (proj / "a.txt").write_text("x", encoding="utf-8")
    (proj / "b.txt").write_text("y", encoding="utf-8")
    _git(proj, "add", "a.txt")
    _git(proj, "commit", "-q", "-m", "первый")
    out = commit_pulse.react(payload(
        "git init && git add a.txt && git commit -m 'первый'", proj
    ))
    assert out is not None
    assert st.load(path)["streak"]["current"] == 1


def test_commit_that_changed_nothing_does_not_count(project, hook_state):
    # «nothing to commit» на чистом дереве с сегодняшним HEAD: прежняя
    # проверка (дерево чистое, дата сегодняшняя) засчитывала и это.
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    commit_pulse.react(payload("ls", proj))
    assert commit_pulse.react(payload("git commit -m 'пусто'", proj)) is None
    assert st.load(path)["streak"]["current"] == 0


def test_rejected_commit_on_a_dirty_tree_does_not_count(project, hook_state):
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    commit_pulse.react(payload("ls", proj))
    (proj / "draft.txt").write_text("в работе", encoding="utf-8")
    assert commit_pulse.react(payload("git commit -m 'мимо'", proj)) is None
    assert st.load(path)["streak"]["current"] == 0


def _quiet_window(path, left):
    data = st.load(path)
    data["commit_nag_left"] = left
    st.save(data, path)


def test_every_real_commit_is_seen_one_after_another(project, hook_state):
    """Увиденный коммит закрывает окно молчания напоминания — по этому
    признаку и видно, что хук его засчитал: строка серии звучит только
    на первом за день (#122)."""
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    commit_pulse.react(payload("ls", proj))
    for number, name in enumerate(("a.txt", "b.txt")):
        (proj / name).write_text("x", encoding="utf-8")
        _git(proj, "add", name)
        _git(proj, "commit", "-q", "-m", name)
        _quiet_window(path, 5)
        out = commit_pulse.react(payload("git commit -m x", proj))
        assert (out is not None) is (number == 0), name
        assert "commit_nag_left" not in st.load(path), name
        # Тот же текст команды без нового коммита — уже не коммит.
        _quiet_window(path, 5)
        assert commit_pulse.react(payload("git commit -m x", proj)) is None
        assert st.load(path)["commit_nag_left"] == 5, name


def test_streak_line_sounds_only_when_the_number_grew(project, hook_state):
    """Первое сохранение дня после вчерашнего — строка с новым числом."""
    proj = project(git=True, commits=1)
    today = datetime.strptime(commit_pulse.today_utc(), "%Y-%m-%d")
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    path = hook_state(project={"path": str(proj)}, streak={
        "current": 3, "best": 3, "last_commit_date": yesterday,
    })
    commit_pulse.react(payload("ls", proj))
    (proj / "a.txt").write_text("x", encoding="utf-8")
    _git(proj, "add", "a.txt")
    _git(proj, "commit", "-q", "-m", "шаг")
    out = commit_pulse.react(payload("git commit -m 'шаг'", proj))
    assert out == {"systemMessage": st.streak_line(4, 4) + "."}
    assert st.load(path)["streak"]["current"] == 4


def test_streak_started_over_after_a_break_is_silent(project, hook_state):
    """Перерыв: серия начата заново, число стало меньше — игра молчит, а не
    упрекает. Серия при этом записана честно."""
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)}, streak={
        "current": 4, "best": 4, "last_commit_date": "2000-01-01",
    })
    commit_pulse.react(payload("ls", proj))
    (proj / "a.txt").write_text("x", encoding="utf-8")
    _git(proj, "add", "a.txt")
    _git(proj, "commit", "-q", "-m", "шаг")
    assert commit_pulse.react(payload("git commit -m 'шаг'", proj)) is None
    streak = st.load(path)["streak"]
    assert (streak["current"], streak["best"]) == (1, 4)
    assert "commit_nag_left" not in st.load(path)


@pytest.mark.parametrize("before, after, expected", [
    ({}, {"current": 1}, True),
    ({"current": 1}, {"current": 1}, False),
    ({"current": 4}, {"current": 1}, False),
    ({"current": "мусор"}, {"current": 2}, True),
    (None, {"current": 1}, True),
])
def test_grew_compares_only_the_number(before, after, expected):
    assert commit_pulse.grew(before, after) is expected


def test_commit_in_another_repo_does_not_count(project, hook_state):
    proj = project(git=True, commits=1)
    other = project(git=True, commits=0)
    path = hook_state(project={"path": str(proj)})
    commit_pulse.react(payload("ls", proj))
    (other / "a.txt").write_text("x", encoding="utf-8")
    _git(other, "add", "a.txt")
    _git(other, "commit", "-q", "-m", "чужой")
    out = commit_pulse.react(
        payload("git -C {} commit -m 'чужой'".format(other), proj)
    )
    assert out is None
    assert st.load(path)["streak"]["current"] == 0


def test_head_of_another_project_is_not_a_starting_point(project, hook_state):
    # Падаван сменил папку проекта: HEAD прежней — не «было» для новой.
    # Иначе любой текст `git commit` в новой папке читался бы сдвигом.
    old = project(git=True, commits=1)
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(old)})
    commit_pulse.react(payload("ls", old))
    saved = st.load(path)
    saved["project"] = {"path": str(proj)}
    st.save(saved, path)
    (proj / "draft.txt").write_text("в работе", encoding="utf-8")
    assert commit_pulse.react(payload("git commit -m 'мимо'", proj)) is None
    assert st.load(path)["streak"]["current"] == 0


# --- Игровая сессия (#97) -----------------------------------------------------
#
# Серия от сессии не зависит: хук смотрит на сдвиг HEAD записанной папки
# проекта, откуда бы человек ни сохранил. Напоминание сохраниться — слова
# игры, и звучит оно только в игровой сессии.

def from_elsewhere(command, cwd, session_id="S-work"):
    request = payload(command, cwd)
    request["session_id"] = session_id
    return request


def untouched(path):
    return (path.stat().st_mtime_ns, path.read_bytes())


def dirty(proj):
    for i in range(commit_pulse.DIRTY_THRESHOLD):
        (proj / "f{}.txt".format(i)).write_text("x", encoding="utf-8")


def test_a_foreign_session_gets_no_reminder_and_the_save_is_untouched(
        project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    dirty(proj)
    path = hook_state(project={"path": str(proj)}, commit_head={
        "path": str(proj), "sha": commit_pulse.head_sha(proj),
    })
    before = untouched(path)

    assert commit_pulse.react(from_elsewhere("ls", tmp_path)) is None

    assert untouched(path) == before


def test_a_foreign_session_does_not_run_down_the_quiet_window(
        project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)}, commit_nag_left=5, commit_head={
        "path": str(proj), "sha": commit_pulse.head_sha(proj),
    })
    before = untouched(path)

    assert commit_pulse.react(from_elsewhere("ls", tmp_path)) is None

    assert untouched(path) == before
    assert st.load(path)["commit_nag_left"] == 5


@pytest.mark.parametrize("sign", ["голокрон", "команда игры"])
def test_a_game_session_outside_the_folder_still_gets_the_reminder(
        project, hook_state, tmp_path, monkeypatch, sign):
    proj = project(git=True, commits=1)
    dirty(proj)
    hook_state(project={"path": str(proj)}, game_sessions=["S-game"])
    if sign == "голокрон":
        monkeypatch.setenv("JEDICODER_GOLOKRON", "1")
        request = from_elsewhere("ls", tmp_path)
    else:
        request = from_elsewhere("ls", tmp_path, session_id="S-game")

    out = commit_pulse.react(request)

    assert out is not None and "сохранить" in out["systemMessage"]


def test_the_series_counts_a_save_made_from_a_foreign_session(
        project, hook_state, tmp_path):
    """Серия — про папку проекта, а не про окно, из которого сохранили."""
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)}, commit_head={
        "path": str(proj), "sha": commit_pulse.head_sha(proj),
    })
    (proj / "new.txt").write_text("x", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "шаг")

    commit_pulse.react(from_elsewhere(
        "git -C {} commit -m 'шаг'".format(proj), tmp_path
    ))

    assert st.load(path)["streak"]["current"] == 1


def test_a_foreign_session_starts_no_save(tmp_path, monkeypatch):
    save = tmp_path / "jc" / "state.json"
    save.parent.mkdir()
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(save))
    assert commit_pulse.react(from_elsewhere("git commit -m x", tmp_path)) is None
    assert list(save.parent.iterdir()) == [], "ни сохранения, ни замка"

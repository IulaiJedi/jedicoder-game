"""Сообщения хуков читает человек первого вечера.

Живой проход 2026-10-09: число «Штрафы» появлялось на первом экране, а в
момент начисления слова «штраф» не звучало вовсе. Сами сообщения говорили
языком прежней игры — «заказ по настроению», «.env в индекс git», «позови
/jedicoder:brainstorm», «квест 03v-user Акта 4».

Каждый тест зовёт хук той же дверью, что Claude Code: решение по данным
вызова. Слова штрафа — те же, что на первом экране (`state.DARK_SIDE_WORDS`).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))

import _shared  # noqa: E402
import bash_guard  # noqa: E402
import commit_pulse  # noqa: E402
import lint_content  # noqa: E402
import vague_prompt  # noqa: E402
from jedicoder import acts, cli  # noqa: E402
from jedicoder import state as st  # noqa: E402

QUEST_IDS = sorted({
    quest_id for entries in acts.QUESTS_BY_ACT.values() for quest_id, _, _ in entries
})


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


def bash(command, cwd):
    return {
        "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "tool_input": {"command": command}, "cwd": str(cwd),
    }


def first_line(out):
    return out["systemMessage"].split("\n")[0]


def assert_human(message):
    """Ни команд игры, ни кодов квестов, ни фраз длиннее предела."""
    assert "/jedicoder:" not in message
    assert [quest for quest in QUEST_IDS if quest in message] == []
    assert lint_content.long_sentences(message) == []


def test_vague_request_names_the_penalty_and_the_way_out(hook_state):
    hook_state()
    out = vague_prompt.react({"prompt": "сделай мне сайт"})
    message = out["systemMessage"]
    assert first_line(out).startswith("Штраф: +1 — запрос без подробностей.")
    assert "«помоги найти идею»" in message
    assert "настроени" not in message and "промпт" not in message.lower()
    assert_human(message)


def test_password_file_names_the_penalty_in_first_evening_words(project, hook_state):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    hook_state(project={"path": str(proj)})
    out = bash_guard.decide(bash("git add .env", proj))
    message = out["systemMessage"]
    assert first_line(out).startswith(
        "Штраф: +2 — файл с паролями едва не попал в сохранение."
    )
    assert "индекс" not in message and "ротаци" not in message
    assert_human(message)
    # Claude получает точную причину — ему и чинить.
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert ".env" in reason and ".gitignore" in reason


def test_delete_outside_the_folder_names_the_penalty(project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    (tmp_path / "sosed").mkdir()
    hook_state(project={"path": str(proj)})
    out = bash_guard.decide(bash("rm -rf ../sosed", proj))
    assert first_line(out).startswith("Штраф: +1 — удаление мимо папки проекта.")
    assert "ничего не удалено" in first_line(out)
    assert_human(out["systemMessage"])


def test_root_login_names_the_penalty_without_a_quest_code(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    out = bash_guard.decide(bash("ssh root@myvps uptime", proj))
    assert first_line(out).startswith(
        "Штраф: +1 — вход на сервер главным пользователем."
    )
    assert_human(out["systemMessage"])


def test_two_penalties_in_one_command_are_both_named(project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (tmp_path / "sosed").mkdir()
    hook_state(project={"path": str(proj)})
    out = bash_guard.decide(bash("git add .env ; rm -rf ../sosed", proj))
    message = out["systemMessage"]
    assert "Штраф: +2 — файл с паролями едва не попал в сохранение." in message
    assert "Штраф: +1 — удаление мимо папки проекта." in message


def test_penalty_words_are_the_first_screen_words():
    assert cli.PENALTY_WORDS is st.DARK_SIDE_WORDS
    assert _shared.penalty_line(1, st.DARK_VAGUE_PROMPT) == (
        "Штраф: +1 — запрос без подробностей."
    )


def test_magistr_is_called_by_words_not_by_a_command():
    assert "наставник" in _shared.MAGISTR_INVITE
    assert "«позови Магистра»" in _shared.MAGISTR_INVITE
    assert_human(_shared.MAGISTR_INVITE)


def test_save_series_is_called_as_on_the_first_screen(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    out = commit_pulse.react({
        "hook_event_name": "PostToolUse", "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'шаг'"}, "cwd": str(proj),
    })
    assert out["systemMessage"] == (
        "Серия сохранений: 1 — дней подряд, когда работа была сохранена."
    )


def test_save_reminder_asks_claude_to_save(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    for i in range(commit_pulse.DIRTY_THRESHOLD):
        (proj / "f{}.txt".format(i)).write_text("x", encoding="utf-8")
    out = commit_pulse.react({
        "hook_event_name": "PostToolUse", "tool_name": "Bash",
        "tool_input": {"command": "ls"}, "cwd": str(proj),
    })
    message = out["systemMessage"]
    assert "Попроси Claude сохранить сделанное" in message
    assert "коммит" not in message.lower()
    assert_human(message)

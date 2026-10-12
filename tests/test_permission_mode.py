"""Игра знает режим разрешений от самого Claude Code (#87).

Второй прогон новичком 2026-10-08: первый квест просил найти внизу окна
серую английскую строку и прочитать её — человек её не нашёл. Claude Code
передаёт режим хукам в поле `permission_mode` (документация, раздел hooks:
поле есть у UserPromptSubmit, PreToolUse, PostToolUse и Stop, у SessionStart
его нет). Хуки игры записывают его в сохранение, контракт называет модели.

Шов: хук — процессом, той же дверью, что Claude Code; контракт — через CLI.
"""
import json

import pytest

from jedicoder import cli, game_session
from jedicoder import state as st
from test_bash_guard import run_hook

#: Сессия, в которой игру уже позвали: режим пишется только из игровой (#97).
GAME = "S-game"


@pytest.fixture
def save(tmp_path):
    path = tmp_path / "state.json"
    data = st.default_state("local-test")
    data[game_session.SESSIONS_KEY] = [GAME]
    st.save(data, path)
    return path


def prompt(save, **fields):
    payload = {
        "hook_event_name": "UserPromptSubmit", "prompt": "начинаем",
        "session_id": GAME,
    }
    payload.update(fields)
    done = run_hook("vague_prompt.py", payload, {"JEDICODER_STATE_PATH": str(save)})
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""
    return st.load(save)


def contract_text(save, content_root, quests_root, capsys):
    capsys.readouterr()
    code = cli.main(
        ["contract"], state_path=save, content_root=content_root,
        quests_root=quests_root,
    )
    assert code == 0
    return capsys.readouterr().out


def test_prompt_hook_records_the_mode_claude_code_reports(save):
    assert st.permission_mode(prompt(save, permission_mode="bypassPermissions")) == (
        "bypassPermissions"
    )


def test_mode_follows_the_latest_report(save):
    prompt(save, permission_mode="bypassPermissions")
    assert st.permission_mode(prompt(save, permission_mode="default")) == "default"


def test_missing_or_strange_mode_erases_what_the_game_knew(save):
    """Устаревшее знание хуже незнания: игра сказала бы неправду."""
    prompt(save, permission_mode="bypassPermissions")
    assert st.permission_mode(prompt(save)) is None
    prompt(save, permission_mode="bypassPermissions")
    assert st.permission_mode(prompt(save, permission_mode=["x"])) is None
    assert st.permission_mode(prompt(save, permission_mode="novyy-rezhim")) is None


def test_bash_hook_records_the_mode_too(save, tmp_path):
    """PreToolUse срабатывает перед каждой командой игры — режим свежий."""
    done = run_hook("bash_guard.py", {
        "hook_event_name": "PreToolUse", "permission_mode": "acceptEdits",
        "tool_name": "Bash", "tool_input": {"command": "ls"},
        "cwd": str(tmp_path), "session_id": GAME,
    }, {"JEDICODER_STATE_PATH": str(save)})
    assert done.returncode == 0, done.stderr
    assert st.permission_mode(st.load(save)) == "acceptEdits"


def test_hook_does_not_start_a_game_for_someone_who_is_not_playing(tmp_path):
    """Сохранение заводит первая команда игры, а не чужой запрос."""
    path = tmp_path / "state.json"
    done = run_hook(
        "vague_prompt.py",
        {"prompt": "привет", "permission_mode": "default"},
        {"JEDICODER_STATE_PATH": str(path)},
    )
    assert done.returncode == 0
    assert not path.exists()


def test_a_foreign_session_does_not_write_its_mode(save, tmp_path):
    """Режим соседнего окна игра человеку не назовёт (#97)."""
    prompt(save, permission_mode="bypassPermissions")
    before = (save.stat().st_mtime_ns, save.read_bytes())
    prompt(save, permission_mode="default", session_id="S-work")
    done = run_hook("bash_guard.py", {
        "hook_event_name": "PreToolUse", "permission_mode": "plan",
        "tool_name": "Bash", "tool_input": {"command": "ls"},
        "cwd": str(tmp_path), "session_id": "S-work",
    }, {"JEDICODER_STATE_PATH": str(save)})
    assert done.returncode == 0, done.stderr
    assert (save.stat().st_mtime_ns, save.read_bytes()) == before
    assert st.permission_mode(st.load(save)) == "bypassPermissions"


def test_the_first_game_command_records_the_mode_of_its_own_request(tmp_path):
    """Голый терминал, сохранения нет: запрос `/jedicoder:start` и делает
    сессию игровой, и приносит её режим — контракту он нужен с первого хода."""
    path = tmp_path / "jc" / "state.json"
    done = run_hook("vague_prompt.py", {
        "hook_event_name": "UserPromptSubmit", "prompt": "/jedicoder:start",
        "session_id": "S-first", "permission_mode": "bypassPermissions",
        "cwd": str(tmp_path),
    }, {"JEDICODER_STATE_PATH": str(path)})
    assert done.returncode == 0 and done.stdout == "", done.stderr
    assert st.permission_mode(st.load(path)) == "bypassPermissions"


@pytest.mark.parametrize("sign", ["голокрон", "папка проекта"])
def test_the_other_signs_let_the_mode_through(save, tmp_path, sign):
    env = {"JEDICODER_STATE_PATH": str(save)}
    payload = {
        "hook_event_name": "UserPromptSubmit", "prompt": "начинаем",
        "session_id": "S-new", "permission_mode": "acceptEdits",
    }
    if sign == "голокрон":
        env[game_session.GOLOKRON_MARK] = "1"
    else:
        data = st.load(save)
        data["project"]["path"] = str(tmp_path)
        st.save(data, save)
        payload["cwd"] = str(tmp_path)
    assert run_hook("vague_prompt.py", payload, env).returncode == 0
    assert st.permission_mode(st.load(save)) == "acceptEdits"


def test_unchanged_mode_does_not_rewrite_the_save(save):
    prompt(save, permission_mode="default")
    before = save.stat().st_mtime_ns
    prompt(save, permission_mode="default")
    assert save.stat().st_mtime_ns == before


def test_mode_does_not_bump_the_schema(save):
    data = prompt(save, permission_mode="default")
    assert data["schema_version"] == st.SCHEMA_VERSION == 4


def test_garbage_in_the_save_reads_as_unknown():
    assert st.permission_mode({"permission_mode": {"a": 1}}) is None
    assert st.permission_mode({"permission_mode": "что-то"}) is None
    assert st.permission_mode({}) is None


def test_broken_save_does_not_break_the_prompt(tmp_path):
    """Закон хуков: любая ошибка — молчаливый выход."""
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"schema_version": 999}), encoding="utf-8")
    done = run_hook(
        "vague_prompt.py",
        {"prompt": "начинаем", "permission_mode": "default"},
        {"JEDICODER_STATE_PATH": str(path)},
    )
    assert done.returncode == 0 and done.stdout == ""


# --- Контракт говорит модели то, что игра знает -----------------------------

def test_contract_names_the_mode_without_questions(
        save, content_root, quests_root, capsys):
    prompt(save, permission_mode="bypassPermissions")
    text = contract_text(save, content_root, quests_root, capsys)
    assert "- Режим Claude Code: без вопросов." in text


def test_contract_says_when_the_mode_is_another(
        save, content_root, quests_root, capsys):
    prompt(save, permission_mode="default")
    text = contract_text(save, content_root, quests_root, capsys)
    assert "- Режим Claude Code: другой, не «без вопросов»." in text
    # Не «перед каждой правкой»: это верно не для всякого режима.
    assert "перед частью действий" in text
    assert "- Режим Claude Code: без вопросов." not in text


def test_contract_does_not_claim_a_mode_it_does_not_know(
        save, content_root, quests_root, capsys):
    text = contract_text(save, content_root, quests_root, capsys)
    assert "- Режим Claude Code игре неизвестен." in text
    assert "Режим Claude Code: без вопросов" not in text

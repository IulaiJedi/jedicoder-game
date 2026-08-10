import pytest

from jedicoder import quests, state as st

OK_SCRIPT = """#!/usr/bin/env bash
printf '{"quest":"t/01","ok":true,"checks":[{"id":"a","ok":true,"label":"А"}]}\\n'
exit 0
"""

FAIL_SCRIPT = """#!/usr/bin/env bash
printf '{"quest":"t/01","ok":false,"checks":[{"id":"a","ok":false,"label":"А","hint":"Сделай А"},{"id":"b","ok":true,"label":"Б"}]}\\n'
exit 1
"""

BAIL_SCRIPT = """#!/usr/bin/env bash
echo "не найден gh" >&2
exit 2
"""

BROKEN_JSON_SCRIPT = """#!/usr/bin/env bash
echo "это не json"
exit 0
"""

INCONSISTENT_SCRIPT = """#!/usr/bin/env bash
printf '{"quest":"t/01","ok":false,"checks":[]}\\n'
exit 0
"""

ENV_SCRIPT = """#!/usr/bin/env bash
if [ "${JEDICODER_HAS_DB:-unset}" = "no" ]; then
  printf '{"quest":"t/01","ok":true,"checks":[]}\\n'; exit 0
fi
printf '{"quest":"t/01","ok":false,"checks":[]}\\n'; exit 1
"""

CWD_SCRIPT = """#!/usr/bin/env bash
if [ -f marker.txt ]; then
  printf '{"quest":"t/01","ok":true,"checks":[]}\\n'; exit 0
fi
printf '{"quest":"t/01","ok":false,"checks":[]}\\n'; exit 1
"""

# Инфраструктурный сбой: 127 — «команда не найдена». JSON при этом может быть
# вполне разбираемым, поэтому попытку легко списать падавану.
CRASH_SCRIPT = """#!/usr/bin/env bash
echo "нет такой команды: гит" >&2
printf '{"quest":"t/01","ok":false,"checks":[]}\\n'
exit 127
"""


@pytest.fixture
def quests_dir(tmp_path):
    def make(quest_id, body):
        directory = tmp_path / "act-test" / quest_id
        directory.mkdir(parents=True, exist_ok=True)
        script = directory / "check.sh"
        script.write_text(body, encoding="utf-8")
        script.chmod(0o755)
        return tmp_path

    return make


def test_missing_script_is_ack(tmp_path):
    result = quests.run_check(tmp_path, "act-test", "06-pipeline", tmp_path)
    assert result.kind == quests.KIND_ACK
    assert result.countable is False
    assert result.ok is False


def test_success_parsed(quests_dir, tmp_path):
    root = quests_dir("01-a", OK_SCRIPT)
    result = quests.run_check(root, "act-test", "01-a", tmp_path)
    assert result.kind == quests.KIND_SCRIPT
    assert result.exit_code == 0
    assert result.ok is True
    assert result.countable is True
    assert result.checks[0]["id"] == "a"


def test_failure_exposes_only_failed_checks(quests_dir, tmp_path):
    root = quests_dir("01-a", FAIL_SCRIPT)
    result = quests.run_check(root, "act-test", "01-a", tmp_path)
    assert result.ok is False
    assert result.countable is True
    failed = quests.failed_checks(result)
    assert [c["id"] for c in failed] == ["a"]
    assert failed[0]["hint"] == "Сделай А"


def test_exit_two_is_not_countable(quests_dir, tmp_path):
    root = quests_dir("01-a", BAIL_SCRIPT)
    result = quests.run_check(root, "act-test", "01-a", tmp_path)
    assert result.exit_code == 2
    assert result.countable is False
    assert result.ok is False
    assert "gh" in result.stderr


def test_exit_127_is_not_counted_against_padawan(quests_dir, tmp_path):
    """Код вне {0,1,2} — тоже «не смог проверить», а не провал квеста."""
    root = quests_dir("01-a", CRASH_SCRIPT)
    result = quests.run_check(root, "act-test", "01-a", tmp_path)
    assert result.exit_code == 127
    assert result.countable is False
    assert result.ok is False
    assert result.checks == ()
    assert quests.cannot_check(result) is True
    assert "гит" in result.stderr


def test_cannot_check_is_false_for_verdicts(quests_dir, tmp_path):
    root = quests_dir("01-a", OK_SCRIPT)
    assert quests.cannot_check(quests.run_check(root, "act-test", "01-a", tmp_path)) is False
    root = quests_dir("01-b", FAIL_SCRIPT)
    assert quests.cannot_check(quests.run_check(root, "act-test", "01-b", tmp_path)) is False


def test_script_path_is_absolute(tmp_path, monkeypatch):
    """Скрипт ищется относительно процесса CLI, а запускается с cwd проекта.

    С относительным quests_root проверка файла проходила, а bash отдавал 127.
    """
    monkeypatch.chdir(tmp_path)
    path = quests.script_path("plugin/quests", "act2-chertezh", "04-git-init")
    assert path.is_absolute()
    assert path == tmp_path / "plugin/quests/act2-chertezh/04-git-init/check.sh"


def test_relative_quests_root_still_runs_script(quests_dir, tmp_path, monkeypatch):
    quests_dir("01-a", OK_SCRIPT)
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    result = quests.run_check(".", "act-test", "01-a", project)
    assert result.ok is True


def test_non_json_stdout_raises(quests_dir, tmp_path):
    root = quests_dir("01-a", BROKEN_JSON_SCRIPT)
    with pytest.raises(quests.QuestError, match="не JSON"):
        quests.run_check(root, "act-test", "01-a", tmp_path)


def test_exit_code_and_ok_must_agree(quests_dir, tmp_path):
    root = quests_dir("01-a", INCONSISTENT_SCRIPT)
    with pytest.raises(quests.QuestError, match="расходятся"):
        quests.run_check(root, "act-test", "01-a", tmp_path)


def test_env_extra_passed_through(quests_dir, tmp_path):
    root = quests_dir("01-a", ENV_SCRIPT)
    assert quests.run_check(root, "act-test", "01-a", tmp_path).ok is False
    assert quests.run_check(
        root, "act-test", "01-a", tmp_path, env_extra={"JEDICODER_HAS_DB": "no"}
    ).ok is True


def test_script_runs_in_project_dir(quests_dir, tmp_path):
    root = quests_dir("01-a", CWD_SCRIPT)
    project = tmp_path / "proj"
    project.mkdir()
    assert quests.run_check(root, "act-test", "01-a", project).ok is False
    (project / "marker.txt").write_text("x", encoding="utf-8")
    assert quests.run_check(root, "act-test", "01-a", project).ok is True


def _result(ok, countable, kind=quests.KIND_SCRIPT):
    return quests.CheckResult(
        quest="01-a", kind=kind, exit_code=0 if ok else 1, ok=ok,
        checks=(), stderr="", countable=countable,
    )


def test_attempts_increment_on_pass_and_fail():
    data = st.default_state("abc123")
    quests.record_attempt(data, 2, "01-a", _result(False, True))
    assert quests.attempts(data, 2, "01-a") == 1
    quests.record_attempt(data, 2, "01-a", _result(True, True))
    assert quests.attempts(data, 2, "01-a") == 2
    assert data["acts"]["2"]["quests"]["01-a"]["status"] == "done"


def test_attempts_not_incremented_on_exit_two():
    data = st.default_state("abc123")
    quests.record_attempt(data, 2, "01-a", _result(False, False))
    assert quests.attempts(data, 2, "01-a") == 0


def test_first_try_counted_only_when_attempts_is_one():
    data = st.default_state("abc123")
    quests.record_attempt(data, 2, "01-a", _result(True, True))
    assert data["first_try"] == {"passed": 1, "attempted": 1}

    quests.record_attempt(data, 2, "02-b", _result(False, True))
    quests.record_attempt(data, 2, "02-b", _result(True, True))
    assert data["first_try"] == {"passed": 1, "attempted": 2}


def test_closed_quest_is_not_reopened():
    data = st.default_state("abc123")
    quests.record_attempt(data, 2, "01-a", _result(True, True))
    quests.record_attempt(data, 2, "01-a", _result(False, True))
    assert data["acts"]["2"]["quests"]["01-a"]["status"] == "done"
    assert quests.attempts(data, 2, "01-a") == 1
    assert data["first_try"] == {"passed": 1, "attempted": 1}


def test_acknowledge_closes_without_touching_first_try():
    data = st.default_state("abc123")
    quests.acknowledge(data, 2, "06-pipeline")
    assert data["acts"]["2"]["quests"]["06-pipeline"]["status"] == "done"
    assert data["first_try"] == {"passed": 0, "attempted": 0}


def test_loop_warning_fires_on_third_attempt():
    data = st.default_state("abc123")
    for _ in range(2):
        quests.record_attempt(data, 2, "01-a", _result(False, True))
    assert quests.loop_warning(data, 2, "01-a") is False
    quests.record_attempt(data, 2, "01-a", _result(False, True))
    assert quests.loop_warning(data, 2, "01-a") is True


def test_loop_warning_silent_after_success():
    data = st.default_state("abc123")
    for _ in range(3):
        quests.record_attempt(data, 2, "01-a", _result(False, True))
    quests.record_attempt(data, 2, "01-a", _result(True, True))
    assert quests.loop_warning(data, 2, "01-a") is False


def test_first_close_awards_quest_xp():
    data = st.default_state("abc123")
    quests.record_attempt(data, 2, "01-x", _result(True, True))
    assert data["xp"] == quests.QUEST_XP


def test_repeat_close_awards_nothing():
    data = st.default_state("abc123")
    quests.record_attempt(data, 2, "01-x", _result(True, True))
    quests.record_attempt(data, 2, "01-x", _result(True, True))
    assert data["xp"] == quests.QUEST_XP


def test_failed_attempt_awards_nothing():
    data = st.default_state("abc123")
    quests.record_attempt(data, 2, "01-x", _result(False, True))
    assert data.get("xp", 0) == 0


def test_ack_awards_quest_xp_once():
    data = st.default_state("abc123")
    quests.acknowledge(data, 2, "06-y")
    quests.acknowledge(data, 2, "06-y")
    assert data["xp"] == quests.QUEST_XP

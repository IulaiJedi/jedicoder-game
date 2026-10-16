"""PreToolUse-хук: разбор bash-команд и блокировки.

Git в тестах живой (временные репозитории), не мокается: разбор вывода
`git status --porcelain` — самая хрупкая часть, мок спрятал бы её.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))

import bash_guard  # noqa: E402

from conftest import _git  # noqa: E402


def test_simple_commands_splits_on_operators():
    assert bash_guard.simple_commands("git add . && git commit -m x") == [
        ["git", "add", "."], ["git", "commit", "-m", "x"],
    ]
    assert bash_guard.simple_commands("cat f | grep x") == [
        ["cat", "f"], ["grep", "x"],
    ]


def test_semicolon_does_not_hide_a_command():
    # Ловушка: голый shlex.split приклеивает «;» к предыдущему токену
    # («ls;»), и вторая команда перестаёт опознаваться — `ls; rm -rf /`
    # прошёл бы мимо блока. Разделители обязаны быть отдельными токенами.
    assert bash_guard.simple_commands("ls; rm -rf build") == [
        ["ls"], ["rm", "-rf", "build"],
    ]
    assert bash_guard.simple_commands("(cd /tmp; rm -rf x)") == [
        ["cd", "/tmp"], ["rm", "-rf", "x"],
    ]


def test_quoted_text_is_not_a_command():
    # Внутри кавычек — данные, а не команда: блокировать `echo "rm -rf /"`
    # значит ловить разговор о команде вместо самой команды.
    assert bash_guard.simple_commands('echo "rm -rf /" && ls') == [
        ["echo", "rm -rf /"], ["ls"],
    ]


def test_simple_commands_on_unparseable_returns_empty():
    # Незакрытая кавычка: разобрать нечем — значит и судить не о чем.
    assert bash_guard.simple_commands('git add "broken') == []


def test_explicit_env_add_is_caught(tmp_path):
    assert bash_guard.stages_env(["git", "add", ".env"], tmp_path) is True
    assert bash_guard.stages_env(["git", "add", "-f", ".env"], tmp_path) is True
    assert bash_guard.stages_env(
        ["git", "add", "config/.env"], tmp_path
    ) is True


def test_unrelated_commands_are_not_env_staging(tmp_path):
    assert bash_guard.stages_env(["ls", "-la"], tmp_path) is False
    assert bash_guard.stages_env(["git", "status"], tmp_path) is False
    assert bash_guard.stages_env(["git", "add", "src/app.py"], tmp_path) is False
    # .env.example — не секрет, а образец: его коммитят намеренно
    assert bash_guard.stages_env(
        ["git", "add", ".env.example"], tmp_path
    ) is False


def test_mass_add_checks_working_tree(project):
    dirty = project(git=True, commits=1)
    (dirty / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    for form in (["git", "add", "."], ["git", "add", "-A"],
                 ["git", "add", "--all"]):
        assert bash_guard.stages_env(form, dirty) is True, form


def test_mass_add_is_fine_when_env_ignored(project):
    clean = project(gitignore=".env\n", git=True, commits=1)
    (clean / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    assert bash_guard.stages_env(["git", "add", "."], clean) is False


def test_mass_add_is_fine_without_env_at_all(project):
    clean = project(git=True, commits=1)
    (clean / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert bash_guard.stages_env(["git", "add", "."], clean) is False


def test_mass_add_outside_repo_does_not_block(tmp_path):
    # Не git-репозиторий: судить не о чем — пропускаем.
    assert bash_guard.stages_env(["git", "add", "."], tmp_path) is False


def test_rm_rf_root_and_home_always_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for target in ("/", "~", "$HOME", str(tmp_path / "home")):
        tokens = ["rm", "-rf", target]
        assert bash_guard.wipes_outside_project(
            tokens, tmp_path, None
        ) is True, target


def test_rm_rf_inside_project_is_allowed(tmp_path):
    project_dir = tmp_path / "proj"
    (project_dir / "build").mkdir(parents=True)
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "build"], project_dir, project_dir
    ) is False
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", str(project_dir / "build")], project_dir, project_dir
    ) is False


def test_rm_rf_outside_project_is_blocked(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (tmp_path / "neighbour").mkdir()
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "../neighbour"], project_dir, project_dir
    ) is True


def test_rm_without_both_flags_is_ignored(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    for tokens in (["rm", "file.txt"], ["rm", "-r", "dir"],
                   ["rm", "-f", "file.txt"]):
        assert bash_guard.wipes_outside_project(
            tokens, project_dir, project_dir
        ) is False, tokens


def test_rm_rf_flag_spellings_are_caught(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    (tmp_path / "neighbour").mkdir()
    for flags in (["-rf"], ["-fr"], ["-r", "-f"], ["--recursive", "--force"],
                  ["-rfv"]):
        tokens = ["rm"] + flags + ["../neighbour"]
        assert bash_guard.wipes_outside_project(
            tokens, project_dir, project_dir
        ) is True, flags


def test_rm_rf_without_known_project_is_allowed(tmp_path):
    # Папка проекта неизвестна — судить не о чем, кроме катастроф выше.
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "build"], tmp_path, None
    ) is False


def test_root_login_detected():
    assert bash_guard.logs_in_as_root(["ssh", "root@203.0.113.7"]) is True
    assert bash_guard.logs_in_as_root(
        ["ssh", "-i", "key", "root@myvps"]
    ) is True
    assert bash_guard.logs_in_as_root(["ssh", "deploy@myvps"]) is False
    assert bash_guard.logs_in_as_root(["ssh", "myvps"]) is False
    assert bash_guard.logs_in_as_root(["cat", "root@x"]) is False


#: Сессия, в которой человек позвал команду игры: её идентификатор лежит в
#: сохранении, которое сеет `hook_state`. Сторож судит только в игровой
#: сессии (#97), и тесты ниже описывают её — где бы ни была открыта.
GAME = "S-game"


def payload(command, cwd, session_id=GAME):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
        "session_id": session_id,
    }


@pytest.fixture
def hook_state(tmp_path, monkeypatch):
    """Состояние падавана под хуком: путь через тот же env-шов, что у лута."""
    from jedicoder import state as st

    path = tmp_path / "state.json"

    def seed(**fields):
        data = st.default_state("local-test")
        data["game_sessions"] = [GAME]
        data.update(fields)
        st.save(data, path)
        monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
        return path

    return seed


def test_env_staging_denies_and_scores(project, hook_state):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    path = hook_state(project={"path": str(proj)})

    out = bash_guard.decide(payload("git add .", proj))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert ".env" in out["hookSpecificOutput"]["permissionDecisionReason"]

    from jedicoder import state as st
    assert st.load(path)["dark_side"] == 2


def test_env_staging_outside_the_project_is_not_judged(project, hook_state):
    """Чужой репозиторий — не предмет суда Тёмной стороны.

    Игра ставится глобально и хук работает во всех проектах машины. Значит
    посторонний, поставивший её ради Акта 1, получал бы отказ на `git add .`
    в своём рабочем репозитории — за `.env`, которого игра ему не показывала
    и о котором ничему не учила. Ложный блок дороже пропуска: судим только
    внутри папки, которую падаван сам назвал проектом.
    """
    proj = project(git=True, commits=1)
    other = project(git=True, commits=1)
    (other / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    path = hook_state(project={"path": str(proj)})

    assert bash_guard.decide(payload("git add .", other)) is None

    from jedicoder import state as st
    assert st.load(path)["dark_side"] == 0


def test_env_staging_without_a_known_project_is_not_judged(project, hook_state):
    """Проект не назван — судить не по чему.

    Ровно состояние того, кто поставил плагин и ещё не доходил до `project
    path`. Тот же выбор, что у `wipes_outside_project`: не знаем проект —
    пропускаем.
    """
    other = project(git=True, commits=1)
    (other / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    path = hook_state()

    assert bash_guard.decide(payload("git add .", other)) is None

    from jedicoder import state as st
    assert st.load(path)["dark_side"] == 0


def test_env_staging_in_a_subfolder_of_the_project_is_judged(project, hook_state):
    """Граница — папка проекта целиком, а не только её корень.

    Иначе правка сузилась бы до бесполезной: работают из подпапок постоянно.
    """
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    inner = proj / "src"
    inner.mkdir(exist_ok=True)
    hook_state(project={"path": str(proj)})

    out = bash_guard.decide(payload("git add {}/.env".format(proj), inner))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_rm_rf_outside_denies_and_scores(project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    (tmp_path / "neighbour").mkdir(exist_ok=True)
    path = hook_state(project={"path": str(proj)})

    out = bash_guard.decide(payload("rm -rf ../neighbour", proj))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    from jedicoder import state as st
    assert st.load(path)["dark_side"] == 1


def test_root_login_warns_but_allows_once(project, hook_state):
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    from jedicoder import state as st

    out = bash_guard.decide(payload("ssh root@myvps 'uptime'", proj))
    assert "hookSpecificOutput" not in out, "предупреждение не блокирует"
    assert "root" in out["systemMessage"]
    assert st.load(path)["dark_side"] == 1

    second = bash_guard.decide(payload("ssh root@myvps 'uptime'", proj))
    assert second is None, "второй раз молчим — счёт уже начислен"
    assert st.load(path)["dark_side"] == 1


def test_clean_command_returns_nothing(project, hook_state):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    assert bash_guard.decide(payload("git status", proj)) is None


def test_magistr_invite_appears_at_threshold(project, hook_state):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    hook_state(project={"path": str(proj)}, dark_side=4)

    out = bash_guard.decide(payload("git add .env", proj))
    assert "«позови Магистра»" in out["systemMessage"]


def test_non_bash_tool_is_ignored(tmp_path, hook_state):
    hook_state()
    assert bash_guard.decide({
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / ".env")},
        "cwd": str(tmp_path),
    }) is None


def test_newlines_split_commands():
    assert bash_guard.simple_commands("cd /tmp\nrm -rf /") == [
        ["cd", "/tmp"], ["rm", "-rf", "/"],
    ]
    assert bash_guard.simple_commands("rm \\\n  -rf build") == [
        ["rm", "-rf", "build"],
    ]


def test_wrappers_and_paths_do_not_hide_rm(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    for tokens in (
        ["sudo", "rm", "-rf", "/"],
        ["env", "FOO=bar", "rm", "-rf", "/"],
        ["FOO=bar", "rm", "-rf", "/"],
        ["/bin/rm", "-rf", "/"],
        ["sudo", "-n", "rm", "-rf", "/"],
    ):
        assert bash_guard.wipes_outside_project(
            tokens, project_dir, project_dir
        ) is True, tokens


def test_git_global_options_do_not_hide_add(project):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    assert bash_guard.stages_env(
        ["git", "-C", str(proj), "add", "."], proj
    ) is True
    assert bash_guard.stages_env(
        ["sudo", "git", "add", ".env"], proj
    ) is True


def test_warning_does_not_mask_a_block(project, hook_state):
    proj = project(git=True, commits=1)
    (proj.parent / "neighbour").mkdir(exist_ok=True)
    path = hook_state(project={"path": str(proj)})
    out = bash_guard.decide(payload(
        "ssh root@myvps 'true' ; rm -rf ../neighbour", proj
    ))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    from jedicoder import state as st
    # +1 за rm и +1 за root: предупреждение не отменяется блоком
    assert st.load(path)["dark_side"] == 2


def test_symlinked_project_does_not_false_block(tmp_path):
    real = tmp_path / "real-proj"
    (real / "build").mkdir(parents=True)
    link = tmp_path / "link-proj"
    link.symlink_to(real)
    # Состояние хранит раскрытый путь (cli.py делает resolve), падаван
    # ходит по симлинку — это не «вне проекта».
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "build"], link, real
    ) is False


def test_env_example_still_allowed_after_normalization(tmp_path):
    assert bash_guard.stages_env(
        ["git", "add", ".env.example"], tmp_path
    ) is False


def test_innocent_rm_inside_project_still_allowed(tmp_path):
    project_dir = tmp_path / "proj"
    (project_dir / "node_modules").mkdir(parents=True)
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "node_modules"], project_dir, project_dir
    ) is False


def test_quoted_newline_does_not_swallow_the_command():
    # Регрессия: нарезка по «\n» до лексера роняла разбор всей строки,
    # и опасный хвост переставал проверяться.
    assert bash_guard.simple_commands(
        'git commit -m "line one\nline two" && sudo rm -rf /important'
    ) == [
        ["git", "commit", "-m", "line one\nline two"],
        ["sudo", "rm", "-rf", "/important"],
    ]


def test_heredoc_tail_is_still_checked():
    commands = bash_guard.simple_commands("cat <<EOF\nhello\nEOF\nrm -rf /")
    assert ["rm", "-rf", "/"] in commands


def test_heredoc_body_is_data_not_commands():
    # Падаван пишет скрипт уборки — это текст, а не удаление.
    commands = bash_guard.simple_commands(
        "cat > cleanup.sh <<'EOF'\nrm -rf /tmp/scratch\ngit add .\nEOF\necho ok"
    )
    assert ["rm", "-rf", "/tmp/scratch"] not in commands
    assert ["git", "add", "."] not in commands
    assert ["echo", "ok"] in commands, "хвост после терминатора проверяется"


def test_trailing_backslash_does_not_disable_the_guard():
    assert bash_guard.simple_commands("rm -rf /home \\") == [
        ["rm", "-rf", "/home"],
    ]


def test_ansi_c_quoting_does_not_hide_the_path():
    # `$'…'` — та же одинарная кавычка для целей опознания пути: без
    # нормализации `$/important` читался бы как относительный путь.
    assert bash_guard.simple_commands("rm -rf $'/important'") == [
        ["rm", "-rf", "/important"]
    ]


def test_wrapper_options_with_values_do_not_hide_the_command(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    for tokens in (
        ["sudo", "-u", "root", "rm", "-rf", "/"],
        ["doas", "-u", "root", "rm", "-rf", "/"],
        ["nice", "-n", "10", "rm", "-rf", "/"],
        ["env", "-u", "FOO", "rm", "-rf", "/"],
        ["sudo", "--user", "root", "rm", "-rf", "/"],
    ):
        assert bash_guard.wipes_outside_project(
            tokens, project_dir, project_dir
        ) is True, tokens


def test_wrapper_options_with_values_do_not_hide_git_add(project):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    assert bash_guard.stages_env(
        ["sudo", "-u", "root", "git", "add", "."], proj
    ) is True


def test_symlinked_dir_inside_project_is_not_false_blocked(tmp_path):
    # build -> кэш пакетного менеджера вне проекта: это по-прежнему файл
    # проекта, а `rm -rf build` без слэша снимает только саму ссылку.
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    cache = tmp_path / "outside-cache"
    cache.mkdir()
    (project_dir / "build").symlink_to(cache)
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "build"], project_dir, project_dir
    ) is False


def test_stale_project_path_does_not_false_block(tmp_path):
    # Папка проекта в состоянии есть, а на диске её больше нет (удалена,
    # переименована) — «не знаем проект», а не «весь диск чужой».
    gone = tmp_path / "gone-project"
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "build"], tmp_path, gone
    ) is False
    # Катастрофы (корень) остаются под защитой независимо от знания проекта.
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "/"], tmp_path, gone
    ) is True


def test_mass_add_dot_is_scoped_to_cwd(project):
    # `cd frontend && git add .` — .env лежит в корне репозитория, но
    # `frontend/` сам по себе чист: `.` добавляет только своё поддерево.
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    frontend = proj / "frontend"
    frontend.mkdir()
    (frontend / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert bash_guard.stages_env(["git", "add", "."], frontend) is False


def test_git_stage_alias_is_caught(project):
    # `git stage` — документированный алиас `git add`.
    proj = project(git=True, commits=1)
    assert bash_guard.stages_env(["git", "stage", ".env"], proj) is True


HOOKS = ROOT / "plugin" / "hooks"


def run_hook(name, payload, env_extra=None):
    """Прогнать хук процессом — той же дверью, что Claude Code."""
    import os
    env = dict(os.environ)
    env.update(env_extra or {})
    done = subprocess.run(
        [sys.executable, str(HOOKS / name)],
        input=json.dumps(payload), capture_output=True, text=True,
        timeout=30, env=env,
    )
    return done


def test_hooks_json_registers_all_three():
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    events = config["hooks"]
    assert any(
        "bash_guard.py" in h["command"]
        for entry in events["PreToolUse"] for h in entry["hooks"]
    )
    assert any(
        "commit_pulse.py" in h["command"]
        for entry in events["PostToolUse"] for h in entry["hooks"]
    )
    assert any(
        "vague_prompt.py" in h["command"]
        for entry in events["UserPromptSubmit"] for h in entry["hooks"]
    )
    # Матчер Bash обязателен: без него хук звался бы на каждый Read. У хука
    # следов матчер свой (`tests/test_traces.py`), но без матчера на этих
    # событиях не стоит никто.
    for event, name in (("PreToolUse", "bash_guard.py"),
                        ("PostToolUse", "commit_pulse.py")):
        assert all(entry.get("matcher") for entry in events[event]), event
        assert all(
            entry.get("matcher") == "Bash" for entry in events[event]
            if any(name in h["command"] for h in entry["hooks"])
        ), event


def test_hook_process_denies_env_staging(project, tmp_path):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    state_path = tmp_path / "hook-state.json"
    from jedicoder import state as st
    data = st.default_state("local-test")
    data["project"] = {"path": str(proj)}
    st.save(data, state_path)

    done = run_hook("bash_guard.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "git add ."},
        "cwd": str(proj),
    }, {"JEDICODER_STATE_PATH": str(state_path)})

    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert st.load(state_path)["dark_side"] == 2


@pytest.mark.parametrize("name", [
    "bash_guard.py", "commit_pulse.py", "vague_prompt.py",
])
def test_hooks_survive_broken_stdin(name, tmp_path):
    """Закон хуков: битый вход — тихий выход, ничего не блокируем."""
    import os
    env = dict(os.environ)
    env["JEDICODER_STATE_PATH"] = str(tmp_path / "state.json")
    done = subprocess.run(
        [sys.executable, str(HOOKS / name)],
        input="не json вовсе", capture_output=True, text=True,
        timeout=30, env=env,
    )
    assert done.returncode == 0
    assert done.stdout.strip() == ""


def test_env_staging_writes_two_entries_of_its_kind(project, hook_state):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    path = hook_state(project={"path": str(proj)})

    bash_guard.decide(payload("git add .", proj))

    from jedicoder import state as st
    saved = st.load(path)
    assert [e["type"] for e in st.dark_side_entries(saved)] == [
        "env_staged", "env_staged",
    ]
    assert len(st.dark_side_entries(saved)) == saved["dark_side"]


def test_rm_outside_the_project_writes_its_kind(project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    (tmp_path / "neighbour").mkdir(exist_ok=True)
    path = hook_state(project={"path": str(proj)})

    bash_guard.decide(payload("rm -rf ../neighbour", proj))

    from jedicoder import state as st
    assert [e["type"] for e in st.dark_side_entries(st.load(path))] == [
        "rm_outside_project",
    ]


def test_root_login_writes_its_kind_once(project, hook_state):
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})

    bash_guard.decide(payload("ssh root@myvps 'uptime'", proj))
    bash_guard.decide(payload("ssh root@myvps 'uptime'", proj))

    from jedicoder import state as st
    assert [e["type"] for e in st.dark_side_entries(st.load(path))] == [
        "root_login",
    ]


def test_the_log_never_holds_the_command(project, hook_state):
    """ADR-0011: журнал уезжает в Свиток, а в команде бывают пути и ключи."""
    proj = project(git=True, commits=1)
    inner = proj / "секрет"
    inner.mkdir(exist_ok=True)
    path = hook_state(project={"path": str(proj)})

    bash_guard.decide(payload("rm -rf {}/../../чужое".format(inner), proj))

    from jedicoder import state as st
    saved = st.load(path)
    assert saved["dark_side_log"], "запись всё-таки появилась"
    for entry in saved["dark_side_log"]:
        assert sorted(entry) == ["date", "type"]
    assert "чужое" not in json.dumps(saved, ensure_ascii=False)


def test_two_kinds_in_one_command_write_both_entries(project, hook_state,
                                                     tmp_path):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (tmp_path / "neighbour").mkdir(exist_ok=True)
    path = hook_state(project={"path": str(proj)})

    bash_guard.decide(payload("git add . && rm -rf ../neighbour", proj))

    from jedicoder import state as st
    saved = st.load(path)
    assert [e["type"] for e in st.dark_side_entries(saved)] == [
        "env_staged", "env_staged", "rm_outside_project",
    ]
    assert len(st.dark_side_entries(saved)) == saved["dark_side"] == 3


def test_broken_journal_does_not_block_and_does_not_kill_the_session(
    project, hook_state, monkeypatch, capsys
):
    """Закон хуков: сломалась запись журнала — молчим и пропускаем.

    Ошибка внутри окна записи оставляет состояние нетронутым (update_state
    не сохраняет после исключения) и не превращается ни в отказ, ни в
    упавшую сессию: падаван продолжает работать.
    """
    import io

    from jedicoder import state as st

    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    path = hook_state(project={"path": str(proj)})

    def boom(*args, **kwargs):
        raise RuntimeError("журнал сломан")

    monkeypatch.setattr(st, "record_dark_side", boom)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps(payload("git add .", proj)))
    )

    assert bash_guard.main() == 0
    assert capsys.readouterr().out == "", "ни решения, ни сообщения"
    assert st.load(path)["dark_side"] == 0


def test_counter_and_journal_go_in_one_pass_over_the_state(
    project, hook_state, monkeypatch, tmp_path
):
    """Очко и запись пишутся одним проходом под блокировкой, а не двумя.

    Два прохода разъезжаются: между ними чужой процесс успевает записать
    своё, и последний сохранивший затирает соседа. Считаем сохранения:
    на одну команду их ровно одно.
    """
    from jedicoder import state as st

    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (tmp_path / "neighbour").mkdir(exist_ok=True)
    path = hook_state(project={"path": str(proj)})

    saves = []
    real_save = st.save

    def counting_save(data, target=st.STATE_PATH):
        saves.append(len(data.get("dark_side_log") or []))
        return real_save(data, target)

    monkeypatch.setattr(st, "save", counting_save)
    bash_guard.decide(payload("git add . && rm -rf ../neighbour", proj))

    assert saves == [3], "одно сохранение, и журнал в нём уже полный"
    assert st.load(path)["dark_side"] == 3


# --- Режим без проверок: хук — единственная защита (тикет Н1) ---------------


def test_heredoc_with_dash_does_not_swallow_the_tail():
    # Долг №5: у `<<-EOF` лексер отдаёт разделитель как «-EOF», и
    # терминатор «EOF» не находился никогда — съедалась вся команда.
    commands = bash_guard.simple_commands(
        "cat <<-EOF\n\tпривет\n\tEOF\nrm -rf /"
    )
    assert ["rm", "-rf", "/"] in commands
    assert ["привет"] not in commands, "тело по-прежнему данные"


def test_heredoc_with_dash_and_quoted_delimiter():
    commands = bash_guard.simple_commands(
        "cat > note.txt <<-'EOF'\n\trm -rf /tmp/scratch\n\tEOF\necho ok"
    )
    assert ["rm", "-rf", "/tmp/scratch"] not in commands
    assert ["echo", "ok"] in commands


def test_trailing_slash_on_symlink_wipes_the_target(tmp_path):
    # Долг №4: `rm -rf build` снимает ссылку, `rm -rf build/` стирает
    # содержимое того, на что она указывает, — а оно вне проекта.
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    cache = tmp_path / "outside-cache"
    cache.mkdir()
    (project_dir / "build").symlink_to(cache)
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "build/"], project_dir, project_dir
    ) is True
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "./build//"], project_dir, project_dir
    ) is True
    # Без слэша — по-прежнему только ссылка, файл проекта.
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "build"], project_dir, project_dir
    ) is False


def test_trailing_slash_on_a_real_folder_is_fine(tmp_path):
    project_dir = tmp_path / "proj"
    (project_dir / "dist").mkdir(parents=True)
    inner = project_dir / "cache"
    inner.mkdir()
    (project_dir / "link").symlink_to(inner)
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "dist/"], project_dir, project_dir
    ) is False
    # Ссылка на папку ВНУТРИ проекта: цель своя, блокировать нечего.
    assert bash_guard.wipes_outside_project(
        ["rm", "-rf", "link/"], project_dir, project_dir
    ) is False


def test_env_in_a_brand_new_folder_is_seen(project):
    # Долг №7: неотслеживаемую папку git сворачивает в одну строку
    # `?? api/`, и `.env` внутри неё не был виден вовсе.
    proj = project(git=True, commits=1)
    (proj / "api").mkdir()
    (proj / "api" / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (proj / "api" / "main.py").write_text("print(1)\n", encoding="utf-8")
    assert bash_guard.stages_env(["git", "add", "."], proj) is True
    assert bash_guard.stages_env(["git", "add", "-A"], proj) is True
    assert bash_guard.stages_env(["git", "add", "."], proj / "api") is True


# Долг №10: хук судит только то, что опознал наверняка. Ниже — сначала
# формы, которые он обязан узнавать, потом формы, которые обязан пропускать.


def denied(out):
    return bool(out) and (
        out.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    )


def test_trailing_comment_does_not_glue_the_next_line():
    # Комментарий съедал перевод строки, и следующая команда приклеивалась
    # к предыдущей аргументами: `echo hi rm -rf /` — уже не rm.
    assert bash_guard.simple_commands("echo hi # заметка\nrm -rf /") == [
        ["echo", "hi"], ["rm", "-rf", "/"],
    ]
    assert bash_guard.simple_commands("# уборка\nrm -rf /") == [
        ["rm", "-rf", "/"],
    ]


def test_comment_inside_heredoc_does_not_hide_the_terminator():
    commands = bash_guard.simple_commands(
        "cat > a.sh <<EOF\nmake # сборка\nEOF\nrm -rf /"
    )
    assert ["rm", "-rf", "/"] in commands


def test_capital_r_is_recursive_too(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    for flags in (["-Rf"], ["-fR"], ["-R", "-f"]):
        assert bash_guard.wipes_outside_project(
            ["rm"] + flags + [str(tmp_path / "other")], project_dir, project_dir
        ) is True, flags


def test_shell_keywords_do_not_hide_the_command(tmp_path):
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    other = str(tmp_path / "other")
    for line in (
        "if [ -d {0} ]; then rm -rf {0}; fi",
        "if false; then true; else rm -rf {0}; fi",
        "for i in 1 2; do rm -rf {0}; done",
        "{{ rm -rf {0}; }}",
        "! rm -rf {0}",
    ):
        hits = [
            bash_guard.wipes_outside_project(tokens, project_dir, project_dir)
            for tokens in bash_guard.simple_commands(line.format(other))
        ]
        assert any(hits), line


def test_wiping_everything_in_root_or_home_is_a_catastrophe(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    for target in ("/*", "~/*", "$HOME/*", "~/"):
        assert bash_guard.wipes_outside_project(
            ["rm", "-rf", target], tmp_path, None
        ) is True, target


def test_cd_into_the_project_then_rm_is_not_blocked(project, hook_state, tmp_path):
    # Сессия открыта этажом выше, Claude пишет `cd проект && rm -rf dist`:
    # относительный путь считается от папки после cd, а не от cwd сессии.
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    out = bash_guard.decide(payload(
        "cd {} && rm -rf dist node_modules".format(proj), tmp_path
    ))
    assert out is None
    out = bash_guard.decide(payload("cd proj1 && rm -rf dist", tmp_path))
    assert out is None
    from jedicoder import state as st
    assert st.load(path)["dark_side"] == 0


def test_cd_out_of_the_project_then_rm_is_blocked(project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert denied(bash_guard.decide(payload(
        "cd {} && rm -rf scratch".format(elsewhere), proj
    )))
    assert denied(bash_guard.decide(payload("cd .. ; rm -rf scratch", proj)))


def test_cd_in_a_subshell_does_not_leak(project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for line in (
        "(cd {} && ls); rm -rf dist",
        "echo $(cd {} && pwd) && rm -rf dist",
    ):
        assert bash_guard.decide(payload(line.format(elsewhere), proj)) is None, line


def test_unknown_folder_means_relative_paths_are_not_judged(
        project, hook_state, tmp_path, monkeypatch):
    monkeypatch.delenv("JC_NO_SUCH_VAR", raising=False)
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    hook_state(project={"path": str(proj)})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for line in (
        # Куда ушли — неизвестно: ни `rm -rf dist`, ни `git add .` не судим.
        'cd "$JC_NO_SUCH_VAR" && rm -rf dist',
        'cd "$JC_NO_SUCH_VAR" && git add .',
        "cd - && rm -rf dist",
        "pushd {0} && popd && rm -rf dist",
        "cd $(mktemp -d) && rm -rf dist",
        # Определение функции и case: cd внутри мог и не выполниться.
        "clean() {{ cd {0}; }}; rm -rf dist",
        "case x in a) cd {0};; esac; rm -rf dist",
    ):
        out = bash_guard.decide(payload(line.format(elsewhere), proj))
        assert out is None, line


def test_cd_that_may_not_have_happened_is_not_trusted(
        project, hook_state, tmp_path):
    # cd под условием: выполнился он или нет, хук не знает. Считать папку
    # известной — значит заблокировать уборку в собственном проекте.
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for line in (
        "cd nope || cd {0}; rm -rf dist",
        "test -d nope && cd {0}; rm -rf dist",
        "if false; then cd {0}; fi; rm -rf dist",
        "cd {0} & rm -rf dist",
        "cd {0} | cat; rm -rf dist",
    ):
        out = bash_guard.decide(payload(line.format(elsewhere), proj))
        assert out is None, line
    # Цепочка `&&` — не условие, а порядок: дошли до rm, значит cd был.
    assert denied(bash_guard.decide(payload(
        "test -d . && cd {} && rm -rf scratch".format(elsewhere), proj
    )))


def test_heredoc_dash_with_a_space_before_the_delimiter():
    commands = bash_guard.simple_commands(
        "cat <<- EOF\n\tпривет\n\tEOF\nrm -rf /"
    )
    assert ["rm", "-rf", "/"] in commands
    assert ["привет"] not in commands


def test_redirection_is_not_a_command_and_not_an_argument():
    # `2>/dev/null` лексер режет на `2`, `>` и путь: без этого цифра
    # становилась аргументом, а путь — отдельной «командой».
    assert bash_guard.simple_commands(
        "make > build.log 2>&1 && echo ok >> build.log"
    ) == [["make"], ["echo", "ok"]]
    assert bash_guard.simple_commands("rm -rf /important &> /dev/null") == [
        ["rm", "-rf", "/important"],
    ]


def test_redirection_does_not_hide_where_cd_went(project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    (proj / "sub").mkdir()
    hook_state(project={"path": str(proj)})
    assert denied(bash_guard.decide(payload(
        "cd sub 2>/dev/null && rm -rf ../../elsewhere", proj
    )))
    assert denied(bash_guard.decide(payload(
        "pushd sub >/dev/null; rm -rf ../../elsewhere", proj
    )))
    assert bash_guard.decide(payload(
        "cd sub 2>/dev/null && rm -rf ../dist", proj
    )) is None


def test_env_by_name_is_judged_even_when_the_folder_is_unknown(
        project, hook_state):
    # Частая запись агента: `cd "$(git rev-parse --show-toplevel)" && …`.
    # Куда ушли, хук не знает, но `.env` назван по имени — тогда судим по
    # папке сессии, как судили всегда.
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    hook_state(project={"path": str(proj)})
    for line in (
        'cd "$(git rev-parse --show-toplevel)" && git add .env',
        "cd - && git add -f .env",
    ):
        assert denied(bash_guard.decide(payload(line, proj))), line


def test_function_or_case_without_cd_does_not_switch_the_guard_off(
        project, hook_state, tmp_path):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    hook_state(project={"path": str(proj)})
    for line in (
        "greet() { echo hi; }; greet; git add .",
        "case $x in a) echo 1;; esac; git add .",
        "case $x in a) echo 1;; esac; rm -rf ../elsewhere",
    ):
        assert denied(bash_guard.decide(payload(line, proj))), line


def test_unknown_folder_does_not_unlock_absolute_paths(
        project, hook_state, tmp_path, monkeypatch):
    monkeypatch.delenv("JC_NO_SUCH_VAR", raising=False)
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert denied(bash_guard.decide(payload(
        'cd "$JC_NO_SUCH_VAR" && rm -rf {}'.format(elsewhere), proj
    )))
    assert denied(bash_guard.decide(payload("cd - && rm -rf /", proj)))


def test_path_with_an_unknown_value_is_not_judged(
        project, hook_state, tmp_path, monkeypatch):
    # Значения переменной или подстановки хук не знает: `$D/build` мог
    # оказаться где угодно, в том числе внутри проекта. Не знаем — пропуск.
    monkeypatch.delenv("JC_NO_SUCH_VAR", raising=False)
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    for line in (
        'rm -rf "$JC_NO_SUCH_VAR/build"',
        "rm -rf /tmp/$(whoami)/build",
        "rm -rf /tmp/`whoami`/build",
        "rm -rf ~jc_no_such_user/build",
    ):
        assert bash_guard.decide(payload(line, tmp_path)) is None, line


def test_known_variable_is_still_resolved(project, hook_state, tmp_path, monkeypatch):
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    monkeypatch.setenv("JC_KNOWN_DIR", str(tmp_path / "elsewhere"))
    assert denied(bash_guard.decide(payload('rm -rf "$JC_KNOWN_DIR/x"', proj)))


def test_pwd_is_the_tracked_folder_not_the_hooks_own(
        project, hook_state, tmp_path, monkeypatch):
    # `$PWD` в окружении хука — папка процесса хука, а не команды: брать
    # его оттуда нельзя ни в ту, ни в другую сторону.
    proj = project(git=True, commits=1)
    hook_state(project={"path": str(proj)})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("PWD", str(elsewhere))
    monkeypatch.setenv("OLDPWD", str(elsewhere))
    assert bash_guard.decide(payload('rm -rf "$PWD/dist"', proj)) is None
    assert bash_guard.decide(payload('rm -rf "${PWD}/dist"', proj)) is None
    assert bash_guard.decide(payload('rm -rf "$OLDPWD/dist"', proj)) is None
    monkeypatch.setenv("PWD", str(proj))
    assert denied(bash_guard.decide(payload(
        'cd {} && rm -rf "$PWD/scratch"'.format(elsewhere), proj
    )))


def test_cd_scopes_mass_add_to_the_new_folder(project, hook_state):
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (proj / "frontend").mkdir()
    (proj / "frontend" / "app.py").write_text("print(1)\n", encoding="utf-8")
    (proj / "api").mkdir()
    (proj / "api" / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    hook_state(project={"path": str(proj)})
    assert bash_guard.decide(payload("cd frontend && git add .", proj)) is None
    assert denied(bash_guard.decide(payload("cd api && git add .", proj)))


def test_adding_a_folder_by_name_is_a_mass_add(project):
    # `git add api` забирает папку целиком — тот же `git add .`, только
    # с именем.
    proj = project(git=True, commits=1)
    (proj / "api").mkdir()
    (proj / "api" / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    (proj / "web").mkdir()
    (proj / "web" / "index.html").write_text("<p>\n", encoding="utf-8")
    assert bash_guard.stages_env(["git", "add", "api"], proj) is True
    assert bash_guard.stages_env(["git", "add", "web", "api/"], proj) is True
    assert bash_guard.stages_env(["git", "add", "web"], proj) is False
    assert bash_guard.stages_env(["git", "add", "web/index.html"], proj) is False


def test_taking_env_out_of_git_is_not_blocked(project):
    # Падаван чинит утечку так, как велит сам хук: .env в .gitignore и
    # вон из индекса. `git add .` после этого отправляет УДАЛЕНИЕ .env —
    # блокировать лечение нельзя.
    proj = project(git=True, commits=1, commit_env=True)
    (proj / ".gitignore").write_text(".env\n", encoding="utf-8")
    _git(proj, "rm", "-q", "--cached", ".env")
    assert bash_guard.stages_env(["git", "add", "."], proj) is False
    assert bash_guard.stages_env(["git", "add", "-A"], proj) is False


def test_deleting_a_committed_env_is_not_blocked(project):
    proj = project(git=True, commits=1, commit_env=True)
    (proj / ".env").unlink()
    assert bash_guard.stages_env(["git", "add", "-A"], proj) is False


def test_hook_process_blocks_in_bypass_mode(project, tmp_path):
    """Режим без проверок: deny от хука — единственное, что стоит между
    командой и диском. Payload тот же, что шлёт Claude Code в этом режиме.
    """
    proj = project(git=True, commits=1)
    (proj / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    state_path = tmp_path / "hook-state.json"
    from jedicoder import state as st
    data = st.default_state("local-test")
    data["project"] = {"path": str(proj)}
    st.save(data, state_path)
    env = {"JEDICODER_STATE_PATH": str(state_path)}

    for command in ("git add .env", "rm -rf ../elsewhere"):
        done = run_hook("bash_guard.py", {
            "hook_event_name": "PreToolUse",
            "permission_mode": "bypassPermissions",
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(proj),
        }, env)
        assert done.returncode == 0, done.stderr
        assert denied(json.loads(done.stdout)), command

    saved = st.load(state_path)
    assert saved["dark_side"] == 3
    assert sorted(e["type"] for e in st.dark_side_entries(saved)) == [
        st.DARK_ENV_STAGED, st.DARK_ENV_STAGED, st.DARK_RM_OUTSIDE_PROJECT,
    ]


# --- Игровая сессия (#97) -----------------------------------------------------
#
# Плагин стоит на всей машине, и сторож видит каждую команду Bash — в том
# числе в проектах, где человек не играет. Там он не судит ничего и
# сохранение не трогает; блок остаётся один — катастрофа, без штрафа.

WORK = "S-work"


def untouched(path):
    return (path.stat().st_mtime_ns, path.read_bytes())


@pytest.mark.parametrize("command", [
    "git add .", "git add .env", "rm -rf ../elsewhere", "rm -rf /tmp/jc-elsewhere",
    "ssh root@example.test",
])
def test_a_foreign_session_is_not_judged_and_the_save_is_untouched(
        project, hook_state, command):
    proj = project(git=True, commits=1)
    other = project(git=True, commits=1)
    (other / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    path = hook_state(project={"path": str(proj)})
    before = untouched(path)

    assert bash_guard.decide(payload(command, other, session_id=WORK)) is None

    assert untouched(path) == before


@pytest.mark.parametrize("command", [
    "rm -rf /", "rm -rf ~", "rm -rf ~/*", "sudo rm -rf /", "ls && rm -rf $HOME",
])
def test_a_catastrophe_is_blocked_in_a_foreign_session_without_a_penalty(
        project, hook_state, command):
    proj = project(git=True, commits=1)
    other = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    before = untouched(path)

    out = bash_guard.decide(payload(command, other, session_id=WORK))

    assert denied(out), command
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert reason == bash_guard.RM_CATASTROPHE_REASON
    assert "папки проекта" not in reason, "вне игры папки проекта нет"
    # Ни слова «штраф», ни правила Кодекса: человек не играет.
    assert "systemMessage" not in out
    assert "Штраф" not in json.dumps(out, ensure_ascii=False)
    assert untouched(path) == before


def test_a_catastrophe_is_blocked_for_someone_who_never_played(tmp_path, monkeypatch):
    save = tmp_path / "jc" / "state.json"
    save.parent.mkdir()
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(save))

    assert denied(bash_guard.decide(payload("rm -rf /", tmp_path, session_id=WORK)))
    assert bash_guard.decide(
        payload("rm -rf ../elsewhere", tmp_path, session_id=WORK)
    ) is None
    assert list(save.parent.iterdir()) == [], "ни сохранения, ни замка"


def test_hook_process_blocks_a_catastrophe_in_a_foreign_session(
        project, tmp_path):
    proj = project(git=True, commits=1)
    state_path = tmp_path / "hook-state.json"
    from jedicoder import state as st
    data = st.default_state("local-test")
    data["project"] = {"path": str(proj)}
    st.save(data, state_path)
    before = untouched(state_path)

    done = run_hook("bash_guard.py", {
        "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "permission_mode": "bypassPermissions",
        "tool_input": {"command": "rm -rf ~"},
        "cwd": str(tmp_path), "session_id": WORK,
    }, {"JEDICODER_STATE_PATH": str(state_path)})

    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert denied(out) and "systemMessage" not in out
    assert untouched(state_path) == before


def test_a_session_without_an_id_outside_the_project_is_foreign(
        project, hook_state):
    proj = project(git=True, commits=1)
    other = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    request = payload("rm -rf ../elsewhere", other)
    del request["session_id"]

    assert bash_guard.decide(request) is None
    from jedicoder import state as st
    assert st.load(path)["dark_side"] == 0


@pytest.mark.parametrize("sign", ["голокрон", "папка проекта", "команда игры"])
def test_each_sign_of_a_game_session_brings_the_penalty_back(
        project, hook_state, monkeypatch, sign):
    proj = project(git=True, commits=1)
    other = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)}, game_sessions=[])
    cwd, session_id = other, WORK
    if sign == "голокрон":
        monkeypatch.setenv("JEDICODER_GOLOKRON", "1")
    elif sign == "папка проекта":
        cwd = proj
    else:
        from jedicoder import state as st
        data = st.load(path)
        data["game_sessions"] = [WORK]
        st.save(data, path)

    out = bash_guard.decide(
        payload("rm -rf {}".format(other / "scratch"), cwd, session_id=session_id)
    )

    assert denied(out)
    assert out["systemMessage"].startswith("Штраф: +1")
    from jedicoder import state as st
    assert st.load(path)["dark_side"] == 1


def test_a_catastrophe_in_a_game_session_still_costs_a_penalty(
        project, hook_state):
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    out = bash_guard.decide(payload("rm -rf /", proj))
    assert denied(out) and out["systemMessage"].startswith("Штраф: +1")
    from jedicoder import state as st
    assert st.load(path)["dark_side"] == 1


def test_a_broken_session_check_never_blocks_more_than_a_catastrophe(
        project, hook_state, monkeypatch):
    """Закон хуков: не смогли понять, игровая ли сессия, — она не игровая."""
    proj = project(git=True, commits=1)
    path = hook_state(project={"path": str(proj)})
    from jedicoder import game_session

    def boom(*args, **kwargs):
        raise RuntimeError("сломано")

    monkeypatch.setattr(game_session, "is_game", boom)
    before = untouched(path)
    assert bash_guard.decide(payload("rm -rf ../elsewhere", proj)) is None
    assert denied(bash_guard.decide(payload("rm -rf /", proj)))
    assert untouched(path) == before

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


def payload(command, cwd):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }


@pytest.fixture
def hook_state(tmp_path, monkeypatch):
    """Состояние падавана под хуком: путь через тот же env-шов, что у лута."""
    from jedicoder import state as st

    path = tmp_path / "state.json"

    def seed(**fields):
        data = st.default_state("local-test")
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
    assert "/magistr" in out["systemMessage"]


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
    # Матчер Bash обязателен: без него хук звался бы на каждый Read.
    for event in ("PreToolUse", "PostToolUse"):
        assert all(
            entry.get("matcher") == "Bash" for entry in events[event]
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

"""Проверки Акта 1 «Знакомство» на фикстурах.

Гоняются через quests.run_check — тем же путём, каким их запускает CLI.
На каждый квест три исхода: прошёл, не прошёл, не смог проверить. Третий
здесь не формальность: «не смог» не тратит попытку, и перепутать его с
провалом значит включить новичку протокол «ходит по кругу» за чужую вину.
"""
import os
import shutil

import pytest

from conftest import _git
from jedicoder import quests

SLUG = "act1-znakomstvo"

IDEA_OK = """# Идея

## Делаю сегодня
Страницу с расписанием кружка для родителей нашей группы.

## Не сегодня
Запись на занятия, оплата, личный кабинет.
"""


def check(quests_root, quest, project_dir, env=None, recorded=True):
    """Запустить проверку так, как её запускает CLI после `project path`.

    `recorded=False` — папка не названа: движок переменную не ставит вовсе.
    """
    extra = {}
    if recorded:
        # Папку назвал сам человек — так движок сообщает об этом проверке.
        extra = {"JEDICODER_PROJECT_PATH": str(project_dir),
                 "JEDICODER_PROJECT_NAMED": "yes"}
    extra.update(env or {})
    return quests.run_check(quests_root, SLUG, quest, project_dir, env_extra=extra)


def failed(result):
    return [item["id"] for item in quests.failed_checks(result)]


def saved_project(project, files=None, gitignore=".env\n"):
    return project(files=files or {"index.html": "<h1>Расписание</h1>\n"},
                   gitignore=gitignore, git=True, commits=1)


# --- 01-folder ---

def test_folder_passes_on_own_folder(quests_root, project):
    result = check(quests_root, "01-folder", project())
    assert result.ok is True, quests.failed_checks(result)


def test_folder_fails_when_path_not_recorded(quests_root, project):
    result = check(quests_root, "01-folder", project(), recorded=False)
    assert result.exit_code == quests.EXIT_FAIL
    assert "path_recorded" in failed(result)


def test_folder_fails_when_only_the_app_recorded_it(quests_root, project):
    """Папку записало приложение на старте сессии — человек её не называл."""
    proj = project()
    result = quests.run_check(
        quests_root, SLUG, "01-folder", proj,
        env_extra={"JEDICODER_PROJECT_PATH": str(proj)},
    )
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result) == ["path_named"]


def test_folder_fails_when_folder_is_gone(quests_root, project, tmp_path):
    result = check(
        quests_root, "01-folder", project(),
        env={"JEDICODER_PROJECT_PATH": str(tmp_path / "нет-такой")},
    )
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result) == ["folder_exists"]


def test_folder_rejects_disk_root(quests_root, project):
    result = check(
        quests_root, "01-folder", project(), env={"JEDICODER_PROJECT_PATH": "/"}
    )
    assert result.exit_code == quests.EXIT_FAIL
    assert "not_root" in failed(result)


def test_folder_rejects_home(quests_root, project):
    proj = project()
    result = check(quests_root, "01-folder", proj, env={"HOME": str(proj)})
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result) == ["not_home"]


def test_folder_rejects_home_behind_a_symlink(quests_root, project, tmp_path):
    """Домашняя папка, названная обходным путём, остаётся домашней."""
    proj = project()
    link = tmp_path / "ярлык"
    link.symlink_to(proj, target_is_directory=True)
    result = check(
        quests_root, "01-folder", proj,
        env={"HOME": str(proj), "JEDICODER_PROJECT_PATH": str(link)},
    )
    assert failed(result) == ["not_home"]


def test_folder_rejects_parent_of_home(quests_root, project):
    """Папка, внутри которой лежит домашняя, — та же свалка, только шире."""
    proj = project()
    home = proj / "user"
    home.mkdir()
    result = check(quests_root, "01-folder", proj, env={"HOME": str(home)})
    assert failed(result) == ["not_home"]


def test_folder_accepts_folder_inside_home(quests_root, project):
    proj = project()
    result = check(quests_root, "01-folder", proj, env={"HOME": str(proj.parent)})
    assert result.ok is True, quests.failed_checks(result)


def test_folder_bails_without_home(quests_root, project):
    result = check(quests_root, "01-folder", project(), env={"HOME": ""})
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False
    assert result.stderr


# --- 02-idea ---

def test_idea_passes(quests_root, project):
    result = check(quests_root, "02-idea", project(files={"IDEA.md": IDEA_OK}))
    assert result.ok is True, quests.failed_checks(result)


def test_idea_fails_without_file(quests_root, project):
    result = check(quests_root, "02-idea", project())
    assert result.exit_code == quests.EXIT_FAIL
    assert "idea_exists" in failed(result)


def test_idea_fails_when_nothing_is_cut(quests_root, project):
    """«Не сегодня» с пустым телом: человек ничего не отложил."""
    text = "## Делаю сегодня\nСтраницу с расписанием кружка.\n\n## Не сегодня\n\n"
    result = check(quests_root, "02-idea", project(files={"IDEA.md": text}))
    assert failed(result) == ["idea_not_today"]


def test_idea_stub_in_not_today_is_empty(quests_root, project):
    text = "## Делаю сегодня\nСтраницу с расписанием кружка.\n\n## Не сегодня\nTODO\n"
    result = check(quests_root, "02-idea", project(files={"IDEA.md": text}))
    assert failed(result) == ["idea_not_today"]


@pytest.mark.parametrize("marker", ["*", "+", "-"])
def test_idea_bare_list_marker_is_empty(quests_root, project, marker):
    """Пустой пункт списка — не отложенное дело."""
    text = "## Делаю сегодня\nСтраницу с расписанием кружка.\n\n## Не сегодня\n{}\n"
    result = check(
        quests_root, "02-idea", project(files={"IDEA.md": text.format(marker)})
    )
    assert failed(result) == ["idea_not_today"]


def test_idea_one_cut_item_is_enough(quests_root, project):
    text = "## Делаю сегодня\nСтраницу с расписанием кружка.\n\n## Не сегодня\nОплата\n"
    result = check(quests_root, "02-idea", project(files={"IDEA.md": text}))
    assert result.ok is True, quests.failed_checks(result)


def test_idea_fails_without_today_section(quests_root, project):
    text = "# Идея\n\nСтраница с расписанием.\n\n## Не сегодня\nОплата и запись.\n"
    result = check(quests_root, "02-idea", project(files={"IDEA.md": text}))
    assert failed(result) == ["idea_today"]


def test_idea_today_section_does_not_borrow_from_not_today(quests_root, project):
    """«Не сегодня» не засчитывается за «Делаю сегодня» по хвосту заголовка."""
    text = "## Не сегодня\nОплата, запись и личный кабинет.\n"
    result = check(quests_root, "02-idea", project(files={"IDEA.md": text}))
    assert failed(result) == ["idea_today"]


def test_idea_accepts_lowercase_headings(quests_root, project):
    text = "## делаю сегодня\nСтраницу с расписанием кружка.\n\n## не сегодня\nОплата\n"
    result = check(quests_root, "02-idea", project(files={"IDEA.md": text}))
    assert result.ok is True, quests.failed_checks(result)


def test_idea_in_subfolder_does_not_count(quests_root, project):
    result = check(
        quests_root, "02-idea", project(files={"research/IDEA.md": IDEA_OK})
    )
    assert "idea_exists" in failed(result)


def test_idea_bails_when_folder_not_recorded(quests_root, project):
    result = check(
        quests_root, "02-idea", project(files={"IDEA.md": IDEA_OK}), recorded=False
    )
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False
    # Квест назван так, как его зовёт человек: эту строку игра печатает ему.
    assert "квест «Папка»" in result.stderr and "01-folder" not in result.stderr


# --- 03-first-request ---

def test_first_request_passes_with_a_code_file(quests_root, project):
    proj = project(files={"IDEA.md": IDEA_OK, "index.html": "<h1>Привет</h1>\n"})
    result = check(quests_root, "03-first-request", proj)
    assert result.ok is True, quests.failed_checks(result)


def test_first_request_passes_with_code_in_subfolder(quests_root, project):
    proj = project(files={"src/app.py": "print('привет')\n"})
    assert check(quests_root, "03-first-request", proj).ok is True


def test_first_request_fails_on_empty_folder(quests_root, project):
    result = check(quests_root, "03-first-request", project())
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result) == ["has_code"]


@pytest.mark.parametrize("files", [
    {"IDEA.md": IDEA_OK, "notes.txt": "мысли вслух\n"},
    {"IDEA.md": IDEA_OK, "docs/jedicoder/README.md": "памятка\n"},
    {".gitignore": ".env\n", ".env": "TOKEN=1\n"},
    {".claude/settings.json": "{}\n", "CLAUDE.md": "# Проект\n"},
    {"README.MD": "# Проект\n", "LICENSE": "MIT\n"},
    # Windows кладёт их в папку сама, а картинка — не код (ревью 2026-10-08).
    {"IDEA.md": IDEA_OK, "desktop.ini": "[.ShellClassInfo]\n", "Thumbs.db": "x"},
    {"IDEA.md": IDEA_OK, "photo.PNG": "x", "scan.pdf": "x", "logo.jpeg": "x"},
    {"index.html": ""},
])
def test_first_request_notes_and_service_files_are_not_code(
        quests_root, project, files):
    result = check(quests_root, "03-first-request", project(files=files))
    assert failed(result) == ["has_code"]


def test_first_request_ignores_git_internals(quests_root, project):
    """Служебная папка git полна файлов без расширения — это не код падавана."""
    proj = project(files={"IDEA.md": IDEA_OK}, git=True, commits=0)
    assert failed(check(quests_root, "03-first-request", proj)) == ["has_code"]


def test_first_request_bails_when_folder_not_recorded(quests_root, project):
    proj = project(files={"index.html": "<h1>Привет</h1>\n"})
    result = check(quests_root, "03-first-request", proj, recorded=False)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False


# --- 04-save ---

def test_save_passes(quests_root, project):
    result = check(quests_root, "04-save", saved_project(project))
    assert result.ok is True, quests.failed_checks(result)


def test_save_fails_without_repository(quests_root, project):
    proj = project(files={"index.html": "<h1>Привет</h1>\n"}, gitignore=".env\n")
    result = check(quests_root, "04-save", proj)
    assert result.exit_code == quests.EXIT_FAIL
    assert "repo_exists" in failed(result)
    assert "has_commit" in failed(result)


def test_save_fails_without_commit(quests_root, project):
    proj = project(files={"index.html": "<h1>Привет</h1>\n"}, gitignore=".env\n",
                   git=True, commits=0)
    assert failed(check(quests_root, "04-save", proj)) == ["has_commit"]


def test_save_fails_when_env_not_ignored(quests_root, project):
    proj = saved_project(project, gitignore="node_modules\n")
    assert failed(check(quests_root, "04-save", proj)) == ["env_ignored"]


def test_save_fails_when_env_is_in_a_save(quests_root, project):
    proj = project(files={"index.html": "<h1>Привет</h1>\n"}, gitignore=".env\n",
                   git=True, commits=1, commit_env=True)
    assert "env_not_tracked" in failed(check(quests_root, "04-save", proj))


def test_save_fails_on_key_in_history(quests_root, project):
    proj = project(files={"index.html": "<h1>Привет</h1>\n"}, gitignore=".env\n",
                   git=True, commits=1, leak_token=True)
    assert failed(check(quests_root, "04-save", proj)) == ["no_secrets_in_history"]


def test_save_does_not_judge_an_outer_repository(quests_root, project):
    """Папка проекта внутри чужого репозитория: своего `.git` нет, и чужая
    история с чужим ключом — не «твой ключ попал в сохранение»."""
    outer = project(files={"index.html": "<h1>Привет</h1>\n"}, gitignore=".env\n",
                    git=True, commits=1, leak_token=True)
    inner = outer / "zateya"
    inner.mkdir()
    (inner / "app.py").write_text("print(1)\n", encoding="utf-8")
    result = check(quests_root, "04-save", inner)
    # Строки-сторожа без своего репозитория молчат все три: сохранять
    # некуда — и настраивать нечего (#87).
    assert failed(result) == ["repo_exists", "has_commit"]


def test_save_guards_are_quiet_and_the_persons_steps_are_not(quests_root, project):
    """Сторожа `.env` и ключей судят молча: человеку их показывают, только
    когда они не сошлись."""
    result = check(quests_root, "04-save", saved_project(project))
    quiet = {row["id"] for row in result.checks if row.get("quiet") is True}
    assert quiet == {"env_ignored", "env_not_tracked", "no_secrets_in_history"}
    loud = [row["id"] for row in result.checks if "quiet" not in row]
    assert loud == ["repo_exists", "has_commit"]


def test_save_bails_without_git(quests_root, project, tmp_path):
    """Нет git на машине — это не провал падавана, попытка не тратится."""
    proj = saved_project(project)
    bin_dir = tmp_path / "nogit"
    bin_dir.mkdir()
    for tool in ("bash", "locale", "grep", "head", "dirname", "env"):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    result = check(quests_root, "04-save", proj, env={"PATH": str(bin_dir)})
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "git" in result.stderr


def test_save_bails_when_folder_not_recorded(quests_root, project):
    result = check(quests_root, "04-save", saved_project(project), recorded=False)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False


# --- общий контракт ---

def _passing_project(project):
    proj = project(
        files={"IDEA.md": IDEA_OK, "index.html": "<h1>Расписание</h1>\n"},
        gitignore=".env\n", git=True, commits=1,
    )
    return proj


SCRIPTED = ("01-folder", "02-idea", "03-first-request", "04-save")


def test_act1_checks_survive_hostile_locale(quests_root, project):
    """Заголовки IDEA.md кириллицей обязаны находиться и при LC_ALL=C."""
    proj = _passing_project(project)
    for quest_id in SCRIPTED:
        result = check(quests_root, quest_id, proj, env={"LC_ALL": "C"})
        assert result.ok is True, (quest_id, quests.failed_checks(result))


def test_act1_checks_survive_mawk(quests_root, project):
    """mawk — awk по умолчанию в WSL Ubuntu; суит на gawk его болезней не видит."""
    if shutil.which("mawk") is None:
        pytest.skip("mawk недоступен")
    proj = _passing_project(project)
    bin_dir = proj.parent / "mawkbin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "awk"
    stub.write_text('#!/bin/sh\nexec mawk "$@"\n', encoding="utf-8")
    stub.chmod(0o755)
    env = {"PATH": "{}:{}".format(bin_dir, os.environ["PATH"]), "LC_ALL": "C"}
    for quest_id in SCRIPTED:
        result = check(quests_root, quest_id, proj, env=env)
        assert result.ok is True, (quest_id, quests.failed_checks(result))
    stubs = "## Делаю сегодня\nTODO\n\n## Не сегодня\n\n"
    (proj / "IDEA.md").write_text(stubs, encoding="utf-8")
    assert failed(check(quests_root, "02-idea", proj, env=env)) == [
        "idea_today", "idea_not_today",
    ]


def _snapshot(root):
    seen = {}
    for folder, _, names in os.walk(str(root)):
        for name in names:
            path = os.path.join(folder, name)
            with open(path, "rb") as handle:
                seen[os.path.relpath(path, str(root))] = handle.read()
    return seen


def test_every_check_is_read_only(quests_root, project):
    """check.sh никогда не мутирует проект падавана — ни файлы, ни git."""
    proj = _passing_project(project)
    (proj / "черновик.txt").write_text("не сохранён\n", encoding="utf-8")
    before = _snapshot(proj)
    for quest_id in SCRIPTED:
        check(quests_root, quest_id, proj)
    assert _snapshot(proj) == before


def test_checks_print_only_json_on_stdout(quests_root, project):
    """Провал и проход печатают в stdout один объект JSON и ничего больше."""
    import json
    import subprocess

    for proj in (_passing_project(project), project()):
        for quest_id in SCRIPTED:
            script = quests.script_path(quests_root, SLUG, quest_id)
            done = subprocess.run(
                ["bash", str(script)], cwd=str(proj), capture_output=True,
                text=True, env=dict(os.environ, JEDICODER_PROJECT_PATH=str(proj)),
            )
            assert done.returncode in (0, 1), (quest_id, done.stderr)
            payload = json.loads(done.stdout)
            assert payload["quest"] == "act1/" + quest_id
            assert payload["ok"] is (done.returncode == 0)


def test_save_check_git_stays_untouched(quests_root, project):
    """Проверка сохранения сама ничего не сохраняет и в индекс не кладёт."""
    proj = saved_project(project)
    (proj / "new.py").write_text("x = 1\n", encoding="utf-8")
    check(quests_root, "04-save", proj)
    import subprocess
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(proj),
        capture_output=True, text=True,
    ).stdout
    assert status.strip() == "?? new.py"
    _git(proj, "rev-parse", "HEAD")

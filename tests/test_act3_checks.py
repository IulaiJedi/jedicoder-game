"""Проверки Акта 3 «Умения» на фикстурах.

Гоняются через quests.run_check — тем же путём, каким их запускает CLI.
На каждый квест три исхода: прошёл, не прошёл, не смог проверить.

Проверок у акта две — «Свой скилл» и «Хук»; «Скилл», «Где брать» и «Мод»
закрывает рассказ (решение оператора 2026-10-14, #116: в игре из интернета
ничего не ставится). Обе судят не только папку проекта, но и машину игрока:
личные скиллы и настройки Claude Code лежат в домашней папке. Домашнюю папку
проверка берёт из `HOME`, и здесь `HOME` — всегда песочная папка теста:
настоящий `~/.claude` суит не читает (сторож — фикстура `home` ниже и тест
`test_checks_never_look_into_the_real_home`).

Файлы кладутся так, как их кладёт Claude в живой сессии — замеры в
`docs/research/2026-10-13-act3-skills-hooks-mods.md`, раздел «Замеры #110».
Проверки прежнего Акта 3 «Первая кровь» — в tests/test_shelf_act3_checks.py.
"""
import json
import os
import shutil
import time
from pathlib import Path

import pytest

from jedicoder import quests

SLUG = "act3-umeniya"
SCRIPTED = ("03-own-skill", "04-hook")

SKILL_MD = "---\nname: {0}\ndescription: Скилл {0}.\n---\n\nДелай так.\n"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: пустая, как у человека до установок.

    Достаётся каждому тесту файла, просил он её или нет: тест, забывший о
    ней, иначе читал бы настоящую домашнюю папку хозяина машины.
    """
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


def personal_skill(home, name, text=None):
    """Личный скилл: `~/.claude/skills/<имя>/SKILL.md`."""
    folder = home / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        SKILL_MD.format(name) if text is None else text, encoding="utf-8"
    )
    return folder


def project_skill(proj, name, text=None):
    """Проектный скилл: `<папка проекта>/.claude/skills/<имя>/SKILL.md`."""
    folder = Path(proj) / ".claude" / "skills" / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        SKILL_MD.format(name) if text is None else text, encoding="utf-8"
    )
    return folder


def started(delta=-3600):
    """Момент входа в акт, как его передаёт команда игры: секунды эпохи."""
    return {"JEDICODER_ACT_STARTED": str(int(time.time()) + delta)}


def check(quests_root, quest, project_dir, env=None, recorded=True):
    extra = {}
    if recorded:
        extra = {"JEDICODER_PROJECT_PATH": str(project_dir)}
    extra.update(env or {})
    return quests.run_check(quests_root, SLUG, quest, project_dir, env_extra=extra)


def failed(result):
    return [item["id"] for item in quests.failed_checks(result)]


# --- 03-own-skill: свой скилл с описанием и правилом ---

#: Свой скилл, как его написал Claude в замере (ж).
OWN_SKILL = (
    "---\n"
    "name: otchet-o-pravke\n"
    "description: Отчёт после правки страницы. Используй после каждой правки.\n"
    "---\n"
    "\n"
    "# Отчёт после правки страницы\n"
    "\n"
    "После каждой правки скажи одной фразой, что изменилось на вид.\n"
)


def test_own_skill_passes_as_claude_writes_it(quests_root, home, project):
    proj = project()
    project_skill(proj, "otchet-o-pravke", OWN_SKILL)
    result = check(quests_root, "03-own-skill", proj, env=started())
    assert result.ok is True, quests.failed_checks(result)


def test_own_skill_fails_on_a_clean_project_with_all_rows(quests_root, home, project):
    result = check(quests_root, "03-own-skill", project(), env=started())
    assert result.exit_code == quests.EXIT_FAIL and result.countable is True
    # Скилла нет — строка одна: дописывать описание пока не у чего.
    assert failed(result) == ["own_skill_exists"]
    assert [row["id"] for row in result.checks] == ["own_skill_exists"]
    assert "Сделай из этого правила скилл" in quests.failed_checks(result)[0]["hint"]


def test_ready_made_skills_are_not_ones_own(quests_root, home, project):
    """Готовые скиллы, которые игра называет примерами в квесте «Где брать»,
    квест «Свой скилл» не закрывают, даже если человек поставил их сам."""
    proj = project()
    project_skill(proj, "impeccable")
    project_skill(proj, "sdd")
    personal_skill(home, "sdd")
    personal_skill(home, "impeccable")
    result = check(quests_root, "03-own-skill", proj, env=started())
    assert failed(result)[0] == "own_skill_exists"


@pytest.mark.parametrize("text,rows", [
    # Блока `---` нет вовсе: просто текст.
    ("Делай так.\n", ["own_skill_described", "own_skill_written"]),
    # Блок есть, описания нет.
    ("---\nname: moi\n---\n\nДелай так.\n",
     ["own_skill_described", "own_skill_written"]),
    ("---\nname: moi\ndescription:\n---\n\nДелай так.\n",
     ["own_skill_described", "own_skill_written"]),
    # Блок не закрыт.
    ("---\nname: moi\ndescription: Моё правило.\n\nДелай так.\n",
     ["own_skill_described", "own_skill_written"]),
    # Описание есть, под ним пусто или один заголовок.
    ("---\nname: moi\ndescription: Моё правило.\n---\n", ["own_skill_written"]),
    ("---\nname: moi\ndescription: Моё правило.\n---\n\n# Правило\n\n",
     ["own_skill_written"]),
])
def test_own_skill_names_what_is_missing(quests_root, home, project, text, rows):
    proj = project()
    project_skill(proj, "moi", text)
    result = check(quests_root, "03-own-skill", proj, env=started())
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result) == rows


@pytest.mark.parametrize("text", [
    "---\nname: moi\ndescription: >\n  Моё правило работы.\n---\n\nДелай так.\n",
    "---\ndescription: |-\n  Моё правило работы.\nname: moi\n---\nДелай так.\n",
    '---\nname: moi\ndescription: "Моё: правило"\n---\nДелай так.\n',
    "﻿---\r\nname: moi\r\ndescription: Моё правило.\r\n---\r\nДелай так.\r\n",
])
def test_own_skill_reads_descriptions_as_claude_may_write_them(
        quests_root, home, project, text):
    proj = project()
    project_skill(proj, "moi", text)
    result = check(quests_root, "03-own-skill", proj, env=started())
    assert result.ok is True, quests.failed_checks(result)


def test_the_best_of_several_own_skills_is_judged(quests_root, home, project):
    proj = project()
    project_skill(proj, "a-chernovik", "черновик\n")
    project_skill(proj, "moi", OWN_SKILL)
    assert check(quests_root, "03-own-skill", proj, env=started()).ok is True


def test_personal_skill_made_in_this_act_counts(quests_root, home, project):
    """Claude положил скилл «для всех проектов» — тоже свой, если он новый."""
    personal_skill(home, "moi", OWN_SKILL)
    result = check(quests_root, "03-own-skill", project(), env=started())
    assert result.ok is True, quests.failed_checks(result)


def test_personal_skill_older_than_the_act_does_not_count(quests_root, home, project):
    """Скилл, стоявший до игры, квест не закрывает."""
    folder = personal_skill(home, "davno-stoit", OWN_SKILL)
    long_ago = time.time() - 86400
    os.utime(str(folder / "SKILL.md"), (long_ago, long_ago))
    result = check(quests_root, "03-own-skill", project(), env=started())
    assert failed(result)[0] == "own_skill_exists"


@pytest.mark.parametrize("value", [None, "", "вчера"])
def test_without_the_entry_moment_only_the_project_folder_is_judged(
        quests_root, home, project, value):
    personal_skill(home, "moi", OWN_SKILL)
    proj = project()
    env = {} if value is None else {"JEDICODER_ACT_STARTED": value}
    assert failed(check(quests_root, "03-own-skill", proj, env=env))[0] == \
        "own_skill_exists"
    project_skill(proj, "moi", OWN_SKILL)
    assert check(quests_root, "03-own-skill", proj, env=env).ok is True


def test_skills_synced_with_the_account_are_not_ones_own(quests_root, home, project):
    """Скиллы учётной записи лежат глубже: `~/.claude/skills/synced/<id>/…`."""
    deep = home / ".claude" / "skills" / "synced" / "e6635ee3" / "docx"
    deep.mkdir(parents=True)
    (deep / "SKILL.md").write_text(OWN_SKILL, encoding="utf-8")
    result = check(quests_root, "03-own-skill", project(), env=started())
    assert failed(result)[0] == "own_skill_exists"


@pytest.mark.skipif(os.geteuid() == 0, reason="root читает всё")
def test_own_skill_bails_when_the_skills_folder_is_closed(quests_root, home, project):
    proj = project()
    folder = project_skill(proj, "moi", OWN_SKILL)
    folder.parent.chmod(0o000)
    try:
        result = check(quests_root, "03-own-skill", proj, env=started())
    finally:
        folder.parent.chmod(0o755)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False
    assert "папку со скиллами" in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root читает всё")
@pytest.mark.parametrize("quest_id", ["03-own-skill", "04-hook"])
def test_new_checks_bail_when_the_settings_folder_is_closed(
        quests_root, home, project, quest_id):
    """Закрытая `.claude` — не «ничего нет»: попытка человеку не в счёт."""
    proj = project()
    project_skill(proj, "moi", OWN_SKILL)
    hook_settings(proj)
    (proj / ".claude").chmod(0o000)
    try:
        result = check(quests_root, quest_id, proj, env=started())
    finally:
        (proj / ".claude").chmod(0o755)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False


def test_own_skill_names_one_reason_when_python_is_missing(
        quests_root, home, project, tmp_path):
    """Причина «не смог проверить» одна — та, что назвала первой."""
    proj = project()
    bin_dir = tmp_path / "bez-python"
    bin_dir.mkdir()
    for tool in ("bash", "dirname", "locale", "grep", "head"):
        found = shutil.which(tool)
        if found:
            (bin_dir / tool).symlink_to(found)
    result = check(quests_root, "03-own-skill", proj,
                   env=dict(started(), PATH=str(bin_dir)))
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "не найден python3" in result.stderr
    assert "папку со скиллами" not in result.stderr


# --- 04-hook: хук на запрос, слово и передача после него ---

def hook_settings(root, event="UserPromptSubmit", name="settings.json", raw=None):
    """Настройки с хуком — как их пишет Claude (замер (з))."""
    path = Path(root) / ".claude" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is None:
        raw = json.dumps({"hooks": {event: [{"hooks": [{
            "type": "command",
            "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/chistka.sh"',
        }]}]}})
    path.write_text(raw, encoding="utf-8")
    return path


def word(at=None):
    """След слова, как его отдаёт команда игры; момент — секунды эпохи."""
    moment = int(time.time()) - 60 if at is None else at
    return {"JEDICODER_TRACE_HOOK_WORD": "yes",
            "JEDICODER_TRACE_HOOK_WORD_AT": str(moment)}


def handoff(proj, age=0):
    path = Path(proj) / "HANDOFF.md"
    path.write_text("# Передача\n", encoding="utf-8")
    moment = time.time() - age
    os.utime(str(path), (moment, moment))
    return path


def test_hook_passes_with_project_settings_word_and_fresh_handoff(
        quests_root, home, project):
    proj = project()
    hook_settings(proj)
    handoff(proj)
    result = check(quests_root, "04-hook", proj, env=word())
    assert result.ok is True, quests.failed_checks(result)


@pytest.mark.parametrize("name", ["settings.json", "settings.local.json"])
def test_hook_may_live_in_either_project_file(quests_root, home, project, name):
    proj = project()
    hook_settings(proj, name=name)
    handoff(proj)
    assert check(quests_root, "04-hook", proj, env=word()).ok is True


def test_hook_may_live_in_the_user_settings(quests_root, home, project):
    proj = project()
    hook_settings(home)
    handoff(proj)
    assert check(quests_root, "04-hook", proj, env=word()).ok is True


def test_hook_fails_on_a_clean_machine_with_all_rows(quests_root, home, project):
    result = check(quests_root, "04-hook", project())
    assert result.exit_code == quests.EXIT_FAIL and result.countable is True
    # Строка одна: пока хука нет, говорить о слове рано.
    assert [row["id"] for row in result.checks] == ["hook_recorded"]
    hint = quests.failed_checks(result)[0]["hint"]
    assert "Сделай хук" in hint and "/clear" in hint


def test_hook_recorded_but_word_not_said_names_the_word(quests_root, home, project):
    proj = project()
    hook_settings(proj)
    handoff(proj)
    result = check(quests_root, "04-hook", proj)
    assert [row["id"] for row in result.checks] == ["hook_recorded", "word_said"]
    assert failed(result) == ["word_said"]
    assert "«чистка»" in quests.failed_checks(result)[0]["hint"]


@pytest.mark.parametrize("event", ["Stop", "PreToolUse", "PreCompact", "SessionStart"])
def test_hooks_on_other_events_are_not_the_hook_of_the_quest(
        quests_root, home, project, event):
    """У автора игры и у набора SDD свои хуки — на других событиях."""
    proj = project()
    hook_settings(home, event=event)
    hook_settings(proj, event=event)
    result = check(quests_root, "04-hook", proj, env=word())
    assert failed(result)[0] == "hook_recorded"


@pytest.mark.parametrize("raw", [
    "{}", '{"hooks": {}}', '{"hooks": {"UserPromptSubmit": []}}',
    '{"hooks": {"UserPromptSubmit": [{"hooks": []}]}}',
    '{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": " "}]}]}}',
    '{"hooks": {"UserPromptSubmit": "строка"}}', '{"hooks": []}',
    '{"permissions": {"allow": []}}',
])
def test_settings_without_a_prompt_hook_are_a_plain_failure(
        quests_root, home, project, raw):
    proj = project()
    hook_settings(proj, raw=raw)
    result = check(quests_root, "04-hook", proj, env=word())
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result)[0] == "hook_recorded"


@pytest.mark.parametrize("raw", ["{ не json", "[]", '"строка"', ""])
def test_hook_bails_on_broken_settings(quests_root, home, project, raw):
    proj = project()
    hook_settings(proj, raw=raw)
    result = check(quests_root, "04-hook", proj, env=word())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False
    assert "настройки Claude Code" in result.stderr


def test_hook_needs_the_trace_exactly_yes(quests_root, home, project):
    proj = project()
    hook_settings(proj)
    handoff(proj)
    for value in ("", "да", "YES", "1"):
        env = dict(word(), JEDICODER_TRACE_HOOK_WORD=value)
        assert failed(check(quests_root, "04-hook", proj, env=env)) == [
            "word_said",
        ], value


def test_handoff_older_than_the_word_means_the_hook_did_not_work(
        quests_root, home, project):
    proj = project()
    hook_settings(proj)
    handoff(proj, age=3600)
    result = check(quests_root, "04-hook", proj, env=word())
    assert failed(result) == ["handoff_after_word"]
    assert quests.failed_checks(result)[0]["hint"].startswith(
        "Слово сказано, а передачи после него нет."
    )


def test_no_handoff_at_all_is_a_plain_failure(quests_root, home, project):
    proj = project()
    hook_settings(proj)
    assert failed(check(quests_root, "04-hook", proj, env=word())) == [
        "handoff_after_word",
    ]


@pytest.mark.parametrize("at", [None, "", "вчера", "-5", "1.5"])
def test_word_without_a_readable_moment_does_not_pass(
        quests_root, home, project, at):
    proj = project()
    hook_settings(proj)
    handoff(proj)
    env = {"JEDICODER_TRACE_HOOK_WORD": "yes"}
    if at is not None:
        env["JEDICODER_TRACE_HOOK_WORD_AT"] = at
    assert failed(check(quests_root, "04-hook", proj, env=env)) == [
        "handoff_after_word",
    ]


@pytest.mark.parametrize("quest_id", ["03-own-skill", "04-hook"])
def test_new_checks_bail_when_folder_not_recorded(quests_root, home, project, quest_id):
    result = check(quests_root, quest_id, project(), env=started(), recorded=False)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "папка проекта не названа" in result.stderr


@pytest.mark.parametrize("quest_id", ["03-own-skill", "04-hook"])
def test_new_checks_bail_without_a_home_folder(quests_root, home, project, quest_id):
    result = check(quests_root, quest_id, project(),
                   env=dict(started(), HOME=str(home / "нет такой")))
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "домашнюю папку" in result.stderr


def test_new_checks_survive_c_locale_and_mawk(quests_root, home, project):
    proj = project()
    project_skill(proj, "moi", OWN_SKILL)
    hook_settings(proj)
    handoff(proj)
    env = dict(started(), LC_ALL="C", **word())
    if shutil.which("mawk") is not None:
        bin_dir = proj.parent / "mawkbin2"
        bin_dir.mkdir()
        stub = bin_dir / "awk"
        stub.write_text('#!/bin/sh\nexec mawk "$@"\n', encoding="utf-8")
        stub.chmod(0o755)
        env["PATH"] = "{}:{}".format(bin_dir, os.environ["PATH"])
    for quest_id in ("03-own-skill", "04-hook"):
        result = check(quests_root, quest_id, proj, env=env)
        assert result.ok is True, (quest_id, quests.failed_checks(result))


def test_the_names_of_ready_skills_live_in_one_place():
    """Перечень готовых скиллов один — в `_lib/machine.sh`."""
    root = Path(__file__).resolve().parents[1] / "plugin"
    text = (root / "quests" / "_lib" / "machine.sh").read_text(encoding="utf-8")
    assert 'JC_KNOWN_SKILLS="impeccable sdd"' in text
    own = (root / "quests" / SLUG / "03-own-skill" / "check.sh").read_text(
        encoding="utf-8")
    code = "\n".join(
        line for line in own.splitlines() if not line.lstrip().startswith("#")
    )
    assert "impeccable" not in code and "sdd" not in code
    machine = (root / "lib" / "jedicoder" / "machine.py").read_text(encoding="utf-8")
    assert '"impeccable"' not in machine and '"sdd"' not in machine


# --- то, что обязано держаться у всех ---

def _everything(home, proj):
    project_skill(proj, "moi", OWN_SKILL)
    hook_settings(proj)
    handoff(proj)


def test_no_check_of_act3_waits_for_skills_from_the_internet():
    """Решение 2026-10-14 (#116): в игре из сети ничего не ставится.

    Проверок квестов «Скилл» и «Где брать» нет вовсе, и ни одна проверка
    акта не читает список плагинов Claude Code и не ищет готовых скиллов.
    """
    root = Path(__file__).resolve().parents[1] / "plugin" / "quests"
    on_disk = sorted(path.name for path in (root / SLUG).iterdir() if path.is_dir())
    assert on_disk == list(SCRIPTED)
    texts = [(root / "_lib" / "machine.sh").read_text(encoding="utf-8")]
    texts += [
        (root / SLUG / quest_id / "check.sh").read_text(encoding="utf-8")
        for quest_id in SCRIPTED
    ]
    for text in texts:
        assert ".claude/plugins" not in text and "installed_plugins" not in text
        assert "jc_skill_installed" not in text


def _snapshot(root):
    out = {}
    for path in sorted(Path(root).rglob("*")):
        if ".git" in path.parts:
            continue
        out[str(path.relative_to(root))] = (
            path.read_bytes() if path.is_file() else None
        )
    return out


@pytest.mark.parametrize("quest_id", SCRIPTED)
def test_checks_write_nothing(quests_root, home, project, quest_id):
    """Ни в папку проекта, ни в домашнюю папку проверка не пишет."""
    proj = project(files={"index.html": "<h1>Дела</h1>\n"}, git=True, commits=1)
    _everything(home, proj)
    personal_skill(home, "moi-lichny", OWN_SKILL)
    before = (_snapshot(proj), _snapshot(home))
    check(quests_root, quest_id, proj, env=dict(started(), **word()))
    assert (_snapshot(proj), _snapshot(home)) == before


def test_checks_never_look_into_the_real_home(quests_root, home, project):
    """Проверка смотрит в `HOME`, а не в домашнюю папку хозяина машины.

    У автора игры стоят личные скиллы и хуки в настройках пользователя:
    прочитай проверка настоящую домашнюю папку, провал на пустой песочной
    был бы невозможен.
    """
    proj = project()
    for quest_id, row in (("03-own-skill", "own_skill_exists"),
                          ("04-hook", "hook_recorded")):
        result = check(quests_root, quest_id, proj, env=dict(started(0), **word()))
        assert failed(result)[0] == row, quest_id


@pytest.mark.parametrize("quest_id", SCRIPTED)
def test_check_prints_only_json(quests_root, home, project, quest_id):
    result = check(quests_root, quest_id, project(), env=started())
    assert result.kind == quests.KIND_SCRIPT
    assert all(set(row) >= {"id", "ok", "label", "hint"} for row in result.checks)

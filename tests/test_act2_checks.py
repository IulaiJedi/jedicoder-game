"""Проверки Акта 2 «Память и силы» на фикстурах.

Гоняются через quests.run_check — тем же путём, каким их запускает CLI.
На каждый квест три исхода: прошёл, не прошёл, не смог проверить.

Три квеста из четырёх судят то, чего нет в папке проекта: одобренный план,
показанный файл и снимок, новый разговор. Их проверкам след приходит готовым,
переменной окружения `JEDICODER_TRACE_*` (ADR-0020 в репозитории сайта).
Здесь переменную подаёт сам тест: кто её ставит в игре — хук и команда —
проверяется не здесь. Без неё проверка отвечает честным провалом с
подсказкой, а не «не смог проверить».
"""
import json
import os
import re
import shutil
import subprocess

import pytest

from jedicoder import quests

SLUG = "act2-pamyat-i-sily"

MEMORY_OK = """# Расписание кружка

## Что это
Страница с расписанием кружка для родителей нашей группы.

## Как открыть
Открыть файл index.html в браузере.

## Не трогать
Файл IDEA.md и цвета на странице.

## Правила
После важных изменений сохраняй сам.
"""

#: Квест → след, который закрывает его строки. Имена переменных — договор с
#: командой игры (`cli._env_for`): менять только с обеих сторон сразу.
TRACES = {
    "01-plan": {"JEDICODER_TRACE_PLAN_APPROVED": "yes"},
    "02-show": {"JEDICODER_TRACE_FILE_SHOWN": "yes",
                "JEDICODER_TRACE_IMAGE_SHOWN": "yes"},
    "04-clear": {"JEDICODER_TRACE_CLEARED": "yes"},
}
SCRIPTED = ("01-plan", "02-show", "03-memory", "04-clear")
ALL_TRACES = {name: "yes" for env in TRACES.values() for name in env}


def check(quests_root, quest, project_dir, env=None, recorded=True):
    """Запустить проверку так, как её запускает CLI после `project path`.

    `recorded=False` — папка не названа: движок переменную не ставит вовсе.
    """
    extra = {}
    if recorded:
        extra = {"JEDICODER_PROJECT_PATH": str(project_dir)}
    extra.update(env or {})
    return quests.run_check(quests_root, SLUG, quest, project_dir, env_extra=extra)


def failed(result):
    return [item["id"] for item in quests.failed_checks(result)]


def memory_project(project, text=MEMORY_OK, name="CLAUDE.md"):
    return project(files={name: text})


# --- квесты со следом: 01-plan, 02-show, 04-clear ---

@pytest.mark.parametrize("quest_id", sorted(TRACES))
def test_trace_quest_passes_when_the_trace_is_given(quests_root, project, quest_id):
    result = check(quests_root, quest_id, project(), env=TRACES[quest_id])
    assert result.ok is True, quests.failed_checks(result)


@pytest.mark.parametrize("quest_id,rows", [
    ("01-plan", ["plan_approved"]),
    ("02-show", ["file_shown", "image_shown"]),
    ("04-clear", ["cleared"]),
])
def test_trace_quest_fails_honestly_without_the_trace(
        quests_root, project, quest_id, rows):
    """След никто не поставил — провал, а не «не смог»: попытка считается."""
    result = check(quests_root, quest_id, project())
    assert result.exit_code == quests.EXIT_FAIL
    assert result.countable is True
    assert failed(result) == rows


@pytest.mark.parametrize("quest_id", sorted(TRACES))
def test_trace_quest_bails_when_folder_not_recorded(quests_root, project, quest_id):
    result = check(quests_root, quest_id, project(), env=TRACES[quest_id],
                   recorded=False)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False
    assert "папка проекта не названа" in result.stderr


@pytest.mark.parametrize("value", ["", "no", "1", "true", "YES", "yes "])
@pytest.mark.parametrize("quest_id", sorted(TRACES))
def test_trace_counts_only_as_the_exact_word_yes(quests_root, project, quest_id, value):
    """След — ровно `yes`: всё остальное читается как «следа нет»."""
    env = {name: value for name in TRACES[quest_id]}
    assert check(quests_root, quest_id, project(), env=env).ok is False


def test_show_judges_file_and_picture_separately(quests_root, project):
    """Показан файл, а картинки не было — не сошлась одна строка, а не обе."""
    proj = project()
    only_file = check(quests_root, "02-show", proj,
                      env={"JEDICODER_TRACE_FILE_SHOWN": "yes"})
    assert failed(only_file) == ["image_shown"]
    only_image = check(quests_root, "02-show", proj,
                       env={"JEDICODER_TRACE_IMAGE_SHOWN": "yes"})
    assert failed(only_image) == ["file_shown"]


def test_a_trace_of_another_quest_closes_nothing(quests_root, project):
    """Чужой след квест не закрывает: у каждой проверки своя переменная."""
    proj = project()
    for quest_id, own in sorted(TRACES.items()):
        foreign = {name: "yes" for name in ALL_TRACES if name not in own}
        assert check(quests_root, quest_id, proj, env=foreign).ok is False, quest_id


def test_trace_hints_name_the_action_to_repeat(quests_root, project):
    """Подсказка говорит словами, какое действие сделать в игре."""
    proj = project()
    expected = {
        "01-plan": ["/plan", "Enter"],
        "02-show": ["@", "снимок экрана"],
        "04-clear": ["/clear"],
    }
    for quest_id, words in expected.items():
        result = check(quests_root, quest_id, proj)
        hints = " ".join(item["hint"] for item in quests.failed_checks(result))
        assert "Игра не видела" in hints, quest_id
        for word in words:
            assert word in hints, (quest_id, word)


# --- 03-memory ---

def test_memory_passes(quests_root, project):
    result = check(quests_root, "03-memory", memory_project(project))
    assert result.ok is True, quests.failed_checks(result)


def test_memory_passes_from_the_dot_claude_folder(quests_root, project):
    """Claude Code читает и `.claude/CLAUDE.md` — проверка принимает оба места."""
    proj = memory_project(project, name=".claude/CLAUDE.md")
    result = check(quests_root, "03-memory", proj)
    assert result.ok is True, quests.failed_checks(result)


def test_memory_empty_root_file_does_not_hide_the_written_one(quests_root, project):
    proj = project(files={"CLAUDE.md": "", ".claude/CLAUDE.md": MEMORY_OK})
    result = check(quests_root, "03-memory", proj)
    assert result.ok is True, quests.failed_checks(result)


def test_memory_fails_without_file(quests_root, project):
    result = check(quests_root, "03-memory", project())
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result) == [
        "memory_exists", "memory_what", "memory_open", "memory_keep",
        "memory_rules",
    ]


def test_memory_in_another_subfolder_does_not_count(quests_root, project):
    proj = memory_project(project, name="docs/CLAUDE.md")
    assert "memory_exists" in failed(check(quests_root, "03-memory", proj))


@pytest.mark.parametrize("heading,row", [
    ("## Что это", "memory_what"),
    ("## Как открыть", "memory_open"),
    ("## Не трогать", "memory_keep"),
    ("## Правила", "memory_rules"),
])
def test_memory_fails_without_a_section(quests_root, project, heading, row):
    text = MEMORY_OK.replace(heading, "## Другое", 1)
    proj = memory_project(project, text)
    assert failed(check(quests_root, "03-memory", proj)) == [row]


@pytest.mark.parametrize("heading,row", [
    ("## Что это", "memory_what"),
    ("## Как открыть", "memory_open"),
    ("## Не трогать", "memory_keep"),
    ("## Правила", "memory_rules"),
])
@pytest.mark.parametrize("body", ["", "TODO", "-", "…", "   "])
def test_memory_fails_on_an_empty_section(quests_root, project, heading, row, body):
    """Заголовок без тела и заглушка вместо тела — раздел пуст."""
    lines, out, skipping = MEMORY_OK.splitlines(), [], False
    for line in lines:
        if line.startswith("## "):
            skipping = line == heading
            out.append(line)
            if skipping:
                out.append(body)
            continue
        if not skipping:
            out.append(line)
    proj = memory_project(project, "\n".join(out) + "\n")
    assert failed(check(quests_root, "03-memory", proj)) == [row]


def test_memory_one_word_is_a_body(quests_root, project):
    text = MEMORY_OK.replace("Файл IDEA.md и цвета на странице.", "Цвета")
    proj = memory_project(project, text)
    assert check(quests_root, "03-memory", proj).ok is True


def test_memory_accepts_lowercase_and_longer_headings(quests_root, project):
    """Регистр первой буквы — любой; «Что это за проект» — тоже «Что это»."""
    text = (MEMORY_OK
            .replace("## Что это", "## что это за проект")
            .replace("## Как открыть", "### как открыть проект")
            .replace("## Не трогать", "## не трогать без спроса"))
    proj = memory_project(project, text)
    result = check(quests_root, "03-memory", proj)
    assert result.ok is True, quests.failed_checks(result)


def test_memory_section_does_not_borrow_from_its_neighbour(quests_root, project):
    text = MEMORY_OK.replace("Открыть файл index.html в браузере.\n", "")
    proj = memory_project(project, text)
    assert failed(check(quests_root, "03-memory", proj)) == ["memory_open"]


def test_memory_title_with_the_same_words_is_not_the_section(quests_root, project):
    """Заголовок документа «# Что это» не заслоняет раздел «## Что это»."""
    text = MEMORY_OK.replace("# Расписание кружка", "# Что это", 1)
    proj = memory_project(project, text)
    result = check(quests_root, "03-memory", proj)
    assert result.ok is True, quests.failed_checks(result)


def test_memory_bails_when_folder_not_recorded(quests_root, project):
    result = check(quests_root, "03-memory", memory_project(project),
                   recorded=False)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False
    assert "папка проекта не названа" in result.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="root читает любой файл")
def test_memory_bails_on_unreadable_file(quests_root, project):
    proj = memory_project(project)
    (proj / "CLAUDE.md").chmod(0o000)
    try:
        result = check(quests_root, "03-memory", proj)
    finally:
        (proj / "CLAUDE.md").chmod(0o644)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "не могу прочитать CLAUDE.md" in result.stderr


def test_powers_quest_has_no_script(quests_root, project):
    result = check(quests_root, "05-powers", project())
    assert result.kind == quests.KIND_ACK


# --- общий контракт ---

def test_act2_checks_survive_hostile_locale(quests_root, project):
    """Заголовки CLAUDE.md кириллицей обязаны находиться и при LC_ALL=C."""
    proj = memory_project(project)
    env = dict(ALL_TRACES, LC_ALL="C")
    for quest_id in SCRIPTED:
        result = check(quests_root, quest_id, proj, env=env)
        assert result.ok is True, (quest_id, quests.failed_checks(result))


def test_act2_checks_survive_mawk(quests_root, project):
    """mawk — awk по умолчанию в WSL Ubuntu; суит на gawk его болезней не видит."""
    if shutil.which("mawk") is None:
        pytest.skip("mawk недоступен")
    proj = memory_project(project)
    bin_dir = proj.parent / "mawkbin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "awk"
    stub.write_text('#!/bin/sh\nexec mawk "$@"\n', encoding="utf-8")
    stub.chmod(0o755)
    env = dict(ALL_TRACES, LC_ALL="C",
               PATH="{}:{}".format(bin_dir, os.environ["PATH"]))
    for quest_id in SCRIPTED:
        result = check(quests_root, quest_id, proj, env=env)
        assert result.ok is True, (quest_id, quests.failed_checks(result))
    stubs = ("## Что это\nTODO\n\n## Как открыть\n\n## Не трогать\nЦвета\n"
             "\n## Правила\nСохраняй сам.\n")
    (proj / "CLAUDE.md").write_text(stubs, encoding="utf-8")
    assert failed(check(quests_root, "03-memory", proj, env=env)) == [
        "memory_what", "memory_open",
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
    """check.sh никогда не мутирует проект падавана."""
    proj = memory_project(project)
    (proj / "черновик.txt").write_text("не сохранён\n", encoding="utf-8")
    before = _snapshot(proj)
    for quest_id in SCRIPTED:
        check(quests_root, quest_id, proj, env=ALL_TRACES)
        check(quests_root, quest_id, proj)
    assert _snapshot(proj) == before


def test_checks_print_only_json_on_stdout(quests_root, project):
    """Провал и проход печатают в stdout один объект JSON и ничего больше."""
    for proj, extra in ((memory_project(project), ALL_TRACES), (project(), {})):
        for quest_id in SCRIPTED:
            script = quests.script_path(quests_root, SLUG, quest_id)
            done = subprocess.run(
                ["bash", str(script)], cwd=str(proj), capture_output=True,
                text=True,
                env=dict(os.environ, JEDICODER_PROJECT_PATH=str(proj), **extra),
            )
            assert done.returncode == (0 if extra else 1), (quest_id, done.stderr)
            payload = json.loads(done.stdout)
            assert payload["quest"] == "act2/" + quest_id
            assert payload["ok"] is (done.returncode == 0)


def test_trace_checks_do_not_read_the_save(quests_root):
    """Проверка сохранения не читает: след ей передаёт команда игры."""
    for quest_id in sorted(TRACES):
        text = quests.script_path(quests_root, SLUG, quest_id).read_text(
            encoding="utf-8"
        )
        code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        assert "state.json" not in code and ".jedicoder" not in code, quest_id


def test_no_check_folds_case_with_grep_i(quests_root):
    """Ни одна проверка игры не складывает регистр через `grep -i`.

    Настоящий отказ отсюда не воспроизвести: у GNU grep на Linux `-i`
    кириллицу складывает. Ломается он на BSD grep из macOS, заявленной
    целевой платформой, — поэтому сторожит правило, а не симптом. Правило
    записано в CLAUDE.md: регистр задаётся классом. Тест заодно закрывает
    «новых таких не заводить» для будущих актов. Проверки на полке стережёт
    тот же тест в tests/test_shelf_act2_checks.py.
    """
    scripts = sorted(quests_root.rglob("check.sh"))
    assert scripts, "проверок не найдено — страж смотрит не туда"
    offenders = []
    for script in scripts:
        for number, line in enumerate(
                script.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"grep\s+(-\w*\s+)*-\w*i", code):
                offenders.append("{}:{}".format(script.parent.name, number))
    assert offenders == [], "регистр складывается классом, а не grep -i: {}".format(
        ", ".join(offenders)
    )


# --- находки ревью: унаследованный след, подразделы, пустой файл -------------

@pytest.mark.parametrize("quest_id", sorted(TRACES))
def test_a_trace_inherited_from_the_shell_does_not_count(
        quests_root, project, quest_id, monkeypatch):
    """След передаёт команда игры, а не оболочка, из которой её позвали.

    Иначе приставка `JEDICODER_TRACE_…=yes` перед командой закрывала бы
    квест без действия: исход решал бы тот, кто набрал команду.
    """
    for name in ALL_TRACES:
        monkeypatch.setenv(name, "yes")
    result = check(quests_root, quest_id, project())
    assert result.exit_code == quests.EXIT_FAIL, quests.failed_checks(result)
    # Переданный командой — считается, как прежде.
    assert check(quests_root, quest_id, project(), env=TRACES[quest_id]).ok is True


def test_memory_subsections_belong_to_their_section(quests_root, project):
    """«## Не трогать», под ним «### Файлы» и список — раздел не пуст."""
    text = MEMORY_OK.replace(
        "Файл IDEA.md и цвета на странице.",
        "### Файлы\n- IDEA.md\n\n### Решения\n- цвета на странице",
    )
    result = check(quests_root, "03-memory", memory_project(project, text))
    assert result.ok is True, quests.failed_checks(result)


def test_memory_section_of_bare_subheadings_is_empty(quests_root, project):
    text = MEMORY_OK.replace(
        "Открыть файл index.html в браузере.", "### В браузере\n\n### В терминале"
    )
    proj = memory_project(project, text)
    assert failed(check(quests_root, "03-memory", proj)) == ["memory_open"]


def test_memory_deep_section_stops_at_the_next_section(quests_root, project):
    """Подраздел соседа разделу не засчитывается."""
    text = (
        "## Что это\nСтраница кружка.\n\n## Как открыть\n\n"
        "## Не трогать\n### Файлы\n- IDEA.md\n\n## Правила\nСохраняй сам.\n"
    )
    proj = memory_project(project, text)
    assert failed(check(quests_root, "03-memory", proj)) == ["memory_open"]


@pytest.mark.parametrize("blank", ["\n", "  \n\n", "\t\n"])
def test_memory_blank_root_file_does_not_hide_the_written_one(
        quests_root, project, blank):
    proj = project(files={"CLAUDE.md": blank, ".claude/CLAUDE.md": MEMORY_OK})
    result = check(quests_root, "03-memory", proj)
    assert result.ok is True, quests.failed_checks(result)


def test_memory_blank_file_is_not_written_memory(quests_root, project):
    proj = project(files={"CLAUDE.md": "\n\n  \n"})
    assert "memory_exists" in failed(check(quests_root, "03-memory", proj))


def test_memory_with_crlf_and_without_final_newline(quests_root, project):
    proj = memory_project(project)
    (proj / "CLAUDE.md").write_bytes(
        MEMORY_OK.rstrip("\n").replace("\n", "\r\n").encode("utf-8")
    )
    result = check(quests_root, "03-memory", proj)
    assert result.ok is True, quests.failed_checks(result)


@pytest.mark.skipif(os.geteuid() == 0, reason="root читает любую папку")
def test_memory_bails_on_unreadable_dot_claude_folder(quests_root, project):
    proj = memory_project(project, name=".claude/CLAUDE.md")
    (proj / ".claude").chmod(0o000)
    try:
        result = check(quests_root, "03-memory", proj)
    finally:
        (proj / ".claude").chmod(0o755)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False


# --- перешло из #100: «Чего не трогать», BOM и неразрывный пробел -------------

def test_memory_accepts_the_heading_the_check_itself_speaks(quests_root, project):
    """Строка проверки говорит «чего не трогать» — и заголовок такой годится."""
    for heading in ("## Чего не трогать", "## чего не трогать в проекте"):
        text = MEMORY_OK.replace("## Не трогать", heading)
        result = check(quests_root, "03-memory", memory_project(project, text))
        assert result.ok is True, (heading, quests.failed_checks(result))


def test_memory_file_with_a_bom_keeps_its_first_section(quests_root, project):
    """Блокнот Windows ставит в начало файла невидимую метку."""
    text = "\ufeff" + MEMORY_OK.split("\n\n", 1)[1]
    assert text.startswith("\ufeff## Что это")
    proj = memory_project(project, text)
    for env in (None, {"LC_ALL": "C"}):
        result = check(quests_root, "03-memory", proj, env=env)
        assert result.ok is True, (env, quests.failed_checks(result))


@pytest.mark.parametrize("heading,broken", [
    ("## Что это", "##\u00a0Что\u00a0это"),
    ("## Как открыть", "## Как\u00a0открыть"),
    ("## Не трогать", "## Не\u00a0трогать"),
    ("## Не трогать", "## Чего\u00a0не\u00a0трогать"),
])
def test_memory_heading_with_a_non_breaking_space_is_the_same_heading(
        quests_root, project, heading, broken):
    proj = memory_project(project, MEMORY_OK.replace(heading, broken))
    for env in (None, {"LC_ALL": "C"}):
        result = check(quests_root, "03-memory", proj, env=env)
        assert result.ok is True, (broken, env, quests.failed_checks(result))


def test_memory_in_another_encoding_does_not_break_the_check(quests_root, project):
    """Файл не в UTF-8 (cp1251 из Блокнота): разделы не найдены — честный
    провал строками, а не сорванная проверка."""
    proj = project()
    (proj / "CLAUDE.md").write_bytes(MEMORY_OK.encode("cp1251"))
    result = check(quests_root, "03-memory", proj)
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result) == [
        "memory_what", "memory_open", "memory_keep", "memory_rules",
    ]


def test_memory_non_breaking_spaces_alone_are_not_a_body(quests_root, project):
    """Раздел из одних неразрывных пробелов пуст, как и из обычных."""
    text = MEMORY_OK.replace("Файл IDEA.md и цвета на странице.", "\u00a0\u00a0")
    proj = memory_project(project, text)
    assert failed(check(quests_root, "03-memory", proj)) == ["memory_keep"]


def test_memory_with_bom_and_nbsp_survives_mawk(quests_root, project):
    if shutil.which("mawk") is None:
        pytest.skip("mawk недоступен")
    text = "\ufeff" + MEMORY_OK.split("\n\n", 1)[1].replace(
        "## Не трогать", "##\u00a0Чего\u00a0не трогать")
    proj = memory_project(project, text)
    bin_dir = proj.parent / "mawkbin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "awk"
    stub.write_text('#!/bin/sh\nexec mawk "$@"\n', encoding="utf-8")
    stub.chmod(0o755)
    env = {"LC_ALL": "C", "PATH": "{}:{}".format(bin_dir, os.environ["PATH"])}
    result = check(quests_root, "03-memory", proj, env=env)
    assert result.ok is True, quests.failed_checks(result)


# --- четвёртый раздел: правило работы (#104, по шпаргалке оператора) -----------

def test_memory_rules_section_takes_any_rule_of_the_person(quests_root, project):
    """Правило человек называет своё: судится раздел, а не его слова."""
    for heading, body in (
        ("## Правила", "После важных изменений сохраняй сам."),
        ("## правила работы", "Спрашивай перед большой правкой."),
        ("## Правило", "- коммит после каждой рабочей версии"),
    ):
        text = MEMORY_OK.split("## Правила")[0] + "{}\n{}\n".format(heading, body)
        proj = memory_project(project, text, name="CLAUDE.md")
        result = check(quests_root, "03-memory", proj)
        assert result.ok is True, (heading, quests.failed_checks(result))


def test_memory_without_rules_fails_on_that_line_alone(quests_root, project):
    proj = memory_project(project, MEMORY_OK.split("## Правила")[0])
    result = check(quests_root, "03-memory", proj)
    assert result.exit_code == quests.EXIT_FAIL
    assert failed(result) == ["memory_rules"]
    hint = quests.failed_checks(result)[0]["hint"]
    assert "сохраняй сам после важных изменений" in hint and "«Правила»" in hint

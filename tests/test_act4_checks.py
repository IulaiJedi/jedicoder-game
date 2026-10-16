"""Проверки Акта 4 «Свой продукт» на фикстурах (#118, #119).

Гоняются через quests.run_check — тем же путём, каким их запускает CLI.
На каждый квест три исхода: прошёл, не прошёл, не смог проверить.

`IDEA.md` здесь — ровно то, что Claude Code написал в живом замере
2026-10-14 (`docs/research/2026-10-14-act4-facts.md`): раздел `## Продукт`
с подписями жирным. След плана, момент входа в акт и тип продукта подаёт сам
тест: кто их ставит в игре — хук и команда — проверяют
`tests/test_act4_entry.py` и `tests/test_act4_walkthrough.py`.

Сайт в «Работает» — настоящий сервер на свободном порту, curl живой; бот —
файлы `.env`, `.gitignore` и кода, ключ выдуманный.
"""
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from conftest import _git
from jedicoder import quests

SLUG = "act4-svoy-produkt"

IDEA_HEAD = """# Идея

## Делаю сегодня

Страница для кружка рисования для детей: расписание и как записаться.

## Не сегодня

- Оплата онлайн
"""

#: Замер, прогон с ботом: четыре подписи, названные в просьбе.
PRODUCT_BOT = IDEA_HEAD + """
## Продукт

**Что это:** Telegram-бот кружка рисования «Радуга».

**Для кого:** родители из нашего района, у которых дети 6–10 лет.

**Что делает:**

1. Родитель пишет боту — бот предлагает две кнопки: «Расписание» и «Записаться».
2. «Записаться на пробное» — бот спрашивает имя ребёнка и телефон.

**Как я пойму, что готово:**

- [ ] Я пишу боту — он отвечает и показывает кнопки.
- [ ] Мне в Telegram приходит заявка.
"""

#: Замер, прогон с сайтом без подсказки про «готово»: Claude списком
#: подписал «для кого» и «что делает», а как понять, что готово, — не
#: записал: человек не назвал.
PRODUCT_SITE_NO_DONE = IDEA_HEAD + """
## Продукт

- **Для кого:** родители из нашего района, дети 6–10 лет.
- **Что делает родитель на сайте:** смотрит расписание и записывает ребёнка на пробное занятие.
- **Запись:** кнопка открывает чат в мессенджере с готовым текстом заявки.
- **Пробное занятие:** бесплатное.
"""

PRODUCT_SITE = PRODUCT_SITE_NO_DONE + (
    "- **Как я пойму, что готово:** открываю страницу — вижу расписание и кнопку записи.\n"
)


def check(quests_root, quest, project_dir, env=None, recorded=True):
    extra = {}
    if recorded:
        extra = {"JEDICODER_PROJECT_PATH": str(project_dir)}
    extra.update(env or {})
    return quests.run_check(quests_root, SLUG, quest, project_dir, env_extra=extra)


def failed(result):
    return [item["id"] for item in quests.failed_checks(result)]


def rows(result):
    return [item["id"] for item in result.checks]


def idea(project, text):
    return project(files={"IDEA.md": text})


# --- «Что строим» ---------------------------------------------------------------

@pytest.mark.parametrize("text", [PRODUCT_BOT, PRODUCT_SITE])
def test_what_passes_on_the_section_claude_wrote(quests_root, project, text):
    result = check(quests_root, "01-what", idea(project, text))
    assert result.ok is True, quests.failed_checks(result)
    assert rows(result) == [
        "product_section", "product_kind", "product_for_whom", "product_does",
        "product_done",
    ]


def test_what_without_the_done_line_names_only_it(quests_root, project):
    """Замер: без слов «как пойму, что готово» Claude этой строки не пишет.
    «Готовым текстом» готовностью не считается."""
    result = check(quests_root, "01-what", idea(project, PRODUCT_SITE_NO_DONE))
    assert result.ok is False
    assert failed(result) == ["product_done"]


def test_what_without_the_section_shows_one_line(quests_root, project):
    result = check(quests_root, "01-what", idea(project, IDEA_HEAD))
    assert result.ok is False
    assert rows(result) == ["product_section"]
    assert "задай вопросы" in result.checks[0]["hint"]


def test_what_without_idea_file_fails(quests_root, project):
    result = check(quests_root, "01-what", project())
    assert result.ok is False and rows(result) == ["product_section"]


def test_what_section_of_one_line_is_not_written(quests_root, project):
    text = IDEA_HEAD + "\n## Продукт\n\nСайт.\n"
    assert failed(check(quests_root, "01-what", idea(project, text))) == [
        "product_section",
    ]


def test_what_reads_subheadings_as_answers(quests_root, project):
    """Подзаголовки вместо подписей — тот же ответ."""
    text = IDEA_HEAD + (
        "\n## Продукт\n\n### Что это\n\nСайт кружка рисования.\n\n"
        "### Для кого\n\nРодители нашего района.\n\n"
        "### Что делает\n\nПоказывает расписание и принимает заявки.\n\n"
        "### Как я пойму, что готово\n\nОткрываю страницу и вижу расписание.\n"
    )
    result = check(quests_root, "01-what", idea(project, text))
    assert result.ok is True, quests.failed_checks(result)


@pytest.mark.parametrize("for_whom,does,done", [
    ("**Кто пользуется:** родители.", "**Что будет делать сайт:** показывать расписание.",
     "**Критерии готовности:** расписание открывается."),
    ("**Пользователи:** родители.", "**Что умеет:** показывать расписание.",
     "**Сайт готов, когда** расписание открывается."),
    ("Им будут пользоваться родители.", "**Что он делает:** показывает расписание.",
     "**Готова, когда** расписание открывается."),
])
def test_what_accepts_natural_labels(quests_root, project, for_whom, does, done):
    """Подписи бывают своими словами — смысл тот же (ревью #118)."""
    text = IDEA_HEAD + (
        "\n## Продукт\n\n**Что это:** сайт кружка рисования «Радуга».\n\n"
        "{}\n\n{}\n\n{}\n".format(for_whom, does, done)
    )
    result = check(quests_root, "01-what", idea(project, text))
    assert result.ok is True, quests.failed_checks(result)


def test_what_hints_name_the_label_to_write(quests_root, project):
    """Подсказка называет подпись строкой — её можно попросить дословно."""
    text = IDEA_HEAD + "\n## Продукт\n\n" + ("Слова о кружке рисования. " * 5) + "\n"
    result = check(quests_root, "01-what", idea(project, text))
    hints = {item["id"]: item["hint"] for item in quests.failed_checks(result)}
    assert sorted(hints) == [
        "product_does", "product_done", "product_for_whom", "product_kind",
    ]
    assert "`**Что это:**`" in hints["product_kind"]
    assert "`**Для кого:**`" in hints["product_for_whom"]
    assert "`**Что делает:**`" in hints["product_does"]
    assert "`**Как я пойму, что готово:**`" in hints["product_done"]


@pytest.mark.parametrize("word", ["работает", "субботу"])
def test_bot_inside_another_word_is_not_a_kind(quests_root, project, word):
    text = IDEA_HEAD + (
        "\n## Продукт\n\n**Что это:** вещь, которая {} для кружка.\n\n"
        "**Для кого:** родители.\n\n**Что делает:** записывает детей.\n\n"
        "**Как я пойму, что готово:** родитель записался.\n".format(word)
    )
    assert failed(check(quests_root, "01-what", idea(project, text))) == [
        "product_kind",
    ]


def test_what_section_stops_at_the_next_section(quests_root, project):
    """Слова из раздела после «Продукта» ему не засчитываются."""
    text = IDEA_HEAD + (
        "\n## Продукт\n\n**Что это:** Telegram-бот кружка рисования «Радуга» "
        "для записи детей на занятия.\n\n"
        "## Потом\n\n**Для кого:** родители. **Что делает:** всё. Готово.\n"
    )
    assert failed(check(quests_root, "01-what", idea(project, text))) == [
        "product_for_whom", "product_does", "product_done",
    ]


def test_what_bails_without_a_named_folder(quests_root, project):
    result = check(quests_root, "01-what", idea(project, PRODUCT_BOT),
                   recorded=False)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


# --- «План» -----------------------------------------------------------------------

def plan_env(at, started, approved="yes"):
    env = {"JEDICODER_ACT_STARTED": str(started)}
    if approved is not None:
        env["JEDICODER_TRACE_PLAN_APPROVED"] = approved
    if at is not None:
        env["JEDICODER_TRACE_PLAN_APPROVED_AT"] = str(at)
    return env


def test_plan_approved_after_entry_passes(quests_root, project):
    now = int(time.time())
    result = check(quests_root, "02-plan", project(), env=plan_env(now, now - 60))
    assert result.ok is True


def test_plan_approved_in_the_same_second_as_entry_passes(quests_root, project):
    now = int(time.time())
    assert check(quests_root, "02-plan", project(), env=plan_env(now, now)).ok


@pytest.mark.parametrize("at,approved", [
    (None, "yes"),        # план второго вечера: момента нет
    (1000, "yes"),        # момент раньше входа в акт
    (None, None),         # следа нет вовсе
    (99999999999, "no"),  # след не тот
    ("вчера", "yes"),     # мусор вместо момента
])
def test_plan_not_approved_in_this_act_fails(quests_root, project, at, approved):
    result = check(quests_root, "02-plan", project(),
                   env=plan_env(at, 5000, approved))
    assert result.ok is False
    assert failed(result) == ["plan_approved"]
    assert "/plan" in result.checks[0]["hint"]


@pytest.mark.parametrize("started", [None, "", "вчера"])
def test_plan_without_entry_moment_cannot_be_judged(quests_root, project, started):
    env = plan_env(int(time.time()), 0)
    if started is None:
        del env["JEDICODER_ACT_STARTED"]
    else:
        env["JEDICODER_ACT_STARTED"] = started
    result = check(quests_root, "02-plan", project(), env=env)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


# --- «Сборка» ---------------------------------------------------------------------

#: Момент входа в акт в тестах «Сборки»: коммиты датируются относительно него.
STARTED = 1790000000


def build_env(started=STARTED):
    return {"JEDICODER_ACT_STARTED": str(started)}


def repo(project, files=None):
    """Папка проекта с git и без сохранений: их кладёт `save`."""
    return project(files=files, gitignore=".env\n", git=True)


def save(proj, files, at, message="шаг"):
    """Claude сохранил шаг: файлы и коммит с датой автора `at`."""
    for name, text in files.items():
        target = proj / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    stamp = "{} +0000".format(at)
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    for argv in (["git", "add", "-A"], ["git", "commit", "-q", "-m", message]):
        subprocess.run(argv, cwd=str(proj), check=True, capture_output=True, env=env)


def built(project, steps, before=1):
    """Сохранения прежних вечеров до входа и шаги после: (файлы, сдвиг)."""
    proj = repo(project)
    for i in range(before):
        save(proj, {"index.html": "<h1>Набросок {}</h1>\n".format(i)},
             STARTED - 86400 + i, "набросок")
    for files, shift in steps:
        save(proj, files, STARTED + shift)
    return proj


def past_the_last_save(proj):
    """Дождаться, пока часы уйдут за секунду последнего сохранения.

    Дата коммита и момент входа в акт — целые секунды. Проход Актов 1–3 в
    тестах быстрый, и сохранение первого вечера могло бы лечь в ту же
    секунду, что вход в Акт 4, — и посчитаться сохранением этого акта.
    """
    done = subprocess.run(
        ["git", "log", "-1", "--format=%ct"], cwd=str(proj),
        capture_output=True, text=True,
    )
    last = int(done.stdout.strip() or 0)
    while int(time.time()) <= last:
        time.sleep(0.05)


THREE_STEPS = [
    ({"index.html": "<h1>Кружок</h1>\n"}, 10),
    ({"style.css": "h1 { color: teal }\n"}, 20),
    ({"index.html": "<h1>Кружок</h1>\n<table></table>\n"}, 30),
]


def test_build_passes_on_three_saves_with_the_product(quests_root, project):
    result = check(quests_root, "03-build", built(project, THREE_STEPS),
                   env=build_env())
    assert result.ok is True, quests.failed_checks(result)
    assert rows(result) == ["saves_after_entry", "code_saved"]


def test_build_counts_a_save_in_the_second_of_entry(quests_root, project):
    steps = [({"a.html": "1\n"}, 0), ({"b.html": "2\n"}, 0), ({"c.html": "3\n"}, 0)]
    assert check(quests_root, "03-build", built(project, steps), env=build_env()).ok


def test_build_with_two_saves_names_how_many_and_only_that(quests_root, project):
    result = check(quests_root, "03-build", built(project, THREE_STEPS[:2]),
                   env=build_env())
    assert result.ok is False
    assert rows(result) == ["saves_after_entry"]
    hint = result.checks[0]["hint"]
    assert "2 из 3" in hint and "«дальше»" in hint


def test_saves_before_the_entry_are_not_counted(quests_root, project):
    """Пять сохранений прежних вечеров — ноль в этом акте."""
    proj = built(project, [], before=5)
    result = check(quests_root, "03-build", proj, env=build_env())
    assert failed(result) == ["saves_after_entry"]
    assert "0 из 3" in result.checks[0]["hint"]


def test_build_of_notes_only_is_not_a_product(quests_root, project):
    """Три сохранения заметок — продукта в них нет. Заглавное `.MD` — тоже заметка."""
    steps = [({"HANDOFF.md": "1\n"}, 10), ({"IDEA.md": "2\n"}, 20),
             ({"docs/PLAN.MD": "3\n"}, 30)]
    result = check(quests_root, "03-build", built(project, steps), env=build_env())
    assert failed(result) == ["code_saved"]
    assert rows(result) == ["saves_after_entry", "code_saved"]


def test_product_saved_before_the_entry_does_not_count_for_this_act(
        quests_root, project):
    steps = [({"HANDOFF.md": "1\n"}, 10), ({"IDEA.md": "2\n"}, 20),
             ({"CLAUDE.md": "3\n"}, 30)]
    proj = built(project, steps, before=3)
    assert failed(check(quests_root, "03-build", proj, env=build_env())) == [
        "code_saved",
    ]


def test_build_reads_cyrillic_file_names(quests_root, project):
    """Имена файлов кириллицей git печатает без кавычек — расширение видно."""
    steps = [({"заметки.md": "1\n"}, 10), ({"план.md": "2\n"}, 20),
             ({"расписание.html": "<table></table>\n"}, 30)]
    assert check(quests_root, "03-build", built(project, steps), env=build_env()).ok
    steps = [({"заметки.md": "1\n"}, 10), ({"план.md": "2\n"}, 20),
             ({"итог.md": "3\n"}, 30)]
    assert failed(check(quests_root, "03-build", built(project, steps),
                        env=build_env())) == ["code_saved"]


def test_service_files_are_not_the_product(quests_root, project):
    """`.gitignore`, `.env.example` и настройки `.claude/` — служебное."""
    steps = [({"IDEA.md": "1\n"}, 10), ({"HANDOFF.md": "2\n"}, 20),
             ({".gitignore": ".env\n__pycache__/\n"}, 30)]
    assert failed(check(quests_root, "03-build", built(project, steps),
                        env=build_env())) == ["code_saved"]
    steps = [({".env.example": "BOT_TOKEN=\n"}, 10),
             ({".claude/settings.json": "{}\n"}, 20),
             ({".gitignore": ".env\n.venv/\n"}, 30)]
    assert failed(check(quests_root, "03-build", built(project, steps),
                        env=build_env())) == ["code_saved"]
    # Файл с точкой не в корне — часть продукта.
    steps = [({"IDEA.md": "1\n"}, 10), ({"HANDOFF.md": "2\n"}, 20),
             ({"static/.nojekyll": "\n"}, 30)]
    assert check(quests_root, "03-build", built(project, steps), env=build_env()).ok


def test_build_without_own_repository_has_no_saves(quests_root, project):
    result = check(quests_root, "03-build", project(files={"index.html": "1\n"}),
                   env=build_env())
    assert failed(result) == ["saves_after_entry"]


def test_build_in_an_empty_repository_has_no_saves(quests_root, project):
    result = check(quests_root, "03-build", repo(project), env=build_env())
    assert failed(result) == ["saves_after_entry"]


@pytest.mark.parametrize("started", [None, "", "вчера"])
def test_build_without_entry_moment_cannot_be_judged(quests_root, project, started):
    env = {} if started is None else {"JEDICODER_ACT_STARTED": started}
    result = check(quests_root, "03-build", built(project, THREE_STEPS), env=env)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_entry_moment_cannot_be_given_by_the_shell(quests_root, project, monkeypatch):
    monkeypatch.setenv("JEDICODER_ACT_STARTED", "0")
    result = check(quests_root, "03-build", built(project, THREE_STEPS))
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


# --- «Работает» ---------------------------------------------------------------------

#: Ключ по форме ключа Telegram — выдуманный: номер бота, двоеточие, хвост.
TOKEN = "7412589630:AAHfAkEkEyFoRtEsTsOnLy_abcdefghijklmn"
BOT_CODE = (
    "import os\n"
    "TOKEN = os.environ['BOT_TOKEN']\n"
)
BOT_ENV = {"JEDICODER_PRODUCT_TYPE": "bot"}
BOT_ROWS = ["key_in_env", "env_not_saved", "key_not_in_files", "key_not_in_saves"]


def site_env(port=None):
    env = {"JEDICODER_PRODUCT_TYPE": "site"}
    if port is not None:
        env["JEDICODER_PORT"] = str(port)
    return env


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def serve(root):
    """Встроенный сервер Python в папке — так Claude запускает сайт.

    Отдаёт (порт, процесс); гасит вызывающий."""
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(root), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while True:
        try:
            urllib.request.urlopen(
                "http://127.0.0.1:{}/".format(port), timeout=1
            ).close()
            return port, proc
        except OSError:
            if time.time() > deadline:
                proc.terminate()
                raise RuntimeError("тестовый сервер не поднялся")
            time.sleep(0.05)


@pytest.fixture
def live_site(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text("<h1>Кружок</h1>\n", encoding="utf-8")
    port, proc = serve(root)
    yield port
    proc.terminate()
    proc.wait(timeout=10)


def bot(project, env_text="BOT_TOKEN={}\n".format(TOKEN), code=BOT_CODE,
        gitignore=".env\n"):
    """Бот, как его кладёт Claude: код сохранён, ключ лежит в `.env`."""
    proj = project(files={"bot.py": code}, gitignore=gitignore, git=True, commits=1)
    if env_text is not None:
        (proj / ".env").write_text(env_text, encoding="utf-8")
    return proj


def test_run_without_a_product_type_cannot_be_judged(quests_root, project):
    for env in ({}, {"JEDICODER_PRODUCT_TYPE": "landing"}):
        result = check(quests_root, "04-run", project(), env=env)
        assert result.exit_code == quests.EXIT_CANNOT_CHECK
        assert "сайт у тебя или бот" in result.stderr


def test_site_without_a_port_cannot_be_judged(quests_root, project):
    result = check(quests_root, "04-run", project(), env=site_env())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "порт" in result.stderr


def test_site_without_curl_cannot_be_judged(quests_root, project, tmp_path):
    """Нет curl — «не смог проверить», а не провал."""
    bin_dir = tmp_path / "nocurl"
    bin_dir.mkdir()
    for name in ("bash", "dirname", "locale", "grep", "head"):
        found = shutil.which(name)
        if found:
            (bin_dir / name).symlink_to(found)
    env = dict(site_env(free_port()), PATH=str(bin_dir))
    result = check(quests_root, "04-run", project(), env=env)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "curl" in result.stderr


def test_bot_without_git_cannot_be_judged(quests_root, project, tmp_path):
    """Без git не узнать, что попало в сохранения, — «не смог проверить»."""
    bin_dir = tmp_path / "nogit"
    bin_dir.mkdir()
    for name in ("bash", "dirname", "locale", "grep", "head"):
        found = shutil.which(name)
        if found:
            (bin_dir / name).symlink_to(found)
    proj = bot(project)
    result = check(quests_root, "04-run", proj, env=dict(BOT_ENV, PATH=str(bin_dir)))
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "git" in result.stderr


def test_site_that_does_not_answer_fails_and_names_the_address(quests_root, project):
    port = free_port()
    result = check(quests_root, "04-run", project(), env=site_env(port))
    assert result.ok is False and result.exit_code == quests.EXIT_FAIL
    assert rows(result) == ["site_answers"]
    assert result.checks[0]["label"] == (
        "Сайт открывается на твоём компьютере: http://localhost:{}".format(port)
    )


def test_site_that_answers_passes(quests_root, project, live_site):
    result = check(quests_root, "04-run", project(), env=site_env(live_site))
    assert result.ok is True, quests.failed_checks(result)
    assert rows(result) == ["site_answers"]


def test_site_on_this_computer_is_opened_past_a_proxy(
        quests_root, project, live_site):
    """Прокси из окружения адрес на своём компьютере не касается: через
    него curl уходил в чужую машину и сайт «не отвечал» (ревью #119)."""
    dead = "http://127.0.0.1:{}".format(free_port())
    env = dict(site_env(live_site), http_proxy=dead, HTTP_PROXY=dead,
               https_proxy=dead, ALL_PROXY=dead, all_proxy=dead)
    result = check(quests_root, "04-run", project(), env=env)
    assert result.ok is True, quests.failed_checks(result)


def test_the_port_cannot_be_given_by_the_shell(
        quests_root, project, live_site, monkeypatch):
    """Порт приходит только от команды игры: унаследованный не в счёт."""
    monkeypatch.setenv("JEDICODER_PORT", str(live_site))
    result = check(quests_root, "04-run", project(), env=site_env())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "порт" in result.stderr


def test_bot_with_the_key_in_env_passes(quests_root, project):
    result = check(quests_root, "04-run", bot(project), env=BOT_ENV)
    assert result.ok is True, quests.failed_checks(result)
    assert rows(result) == BOT_ROWS


@pytest.mark.parametrize("env_text", [
    None, "", "BOT_TOKEN=\n", "BOT_TOKEN=вставь_сюда_ключ\n", "BOT_TOKEN=12345:AAH\n",
])
def test_bot_without_a_key_in_env_shows_one_line(quests_root, project, env_text):
    result = check(quests_root, "04-run", bot(project, env_text=env_text), env=BOT_ENV)
    assert result.ok is False
    assert rows(result) == ["key_in_env"]
    assert "@BotFather" in result.checks[0]["hint"]
    assert "положи его в .env" in result.checks[0]["hint"]


def test_bot_key_with_quotes_and_another_name_is_found(quests_root, project):
    text = '# ключ бота\nTELEGRAM_BOT_TOKEN="{}"\n'.format(TOKEN)
    assert check(quests_root, "04-run", bot(project, env_text=text), env=BOT_ENV).ok


def hint_of(result, check_id):
    return next(item for item in result.checks if item["id"] == check_id)["hint"]


def test_env_not_closed_from_saves_fails(quests_root, project):
    proj = bot(project, gitignore="node_modules\n")
    result = check(quests_root, "04-run", proj, env=BOT_ENV)
    assert failed(result) == ["env_not_saved"]
    assert "допиши его в .gitignore" in hint_of(result, "env_not_saved")


def test_env_inside_a_save_fails_twice(quests_root, project):
    """`.env` сохранён: он в сохранениях, и ключ вместе с ним. `.gitignore`
    при этом записан — подсказка зовёт убрать файл из сохранений, а не
    дописать то, что уже дописано."""
    proj = bot(project)
    _git(proj, "add", "-f", ".env")
    _git(proj, "commit", "-q", "-m", "случайно сохранил ключ")
    result = check(quests_root, "04-run", proj, env=BOT_ENV)
    assert failed(result) == ["env_not_saved", "key_not_in_saves"]
    hint = hint_of(result, "env_not_saved")
    assert "Убери .env из сохранений, сам файл оставь" in hint
    assert ".gitignore" not in hint


def test_env_in_a_save_and_not_closed_names_both(quests_root, project):
    proj = bot(project, gitignore="node_modules\n")
    _git(proj, "add", ".env")
    _git(proj, "commit", "-q", "-m", "сохранил ключ")
    hint = hint_of(check(quests_root, "04-run", proj, env=BOT_ENV), "env_not_saved")
    assert "Убери .env из сохранений и допиши его в .gitignore" in hint


def test_env_in_a_subfolder_is_named_as_the_wrong_place(quests_root, project):
    """`.env` лежит глубже корня — подсказка о месте, а не о ключе."""
    proj = bot(project, env_text=None)
    (proj / "bot").mkdir()
    (proj / "bot" / ".env").write_text("BOT_TOKEN={}\n".format(TOKEN), encoding="utf-8")
    result = check(quests_root, "04-run", proj, env=BOT_ENV)
    assert rows(result) == ["key_in_env"]
    hint = result.checks[0]["hint"]
    assert "в корне папки проекта" in hint and "@BotFather" not in hint
    assert TOKEN not in result.stderr and TOKEN not in str(result.checks)


def test_a_folder_without_git_says_so_in_its_own_line(quests_root, project):
    """Без своего репозитория сохранений нет — строка о git, а не о .gitignore."""
    proj = project(files={"bot.py": BOT_CODE, ".env": "BOT_TOKEN={}\n".format(TOKEN)})
    result = check(quests_root, "04-run", proj, env=BOT_ENV)
    assert rows(result) == ["key_in_env", "repo_exists", "key_not_in_files"]
    assert failed(result) == ["repo_exists"]
    assert "завести git" in hint_of(result, "repo_exists")


def test_an_old_key_written_into_the_code_fails_too(quests_root, project):
    """В коде — любой ключ формы Telegram, не только тот, что в `.env`."""
    old = "5012345678:AAGoLdKeYfRoMlAsTwEeKaBcDeFgHiJkLmN"
    proj = bot(project)
    (proj / "config.py").write_text("TOKEN = '{}'\n".format(old), encoding="utf-8")
    result = check(quests_root, "04-run", proj, env=BOT_ENV)
    assert failed(result) == ["key_not_in_files"]
    assert old not in str(result.checks) and old not in result.stderr


def test_key_written_into_the_code_fails(quests_root, project):
    proj = bot(project)
    (proj / "bot.py").write_text("TOKEN = '{}'\n".format(TOKEN), encoding="utf-8")
    result = check(quests_root, "04-run", proj, env=BOT_ENV)
    assert failed(result) == ["key_not_in_files"]
    hint = next(item for item in result.checks if item["id"] == "key_not_in_files")["hint"]
    assert ".env" in hint


def test_key_in_a_handoff_is_a_leak_too(quests_root, project):
    proj = bot(project)
    (proj / "HANDOFF.md").write_text("Ключ: {}\n".format(TOKEN), encoding="utf-8")
    assert failed(check(quests_root, "04-run", proj, env=BOT_ENV)) == ["key_not_in_files"]


def test_key_saved_once_and_removed_stays_in_the_saves(quests_root, project):
    proj = bot(project)
    (proj / "bot.py").write_text("TOKEN = '{}'\n".format(TOKEN), encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "ключ в коде")
    (proj / "bot.py").write_text(BOT_CODE, encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "ключ из .env")
    result = check(quests_root, "04-run", proj, env=BOT_ENV)
    assert failed(result) == ["key_not_in_saves"]
    hint = result.checks[-1]["hint"]
    assert "@BotFather" in hint and "/revoke" in hint
    assert "переписывать сохранения не нужно" in hint
    assert "Магистр" not in hint
    # Ключ сменили у @BotFather: старый в истории мёртв, новый — в .env.
    new = "7412589630:AAHnEwKeYaFtErReVoKeAbCdEfGhIjKlMn"
    (proj / ".env").write_text("BOT_TOKEN={}\n".format(new), encoding="utf-8")
    assert check(quests_root, "04-run", proj, env=BOT_ENV).ok


def test_the_telegram_key_has_one_form_for_the_whole_game(quests_root):
    """Форма ключа — в `_lib/secrets.sh`; общий образец утечек собран из неё
    и не изменился."""
    lib = quests_root / "_lib" / "secrets.sh"
    done = subprocess.run(
        ["bash", "-c", 'source "$1"; printf "%s\\n%s\\n" "$JC_TELEGRAM_TOKEN_RE" '
         '"$JC_SECRET_RE"', "_", str(lib)],
        capture_output=True, text=True, check=True,
    )
    telegram, secret = done.stdout.splitlines()
    assert telegram == "[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}"
    assert secret == (
        "((^|[^A-Za-z0-9])sk-[A-Za-z0-9]{16,}|(^|[^A-Za-z0-9])sk-(ant|proj)-"
        "[A-Za-z0-9_-]{16,}|(^|[^A-Za-z0-9])(sk|rk)_(live|test)_[A-Za-z0-9]{16,}"
        "|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{22,}|(^|[^A-Za-z0-9])"
        "AKIA[A-Z0-9]{16}|(^|[^A-Za-z0-9])xox[bpasr]-[A-Za-z0-9-]{10,}|"
        "[0-9]{8,10}:AA[A-Za-z0-9_-]{30,})"
    )
    run = (quests_root / "act4-svoy-produkt" / "04-run" / "check.sh").read_text(
        encoding="utf-8")
    assert "JC_TELEGRAM_TOKEN_RE" in run and "{8,10}" not in run


def test_libraries_and_their_folders_are_not_searched(quests_root, project):
    """Библиотеки ставит не человек: ключ в их папках — не его утечка."""
    proj = bot(project, gitignore=".env\n.venv/\nnode_modules/\n__pycache__/\n")
    for folder in (".venv", "node_modules", "__pycache__"):
        (proj / folder).mkdir()
        (proj / folder / "cache.txt").write_text(TOKEN, encoding="utf-8")
    assert check(quests_root, "04-run", proj, env=BOT_ENV).ok


def test_unreadable_env_cannot_be_judged(quests_root, project):
    if os.geteuid() == 0:
        pytest.skip("root читает любой файл")
    proj = bot(project)
    (proj / ".env").chmod(0)
    try:
        result = check(quests_root, "04-run", proj, env=BOT_ENV)
    finally:
        (proj / ".env").chmod(0o600)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_the_type_cannot_be_given_by_the_shell(quests_root, project, monkeypatch):
    """Тип продукта приходит только от команды игры: приставка не в счёт."""
    monkeypatch.setenv("JEDICODER_PRODUCT_TYPE", "bot")
    result = check(quests_root, "04-run", bot(project))
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


@pytest.mark.parametrize("quest_id", ["01-what", "02-plan", "03-build", "04-run"])
def test_every_check_bails_without_a_named_folder(quests_root, project, quest_id):
    result = check(quests_root, quest_id, project(), recorded=False)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


# --- общий контракт ---------------------------------------------------------------

def test_act4_checks_survive_hostile_locale_and_mawk(quests_root, project):
    """Кириллица в IDEA.md находится и при LC_ALL=C, и на mawk."""
    proj = idea(project, PRODUCT_BOT)
    env = {"LC_ALL": "C"}
    if shutil.which("mawk") is not None:
        bin_dir = proj.parent / "mawkbin"
        bin_dir.mkdir(exist_ok=True)
        stub = bin_dir / "awk"
        stub.write_text('#!/bin/sh\nexec mawk "$@"\n', encoding="utf-8")
        stub.chmod(0o755)
        env["PATH"] = "{}:{}".format(bin_dir, os.environ["PATH"])
    assert check(quests_root, "01-what", proj, env=env).ok
    (proj / "IDEA.md").write_text(PRODUCT_SITE_NO_DONE, encoding="utf-8")
    assert failed(check(quests_root, "01-what", proj, env=env)) == ["product_done"]
    steps = [({"заметки.md": "1\n"}, 10), ({"план.MD": "2\n"}, 20),
             ({"расписание.html": "<table></table>\n"}, 30)]
    build = dict(env, **build_env())
    assert check(quests_root, "03-build", built(project, steps), env=build).ok
    steps[2] = ({"итог.md": "3\n"}, 30)
    assert failed(check(quests_root, "03-build", built(project, steps),
                        env=build)) == ["code_saved"]
    text = 'TELEGRAM_BOT_TOKEN="{}"\n'.format(TOKEN)
    assert check(quests_root, "04-run", bot(project, env_text=text),
                 env=dict(env, **BOT_ENV)).ok
    assert failed(check(quests_root, "04-run", bot(project, gitignore="x\n"),
                        env=dict(env, **BOT_ENV))) == ["env_not_saved"]


def test_checks_never_touch_the_project(quests_root, project):
    proj = idea(project, PRODUCT_BOT)
    before = sorted(
        (path.name, path.read_bytes()) for path in proj.rglob("*") if path.is_file()
    )
    for quest_id in ("01-what", "02-plan", "03-build", "04-run"):
        check(quests_root, quest_id, proj, env=plan_env(1, 0))
    after = sorted(
        (path.name, path.read_bytes()) for path in proj.rglob("*") if path.is_file()
    )
    assert after == before


def test_build_and_run_never_touch_the_project(quests_root, project):
    """Сохранения, `.env` и `.gitignore` — ровно такие, как до проверки."""
    proj = bot(project)

    def snapshot():
        return sorted(
            (str(path.relative_to(proj)), path.read_bytes())
            for path in proj.rglob("*") if path.is_file()
        )

    before = snapshot()
    for env in (BOT_ENV, site_env(free_port()), site_env(), build_env(), {}):
        check(quests_root, "03-build", proj, env=env)
        check(quests_root, "04-run", proj, env=env)
    assert snapshot() == before

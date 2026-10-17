"""Проверки Акта 5 «Три места кода» (спека jedicoder.store#123, тикеты #124, #125).

GitHub в тестах недостижим и не нужен: `curl` подменяется стабом в PATH (как
`ssh` у полок — `tests/fake_ssh.py`), и стаб отвечает тем кодом HTTP, какой
задал тест. Ответы взяты из живого замера 2026-10-16
(`docs/research/2026-10-16-act5-facts.md`): закрытое хранилище без входа —
404, открытое — 200, лимит запросов без входа — 403. Стаб записывает, с
какими аргументами его позвали: адрес API, таймауты, прокси.

Отправка на GitHub сеется локально: ветку `origin/<ветка>` git заводит после
удачной отправки, тест кладёт её `git update-ref` — сеть не нужна, дверь та же.

«Одна версия» и «Чужой сервис» (#125) в сеть не ходят вовсе: первая сравнивает
`HEAD` с веткой `origin/<ветка>`, вторая ищет ключи в папке и в истории.
Сквозной проход с отправкой в голую копию — tests/test_act5_walkthrough.py.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import _git
from jedicoder import quests

ACT = "act5-tri-mesta"

#: Стаб `curl`: аргументы — построчно в файл, ответ — тело и код из FAKE_CURL,
#: как их печатает настоящий `curl -w '\n%{http_code}'`. Тела 404 и 200 — по
#: замеру (`{"message": "Not Found", …}`, `"private": false`). `down` — сети
#: нет (код 000 и выход 6, как у настоящего curl без DNS); `portal` и
#: `portal404` — страница входа гостевого Wi-Fi вместо GitHub; `private200` —
#: ответ, какой бывает только со входом.
FAKE_CURL = """#!/usr/bin/env bash
printf '%s\\n' "$@" > "$FAKE_CURL_LOG"
case "${FAKE_CURL:-404}" in
  down) printf '\\n000'; exit 6 ;;
  slow) printf '\\n000'; exit 28 ;;
  404) printf '{\\n  "message": "Not Found",\\n  "status": "404"\\n}\\n404' ;;
  200) printf '{\\n  "full_name": "padawan/kruzhok",\\n  "private": false,\\n  "visibility": "public"\\n}\\n200' ;;
  private200) printf '{\\n  "full_name": "padawan/kruzhok",\\n  "private": true\\n}\\n200' ;;
  portal) printf '<html><body>Войдите в сеть Wi-Fi</body></html>\\n200' ;;
  portal404) printf '<html><body>Not here</body></html>\\n404' ;;
  *) printf '{"message": "something"}\\n%s' "$FAKE_CURL" ;;
esac
"""


@pytest.fixture
def fake_github(tmp_path, monkeypatch):
    """Подложить стаб `curl` первым в PATH. Отдаёт функцию: задать ответ и
    узнать, с какими аргументами стаб позвали (None — не звали вовсе)."""
    bin_dir = tmp_path / "fakecurl"
    bin_dir.mkdir()
    stub = bin_dir / "curl"
    stub.write_text(FAKE_CURL, encoding="utf-8")
    stub.chmod(0o755)
    log = tmp_path / "curl-args.txt"
    monkeypatch.setenv("PATH", "{}{}{}".format(bin_dir, os.pathsep, os.environ["PATH"]))
    monkeypatch.setenv("FAKE_CURL_LOG", str(log))

    class Github:
        def answer(self, code):
            monkeypatch.setenv("FAKE_CURL", str(code))

        def called_with(self):
            if not log.exists():
                return None
            return log.read_text(encoding="utf-8").splitlines()

    github = Github()
    github.answer(404)
    return github


def check(quests_root, proj, quest="02-private", env=None):
    extra = {"JEDICODER_PROJECT_PATH": str(proj)}
    extra.update(env or {})
    return quests.run_check(quests_root, ACT, quest, proj, env_extra=extra)


def branch(proj):
    import subprocess

    return subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"], cwd=str(proj),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def link(proj, url="https://github.com/padawan/kruzhok.git", pushed=True):
    """Claude связал проект с хранилищем и (если `pushed`) отправил код."""
    _git(proj, "remote", "add", "origin", url)
    if pushed:
        _git(proj, "update-ref", "refs/remotes/origin/{}".format(branch(proj)), "HEAD")


def rows(result):
    return [(row["id"], row["ok"]) for row in result.checks]


def api_url(github):
    args = github.called_with()
    assert args is not None, "GitHub не спрашивали"
    return args[-1]


# --- адрес origin -------------------------------------------------------------

def test_without_a_named_folder_the_check_cannot_judge(quests_root, project, fake_github):
    proj = project(git=True, commits=1)
    result = quests.run_check(quests_root, ACT, "02-private", proj)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "папка проекта не названа" in result.stderr


def test_without_origin_the_first_line_fails_and_nothing_else_is_asked(
        quests_root, project, fake_github):
    proj = project(git=True, commits=1)
    result = check(quests_root, proj)
    assert result.ok is False and result.countable is True
    assert rows(result) == [("on_github", False)]
    assert "закрытое хранилище" in result.checks[0]["hint"]
    assert fake_github.called_with() is None


def test_a_folder_without_git_is_not_on_github(quests_root, project, fake_github):
    proj = project(files={"index.html": "<h1>Радуга</h1>\n"})
    result = check(quests_root, proj)
    assert result.ok is False and rows(result) == [("on_github", False)]


@pytest.mark.parametrize("url", [
    # Долг №16: локальная папка с github.com в пути — не GitHub.
    "/tmp/github.com/padawan/kruzhok.git",
    "file:///tmp/github.com/padawan/kruzhok.git",
    "../github.com/padawan/kruzhok",
    "https://gitlab.com/padawan/kruzhok.git",
    "git@gitlab.com:padawan/kruzhok.git",
    "https://github.com.evil.example/padawan/kruzhok.git",
    # Псевдоним хоста из ~/.ssh/config проверка не разбирает (ревью #124).
    "git@github-work:padawan/kruzhok.git",
    "https://github.com/padawan",
    "https://github.com/",
])
def test_an_origin_that_is_not_a_github_repository_is_refused(
        quests_root, project, fake_github, url):
    proj = project(git=True, commits=1)
    link(proj, url)
    result = check(quests_root, proj)
    assert result.ok is False
    assert rows(result) == [("on_github", False)]
    assert fake_github.called_with() is None


@pytest.mark.parametrize("url", [
    "https://github.com/padawan/kruzhok.git",
    "https://github.com/padawan/kruzhok",
    "https://github.com/padawan/kruzhok/",
    "https://GitHub.com/padawan/kruzhok.git",
    "https://www.github.com/padawan/kruzhok.git",
    "http://github.com/padawan/kruzhok.git",
    "https://padawan@github.com/padawan/kruzhok.git",
    "git@github.com:padawan/kruzhok.git",
    "git@github.com:padawan/kruzhok",
    "ssh://git@github.com/padawan/kruzhok.git",
    "ssh://git@github.com:22/padawan/kruzhok.git",
    # ssh через порт 443 — когда порт 22 закрыт сетью.
    "ssh://git@ssh.github.com:443/padawan/kruzhok.git",
])
def test_every_form_of_a_github_address_leads_to_the_same_repository(
        quests_root, project, fake_github, url):
    proj = project(git=True, commits=1)
    link(proj, url)
    result = check(quests_root, proj)
    assert result.ok is True, (url, result.checks, result.stderr)
    assert api_url(fake_github) == "https://api.github.com/repos/padawan/kruzhok"


def test_names_with_dots_dashes_and_underscores_are_kept(quests_root, project, fake_github):
    proj = project(git=True, commits=1)
    link(proj, "git@github.com:Padawan-42/my_site.v2.git")
    assert check(quests_root, proj).ok is True
    assert api_url(fake_github) == "https://api.github.com/repos/Padawan-42/my_site.v2"


def test_a_key_in_the_address_is_never_printed(quests_root, project, fake_github):
    """Адрес с ключом перед `@` — ключ срезается и не звучит нигде."""
    secret = "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
    proj = project(git=True, commits=1)
    link(proj, "https://padawan:{}@github.com/padawan/kruzhok.git".format(secret))
    for answer in (404, 200, 403, "down"):
        fake_github.answer(answer)
        result = check(quests_root, proj)
        assert secret not in result.stderr
        assert secret not in repr(result.checks)
        assert secret not in "\n".join(fake_github.called_with())


# --- отправка -------------------------------------------------------------------

def test_not_pushed_yet_the_second_line_fails_and_github_is_not_asked(
        quests_root, project, fake_github):
    proj = project(git=True, commits=1)
    link(proj, pushed=False)
    result = check(quests_root, proj)
    assert result.ok is False
    assert rows(result) == [("on_github", True), ("pushed", False)]
    assert result.checks[1]["label"] == "Код отправлен в хранилище padawan/kruzhok"
    assert "Отправь код на GitHub" in result.checks[1]["hint"]
    assert fake_github.called_with() is None


def test_another_branch_on_github_is_not_this_one(quests_root, project, fake_github):
    proj = project(git=True, commits=1)
    link(proj, pushed=False)
    _git(proj, "update-ref", "refs/remotes/origin/other", "HEAD")
    result = check(quests_root, proj)
    assert rows(result) == [("on_github", True), ("pushed", False)]


def test_a_detached_head_counts_any_branch_on_github(quests_root, project, fake_github):
    proj = project(git=True, commits=2)
    link(proj)
    _git(proj, "checkout", "-q", "--detach", "HEAD~1")
    assert check(quests_root, proj).ok is True


# --- закрытое или открытое: ответ GitHub без входа ------------------------------

def test_a_private_repository_passes(quests_root, project, fake_github):
    """Приёмка тикета: закрытое — GitHub без входа отвечает 404, квест закрыт."""
    proj = project(git=True, commits=1)
    link(proj)
    fake_github.answer(404)
    result = check(quests_root, proj)
    assert result.exit_code == quests.EXIT_PASS and result.ok is True
    assert rows(result) == [("on_github", True), ("pushed", True), ("private", True)]
    assert [row["label"] for row in result.checks] == [
        "Проект связан с хранилищем на GitHub",
        "Код отправлен в хранилище padawan/kruzhok",
        "Хранилище закрытое: чужие его не видят",
    ]


def test_a_public_repository_fails_with_a_way_to_close_it(quests_root, project, fake_github):
    """Приёмка тикета: открытое — 200, провал с подсказкой, попытка в счёт."""
    proj = project(git=True, commits=1)
    link(proj)
    fake_github.answer(200)
    result = check(quests_root, proj)
    assert result.exit_code == quests.EXIT_FAIL
    assert result.ok is False and result.countable is True
    assert rows(result) == [("on_github", True), ("pushed", True), ("private", False)]
    hint = result.checks[2]["hint"]
    assert "открытое" in hint and "Сделай хранилище на GitHub закрытым" in hint
    assert "Change visibility" in hint


@pytest.mark.parametrize("answer, words", [
    ("down", "не достучался до GitHub"),
    # Код без тела GitHub — отвечал не он: страница входа гостевого Wi-Fi
    # (ревью #124). Открытым или закрытым такой ответ не считается.
    ("portal", "ответил не GitHub"),
    ("portal404", "ответил не GitHub"),
    ("private200", "ответил не GitHub"),
    ("slow", "не достучался до GitHub"),
    (403, "не чаще 60 раз в час"),
    (429, "не чаще 60 раз в час"),
    (500, "код 500"),
    (301, "код 301"),
])
def test_no_network_or_a_strange_answer_cannot_judge(
        quests_root, project, fake_github, answer, words):
    """Приёмка тикета: нет сети или GitHub ответил иначе — «не смог проверить»."""
    proj = project(git=True, commits=1)
    link(proj)
    fake_github.answer(answer)
    result = check(quests_root, proj)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False
    assert words in result.stderr


def test_without_curl_the_check_cannot_judge(quests_root, project, tmp_path, monkeypatch):
    """Приёмка тикета: нет `curl` — «не смог проверить», а не провал."""
    proj = project(git=True, commits=1)
    link(proj)
    bin_dir = tmp_path / "nocurl"
    bin_dir.mkdir()
    for name in ("bash", "git", "locale", "grep", "head", "tr", "dirname", "cat"):
        found = shutil.which(name)
        assert found, name
        (bin_dir / name).symlink_to(found)
    monkeypatch.setenv("PATH", str(bin_dir))
    result = check(quests_root, proj)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "не найден curl" in result.stderr


def test_the_question_to_github_has_timeouts_and_keeps_the_proxy(
        quests_root, project, fake_github):
    """Таймауты обязательны; `--noproxy` нет: API GitHub — внешний адрес, и
    прокси человека ему нужен (в отличие от `localhost` Акта 4). Вход не
    передаётся: игра спрашивает так, как спросил бы чужой."""
    proj = project(git=True, commits=1)
    link(proj)
    check(quests_root, proj)
    args = fake_github.called_with()
    assert "--connect-timeout" in args and "--max-time" in args
    assert not any(arg.startswith("--noproxy") for arg in args)
    assert not any("Authorization" in arg or arg in ("-u", "--user") for arg in args)
    assert "-L" in args
    # `-q` первым: `~/.curlrc` с ключом входа не читается (ревью #124).
    assert args[0] == "-q"


def test_the_answer_does_not_depend_on_the_locale(quests_root, project, fake_github, monkeypatch):
    proj = project(git=True, commits=1)
    link(proj, "git@github.com:padawan/kruzhok.git")
    monkeypatch.setenv("LC_ALL", "C")
    assert check(quests_root, proj).ok is True
    fake_github.answer(200)
    assert check(quests_root, proj).ok is False


def test_the_check_never_touches_the_project(quests_root, project, fake_github):
    import subprocess

    proj = project(git=True, commits=1)
    link(proj)
    before = subprocess.run(
        ["git", "status", "--porcelain", "--ignored"], cwd=str(proj),
        capture_output=True, text=True, check=True,
    ).stdout
    refs = subprocess.run(
        ["git", "for-each-ref"], cwd=str(proj), capture_output=True, text=True,
        check=True,
    ).stdout
    for answer in (404, 200, "down"):
        fake_github.answer(answer)
        check(quests_root, proj)
    assert subprocess.run(
        ["git", "status", "--porcelain", "--ignored"], cwd=str(proj),
        capture_output=True, text=True, check=True,
    ).stdout == before
    assert subprocess.run(
        ["git", "for-each-ref"], cwd=str(proj), capture_output=True, text=True,
        check=True,
    ).stdout == refs


# --- «Одна версия» ----------------------------------------------------------------
#
# Сохранения датируются относительно момента входа в акт: прежние вечера — за
# сутки до него, правка этого квеста — после. Отправку на GitHub сеет
# `git update-ref`, как и в «Приватном репозитории»: ветку `origin/<ветка>`
# git двигает при удачной отправке.

#: Момент входа в акт в тестах «Одной версии» и «Чужого сервиса».
STARTED = 1790000000


def act_env(started=STARTED):
    return {"JEDICODER_ACT_STARTED": str(started)}


def save(proj, files, at, message="правка"):
    """Claude сохранил правку: файлы и коммит с датой автора `at`."""
    for name, text in files.items():
        target = proj / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    stamp = "{} +0000".format(at)
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    for argv in (["git", "add", "-A"], ["git", "commit", "-q", "-m", message]):
        subprocess.run(argv, cwd=str(proj), check=True, capture_output=True, env=env)


def push(proj):
    """Отправка на GitHub: git сдвинул ветку `origin/<ветка>` на HEAD."""
    _git(proj, "update-ref", "refs/remotes/origin/{}".format(branch(proj)), "HEAD")


def on_github(project):
    """Проект прежних вечеров уже на GitHub — квест «Приватный репозиторий»
    закрыт: `origin` смотрит на GitHub, отправка была до входа в акт."""
    proj = project(gitignore=".env\n", git=True)
    save(proj, {"index.html": "<h1>Кружок</h1>\n"}, STARTED - 86400, "сайт")
    link(proj, "git@github.com:padawan/kruzhok.git", pushed=False)
    push(proj)
    return proj


def synced(project):
    """Мелочь поправлена, сохранена и отправлена после входа в акт."""
    proj = on_github(project)
    save(proj, {"index.html": "<h1>Кружок «Радуга»</h1>\n"}, STARTED + 60)
    push(proj)
    return proj


def sync(quests_root, proj, env=None):
    return check(quests_root, proj, "03-sync", env=dict(act_env(), **(env or {})))


def test_one_version_passes_after_a_fix_saved_and_sent(quests_root, project):
    """Приёмка тикета: правка после входа, сохранена, отправлена, папка чистая."""
    result = sync(quests_root, synced(project))
    assert result.exit_code == quests.EXIT_PASS, (result.checks, result.stderr)
    assert rows(result) == [
        ("saved_after_entry", True), ("nothing_unsaved", True), ("same_version", True),
    ]
    assert [row["label"] for row in result.checks] == [
        "После входа в акт есть новое сохранение",
        "Несохранённых правок нет",
        "На GitHub та же версия, что на компьютере",
    ]


def test_without_a_save_after_entry_only_the_first_line_speaks(quests_root, project):
    """Сохранения прежних вечеров не в счёт — даже отправленные."""
    proj = on_github(project)
    result = sync(quests_root, proj)
    assert result.ok is False and result.countable is True
    assert rows(result) == [("saved_after_entry", False)]
    assert "Сделай коммит и отправь на GitHub" in result.checks[0]["hint"]


def test_a_fix_without_a_save_is_not_one_version(quests_root, project):
    """Поправил, но не сохранил — сохранения после входа нет."""
    proj = on_github(project)
    (proj / "index.html").write_text("<h1>Новое</h1>\n", encoding="utf-8")
    assert rows(sync(quests_root, proj)) == [("saved_after_entry", False)]


@pytest.mark.parametrize("change", ["edit", "new_file", "staged"])
def test_unsaved_changes_after_the_save_fail_the_second_line(quests_root, project, change):
    proj = synced(project)
    if change == "edit":
        (proj / "index.html").write_text("<h1>Ещё правка</h1>\n", encoding="utf-8")
    elif change == "new_file":
        (proj / "style.css").write_text("h1 { color: teal }\n", encoding="utf-8")
    else:
        (proj / "style.css").write_text("h1 { color: teal }\n", encoding="utf-8")
        _git(proj, "add", "style.css")
    result = sync(quests_root, proj)
    assert result.ok is False
    assert rows(result) == [("saved_after_entry", True), ("nothing_unsaved", False)]
    assert "Сделай коммит и отправь на GitHub" in result.checks[1]["hint"]


def test_the_closed_env_is_not_an_unsaved_change(quests_root, project):
    """`.env` закрыт от сохранений: git его не показывает, правок нет."""
    proj = synced(project)
    (proj / ".env").write_text("WEATHER_API_KEY=3f2a9c1d7e5b4a6f8c0d2e4f6a8b0c1d\n",
                               encoding="utf-8")
    assert sync(quests_root, proj).ok is True


@pytest.mark.parametrize("state, words", [
    ("not_sent", "Последнее сохранение ещё не на GitHub. Скажи Claude: «Отправь на GitHub»."),
    ("never_sent", "Этой версии на GitHub ещё нет. Скажи Claude: «Отправь на GitHub»."),
    ("github_newer", "На GitHub версия новее, чем на компьютере. Скажи Claude: "
                     "«Скачай последнюю версию с GitHub»."),
    ("diverged", "Версии на компьютере и на GitHub разошлись. Скажи Claude: "
                 "«Сведи версии на компьютере и на GitHub в одну»."),
    ("old_save", "Сейчас открыто старое сохранение, а не последняя версия. "
                 "Скажи Claude: «Вернись к последней версии»."),
])
def test_another_version_on_github_says_what_differs(quests_root, project, state, words):
    if state == "never_sent":
        proj = project(gitignore=".env\n", git=True)
        save(proj, {"index.html": "<h1>Кружок</h1>\n"}, STARTED + 60)
        link(proj, "git@github.com:padawan/kruzhok.git", pushed=False)
    else:
        proj = synced(project)
    if state == "not_sent":
        save(proj, {"index.html": "<h1>Ещё</h1>\n"}, STARTED + 120)
    elif state == "github_newer":
        save(proj, {"index.html": "<h1>С сайта GitHub</h1>\n"}, STARTED + 120)
        push(proj)
        _git(proj, "reset", "-q", "--hard", "HEAD~1")
    elif state == "diverged":
        save(proj, {"about.html": "<p>С сайта GitHub</p>\n"}, STARTED + 120)
        push(proj)
        _git(proj, "reset", "-q", "--hard", "HEAD~1")
        save(proj, {"index.html": "<h1>С компьютера</h1>\n"}, STARTED + 180)
    elif state == "old_save":
        save(proj, {"index.html": "<h1>Ещё</h1>\n"}, STARTED + 120)
        push(proj)
        _git(proj, "checkout", "-q", "--detach", "HEAD~1")
    result = sync(quests_root, proj)
    assert result.ok is False and result.countable is True
    assert rows(result) == [
        ("saved_after_entry", True), ("nothing_unsaved", True), ("same_version", False),
    ]
    assert result.checks[2]["hint"] == words


def track(proj, remote_branch):
    """`git push -u origin <ветка>:<remote_branch>`: текущая следит за ней."""
    name = branch(proj)
    _git(proj, "config", "branch.{}.remote".format(name), "origin")
    _git(proj, "config", "branch.{}.merge".format(name), "refs/heads/" + remote_branch)


def test_one_version_compares_with_the_branch_it_tracks(quests_root, project):
    """Текущая следит за веткой `origin/main` — сравнение с ней, а не с
    одноимённой: у `git push -u origin master:main` одноимённой нет."""
    proj = on_github(project)
    save(proj, {"index.html": "<h1>Радуга</h1>\n"}, STARTED + 60)
    _git(proj, "update-ref", "refs/remotes/origin/main", "HEAD")
    track(proj, "main")
    assert sync(quests_root, proj).ok is True
    # Одноимённая на GitHub совпадает, а та, за которой следит, — нет.
    save(proj, {"index.html": "<h1>Ещё</h1>\n"}, STARTED + 120)
    push(proj)
    result = sync(quests_root, proj)
    assert rows(result)[2] == ("same_version", False)
    assert "ещё не на GitHub" in result.checks[2]["hint"]


def test_a_tracked_branch_not_on_origin_falls_back_to_origin(quests_root, project):
    """Следит не за GitHub (ветка на этом же компьютере) — судит `origin`."""
    proj = synced(project)
    _git(proj, "config", "branch.{}.remote".format(branch(proj)), ".")
    _git(proj, "config", "branch.{}.merge".format(branch(proj)), "refs/heads/nowhere")
    assert sync(quests_root, proj).ok is True


@pytest.mark.parametrize("saved, words", [
    (False, "Файл .env не закрыт от сохранений, а это файл для ключей. Попроси "
            "Claude: «Закрой .env от сохранений — допиши его в .gitignore»."),
    (True, "Файл .env уже в сохранениях, а это файл для ключей. Попроси Claude: "
           "«Убери .env из сохранений и допиши его в .gitignore»."),
])
def test_an_unsaved_env_says_to_close_it_not_to_save_it(quests_root, project, saved, words):
    """`.env` среди несохранённого — не «сделай коммит»: его закрывают."""
    proj = synced(project)
    save(proj, {".gitignore": "node_modules\n"}, STARTED + 120)
    if saved:
        save(proj, {".env": "WEATHER_API_KEY=old\n"}, STARTED + 150)
    push(proj)
    (proj / ".env").write_text(
        "WEATHER_API_KEY=3f2a9c1d7e5b4a6f8c0d2e4f6a8b0c1d\n", encoding="utf-8")
    result = sync(quests_root, proj)
    assert rows(result) == [("saved_after_entry", True), ("nothing_unsaved", False)]
    assert result.checks[1]["hint"] == words


def test_one_version_does_not_rewrite_the_index(quests_root, project):
    """`git status` обновил бы индекс, увидев файл с новой датой. Проверка
    проект не меняет: статус — с `--no-optional-locks`."""
    import time

    proj = synced(project)
    index = proj / ".git" / "index"
    before = index.read_bytes()
    later = time.time() + 3600
    os.utime(str(proj / "index.html"), (later, later))
    assert sync(quests_root, proj).ok is True
    assert index.read_bytes() == before


def test_one_version_without_the_moment_of_entry_cannot_judge(quests_root, project):
    proj = synced(project)
    result = check(quests_root, proj, "03-sync")
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "когда начался этот акт" in result.stderr


def test_one_version_without_a_named_folder_cannot_judge(quests_root, project):
    proj = synced(project)
    result = quests.run_check(quests_root, ACT, "03-sync", proj, env_extra=act_env())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "папка проекта не названа" in result.stderr


def test_one_version_in_a_folder_without_git_says_so(quests_root, project):
    proj = project(files={"index.html": "<h1>Радуга</h1>\n"})
    result = sync(quests_root, proj)
    assert result.ok is False
    assert rows(result) == [("repo_exists", False)]


def test_one_version_never_fetches_or_touches_the_project(quests_root, project):
    """Без `fetch`: проверка не меняет проект и не ходит в сеть — `origin`
    здесь ведёт в никуда, и `fetch` упал бы."""
    proj = synced(project)
    _git(proj, "remote", "set-url", "origin", "git@github.com:padawan/nowhere.git")
    before = [
        subprocess.run(argv, cwd=str(proj), capture_output=True, text=True,
                       check=True).stdout
        for argv in (["git", "status", "--porcelain", "--ignored"],
                     ["git", "for-each-ref"])
    ]
    assert sync(quests_root, proj).ok is True
    after = [
        subprocess.run(argv, cwd=str(proj), capture_output=True, text=True,
                       check=True).stdout
        for argv in (["git", "status", "--porcelain", "--ignored"],
                     ["git", "for-each-ref"])
    ]
    assert after == before


# --- «Чужой сервис» ---------------------------------------------------------------
#
# Ключи выдуманные, по форме настоящих: ключ сервиса погоды — 32 знака
# шестнадцатеричной записи, ключ бота — по форме Telegram, ключ OpenAI — `sk-…`.

WEATHER_KEY = "3f2a9c1d7e5b4a6f8c0d2e4f6a8b0c1d"
BOT_TOKEN = "7412589630:AAHfAkEkEyFoRtEsTsOnLy_abcdefghijklmn"
OPENAI_KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUv0123456789"

WEATHER_CODE = (
    "import os\n"
    "KEY = os.environ['WEATHER_API_KEY']\n"
    "URL = 'https://api.openweathermap.org/data/2.5/weather'\n"
)


def service(project, env_text="WEATHER_API_KEY={}\n".format(WEATHER_KEY),
            gitignore=".env\n", files=None):
    """Сервис подключён: код сохранён, ключ лежит в `.env` (не в сохранениях)."""
    proj = project(gitignore=gitignore, git=True)
    save(proj, dict({"weather.py": WEATHER_CODE}, **(files or {})), STARTED + 60,
         "погода")
    if env_text is not None:
        (proj / ".env").write_text(env_text, encoding="utf-8")
    return proj


def keys(quests_root, proj, env=None):
    return check(quests_root, proj, "04-service", env=dict(act_env(), **(env or {})))


ALL_CLEAR = [("env_not_saved", True), ("no_keys_in_files", True), ("no_keys_in_saves", True)]


def test_a_service_with_its_key_only_in_env_passes(quests_root, project):
    """Приёмка тикета: ключ в `.env`, `.env` закрыт, ключа нет ни в файлах, ни
    в сохранениях."""
    result = keys(quests_root, service(project))
    assert result.exit_code == quests.EXIT_PASS, (result.checks, result.stderr)
    assert rows(result) == ALL_CLEAR
    assert [row["label"] for row in result.checks] == [
        "Файл .env не попадает в сохранения и на GitHub",
        "Ключей нет в коде и в других файлах",
        "Ключей нет в сохранениях",
    ]


@pytest.mark.parametrize("env_text", [None, "", "# ключ потом\n\n"])
def test_a_service_without_a_key_is_judged_only_for_leaks(quests_root, project, env_text):
    """Сервис без ключа — законно: строки о `.env` нет, судится одно — ключей
    нет нигде."""
    result = keys(quests_root, service(project, env_text=env_text))
    assert result.ok is True, (result.checks, result.stderr)
    assert rows(result) == [("no_keys_in_files", True), ("no_keys_in_saves", True)]


def test_an_env_open_to_saves_fails_first_and_alone(quests_root, project):
    proj = service(project, gitignore="node_modules\n")
    result = keys(quests_root, proj)
    assert result.ok is False and result.countable is True
    assert rows(result) == [("env_not_saved", False)]
    assert "допиши его в .gitignore" in result.checks[0]["hint"]


@pytest.mark.parametrize("ignored, words", [
    (True, "Убери .env из сохранений, сам файл оставь"),
    (False, "Убери .env из сохранений и допиши его в .gitignore"),
])
def test_an_env_already_saved_says_how_to_take_it_out(quests_root, project, ignored, words):
    proj = service(project, gitignore=".env\n" if ignored else "node_modules\n")
    _git(proj, "add", "-f", ".env")
    _git(proj, "commit", "-q", "-m", "случайно сохранил env")
    result = keys(quests_root, proj)
    assert rows(result) == [("env_not_saved", False)]
    assert "уже в сохранениях" in result.checks[0]["hint"]
    assert words in result.checks[0]["hint"]


@pytest.mark.parametrize("where", ["new_file", "saved_file", "env_example"])
def test_a_key_from_env_written_into_a_file_fails(quests_root, project, where):
    """Ключ из `.env` — в коде: в новом файле, в сохранённом, в примере `.env`."""
    proj = service(project)
    leak = "KEY = '{}'\n".format(WEATHER_KEY)
    if where == "new_file":
        (proj / "weather2.py").write_text(leak, encoding="utf-8")
    elif where == "saved_file":
        save(proj, {"weather2.py": leak}, STARTED + 120)
    else:
        save(proj, {".env.example": "WEATHER_API_KEY={}\n".format(WEATHER_KEY)},
             STARTED + 120)
    result = keys(quests_root, proj)
    assert result.ok is False
    assert rows(result) == [("env_not_saved", True), ("no_keys_in_files", False)]
    hint = result.checks[1]["hint"]
    # Подсказка называет файл — имя не секрет; сам ключ — нет.
    name = ".env.example" if where == "env_example" else "weather2.py"
    assert hint == ("Ключ лежит здесь: {}. Попроси Claude: «Убери ключ из кода — "
                    "пусть код берёт его из .env».".format(name))
    assert WEATHER_KEY not in hint


def test_a_key_in_many_files_names_three_and_counts_the_rest(quests_root, project):
    proj = service(project)
    for number in range(5):
        (proj / "leak{}.py".format(number)).write_text(
            "K = '{}'\n".format(WEATHER_KEY), encoding="utf-8")
    hint = keys(quests_root, proj).checks[1]["hint"]
    assert hint.startswith("Ключ лежит здесь: leak0.py, leak1.py, leak2.py и ещё 2.")


def test_a_key_in_the_page_of_a_site_says_to_choose_a_service_without_a_key(
        quests_root, project):
    """У сайта нет своей программы: «пусть код берёт ключ из .env» ему не
    выполнить — ключ в странице видит каждый."""
    page = "<script>fetch('https://api.example/w?appid={}')</script>\n".format(WEATHER_KEY)
    proj = service(project, files={"index.html": page})
    result = keys(quests_root, proj, env={"JEDICODER_PRODUCT_TYPE": "site"})
    assert rows(result) == [("env_not_saved", True), ("no_keys_in_files", False)]
    hint = result.checks[1]["hint"]
    assert hint.startswith("Ключ лежит здесь: index.html. Страницу видит каждый")
    assert "«Подключи сервис без ключа»" in hint and "/jedicoder:magistr" in hint
    assert ".env" not in hint and WEATHER_KEY not in hint


def test_a_key_shaped_string_in_the_code_fails_even_without_env(quests_root, project):
    proj = service(project, env_text=None,
                   files={"bot.py": "TOKEN = '{}'\n".format(BOT_TOKEN)})
    result = keys(quests_root, proj)
    assert rows(result) == [("no_keys_in_files", False)]


@pytest.mark.parametrize("example", [
    # Заглушка в `.env` и в примере — одна и та же: это не ключ.
    "WEATHER_API_KEY=your_api_key_here\n",
    # Адрес API и город — не ключи: Claude кладёт их и в пример, и в код.
    "WEATHER_URL=https://api.openweathermap.org/data/2.5/weather\nCITY=Ufa\n",
    # Адрес с «токеном» в имени — всё равно адрес, а не ключ (ревью #125).
    "TOKEN_URL=https://oauth.example.com/v2/token\n",
])
def test_values_that_are_not_keys_may_repeat_in_the_files(quests_root, project, example):
    env_text = example + "WEATHER_API_KEY_REAL={}\n".format(WEATHER_KEY)
    proj = service(project, env_text=env_text,
                   files={".env.example": example, "config.py": example})
    assert keys(quests_root, proj).ok is True


@pytest.mark.parametrize("line", [
    'export WEATHER_API_KEY="{}"\n',
    "WEATHER_API_KEY='{}'\n",
    "WEATHER_API_KEY = {}   # ключ погоды\n",
    "WEATHER_API_KEY={}\r\n",
    "weather_api_key={}",
])
def test_every_way_of_writing_a_key_in_env_is_understood(quests_root, project, line):
    proj = service(project, env_text=line.format(WEATHER_KEY),
                   files={"leak.txt": "ключ: {}\n".format(WEATHER_KEY)})
    assert rows(keys(quests_root, proj))[1] == ("no_keys_in_files", False)


def test_a_key_in_the_saves_fails_the_last_line(quests_root, project):
    """Ключ сохранили и потом убрали из кода — в истории он остался, а с ней
    уехал и на GitHub."""
    proj = service(project)
    save(proj, {"weather2.py": "KEY = '{}'\n".format(WEATHER_KEY)}, STARTED + 120)
    save(proj, {"weather2.py": "import os\n"}, STARTED + 180)
    result = keys(quests_root, proj)
    assert result.ok is False and result.countable is True
    assert rows(result) == ALL_CLEAR[:2] + [("no_keys_in_saves", False)]
    hint = result.checks[2]["hint"]
    assert "новый ключ" in hint and "переписывать сохранения не нужно" in hint
    assert WEATHER_KEY not in hint


def test_an_env_saved_once_and_taken_out_leaves_its_key_in_the_saves(quests_root, project):
    proj = service(project)
    _git(proj, "add", "-f", ".env")
    _git(proj, "commit", "-q", "-m", "случайно")
    _git(proj, "rm", "-q", "--cached", ".env")
    _git(proj, "commit", "-q", "-m", "убрал .env")
    assert rows(keys(quests_root, proj)) == ALL_CLEAR[:2] + [("no_keys_in_saves", False)]


def test_a_revoked_key_left_in_the_saves_does_not_fail(quests_root, project):
    """В истории ищется только нынешний ключ из `.env`, как в «Работает»
    Акта 4: отозванный ключ уже не работает, переписывать историю незачем
    (решение координатора по ревью #125). Строка известной формы, которой
    в `.env` больше нет, проверку не роняет."""
    proj = service(project)
    save(proj, {"ai.py": "KEY = '{}'\n".format(OPENAI_KEY)}, STARTED + 120)
    save(proj, {"ai.py": "import os\n"}, STARTED + 180)
    save(proj, {"bot.py": "TOKEN = '{}'\n".format(BOT_TOKEN)}, STARTED + 240)
    save(proj, {"bot.py": "import os\n"}, STARTED + 300)
    assert keys(quests_root, proj).ok is True


def test_rewritten_history_kept_by_git_is_not_the_saves(quests_root, project):
    """Сохранения — ветки, метки и копии веток с GitHub. Запасные ссылки,
    которые git оставляет после переписанной истории (`refs/original/`), и
    отложенное (`refs/stash`) на GitHub не уходят."""
    proj = service(project)
    save(proj, {"weather2.py": "KEY = '{}'\n".format(WEATHER_KEY)}, STARTED + 120)
    leaked = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(proj),
                            capture_output=True, text=True, check=True).stdout.strip()
    _git(proj, "reset", "-q", "--hard", "HEAD~1")
    _git(proj, "update-ref", "refs/original/refs/heads/{}".format(branch(proj)), leaked)
    _git(proj, "update-ref", "refs/stash", leaked)
    assert keys(quests_root, proj).ok is True
    _git(proj, "update-ref", "refs/tags/v1", leaked)
    assert rows(keys(quests_root, proj))[2] == ("no_keys_in_saves", False)


def test_a_key_on_another_branch_is_in_the_saves(quests_root, project):
    """Вся история — все ветки: на GitHub уходят и они."""
    proj = service(project)
    _git(proj, "checkout", "-q", "-b", "proba")
    save(proj, {"weather2.py": "KEY = '{}'\n".format(WEATHER_KEY)}, STARTED + 120)
    _git(proj, "checkout", "-q", "-")
    assert rows(keys(quests_root, proj))[2] == ("no_keys_in_saves", False)


def test_the_bot_key_of_act4_counts_as_a_key(quests_root, project):
    """Ключ бота четвёртого вечера — тоже ключ из `.env`."""
    proj = service(project, env_text="BOT_TOKEN={}\n".format(BOT_TOKEN))
    assert keys(quests_root, proj).ok is True
    (proj / "notes.txt").write_text(BOT_TOKEN + "\n", encoding="utf-8")
    assert rows(keys(quests_root, proj))[1] == ("no_keys_in_files", False)


def test_no_key_is_ever_printed(quests_root, project):
    """Ни в строках, ни в подсказках, ни в диагностике — при любом исходе."""
    proj = service(project, env_text="WEATHER_API_KEY={}\nBOT_TOKEN={}\n".format(
        WEATHER_KEY, BOT_TOKEN))
    outcomes = []
    outcomes.append(keys(quests_root, proj))
    (proj / "leak.py").write_text("K = '{}'\n".format(WEATHER_KEY), encoding="utf-8")
    outcomes.append(keys(quests_root, proj))
    save(proj, {"leak.py": "K = '{}'\n".format(BOT_TOKEN)}, STARTED + 120)
    save(proj, {"leak.py": "import os\n"}, STARTED + 180)
    outcomes.append(keys(quests_root, proj))
    for result in outcomes:
        text = result.stderr + repr(result.checks)
        for secret in (WEATHER_KEY, BOT_TOKEN):
            assert secret not in text


def test_keys_never_reach_a_command_line(quests_root, project, tmp_path, monkeypatch):
    """Значения из `.env` идут поиску потоком, а не аргументом: строку
    команды видит любой процесс машины. Подменённые `git` и `grep` пишут свои
    аргументы в журнал и зовут настоящих."""
    proj = service(project)
    save(proj, {"leak.py": "K = '{}'\n".format(WEATHER_KEY)}, STARTED + 120)
    save(proj, {"leak.py": "import os\n"}, STARTED + 180)
    bin_dir = tmp_path / "spybin"
    bin_dir.mkdir()
    log = tmp_path / "argv.log"
    for name in ("git", "grep"):
        real = shutil.which(name)
        spy = bin_dir / name
        spy.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "{}"\nexec "{}" "$@"\n'.format(log, real),
            encoding="utf-8",
        )
        spy.chmod(0o755)
    monkeypatch.setenv("PATH", "{}{}{}".format(bin_dir, os.pathsep, os.environ["PATH"]))
    result = keys(quests_root, proj)
    assert rows(result)[2] == ("no_keys_in_saves", False)
    assert log.exists()
    assert WEATHER_KEY not in log.read_text(encoding="utf-8")


def test_an_unreadable_env_cannot_judge(quests_root, project):
    if os.geteuid() == 0:
        pytest.skip("root читает любой файл")
    proj = service(project)
    (proj / ".env").chmod(0o000)
    try:
        result = keys(quests_root, proj)
    finally:
        (proj / ".env").chmod(0o600)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "не могу прочитать файл .env" in result.stderr


def test_service_without_a_named_folder_cannot_judge(quests_root, project):
    proj = service(project)
    result = quests.run_check(quests_root, ACT, "04-service", proj, env_extra=act_env())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_service_in_a_folder_without_git_says_so(quests_root, project):
    proj = project(files={"weather.py": WEATHER_CODE})
    result = keys(quests_root, proj)
    assert rows(result) == [("repo_exists", False)]


def test_service_check_never_touches_the_project(quests_root, project):
    proj = service(project)
    (proj / "leak.py").write_text("K = '{}'\n".format(WEATHER_KEY), encoding="utf-8")
    before = sorted(
        (str(path.relative_to(proj)), path.read_bytes())
        for path in proj.rglob("*") if path.is_file()
    )
    keys(quests_root, proj)
    after = sorted(
        (str(path.relative_to(proj)), path.read_bytes())
        for path in proj.rglob("*") if path.is_file()
    )
    assert after == before


# --- общий контракт ---------------------------------------------------------------

def test_act5_checks_survive_hostile_locale_and_mawk(quests_root, project, tmp_path):
    env = {"LC_ALL": "C"}
    if shutil.which("mawk") is not None:
        bin_dir = tmp_path / "mawkbin"
        bin_dir.mkdir()
        stub = bin_dir / "awk"
        stub.write_text('#!/bin/sh\nexec mawk "$@"\n', encoding="utf-8")
        stub.chmod(0o755)
        env["PATH"] = "{}:{}".format(bin_dir, os.environ["PATH"])
    assert sync(quests_root, synced(project), env=env).ok is True
    assert rows(sync(quests_root, on_github(project), env=env)) == [
        ("saved_after_entry", False)
    ]
    assert keys(quests_root, service(project), env=env).ok is True
    proj = service(project, files={"ключи.txt": "погода: {}\n".format(WEATHER_KEY)})
    assert rows(keys(quests_root, proj, env=env))[1] == ("no_keys_in_files", False)


def test_every_scripted_quest_of_act5_has_its_script(quests_root):
    from jedicoder import acts

    for quest_id in acts.quest_ids(5):
        script = Path(quests_root) / ACT / quest_id / "check.sh"
        assert script.is_file() is (acts.quest_kind(5, quest_id) == acts.KIND_SCRIPT), quest_id

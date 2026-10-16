"""Снимок для Лица игры: `cli.py face` (спека #89, тикет #90, ADR-0019).

Лицо — модуль внутри Claude Code — рисует Полосу над полем ввода. Слов и
чисел у него нет: всё отдаёт одна команда игры одним снимком в JSON. Тесты
ходят той же дверью, что модуль, — через CLI.

Три вещи, ради которых файл существует:

- слова Полосы — те же, что строка «Что дальше» первого экрана: второго
  текста в игре быть не должно;
- Игровая сессия определяется здесь, а не в модуле: вне её Лица нет;
- команда только читает. Модуль зовёт её после каждого хода в любой сессии
  на машине, где стоит плагин, — завести или тронуть сохранение она не вправе.
"""
import json
import os
from pathlib import Path

import pytest

from jedicoder import cli, ranks
from jedicoder import state as st

EMPTY = {
    "is_game": False, "next": [], "rank": "", "quests_closed": 0, "say": "",
    "toast_quest": "", "toast_rank": "",
}


@pytest.fixture(autouse=True)
def no_golokron(monkeypatch):
    """Признак «запущена Голокроном» — только там, где тест его ставит сам."""
    monkeypatch.delenv(cli.GOLOKRON_MARK, raising=False)


@pytest.fixture
def game(tmp_path, content_root, quests_root, capsys):
    state_path = tmp_path / "state.json"

    def jc(*argv):
        code = cli.main(
            list(argv), state_path=state_path, content_root=content_root,
            quests_root=quests_root,
        )
        return code, capsys.readouterr().out

    def face(*argv):
        code, out = jc("face", *argv)
        assert code == 0, out
        snapshot = json.loads(out)
        # Отпечаток раздела с контрактом — отдельная история со своими
        # тестами (tests/test_contract_section.py): здесь он только есть.
        assert isinstance(snapshot.pop("contract"), str)
        return snapshot

    jc.state_path = state_path
    jc.face = face
    return jc


def next_step_of_status(game):
    """Хвост первого экрана: строки «Что дальше», как их видит человек."""
    _, out = game("status")
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Что дальше"))
    tail = lines[start:]
    end = tail.index("") if "" in tail else len(tail)
    return [line.strip() for line in tail[:end]]


# --- Снимок на пути прохождения ---------------------------------------------

def test_clean_install_in_a_game_session(game):
    assert game("status")[0] == 0
    assert game.face("--called") == {
        "is_game": True,
        "next": [
            "Что дальше: начать Акт 1 «Знакомство» — квестов в нём 5.",
            "Скажи Claude: «начинаем».",
        ],
        "rank": "Юнлинг",
        "quests_closed": 0,
        "say": "начинаем",
        "toast_quest": "Квест закрыт",
        "toast_rank": "Новый ранг: Юнлинг",
    }


def test_after_entering_the_act(game):
    assert game("enter", "1")[0] == 0
    snapshot = game.face("--called")
    assert snapshot["next"] == [
        "Что дальше: квест «Папка» — Акт 1 «Знакомство».",
        "Назови папку своего проекта.",
    ]
    assert snapshot["quests_closed"] == 0


def test_after_a_closed_quest(game, project):
    proj = project()
    assert game("enter", "1")[0] == 0
    assert game("project", "path", str(proj))[0] == 0
    assert game("check", "1", "01-folder")[0] == 0
    snapshot = game.face("--called")
    assert snapshot["next"][0] == (
        "Что дальше: квест «Идея на вечер» — Акт 1 «Знакомство»."
    )
    assert len(snapshot["next"]) == 2
    assert snapshot["quests_closed"] == 1
    assert snapshot["rank"] == "Юнлинг"


def test_rank_is_a_word_and_grows_with_the_act(game, project):
    from test_human_screens import walk_act1

    walk_act1(game, project())
    snapshot = game.face("--called")
    assert snapshot["rank"] == "Искатель"
    assert snapshot["quests_closed"] == 5


def test_snapshot_is_one_line_of_json(game):
    game("status")
    code, out = game("face", "--called")
    assert code == 0
    assert out.count("\n") == 1 and out.endswith("\n")
    assert sorted(json.loads(out)) == sorted(dict(EMPTY, contract=""))


# --- Фраза, которую игра предлагает сказать (#94) ------------------------------

def quoted(line):
    """Слово в «ёлочках» строки — то, что строка просит сказать."""
    return line.split("«", 1)[1].split("»", 1)[0]


def test_before_the_act_the_game_offers_the_word_that_starts_it(game):
    game("status")
    assert game.face("--called")["say"] == "начинаем"


def test_the_phrase_to_say_is_the_word_the_strip_asks_for(game):
    """Подсказка в поле ввода и вторая строка Полосы — одно слово, один источник."""
    game("status")
    snapshot = game.face("--called")
    assert snapshot["say"] == quoted(snapshot["next"][1])
    assert quoted(next_step_of_status(game)[1]) == snapshot["say"]


def test_strip_and_phrase_cannot_drift_apart(game, monkeypatch):
    """Сменили слово в одном месте — сменились и Полоса, и подсказка."""
    game("status")
    monkeypatch.setattr(cli, "SAY_START", "поехали")
    snapshot = game.face("--called")
    assert snapshot["say"] == "поехали"
    assert quoted(snapshot["next"][1]) == "поехали"


def test_after_entering_the_act_there_is_nothing_to_say(game, project):
    """На вопросы квестов человек отвечает сам: поле ввода пустое на всём пути.

    Акт закрыт, следующий ждёт — фраза возвращается: она зовёт в Акт 2 так
    же, как звала в первый.
    """
    from test_act1_walkthrough import ACK, do_first_request, do_idea, do_save

    proj = project()
    said = []

    def say():
        said.append(game.face("--called")["say"])

    game("enter", "1")
    say()
    game("project", "path", str(proj))
    say()
    game("check", "1", "01-folder")
    say()
    do_idea(proj)
    game("check", "1", "02-idea")
    say()
    do_first_request(proj)
    game("seen", "1", "03-first-request")
    say()
    game("check", "1", "03-first-request")
    say()
    do_save(proj)
    game("check", "1", "04-save")
    say()
    assert game("ack", "1", ACK)[0] == 0
    say()
    assert said == [""] * 7 + [cli.SAY_START]
    assert game("enter", "2")[0] == 0
    say()
    assert said[-1] == ""


def test_outside_a_game_session_there_is_nothing_to_say(game, tmp_path):
    game("status")
    assert game.face("--cwd", str(tmp_path))["say"] == ""


SAVES_EDITED_BY_HAND = [
    {},
    {"acts": []},
    {"acts": {"1": "мусор"}},
    {"acts": {"1": {"status": "мусор"}}},
    {"acts": {"1": {"status": "in_progress"}}},
    {"acts": {"1": {"status": "in_progress", "quests": []}}},
    {"acts": {"1": {"status": "in_progress", "quests": {"01-folder": "мусор"}}}},
    {"acts": {"1": {"status": "done"}}},
]


@pytest.mark.parametrize("save", SAVES_EDITED_BY_HAND)
def test_phrase_is_offered_only_where_the_strip_asks_for_it(save):
    """Фраза считается там же, где строка «Что дальше», — и на правленом сохранении."""
    lines = cli.render_next_step(save, {})
    asked = any("«{}»".format(cli.SAY_START) in line for line in lines)
    assert (cli.phrase_to_say(save) == cli.SAY_START) == asked
    assert cli.phrase_to_say(save) in ("", cli.SAY_START)


def test_phrase_is_offered_before_the_act_and_not_inside_it():
    assert cli.phrase_to_say(st.default_state()) == cli.SAY_START
    started = {"acts": {"1": {"status": "in_progress", "quests": {}}}}
    assert cli.phrase_to_say(started) == ""
    # Первый акт закрыт, второй не начат — фраза зовёт во второй.
    between = {"acts": {"1": {"status": "done"}}}
    assert cli.phrase_to_say(between) == cli.SAY_START
    inside = {"acts": {"1": {"status": "done"},
                       "2": {"status": "in_progress", "quests": {}}}}
    assert cli.phrase_to_say(inside) == ""
    done = {"acts": {str(n): {"status": "done"} for n in ranks.playable_acts()}}
    assert cli.phrase_to_say(done) == ""


def test_no_save_and_a_broken_save_offer_nothing(game):
    assert game.face("--called")["say"] == ""
    game.state_path.write_text("{не json", encoding="utf-8")
    assert game.face("--called")["say"] == ""


# --- Второго текста нет -------------------------------------------------------

def test_strip_words_are_the_next_step_of_the_first_screen(game, project):
    """Полоса и первый экран называют один шаг одними словами — на всём пути."""
    from test_act1_walkthrough import ACK, do_first_request, do_idea, do_save

    proj = project()
    seen = []

    def same():
        expected = next_step_of_status(game)
        assert game.face("--called")["next"] == expected
        seen.append(expected[0])

    same()
    game("enter", "1")
    same()
    game("project", "path", str(proj))
    game("check", "1", "01-folder")
    same()
    do_idea(proj)
    game("check", "1", "02-idea")
    same()
    do_first_request(proj)
    game("seen", "1", "03-first-request")
    game("check", "1", "03-first-request")
    same()
    do_save(proj)
    game("check", "1", "04-save")
    same()
    assert game("ack", "1", ACK)[0] == 0
    same()
    assert len(set(seen)) == 7, seen


# --- Игровая сессия -------------------------------------------------------------

def test_outside_a_game_session_there_is_no_face(game, project, tmp_path):
    proj = project()
    game("enter", "1")
    game("project", "path", str(proj))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert game.face("--cwd", str(elsewhere)) == EMPTY
    assert game.face() == EMPTY


def test_session_started_by_golokron_is_a_game_session(game, tmp_path, monkeypatch):
    game("status")
    monkeypatch.setenv(cli.GOLOKRON_MARK, "1")
    snapshot = game.face("--cwd", str(tmp_path))
    assert snapshot["is_game"] is True
    assert snapshot["next"][0].startswith("Что дальше: начать Акт 1")


def test_session_in_the_project_folder_is_a_game_session(game, project):
    proj = project()
    game("project", "path", str(proj))
    snapshot = game.face("--cwd", str(proj))
    assert snapshot["is_game"] is True
    assert snapshot["next"] != []


def test_session_where_the_game_was_called_is_a_game_session(game, tmp_path):
    game("status")
    assert game.face("--cwd", str(tmp_path), "--called")["is_game"] is True
    assert game.face("--cwd", str(tmp_path))["is_game"] is False


def test_subfolder_of_the_project_folder_is_a_game_session(game, project):
    proj = project()
    deep = proj / "src" / "pages"
    deep.mkdir(parents=True)
    game("project", "path", str(proj))
    assert game.face("--cwd", str(deep))["is_game"] is True


def test_parent_and_neighbour_of_the_project_folder_are_not(game, project, tmp_path):
    proj = project()
    game("project", "path", str(proj))
    neighbour = proj.parent / (proj.name + "-2")
    neighbour.mkdir()
    assert game.face("--cwd", str(proj.parent))["is_game"] is False
    assert game.face("--cwd", str(neighbour))["is_game"] is False


def test_project_folder_reached_by_a_symlink_is_a_game_session(game, project, tmp_path):
    proj = project()
    game("project", "path", str(proj))
    link = tmp_path / "link"
    link.symlink_to(proj, target_is_directory=True)
    assert game.face("--cwd", str(link))["is_game"] is True


def test_garbage_project_path_is_no_folder(game, tmp_path):
    game("status")
    data = json.loads(game.state_path.read_text(encoding="utf-8"))
    data["project"] = {"path": ["/tmp"]}
    game.state_path.write_text(json.dumps(data), encoding="utf-8")
    assert game.face("--cwd", str(tmp_path)) == EMPTY


@pytest.mark.parametrize("where", ["home", "root"])
def test_home_or_disk_root_as_project_does_not_cover_every_folder(
        game, tmp_path, monkeypatch, where):
    """Плагин стоит на всю машину: Лицо не должно встать в каждом проекте."""
    home = tmp_path / "home"
    (home / "work" / "site").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    wide = home if where == "home" else Path(home.anchor)
    game("status")
    data = json.loads(game.state_path.read_text(encoding="utf-8"))
    data["project"] = {"path": str(wide)}
    game.state_path.write_text(json.dumps(data), encoding="utf-8")
    assert game.face("--cwd", str(home / "work" / "site"))["is_game"] is False
    assert game.face("--cwd", str(wide))["is_game"] is True


def test_relative_project_path_is_no_folder(game, tmp_path, monkeypatch):
    game("status")
    data = json.loads(game.state_path.read_text(encoding="utf-8"))
    data["project"] = {"path": "."}
    game.state_path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert game.face("--cwd", str(tmp_path))["is_game"] is False


def test_snapshot_survives_a_terminal_without_utf8(game):
    game("status")
    _, out = game("face", "--called")
    out.encode("ascii")
    assert json.loads(out)["rank"] == "Юнлинг"


def test_unknown_arguments_do_not_break_the_snapshot(game, tmp_path):
    """Модуль новее команды не должен остаться без Полосы из-за нового флага."""
    game("status")
    assert game.face("--called", "--later-flag")["is_game"] is True
    assert game.face("--called", "--cwd")["is_game"] is True
    assert game.face("--cwd", "--called")["is_game"] is True


# --- Команда только читает ------------------------------------------------------

def files_around(path):
    return sorted(item.name for item in path.parent.iterdir())


def test_no_save_means_an_empty_snapshot_and_no_file(game):
    before = files_around(game.state_path)
    assert game.face("--called") == dict(EMPTY, is_game=True)
    assert game.face() == EMPTY
    assert not game.state_path.exists()
    assert files_around(game.state_path) == before


def test_no_save_folder_is_not_created(tmp_path, content_root, quests_root, capsys):
    state_path = tmp_path / "nowhere" / "state.json"
    code = cli.main(
        ["face", "--called"], state_path=state_path, content_root=content_root,
        quests_root=quests_root,
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out) == dict(
        EMPTY, is_game=True, contract=""
    )
    assert not state_path.parent.exists()


def test_snapshot_does_not_touch_the_save(game, project):
    proj = project()
    game("enter", "1")
    game("project", "path", str(proj))
    os.utime(str(game.state_path), (1_000_000_000, 1_000_000_000))
    before = (game.state_path.read_bytes(), game.state_path.stat().st_mtime_ns,
              files_around(game.state_path))
    game.face("--cwd", str(proj), "--called")
    assert (game.state_path.read_bytes(), game.state_path.stat().st_mtime_ns,
            files_around(game.state_path)) == before


def test_snapshot_does_not_take_the_one_time_notice(game):
    """Объяснение «игра перестроена» снимает первый экран, а не Полоса."""
    game("status")
    data = json.loads(game.state_path.read_text(encoding="utf-8"))
    data["notices"] = [st.NOTICE_GAME_REBUILT]
    game.state_path.write_text(json.dumps(data), encoding="utf-8")
    game.face("--called")
    kept = json.loads(game.state_path.read_text(encoding="utf-8"))
    assert kept["notices"] == [st.NOTICE_GAME_REBUILT]


@pytest.mark.parametrize("text", ["{не json", "[1, 2]", ""])
def test_broken_save_means_an_empty_snapshot_and_stays_in_place(game, text):
    """Чинит сохранение команда игры, а не Полоса: файл не уходит в сторону."""
    game.state_path.write_text(text, encoding="utf-8")
    before = files_around(game.state_path)
    assert game.face("--called") == dict(EMPTY, is_game=True)
    assert game.state_path.read_text(encoding="utf-8") == text
    assert files_around(game.state_path) == before


def test_previous_game_save_is_not_archived(game, tmp_path):
    """Прежнюю игру уносит в архив `state.load`; снимок её только видит."""
    old = {"schema_version": st.REBUILT_GAME_SCHEMA - 1, "padawan_id": "p",
           "project": {"path": str(tmp_path)}, "acts": {"1": {"status": "done"}}}
    game.state_path.write_text(json.dumps(old), encoding="utf-8")
    os.utime(str(game.state_path), (1_000_000_000, 1_000_000_000))
    before = files_around(game.state_path)
    assert game.face("--cwd", str(tmp_path)) == EMPTY
    assert game.face("--called") == dict(EMPTY, is_game=True)
    assert json.loads(game.state_path.read_text(encoding="utf-8")) == old
    assert game.state_path.stat().st_mtime_ns == 1_000_000_000 * 10 ** 9
    assert files_around(game.state_path) == before


def test_peek_answers_none_instead_of_raising_on_a_hand_edited_save(game):
    """Вторая дверь обещает «сохранение либо None» — и следующему читателю."""
    game.state_path.write_text(
        json.dumps({"schema_version": st.SCHEMA_VERSION, "streak": 5}),
        encoding="utf-8",
    )
    assert st.peek(game.state_path) is None


def test_save_newer_than_the_plugin_means_an_empty_snapshot(game):
    game.state_path.write_text(
        json.dumps({"schema_version": st.SCHEMA_VERSION + 1}), encoding="utf-8"
    )
    assert game.face("--called") == dict(EMPTY, is_game=True)


@pytest.mark.parametrize("save", [
    {"schema_version": st.SCHEMA_VERSION, "acts": [1], "rank": 7, "project": "x"},
    {"schema_version": st.SCHEMA_VERSION, "acts": {"1": "x"}, "streak": 5},
])
def test_hand_edited_save_means_silence_not_a_traceback(game, save):
    """Закон лица: ошибка — тишина. О поломке скажет первый экран."""
    text = json.dumps(save)
    game.state_path.write_text(text, encoding="utf-8")
    assert game.face("--called") == dict(EMPTY, is_game=True)
    assert game.state_path.read_text(encoding="utf-8") == text


def test_snapshot_does_not_send_events_to_the_bot(game, monkeypatch):
    """Полоса зовёт команду после каждого хода: сети в ней быть не должно."""
    from jedicoder import sync

    game("status")
    called = []
    monkeypatch.setattr(sync, "maybe_flush", lambda path: called.append(path))
    game.face("--called")
    assert called == []


# --- Вторая форма: действие сделано, проверка ещё не шла (#91) --------------

FOLDER_STEP = "Что дальше: квест «Папка» — Акт 1 «Знакомство»."
FOLDER_TASK = "Назови папку своего проекта."
FOLDER_NAMED = "Папка названа. Дальше — проверка квеста."
REQUEST_STEP = "Что дальше: квест «Первый запрос» — Акт 1 «Знакомство»."
REQUEST_TASK = "Попроси Claude сделать первую версию и посмотри на неё."
REQUEST_TOLD = "Рассказ записан. Дальше — проверка квеста."


def both(game):
    """Шаг, как его называют первый экран и Полоса, — и они обязаны совпасть."""
    step = next_step_of_status(game)
    assert game.face("--called")["next"] == step
    return step


def test_folder_quest_asks_for_the_folder_until_it_is_named(game):
    game("enter", "1")
    assert both(game) == [FOLDER_STEP, FOLDER_TASK]


def test_folder_recorded_by_the_app_is_not_a_named_folder(
        game, project, monkeypatch):
    """Приложение записало папку на старте сессии — человек её ещё не назвал."""
    from test_human_screens import _record_by_launch

    _record_by_launch(game, project(), monkeypatch)
    game("enter", "1")
    assert both(game) == [FOLDER_STEP, FOLDER_TASK]


def test_folder_named_by_the_person_waits_for_the_check(game, project):
    game("enter", "1")
    assert game("project", "path", str(project()))[0] == 0
    assert both(game) == [FOLDER_STEP, FOLDER_NAMED]


def test_another_folder_recorded_later_is_not_the_named_one(
        game, project, tmp_path):
    game("enter", "1")
    assert game("project", "path", str(project()))[0] == 0
    other = tmp_path / "drugaya"
    other.mkdir()
    data = st.load(game.state_path)
    data["project"]["path"] = str(other)
    st.save(data, game.state_path)
    assert both(game) == [FOLDER_STEP, FOLDER_TASK]


def test_closed_folder_quest_moves_the_step_on(game, project):
    game("enter", "1")
    game("project", "path", str(project()))
    assert game("check", "1", "01-folder")[0] == 0
    assert both(game) == [
        "Что дальше: квест «Идея на вечер» — Акт 1 «Знакомство».",
        "Выбери одно дело на этот вечер и отложи остальное.",
    ]


def _name_the_home_folder(game, project, monkeypatch):
    """Назвать папкой проекта домашнюю целиком — её проверка не принимает."""
    home = project()
    monkeypatch.setenv("HOME", str(home))
    game("enter", "1")
    assert game("project", "path", str(home))[0] == 0
    assert game("check", "1", "01-folder")[0] == 1
    return home


def test_folder_refused_by_the_check_brings_the_task_back(
        game, project, monkeypatch):
    """Проверка не сошлась: «Дальше — проверка» звала бы ту же проверку снова."""
    _name_the_home_folder(game, project, monkeypatch)
    assert both(game) == [FOLDER_STEP, FOLDER_TASK]


def test_folder_named_again_after_a_failed_check_waits_for_the_check(
        game, project, monkeypatch):
    home = _name_the_home_folder(game, project, monkeypatch)
    inner = home / "proekt"
    inner.mkdir()
    assert game("project", "path", str(inner))[0] == 0
    assert both(game) == [FOLDER_STEP, FOLDER_NAMED]
    assert game("check", "1", "01-folder")[0] == 0


def test_first_request_asks_for_the_first_version_until_the_words(game, project):
    from test_act1_walkthrough import do_first_request
    from test_human_screens import _up_to_first_request

    proj = _up_to_first_request(game, project)
    assert both(game) == [REQUEST_STEP, REQUEST_TASK]
    do_first_request(proj)
    assert both(game) == [REQUEST_STEP, REQUEST_TASK]


def test_first_request_with_the_words_taken_waits_for_the_check(game, project):
    from test_act1_walkthrough import do_first_request
    from test_human_screens import _up_to_first_request

    proj = _up_to_first_request(game, project)
    do_first_request(proj)
    assert game("seen", "1", "03-first-request")[0] == 0
    assert both(game) == [REQUEST_STEP, REQUEST_TOLD]


def test_words_wiped_by_a_failed_check_bring_the_task_back(game, project):
    from test_act1_walkthrough import do_first_request
    from test_human_screens import _up_to_first_request

    proj = _up_to_first_request(game, project)
    do_first_request(proj)
    assert game("seen", "1", "03-first-request")[0] == 0
    (proj / "index.html").unlink()
    assert game("check", "1", "03-first-request")[0] == 1
    assert both(game) == [REQUEST_STEP, REQUEST_TASK]


@pytest.mark.parametrize("project_field", [
    None, "строка", ["список"], {"path_named": 5}, {"path": 5, "path_named": 5},
    {"path": "/p", "path_named": ["/p"]},
])
def test_second_form_survives_a_hand_edited_save(project_field):
    """Сохранение правят руками: мусор читается как «не сделано»."""
    from jedicoder import ranks

    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    data["project"] = project_field
    tasks = {(1, "01-folder"): FOLDER_TASK, (1, "03-first-request"): REQUEST_TASK}
    assert cli.render_next_step(data, {}, tasks)[1] == "  " + FOLDER_TASK
    data["acts"]["1"]["quests"] = {
        "01-folder": {"status": ranks.STATUS_DONE},
        "02-idea": {"status": ranks.STATUS_DONE},
        "03-first-request": "строка",
    }
    assert cli.render_next_step(data, {}, tasks)[1] == "  " + REQUEST_TASK


def test_second_form_does_not_depend_on_the_content_of_the_act():
    """Слова второй формы живут в команде: испорченный контент их не уносит."""
    from jedicoder import ranks

    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    data["project"] = {"path": "/p", "path_named": "/p"}
    assert cli.render_next_step(data, {}, {}) == [
        "Что дальше: квест 01-folder — Акт 1 «Знакомство».",
        "  " + FOLDER_NAMED,
    ]


# --- Подписи всплывающих (#91) ------------------------------------------------

def test_toast_captions_come_with_every_game_snapshot(game, project):
    """Модуль слов не держит: что показать, он берёт из снимка."""
    from test_human_screens import walk_act1

    game("enter", "1")
    before = game.face("--called")
    assert before["toast_quest"] == "Квест закрыт"
    walk_act1(game, project())
    after = game.face("--called")
    assert after["toast_quest"] == "Квест закрыт"
    assert after["toast_rank"] == "Новый ранг: Искатель"
    assert after["toast_rank"] != before["toast_rank"]


def test_rank_caption_carries_the_rank_of_the_snapshot(game):
    game("status")
    snapshot = game.face("--called")
    assert snapshot["toast_rank"] == "Новый ранг: {}".format(snapshot["rank"])


def test_outside_a_game_session_there_are_no_captions(game, project, tmp_path):
    game("enter", "1")
    game("project", "path", str(project()))
    snapshot = game.face("--cwd", str(tmp_path))
    assert snapshot["toast_quest"] == "" and snapshot["toast_rank"] == ""


def test_captions_are_short_plain_lines(game):
    game("status")
    snapshot = game.face("--called")
    for key in ("toast_quest", "toast_rank"):
        assert "\n" not in snapshot[key]
        assert not snapshot[key].endswith(".")
        assert len(snapshot[key].split()) <= 4

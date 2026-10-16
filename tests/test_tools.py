"""Инструменты игры: `cli.py tools` и `cli.py tool <имя>` (спека #89, тикет #93).

Команды пути модель зовёт инструментами, а не длинной строкой в терминале.
Модуль Лица слов и перечня не держит: что за инструменты, как они описаны и
что принимают, отдаёт команда `tools`, а выполняет их команда `tool`. Тесты
ходят той же дверью, что модуль, — через CLI.

Четыре вещи, ради которых файл существует:

- инструмент не принимает ни номера акта, ни кода квеста: вызов видит человек
  на экране, а кодов квестов на экране нет. Квест называется словами, как на
  экране, и игра сверяет название с открытым квестом: не совпало — ничего
  не запускается и не тратится;
- ответ инструмента — ответ той же команды игры, слово в слово и с тем же
  кодом возврата: второго текста и второго судьи нет;
- через инструмент нельзя позвать то, чего нет в перечне;
- перечень покрывает весь путь Акта 1 — акт проходится одними инструментами.
"""
import json
import re
import sys
from pathlib import Path

import pytest

from jedicoder import acts, cli, ranks, tools
from jedicoder import state as st
from test_act1_walkthrough import ACK, do_first_request, do_idea, do_save

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
sys.path.insert(0, str(ROOT / "scripts"))

import lint_content  # noqa: E402

#: Команды, которым в перечне не место: они не на пути Акта 1 или необратимы.
NEVER = (
    "reset", "link", "sync", "finale", "track", "debrief", "book", "root",
    "face", "artifact", "recipe", "tools", "tool",
)


@pytest.fixture(autouse=True)
def no_golokron(monkeypatch):
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

    def tool(name, *values):
        """Вызов, каким его собирает модуль: `tool`, имя, значения входа."""
        return jc(cli.TOOL_CALL, name, *values)

    def listing():
        code, out = jc(cli.TOOL_LIST)
        assert code == 0, out
        return json.loads(out)

    jc.state_path = state_path
    jc.tool = tool
    jc.listing = listing
    return jc


def twin(tmp_path, game, content_root, quests_root, capsys):
    """Та же игра на копии сохранения: что ответила бы прежняя команда."""
    copy = tmp_path / "twin-state.json"
    copy.write_text(game.state_path.read_text(encoding="utf-8"), encoding="utf-8")

    def jc(*argv):
        code = cli.main(
            list(argv), state_path=copy, content_root=content_root,
            quests_root=quests_root,
        )
        return code, capsys.readouterr().out

    return jc


# --- Перечень ----------------------------------------------------------------

def test_listing_is_one_line_of_ascii_json(game):
    code, out = game(cli.TOOL_LIST)
    assert code == 0
    assert out.count("\n") == 1
    out.encode("ascii")
    assert isinstance(json.loads(out), list)


def test_listing_names_the_tools_of_the_act1_path(game):
    names = [item["name"] for item in game.listing()]
    assert names == [
        "status", "enter", "folder", "check", "seen", "ack", "scroll", "contract",
    ]
    assert names == list(tools.NAMES)


def test_every_tool_is_declared_whole(game):
    """Договор с модулем: имя, описание, схема входа и порядок значений."""
    for item in game.listing():
        assert sorted(item) == ["description", "input", "inputSchema", "name"]
        assert set(item["inputSchema"]) <= {
            "type", "properties", "additionalProperties", "required",
        }
        assert re.fullmatch(r"[a-z][a-z_]{1,30}", item["name"]), item["name"]
        assert item["description"].strip()
        schema = item["inputSchema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert list(schema["properties"]) == item["input"]
        for key in item["input"]:
            assert schema["properties"][key]["type"] == "string"
            assert schema["properties"][key]["description"].strip()


def test_no_tool_takes_an_act_or_a_quest_code(game):
    """Вызов инструмента видит человек: кодов квестов на экране нет.

    Квест называется словами, как на экране, и только там, где инструмент
    действует на квест: название обязательно. Путь к папке — нет.
    """
    takes = {item["name"]: item["input"] for item in game.listing()}
    assert {name: keys for name, keys in takes.items() if keys} == {
        "folder": ["path"], "check": ["quest"], "seen": ["quest"],
        "ack": ["quest"],
    }
    for item in game.listing():
        required = item["inputSchema"].get("required", [])
        assert required == [key for key in item["input"] if key == "quest"]
        if "quest" in item["input"]:
            text = item["inputSchema"]["properties"]["quest"]["description"]
            assert "«Папка»" in text


def test_listing_holds_nothing_off_the_path(game):
    names = {item["name"] for item in game.listing()}
    assert names.isdisjoint(NEVER)
    for name in names:
        assert tools.COMMANDS[name] in cli.HANDLERS, name
    assert sorted(set(tools.COMMANDS.values())) == [
        "ack", "check", "contract", "enter", "project", "scroll", "seen",
        "status",
    ]


def test_descriptions_follow_the_language_rules(game):
    """Описание читает модель и видит человек в списке инструментов."""
    for item in game.listing():
        texts = [item["description"]] + [
            item["inputSchema"]["properties"][key]["description"]
            for key in item["input"]
        ]
        for text in texts:
            assert lint_content.long_sentences(text) == [], text
            assert lint_content.forbidden_images(text) == [], text
            assert not re.search(r"\d\d-[a-z]", text), text


def test_listing_does_not_touch_the_save(game):
    """Перечень модуль берёт на старте любой сессии этой машины."""
    game.listing()
    assert not game.state_path.exists()


def test_listing_does_not_send_events_to_the_bot(game, monkeypatch):
    from jedicoder import sync

    called = []
    monkeypatch.setattr(sync, "maybe_flush", lambda path: called.append(path))
    game.listing()
    assert called == []


# --- Вызов по названию квеста ---------------------------------------------------

#: Названия квестов Акта 1, как их печатает первый экран: {код: название}.
TITLES = {
    quest_id: title
    for (act, quest_id), title in cli._quest_titles(PLUGIN / "content" / "ru").items()
    if act == 1
}
FOLDER, IDEA_Q, REQUEST, SAVE, STOP = (
    TITLES[quest_id] for quest_id, _, _ in acts.ACT1_QUESTS
)


def attempts(game, quest_id):
    from jedicoder import quests

    return quests.attempts(st.load(game.state_path), 1, quest_id)


def test_quest_titles_come_from_the_first_screen(game):
    """Второго перечня названий нет: те же слова печатает вход в акт."""
    assert (FOLDER, STOP) == ("Папка", "Стоп и отмена")
    _, out = game("enter", "1")
    for title in TITLES.values():
        assert title in out


def test_clean_install_is_answered_in_plain_words(game):
    for name in ("check", "seen", "ack"):
        code, out = game.tool(name, FOLDER)
        assert code == 1, out
        assert out.strip() == cli.ACT_NOT_STARTED.format(1)
    code, out = game.tool("scroll")
    assert code == 1 and "Traceback" not in out and out.strip()


def test_enter_takes_the_nearest_act_without_a_number(game):
    code, out = game.tool("enter")
    assert code == 0, out
    data = st.load(game.state_path)
    assert data["acts"]["1"]["status"] == ranks.STATUS_IN_PROGRESS


def test_tool_answers_what_the_command_answers(
        game, project, tmp_path, content_root, quests_root, capsys):
    """Слово в слово и с тем же кодом — на каждом шаге пути."""
    proj = project()
    game("enter", "1")

    def same(name, values, command):
        old = twin(tmp_path, game, content_root, quests_root, capsys)
        expected = old(*command)
        got = game.tool(name, *values)
        assert got == expected, name
        return got

    assert same("check", (FOLDER,), ("check", "1", "01-folder"))[0] == 1
    assert same("ack", (FOLDER,), ("ack", "1", "01-folder"))[0] == 1
    assert same("seen", (FOLDER,), ("seen", "1", "01-folder"))[0] == 1
    assert same("folder", (), ("project",))[0] == 0
    assert same("folder", (str(proj),), ("project", "path", str(proj)))[0] == 0
    assert same("folder", (), ("project",))[0] == 0
    assert same("check", (FOLDER,), ("check", "1", "01-folder"))[0] == 0
    assert same("check", (IDEA_Q,), ("check", "1", "02-idea"))[0] == 1
    assert same("status", (), ("status",))[0] == 0
    assert same("enter", (), ("enter", "1"))[0] == 0
    assert same("contract", (), ("contract",))[0] == 0


@pytest.mark.parametrize("spelled", [
    "Папка", "папка", "ПАПКА", "  Папка  ", "«Папка»", '"Папка"', "'папка'",
    "“Папка”", " « Папка » ",
])
def test_quest_name_is_compared_forgivingly(game, project, spelled):
    game.tool("enter")
    game.tool("folder", str(project()))
    code, out = game.tool("check", spelled)
    assert code == 0, out


def test_inner_spaces_and_yo_do_not_matter(game, project):
    proj = project()
    game.tool("enter")
    game.tool("folder", str(proj))
    game.tool("check", FOLDER)
    do_idea(proj)
    code, out = game.tool("check", "идея   на  вечер")
    assert code == 0, out


def test_another_quest_named_runs_nothing_and_writes_nothing(game, project):
    """Назван не тот квест: попытка цела, сохранение не тронуто."""
    proj = project()
    game.tool("enter")
    game.tool("folder", str(proj))
    assert game.tool("check", FOLDER)[0] == 0
    before = game.state_path.read_bytes()
    stamp = game.state_path.stat().st_mtime_ns
    for name in ("check", "seen", "ack"):
        for named in (SAVE, STOP, "Нет такого", "02-idea", ""):
            code, out = game.tool(name, named)
            assert code == 1, out
            assert cli.TOOL_QUEST_OPEN.format("«{}»".format(IDEA_Q)) in out, out
            assert "02-idea" not in out and "Traceback" not in out
    # Без названия вовсе — то же самое.
    code, out = game.tool("check")
    assert code == 1 and cli.TOOL_QUEST_OPEN.format("«{}»".format(IDEA_Q)) in out
    assert game.state_path.read_bytes() == before
    assert game.state_path.stat().st_mtime_ns == stamp
    assert attempts(game, "02-idea") == 0
    assert attempts(game, "04-save") == 0


def test_check_repeated_on_a_quest_just_closed_spends_nothing(game, project):
    """Модель повторила проверку: удар не приходится по следующему квесту."""
    proj = project()
    game.tool("enter")
    game.tool("folder", str(proj))
    assert game.tool("check", FOLDER)[0] == 0
    stamp = game.state_path.stat().st_mtime_ns
    for _ in range(4):
        code, out = game.tool("check", FOLDER)
        assert code == 1, out
        lines = out.splitlines()
        assert lines[0] == cli.TOOL_QUEST_CLOSED.format("«{}»".format(FOLDER))
        assert lines[1] == cli.TOOL_QUEST_OPEN.format("«{}»".format(IDEA_Q))
    assert attempts(game, "02-idea") == 0
    assert attempts(game, "01-folder") == 1
    assert game.state_path.stat().st_mtime_ns == stamp
    # Ни протокола «третья попытка», ни слова о провале в ответе не было.
    assert "попытк" not in out.lower()


def test_actions_follow_the_named_quest(game, project):
    proj = project()
    game.tool("enter")
    game.tool("folder", str(proj))
    assert game.tool("check", FOLDER)[0] == 0
    do_idea(proj)
    assert game.tool("check", IDEA_Q)[0] == 0
    # Квест «Первый запрос»: рассказ раньше проверки.
    code, out = game.tool("check", REQUEST)
    assert code == 1 and "03-first-request" not in out
    do_first_request(proj)
    assert game.tool("seen", REQUEST)[0] == 0
    assert game.tool("check", REQUEST)[0] == 0
    data = st.load(game.state_path)
    assert acts.next_quest(data, 1) == "04-save"


def test_whole_act1_is_walked_by_the_tools_alone(game, project):
    """Той же дверью, что модуль: только вызовы, которые собирает перечень."""
    proj = project()
    listed = {item["name"]: item["input"] for item in game.listing()}
    screens = []

    def call(name, expect=0, **given):
        assert sorted(given) == sorted(listed[name]) or name == "folder", name
        values = [given[key] for key in listed[name] if key in given]
        code, out = game.tool(name, *values)
        assert code == expect, "{}: {}".format(name, out)
        screens.append(out)
        return out

    call("status")
    call("enter")
    call("check", expect=1, quest=FOLDER)
    call("folder", path=str(proj))
    call("check", quest=FOLDER)
    call("check", expect=1, quest=IDEA_Q)
    do_idea(proj)
    call("check", quest=IDEA_Q)
    call("check", expect=1, quest=REQUEST)
    do_first_request(proj)
    call("seen", quest=REQUEST)
    call("check", quest=REQUEST)
    call("check", expect=1, quest=SAVE)
    do_save(proj)
    call("check", quest=SAVE)
    call("check", expect=1, quest=STOP)
    call("ack", quest=STOP)
    call("status")
    call("scroll")

    data = st.load(game.state_path)
    assert data["rank"] == ranks.ACTS[1]["rank"] == "seeker"
    assert data["acts"]["1"]["status"] == ranks.STATUS_DONE
    assert (proj / "docs" / "jedicoder").is_dir()
    for screen in screens:
        for quest_id, _, _ in acts.ACT1_QUESTS:
            assert quest_id not in screen, screen


def walk_to_the_end(game, proj):
    game.tool("enter")
    game.tool("folder", str(proj))
    game.tool("check", FOLDER)
    do_idea(proj)
    game.tool("check", IDEA_Q)
    do_first_request(proj)
    game.tool("seen", REQUEST)
    game.tool("check", REQUEST)
    do_save(proj)
    game.tool("check", SAVE)
    assert game.tool("ack", STOP)[0] == 0


def test_between_acts_the_tool_says_the_next_act_is_not_entered(game, project):
    """Акт 1 закрыт, Акт 2 не начат: инструмент квеста говорит войти в акт."""
    walk_to_the_end(game, project())
    for name in ("check", "seen", "ack"):
        code, out = game.tool(name, STOP)
        assert code == 1, out
        assert out.splitlines() == [cli.ACT_NOT_STARTED.format(2)]
        assert ACK not in out and "Traceback" not in out


#: Названия квестов Акта 2, как их печатает первый экран.
PLAN, SHOW, MEMORY, CLEAR, POWERS = (
    cli._quest_titles(PLUGIN / "content" / "ru")[(2, quest_id)]
    for quest_id in acts.quest_ids(2)
)


def walk_act2_by_tools(game, proj, call=None):
    """Акт 2 одними инструментами; действия человека видят хуки.

    `call(name, *values)` — как звать инструмент; по умолчанию `game.tool` с
    проверкой, что команда ответила нулём.
    """
    from test_act2_walkthrough import (
        do_clear, do_memory, do_plan, do_show, statusline_answered,
    )

    def plain(name, *values):
        code, out = game.tool(name, *values)
        assert code == 0, "{}: {}".format(name, out)
        return out

    call = call or plain
    call("enter")
    do_plan(game, proj)
    call("check", PLAN)
    do_show(game, proj)
    call("check", SHOW)
    do_memory(game, proj)
    call("check", MEMORY)
    do_clear(game, proj)
    call("seen", CLEAR)
    call("check", CLEAR)
    statusline_answered(game)
    call("folder")
    return call("ack", POWERS)


def test_whole_act2_is_walked_by_the_tools_alone(game, project):
    """Акт 2 новых инструментов не требует (спека #99): квест «Силы» берёт
    то, что игра видит сама, инструментом `folder` без пути."""
    proj = project()
    walk_to_the_end(game, proj)
    screens = []

    def call(name, *values):
        code, out = game.tool(name, *values)
        assert code == 0, "{}: {}".format(name, out)
        screens.append(out)
        return out

    closing = walk_act2_by_tools(game, proj, call)

    assert "Новый ранг: Падаван." in closing
    assert "Модель: Opus" in screens[-2]
    data = st.load(game.state_path)
    assert data["rank"] == "padawan"
    assert data["acts"]["2"]["status"] == ranks.STATUS_DONE
    for screen in screens:
        for quest_id in acts.quest_ids(2):
            assert quest_id not in screen, screen
    call("status")
    call("scroll")
    assert (proj / "docs" / "jedicoder" / "handoff.md").is_file()


#: Названия квестов Акта 3, как их печатает первый экран.
SKILL, WHERE, OWN_SKILL, HOOK, MOD = (
    cli._quest_titles(PLUGIN / "content" / "ru")[(3, quest_id)]
    for quest_id in acts.quest_ids(3)
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: в неё смотрят проверки Акта 3."""
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


def walk_act3_by_tools(game, proj, home, call=None):
    """Акт 3 одними инструментами; что делает Claude по словам человека,
    кладёт тест — как в `tests/test_act3_walkthrough.py`."""
    from test_act3_walkthrough import do_hook, do_own_skill

    def plain(name, *values):
        code, out = game.tool(name, *values)
        assert code == 0, "{}: {}".format(name, out)
        return out

    call = call or plain
    call("enter")
    # «Скилл» и «Где брать» закрывает рассказ: ставить нечего (#116).
    call("ack", SKILL)
    call("ack", WHERE)
    do_own_skill(proj)
    call("check", OWN_SKILL)
    do_hook(game, proj)
    call("check", HOOK)
    call("folder")
    return call("ack", MOD)


def test_whole_act3_is_walked_by_the_tools_alone(game, project, home):
    """Акт 3 новых инструментов не требует (#110): то, что игра знает о своём
    моде, отдаёт тот же `folder` без пути."""
    proj = project()
    walk_to_the_end(game, proj)
    walk_act2_by_tools(game, proj)
    screens = []

    def call(name, *values):
        code, out = game.tool(name, *values)
        assert code == 0, "{}: {}".format(name, out)
        screens.append(out)
        return out

    closing = walk_act3_by_tools(game, proj, home, call)

    assert "Новый ранг: Рыцарь." in closing
    assert screens[-2].splitlines()[-1] == cli.MOD_WORKS
    data = st.load(game.state_path)
    assert data["rank"] == "knight"
    assert data["acts"]["3"]["status"] == ranks.STATUS_DONE
    for screen in screens:
        for quest_id in acts.quest_ids(3):
            assert quest_id not in screen, screen
    call("status")
    call("scroll")
    assert (proj / "docs" / "jedicoder" / "investigate.md").is_file()
    assert tools.NAMES == (
        "status", "enter", "folder", "check", "seen", "ack", "scroll", "contract",
    )


#: Названия квестов Акта 4, как их печатает первый экран.
WHAT, PRODUCT_PLAN, BUILD, RUN, ACCEPT = (
    cli._quest_titles(PLUGIN / "content" / "ru")[(4, quest_id)]
    for quest_id in acts.quest_ids(4)
)


def walk_act4_by_tools(game, proj, call=None):
    """Акт 4 одними инструментами, ботом; что делает Claude, кладёт тест —
    как в `tests/test_act4_walkthrough.py`. Тип продукта записывает команда:
    инструмента для неё нет, как и для ответа про Книгу."""
    from test_act4_walkthrough import (
        BOT, approve_plan, do_build, do_key, do_what,
    )

    def plain(name, *values):
        code, out = game.tool(name, *values)
        assert code == 0, "{}: {}".format(name, out)
        return out

    call = call or plain
    call("enter")
    assert game("project", "type", BOT)[0] == 0
    do_what(proj, BOT)
    call("check", WHAT)
    approve_plan(game, proj)
    call("check", PRODUCT_PLAN)
    do_build(proj, BOT)
    call("check", BUILD)
    do_key(proj)
    call("seen", RUN)
    call("check", RUN)
    return call("ack", ACCEPT)


def test_whole_act4_is_walked_by_the_tools_alone(game, project, home):
    """Акт 4 новых инструментов не требует (#119): рассказ о боте — тот же
    `seen`, приёмка — тот же `ack`."""
    proj = project()
    walk_to_the_end(game, proj)
    walk_act2_by_tools(game, proj)
    walk_act3_by_tools(game, proj, home)
    screens = []

    def call(name, *values):
        code, out = game.tool(name, *values)
        assert code == 0, "{}: {}".format(name, out)
        screens.append(out)
        return out

    closing = walk_act4_by_tools(game, proj, call)

    assert "Новый ранг: Страж." in closing
    data = st.load(game.state_path)
    assert data["rank"] == ranks.FINAL_RANK == "sentinel"
    assert data["acts"]["4"]["status"] == ranks.STATUS_DONE
    for screen in screens:
        for quest_id in acts.quest_ids(4):
            assert quest_id not in screen, screen
    call("status")
    call("scroll")
    assert (proj / "docs" / "jedicoder" / "goal.md").is_file()
    assert tools.NAMES == (
        "status", "enter", "folder", "check", "seen", "ack", "scroll", "contract",
    )


def test_closed_act_is_answered_in_plain_words(game, project, home):
    """Последний играемый акт закрыт: открытого квеста нет."""
    proj = project()
    walk_to_the_end(game, proj)
    walk_act2_by_tools(game, proj)
    walk_act3_by_tools(game, proj, home)
    walk_act4_by_tools(game, proj)
    for name in ("check", "seen", "ack"):
        code, out = game.tool(name, ACCEPT)
        assert code == 1, out
        lines = out.splitlines()
        assert lines[0] == cli.TOOL_QUEST_CLOSED.format("«{}»".format(ACCEPT))
        assert lines[1] == cli.TOOL_NO_QUEST
        assert cli.preparing_phrase([5]) in out
        assert "05-accept" not in out and "Traceback" not in out
        code, out = game.tool(name, "Нет такого")
        assert code == 1 and out.splitlines()[0] == cli.TOOL_NO_QUEST
    code, out = game.tool("enter")
    assert code == 1 and "ещё не написан" in out


@pytest.mark.parametrize("text", ["", "{", "[1, 2]"])
def test_broken_save_is_not_a_traceback(game, text):
    game.state_path.write_text(text, encoding="utf-8")
    for name in tools.NAMES:
        code, out = game.tool(name, FOLDER)
        assert code in (0, 1), out
        assert "Traceback" not in out


def test_command_that_breaks_is_said_in_words_not_in_a_traceback(game, tmp_path):
    """Путь длиннее, чем терпит система: прежняя команда падала трейсбеком."""
    game.tool("enter")
    code, out = game.tool("folder", str(tmp_path / ("x" * 5000)))
    assert code == 1
    assert out.strip() == cli.TOOL_BROKEN.format("OSError")
    assert st.load(game.state_path)["project"].get("path") is None


def test_act_waiting_for_a_choice_is_answered_by_the_game(
        game, old_acts_open, monkeypatch):
    """Состав акта ждёт выбора: открытого квеста нет, и это сказано словами."""
    data = st.default_state("local-test")
    data["acts"] = {
        str(n): {"status": ranks.STATUS_DONE, "quests": {}} for n in (1, 2, 3)
    }
    data["acts"]["4"] = {"status": ranks.STATUS_IN_PROGRESS, "quests": {}}
    st.save(data, game.state_path)
    code, out = game.tool("check", FOLDER)
    assert code == 1
    assert out.splitlines()[0] == cli.TOOL_NO_QUEST
    assert "Traceback" not in out


# --- Чего через инструмент не позвать ----------------------------------------

@pytest.mark.parametrize("name", NEVER + ("", "project", "CHECK", "check;ls"))
def test_unlisted_name_is_refused_and_nothing_runs(game, name, monkeypatch):
    ran = []
    for command in cli.HANDLERS:
        if command == cli.TOOL_CALL:
            continue
        monkeypatch.setitem(
            cli.HANDLERS, command,
            lambda *args, _name=command: ran.append(_name) or 0,
        )
    code, out = game.tool(name, "confirm")
    assert code == 1, out
    assert "Traceback" not in out and out.strip()
    assert ran == []
    assert not game.state_path.exists()


def test_unlisted_name_is_named_back_with_the_list(game):
    code, out = game.tool("reset", "confirm")
    assert code == 1
    assert "reset" in out
    for name in tools.NAMES:
        assert name in out
    assert not game.state_path.exists()


def test_call_without_a_name_is_refused(game):
    code, out = game(cli.TOOL_CALL)
    assert code == 1 and out.strip()


def test_values_beyond_the_declared_input_are_dropped(game, project):
    """Модель не дотянется до чужой ручки лишним значением."""
    proj = project()
    game.tool("enter")
    game.tool("folder", str(proj), "db", "yes")
    data = st.load(game.state_path)
    assert data["project"]["path"] == str(proj)
    assert data["project"].get("has_db") is None
    # Проверке не подсунуть ни код другого квеста, ни другую папку.
    code, out = game.tool("check", FOLDER, "05-stop-undo", "/")
    assert code == 0, out
    assert acts.next_quest(st.load(game.state_path), 1) == "02-idea"
    code, out = game.tool("ack", "1", "05-stop-undo")
    assert code == 1 and attempts(game, "05-stop-undo") == 0


def test_folder_value_is_always_a_path_never_a_handle(game, tmp_path, monkeypatch):
    """`db`, `deploy`, `--help` — имена папок, а не ручки `project`."""
    monkeypatch.chdir(tmp_path)
    game.tool("enter")
    for value in ("db", "deploy", "ssh", "--help", "path", "-rf", "a; touch pwned"):
        code, out = game.tool("folder", value)
        assert code == 1, value
        assert "Не найдена папка" in out, out
    assert st.load(game.state_path)["project"].get("path") is None
    assert not (tmp_path / "pwned").exists()


# --- Папка -------------------------------------------------------------------

def test_relative_folder_is_counted_from_where_the_call_runs(
        game, tmp_path, monkeypatch):
    """Модуль зовёт команду из папки сессии: «здесь» значит её."""
    here = tmp_path / "session" / "my project; one"
    here.mkdir(parents=True)
    monkeypatch.chdir(here)
    game.tool("enter")
    code, out = game.tool("folder", ".")
    assert code == 0, out
    data = st.load(game.state_path)
    assert data["project"]["path"] == str(here.resolve())
    assert data["project"]["path_named"] == str(here.resolve())


def test_folder_in_home_is_written_with_a_tilde(game, tmp_path, monkeypatch):
    """Оболочки между моделью и командой нет: тильду раскрывает игра."""
    home = tmp_path / "home"
    (home / "site").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    game.tool("enter")
    code, out = game.tool("folder", "~/site")
    assert code == 0, out
    assert st.load(game.state_path)["project"]["path"] == str((home / "site").resolve())


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_folder_names_nothing(game, tmp_path, monkeypatch, value):
    """Пустой путь не записывает папку, в которой оказался вызов."""
    monkeypatch.chdir(tmp_path)
    game.tool("enter")
    code, out = game.tool("folder", value)
    assert code == 0, out
    assert "не названа" in out
    assert st.load(game.state_path)["project"].get("path") is None


# --- Страж: перечень и путь акта в скилле --------------------------------------

ACT1_SKILL = PLUGIN / "skills" / "act1-znakomstvo" / "SKILL.md"
CORE_SKILL = PLUGIN / "skills" / "core" / "SKILL.md"
START = PLUGIN / "commands" / "start.md"

#: Правило скиллов — одно на игру, дословно: есть инструмент — зови его,
#: нет — прежняя команда. Раздела системного промпта может не быть (чистая
#: машина, старый Claude Code), поэтому правило стоит в самих скиллах.
TOOL_RULE = "**Есть инструмент игры — зови его.**"
TOOL_FALLBACK = "Инструмента нет в списке"
TOOL_PREFIX = "`mcp__jedicoder__`"


def flat(path):
    return " ".join(path.read_text(encoding="utf-8").split())


def cells(row):
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def skill_table():
    """Таблица квестов скилла акта: (заголовки, строки по квестам)."""
    text = ACT1_SKILL.read_text(encoding="utf-8")
    body = re.search(r"^## Квесты\n(.*?)(?=^## )", text, re.M | re.S).group(1)
    rows = [line for line in body.splitlines() if line.startswith("|")]
    head = cells(rows[0])
    return head, [dict(zip(head, cells(row))) for row in rows[2:]]


@pytest.mark.parametrize("path", [CORE_SKILL, ACT1_SKILL, START],
                         ids=lambda p: p.parent.name)
def test_skill_says_tool_first_and_command_when_there_is_none(path):
    text = flat(path)
    assert TOOL_RULE in text, path
    assert TOOL_FALLBACK in text, path
    assert TOOL_PREFIX in text, path


def test_every_way_to_close_a_quest_in_the_skill_is_a_tool(game):
    """Таблица скилла — единственный перечень пути; инструменты идут по ней."""
    listed = {item["name"] for item in game.listing()}
    head, rows = skill_table()
    assert head[-2:] == ["Как закрывается", "Инструмент игры"]
    assert len(rows) == len(acts.ACT1_QUESTS)
    ways = set()
    for row, (quest_id, _, _) in zip(rows, acts.ACT1_QUESTS):
        assert row["Код"] == "`{}`".format(quest_id)
        commands = re.findall(
            r"`(\w+) 1 {}`".format(re.escape(quest_id)), row["Как закрывается"]
        )
        assert commands, row
        # Столбец инструментов называет те же шаги в том же порядке —
        # и ни акта, ни кода квеста.
        assert re.findall(r"`([^`]+)`", row["Инструмент игры"]) == commands, row
        for command in commands:
            assert command in listed, "{}: нет инструмента".format(command)
            assert tools.COMMANDS[command] == command
            ways.add(command)
    # Остальное на пути: контракт, первый экран, вход, папка и памятка.
    assert listed - ways == {"contract", "status", "enter", "folder", "scroll"}


ACT2_SKILL = PLUGIN / "skills" / "act2-pamyat-i-sily" / "SKILL.md"

#: Команды без инструмента: вопрос о Книге игра задаёт один раз, после
#: первого ранга, а ключ от бота называют не все (правило перечня: команд,
#: которые говорят с ботом, в нём нет).
NO_TOOL = ("book", "link")


@pytest.mark.parametrize("skill", [ACT1_SKILL, ACT2_SKILL],
                         ids=lambda p: p.parent.name)
def test_act_skill_names_a_tool_at_every_game_command_of_the_path(skill):
    """Строка с командой в терминале — и рядом инструмент, который её заменяет.

    Замер прототипа: где скилл называет только команду, модель её и
    выполняет.
    """
    text = skill.read_text(encoding="utf-8")
    lines = text.splitlines()
    by_command = {command: name for name, command in tools.COMMANDS.items()}
    seen_calls = 0
    for index, line in enumerate(lines):
        call = re.search(r'cli\.py" (\w+)', line)
        if not call or call.group(1) in NO_TOOL:
            continue
        seen_calls += 1
        name = by_command[call.group(1)]
        before = " ".join(lines[max(0, index - 4):index + 3])
        assert "`{}`".format(name) in before and "нструмент" in before, line
    assert seen_calls >= 8


def test_core_skill_lists_every_tool_and_nothing_else(game):
    text = CORE_SKILL.read_text(encoding="utf-8")
    body = re.search(r"^## Инструменты игры\n(.*?)(?=^## )", text, re.M | re.S).group(1)
    rows = [cells(line) for line in body.splitlines() if line.startswith("| `")]
    assert [row[0].strip("`") for row in rows] == list(tools.NAMES)
    for row in rows:
        name = row[0].strip("`")
        commands = re.findall(r"`(\w+)", row[2])
        assert commands and set(commands) == {tools.COMMANDS[name]}, row


def test_start_command_shows_the_first_screen_by_the_tool():
    """Первая команда игры тоже идёт инструментом, а не строкой в терминале."""
    text = START.read_text(encoding="utf-8")
    assert text.index(TOOL_RULE) < text.index("1. Найди корень плагина")
    rule = " ".join(text[text.index(TOOL_RULE):text.index("1. Найди")].split())
    assert "инструмент `status`" in rule

"""Контракт игры разделом системного промпта: `cli.py contract --section` (#92).

В Игровой сессии Лицо кладёт контракт в системный промпт, и модель больше не
грузит его командой в терминале. Слов у модуля нет: готовый текст раздела —
заголовок, по которому скиллы его опознают, и сам контракт — отдаёт команда.
Тесты ходят той же дверью, что модуль, — через CLI.

Три вещи, ради которых файл существует:

- текст раздела — тот же контракт, что печатает `contract`: второго текста
  в игре быть не должно;
- команда только читает. Модуль зовёт её в любой сессии на машине, где
  стоит плагин, — завести, починить или унести сохранение она не вправе;
- снимок Лица несёт отпечаток раздела: по нему модуль узнаёт, что текст
  сменился, и не зовёт команду раздела на каждом ходу.
"""
import json
import os
import re
from pathlib import Path

import pytest

from jedicoder import cli, contract
from jedicoder import state as st
from test_face import files_around

PLUGIN = Path(__file__).resolve().parents[1] / "plugin"

#: Фраза, которой скилл велит грузить контракт командой, — одна на все скиллы.
SKILL_RULE = "Раздела нет — загрузи контракт командой"


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

    def section():
        code, out = jc("contract", cli.CONTRACT_SECTION)
        assert code == 0, out
        return json.loads(out)

    def face(*argv):
        code, out = jc("face", *argv)
        assert code == 0, out
        return json.loads(out)

    jc.state_path = state_path
    jc.section = section
    jc.face = face
    return jc


def set_mode(game, mode):
    """Режим, как его записал бы хук: сохранение к этому часу уже есть."""
    if not game.state_path.exists():
        game("status")
    data = json.loads(game.state_path.read_text(encoding="utf-8"))
    data["permission_mode"] = mode
    game.state_path.write_text(json.dumps(data), encoding="utf-8")


# --- Текст раздела ------------------------------------------------------------

def test_section_opens_with_the_marker_and_carries_the_contract(game):
    set_mode(game, "bypassPermissions")
    _, printed = game("contract")
    text = game.section()["text"]
    assert text.splitlines()[0] == contract.SECTION_HEADER
    # `print` добавил команде свой перевод строки.
    assert printed.endswith("\n\n") and text.endswith(printed[:-1])
    # Заголовок раздела — не строка самого контракта: скилл опознаёт по нему
    # именно раздел системного промпта, а не вывод команды в разговоре.
    assert contract.SECTION_HEADER not in printed


def test_section_says_that_the_command_is_not_needed(game):
    set_mode(game, "bypassPermissions")
    lines = game.section()["text"].splitlines()
    assert lines[1] == "" and lines[2] == contract.SECTION_NOTE and lines[3] == ""


def test_section_tells_the_model_about_the_tools_of_the_game(game):
    """Инструменты объявляет модуль, а слова о них — здесь, не в модуле (#93)."""
    from jedicoder import tools

    set_mode(game, "bypassPermissions")
    lines = game.section()["text"].splitlines()
    assert lines[4] == contract.SECTION_TOOLS and lines[5] == ""
    said = contract.SECTION_TOOLS
    assert "`mcp__jedicoder__`" in said
    # Все, кроме одного: контракт уже лежит в этом разделе, грузить нечего.
    named = [name for name in tools.NAMES if name != "contract"]
    assert len(named) == len(tools.NAMES) - 1
    assert re.findall(r"`([a-z_]+)`", said.replace("`mcp__jedicoder__`", "")) == named
    # Без инструмента игра идёт прежней командой — и раздел это говорит.
    assert "в терминале" in said
    # В выводе команды `contract` этой строки нет: её читает только раздел.
    _, printed = game("contract")
    assert said not in printed


def test_no_line_of_the_contract_is_a_linter_marker(game, content_root):
    """Маркеры линтера нужны файлу, а не читателю: в выводе их нет.

    Инструмент `contract` показывает человеку первые строки ответа — и
    первой стояла `<!-- lint:novelty-ok: …` из `behavior.md`.
    """
    source = (content_root / "behavior.md").read_text(encoding="utf-8")
    assert "<!-- lint:" in source
    set_mode(game, "bypassPermissions")
    _, printed = game("contract")
    for text in (printed, game.section()["text"],
                 contract.load_behavior(content_root)):
        assert "lint:" not in text
        assert not any(
            line.lstrip().startswith("<!-- lint:") for line in text.splitlines()
        )
    assert printed.splitlines()[0].startswith("# ")


def test_marker_is_cut_whole_and_nothing_else_goes(tmp_path):
    (tmp_path / "behavior.md").write_text(
        "---\ncontract: behavior\nversion: 1\n---\n"
        "<!-- lint:novelty-ok: tool — причина\n     на две строки -->\n\n"
        "# Заголовок\n\nСтрока <!-- обычный комментарий --> остаётся.\n"
        "  <!-- lint:language-ok: images — ещё один -->\n"
        "Хвост про lint в тексте.\n",
        encoding="utf-8",
    )
    body = contract.load_behavior(tmp_path)
    assert body.strip().splitlines() == [
        "# Заголовок", "", "Строка <!-- обычный комментарий --> остаётся.",
        "Хвост про lint в тексте.",
    ]


def test_section_is_one_line_of_ascii_json(game):
    """Как снимок: локаль терминала, из которого позвал модуль, не уронит."""
    set_mode(game, "default")
    _, out = game("contract", cli.CONTRACT_SECTION)
    assert out.endswith("\n") and out.count("\n") == 1
    out.encode("ascii")
    assert sorted(json.loads(out)) == ["stamp", "text"]


def test_plain_contract_is_printed_as_before(game):
    """Без флага — прежний текст для модели: версии без модуля грузят его."""
    code, printed = game("contract")
    assert code == 0
    assert printed.startswith("<!--") or printed.startswith("# ")
    assert contract.SETTINGS_HEADER in printed
    assert contract.SECTION_HEADER not in printed


@pytest.mark.parametrize("mode, line", [
    ("bypassPermissions", contract.MODE_FREE),
    ("default", contract.MODE_OTHER.format("default")),
])
def test_section_names_the_mode_the_save_holds(game, mode, line):
    set_mode(game, mode)
    assert "- {}\n".format(line) in game.section()["text"]


@pytest.mark.parametrize("mode", [None, "что-то", ["default"]])
def test_no_section_until_the_game_knows_the_mode(game, mode):
    """Раздел застывает на всю сессию: «режим неизвестен» остался бы в нём.

    Без раздела модель грузит контракт командой — после первой команды игры,
    когда хук режим уже записал, и первый квест говорит о нём правду (#87).
    """
    game("status")
    if mode is not None:
        set_mode(game, mode)
    assert game("contract", cli.CONTRACT_SECTION) == (1, "")
    assert game.face("--called")["contract"] == ""
    # Команда для модели при этом печатает контракт, как печатала.
    code, printed = game("contract")
    assert code == 0 and "- {}\n".format(contract.MODE_UNKNOWN) in printed


# --- Отпечаток ----------------------------------------------------------------

def test_stamp_changes_with_the_text_and_only_with_it(game):
    set_mode(game, "default")
    first = game.section()
    assert first["stamp"] and game.section() == first
    set_mode(game, "bypassPermissions")
    second = game.section()
    assert second["stamp"] != first["stamp"] and second["text"] != first["text"]


def test_snapshot_carries_the_stamp_of_the_section(game):
    set_mode(game, "bypassPermissions")
    assert game.face("--called")["contract"] == game.section()["stamp"]
    set_mode(game, "default")
    assert game.face("--called")["contract"] == game.section()["stamp"]


def test_outside_a_game_session_the_snapshot_has_no_stamp(game, tmp_path):
    set_mode(game, "bypassPermissions")
    assert game.face("--called")["contract"]
    assert game.face("--cwd", str(tmp_path))["contract"] == ""


def test_unreadable_contract_means_no_stamp_and_no_section(game, tmp_path, capsys):
    set_mode(game, "bypassPermissions")
    capsys.readouterr()
    empty = tmp_path / "no-content"
    empty.mkdir()
    code = cli.main(["contract", cli.CONTRACT_SECTION], state_path=game.state_path,
                    content_root=empty, quests_root=empty)
    assert code == 1
    assert capsys.readouterr().out == ""
    code = cli.main(["face", "--called"], state_path=game.state_path,
                    content_root=empty, quests_root=empty)
    assert code == 0
    assert json.loads(capsys.readouterr().out)["contract"] == ""


def test_unknown_passport_value_means_no_section(game):
    """Паспорт правили руками: о поломке скажет команда игры, раздел молчит."""
    set_mode(game, "bypassPermissions")
    data = json.loads(game.state_path.read_text(encoding="utf-8"))
    data["passport"] = {"explain_depth": "whatever"}
    game.state_path.write_text(json.dumps(data), encoding="utf-8")
    code, out = game("contract", cli.CONTRACT_SECTION)
    assert (code, out) == (1, "")
    assert game.face("--called")["contract"] == ""


# --- Команда только читает ----------------------------------------------------

def test_no_save_means_no_section_and_no_file(game):
    before = files_around(game.state_path)
    assert game("contract", cli.CONTRACT_SECTION) == (1, "")
    assert game.face("--called")["contract"] == ""
    assert not game.state_path.exists()
    assert files_around(game.state_path) == before


def test_no_save_folder_is_not_created(tmp_path, content_root, quests_root, capsys):
    state_path = tmp_path / "nowhere" / "state.json"
    code = cli.main(
        ["contract", cli.CONTRACT_SECTION], state_path=state_path,
        content_root=content_root, quests_root=quests_root,
    )
    assert (code, capsys.readouterr().out) == (1, "")
    assert not state_path.parent.exists()


def test_section_does_not_touch_the_save(game):
    game("status")
    set_mode(game, "bypassPermissions")
    os.utime(str(game.state_path), (1_000_000_000, 1_000_000_000))
    before = (game.state_path.read_bytes(), game.state_path.stat().st_mtime_ns,
              files_around(game.state_path))
    game.section()
    assert (game.state_path.read_bytes(), game.state_path.stat().st_mtime_ns,
            files_around(game.state_path)) == before


def test_previous_game_save_is_not_archived(game, tmp_path):
    """Прежнюю игру уносит в архив `state.load`; раздел её только видит."""
    old = {"schema_version": st.REBUILT_GAME_SCHEMA - 1, "padawan_id": "p",
           "permission_mode": "bypassPermissions",
           "project": {"path": str(tmp_path)}, "acts": {"1": {"status": "done"}}}
    game.state_path.write_text(json.dumps(old), encoding="utf-8")
    os.utime(str(game.state_path), (1_000_000_000, 1_000_000_000))
    before = files_around(game.state_path)
    # Из прежней игры в раздел не берётся ничего — и режим тоже.
    assert game("contract", cli.CONTRACT_SECTION) == (1, "")
    assert json.loads(game.state_path.read_text(encoding="utf-8")) == old
    assert game.state_path.stat().st_mtime_ns == 1_000_000_000 * 10 ** 9
    assert files_around(game.state_path) == before


@pytest.mark.parametrize("text", ["{не json", "[1, 2]", ""])
def test_broken_save_stays_in_place_and_there_is_no_section(game, text):
    game.state_path.write_text(text, encoding="utf-8")
    before = files_around(game.state_path)
    assert game("contract", cli.CONTRACT_SECTION) == (1, "")
    assert game.state_path.read_text(encoding="utf-8") == text
    assert files_around(game.state_path) == before


def test_section_does_not_send_events_to_the_bot(game, monkeypatch):
    from jedicoder import sync

    set_mode(game, "bypassPermissions")
    calls = []
    monkeypatch.setattr(sync, "maybe_flush", lambda *a, **k: calls.append(a))
    game.section()
    assert calls == []
    game("contract")
    assert len(calls) == 1


# --- Скиллы называют тот же заголовок ----------------------------------------

LOADERS = sorted(
    path for path in list((PLUGIN / "skills").glob("*/SKILL.md"))
    + list((PLUGIN / "commands").glob("*.md"))
    if "cli.py\" contract" in path.read_text(encoding="utf-8")
)


def test_every_skill_that_loads_the_contract_is_found():
    names = {path.parent.name for path in LOADERS}
    assert {"core", "act1-znakomstvo", "magistr"} <= names


@pytest.mark.parametrize("path", LOADERS, ids=lambda p: p.parent.name)
def test_skill_loads_the_contract_only_when_the_section_is_missing(path):
    """Признак один на игру: заголовок, который печатает команда раздела.

    Скилл называет его дословно и велит грузить контракт командой, только
    когда раздела в системном промпте нет. Без Лица (старый Claude Code)
    раздела нет никогда — модель грузит контракт, как раньше.
    """
    text = path.read_text(encoding="utf-8")
    assert "`{}`".format(contract.SECTION_HEADER) in text, path
    assert SKILL_RULE in " ".join(text.split()), path


def test_no_skill_speaks_of_loading_the_contract_first_any_more():
    stale = ("грузишь первым делом", "загруженного шагом 1",
             "загруженного перед началом")
    for path in (PLUGIN / "skills").glob("*/SKILL.md"):
        text = " ".join(path.read_text(encoding="utf-8").split())
        for phrase in stale:
            assert phrase not in text, "{}: {}".format(path.parent.name, phrase)

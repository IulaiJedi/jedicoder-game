"""Квест «Силы»: что игра сама видит в Claude Code (#103).

Квест закрывает рассказ человека: какая модель стоит и сколько осталось до
лимита. Модели нужно, с чем его сверить, — и игра это знает: строка состояния
(`statusline.py`) после каждого ответа кладёт снимок рядом с сохранением.
Модель получает его словами одним вызовом — экраном `project` без аргументов
(инструмент `folder` без пути), тем же, где игра говорит ей, что знает о
проекте.

Шов — команда игры и скрипт строки состояния процессом, как его зовёт Claude
Code. Снимок ложится рядом с сохранением теста: настоящий
`~/.jedicoder/statusline.json` не читается и не пишется.

Имён моделей и чисел лимитов в текстах игры нет: печатается то, что пришло от
Claude Code.
"""
import json
from pathlib import Path

import pytest

from jedicoder import cli, statusline
from jedicoder import state as st
from test_act2_entry import close_act1, entered, game  # noqa: F401 — фикстуры
import test_act2_walkthrough as w
from test_act2_walkthrough import statusline_answered
from test_statusline import EXAMPLE

ROOT = Path(__file__).resolve().parents[1]
HEAD = "Claude Code — что игра видит сама:"
UNSEEN = [
    "",
    HEAD,
    "  Модель, уровень усилий и лимиты: игра этого не видит.",
    "  Свежих данных от строки состояния Claude Code нет.",
]


def powers(game):  # noqa: F811
    """Строки о Claude Code на экране `project` — с пустой строки перед ними."""
    code, out = game("project")
    assert code == 0, out
    lines = out.splitlines()
    assert HEAD in lines, out
    return lines[lines.index(HEAD) - 1:]


def test_the_game_says_what_claude_code_told_it(entered):
    game, _ = entered  # noqa: F811
    statusline_answered(game)
    assert powers(game) == [
        "",
        HEAD,
        "  Модель: Opus",
        "  Уровень усилий: high",
        "  Лимит на пять часов: занято 24%",
        "  Лимит на неделю: занято 41%",
    ]


def test_the_words_come_from_claude_code_and_not_from_the_game(entered):
    """Ни имени модели, ни числа игра не держит: что пришло, то и печатает."""
    game, _ = entered  # noqa: F811
    told = dict(
        EXAMPLE, model={"id": "proverochnaya-9", "display_name": "Проверочная 9"},
        effort={"level": "проверочный"},
        rate_limits={"five_hour": {"used_percentage": 7},
                     "seven_day": {"used_percentage": 99.6}},
    )
    statusline_answered(game, told)
    assert powers(game)[2:] == [
        "  Модель: Проверочная 9",
        "  Уровень усилий: проверочный",
        "  Лимит на пять часов: занято 7%",
        "  Лимит на неделю: занято 100%",
    ]


def test_without_a_statusline_the_game_says_it_does_not_see(entered):
    """Строка состояния не включена: снимка нет — и игра не выдумывает."""
    game, _ = entered  # noqa: F811
    assert not (game.state_path.parent / statusline.SNAPSHOT_NAME).exists()
    assert powers(game) == UNSEEN


def test_limits_claude_code_did_not_tell_are_named_unseen(entered):
    """Не подписчик или первый ответ ещё не пришёл: лимитов в данных нет."""
    game, _ = entered  # noqa: F811
    statusline_answered(
        game, {k: v for k, v in EXAMPLE.items() if k != "rate_limits"}
    )
    assert powers(game)[2:] == [
        "  Модель: Opus",
        "  Уровень усилий: high",
        "  Лимиты: игра этого не видит — Claude Code их не передал.",
    ]


def test_one_limit_told_and_one_not(entered):
    game, _ = entered  # noqa: F811
    statusline_answered(game, dict(
        EXAMPLE, rate_limits={"five_hour": {"used_percentage": 23.5}},
    ))
    assert powers(game)[4:] == [
        "  Лимит на пять часов: занято 24%",
        "  Лимит на неделю: игра этого не видит.",
    ]


def test_model_and_effort_claude_code_did_not_tell_are_named_unseen(entered):
    game, _ = entered  # noqa: F811
    statusline_answered(game, {
        k: v for k, v in EXAMPLE.items() if k not in ("model", "effort")
    })
    assert powers(game)[2:4] == [
        "  Модель: игра этого не видит.",
        "  Уровень усилий: игра этого не видит.",
    ]


def test_an_old_snapshot_is_not_passed_off_as_today(entered):
    """Строку состояния убрали неделю назад — файл остался. Сверять рассказ
    с прошлой неделей нельзя: игра говорит, что не видит."""
    game, _ = entered  # noqa: F811
    path = game.state_path.parent / statusline.SNAPSHOT_NAME
    week_ago = statusline.snapshot(EXAMPLE)["written_at"] - 7 * 24 * 3600
    statusline.write_snapshot(statusline.snapshot(EXAMPLE, now=week_ago), path)
    assert powers(game) == UNSEEN


@pytest.mark.parametrize("text", [
    "", "{", "[1, 2]", '"строка"', "null",
    '{"model": "Opus", "effort": 5, "limits": [], "written_at": "вчера"}',
    '{"model": {"name": 7}, "limits": {"five_hour": {"used": "много"}}}',
])
def test_a_broken_snapshot_is_not_a_traceback(entered, text):
    game, _ = entered  # noqa: F811
    path = game.state_path.parent / statusline.SNAPSHOT_NAME
    path.write_text(text, encoding="utf-8")
    assert powers(game) == UNSEEN


def test_a_fresh_snapshot_with_garbage_inside_names_each_thing_unseen(entered):
    game, _ = entered  # noqa: F811
    path = game.state_path.parent / statusline.SNAPSHOT_NAME
    snap = statusline.snapshot(EXAMPLE)
    snap.update(model={"name": 7}, effort=["high"],
                limits={"five_hour": {"used": "много"}, "seven_day": None})
    path.write_text(json.dumps(snap), encoding="utf-8")
    assert powers(game)[2:] == [
        "  Модель: игра этого не видит.",
        "  Уровень усилий: игра этого не видит.",
        "  Лимиты: игра этого не видит — Claude Code их не передал.",
    ]


@pytest.mark.parametrize("used", [
    -5, 250, float("inf"), 10 ** 400, True, "14",
])
def test_a_limit_that_is_not_a_share_is_named_unseen(entered, used):
    game, _ = entered  # noqa: F811
    path = game.state_path.parent / statusline.SNAPSHOT_NAME
    snap = statusline.snapshot(EXAMPLE)
    snap["limits"]["five_hour"]["used"] = used
    path.write_text(json.dumps(snap), encoding="utf-8")
    assert powers(game)[4:] == [
        "  Лимит на пять часов: игра этого не видит.",
        "  Лимит на неделю: занято 41%",
    ]


@pytest.mark.parametrize("written", [
    10 ** 400, float("inf"), -1, statusline.snapshot(EXAMPLE)["written_at"] + 86400,
])
def test_a_snapshot_with_an_impossible_time_is_not_fresh(entered, written):
    game, _ = entered  # noqa: F811
    path = game.state_path.parent / statusline.SNAPSHOT_NAME
    snap = dict(statusline.snapshot(EXAMPLE), written_at=written)
    path.write_text(json.dumps(snap), encoding="utf-8")
    assert powers(game) == UNSEEN


def test_a_name_from_claude_code_stays_one_plain_line(entered):
    game, _ = entered  # noqa: F811
    statusline_answered(game, dict(
        EXAMPLE, model={"display_name": "Opus\n\x1b[31m  красный" + "я" * 300},
    ))
    line = powers(game)[2]
    assert line.startswith("  Модель: Opus [31m красный")
    assert "\x1b" not in line and len(line) < 100


def test_the_tool_gives_the_same_words(entered):
    """Модель зовёт инструмент `folder` без пути — ответ той же команды."""
    game, _ = entered  # noqa: F811
    statusline_answered(game)
    assert game(cli.TOOL_CALL, "folder") == game("project")


def test_before_the_act_the_project_screen_says_nothing_about_claude_code(
        game, project):  # noqa: F811
    """Первый вечер: о модели и лимитах человек ещё не слышал."""
    proj = project()
    close_act1(game, proj)
    statusline_answered(game)
    code, out = game("project")
    assert code == 0
    assert out == "Проект:\n  Папка: {}\n".format(proj.resolve())


def test_reading_the_snapshot_does_not_write_anything(entered):
    game, _ = entered  # noqa: F811
    statusline_answered(game)
    path = game.state_path.parent / statusline.SNAPSHOT_NAME
    before = (path.read_bytes(), game.state_path.read_bytes())
    powers(game)
    assert (path.read_bytes(), game.state_path.read_bytes()) == before


def test_the_real_snapshot_is_never_read(entered, monkeypatch, tmp_path):
    """Снимок ищется рядом с сохранением команды, а не дома."""
    game, _ = entered  # noqa: F811
    elsewhere = tmp_path / "doma"
    elsewhere.mkdir()
    statusline.write_snapshot(
        statusline.snapshot(EXAMPLE), elsewhere / statusline.SNAPSHOT_NAME
    )
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(elsewhere / "state.json"))
    assert st.state_path() == elsewhere / "state.json"
    assert powers(game) == UNSEEN


# --- Правила про лимит печатает экран закрытия (#122) ------------------------
#
# Живая приёмка 0.11.0: модель закрыла «Силы», не сказав трёх правил, и урок
# квеста пропал. Правила теперь печатает игра — тем же экраном, что закрывает
# квест, — а скилл велит прочитать их с экрана.

LIMIT_SCREEN = [
    "Квест «Силы» закрыт: ты рассказал, что увидел.",
    "",
    "Три правила про лимит.",
    "  1. Упёрся в лимит посреди работы — не страшно. Claude спросит, что "
    "делать: выбери «продолжить после сброса».",
    "  2. Лимит кончается, а большая задача не начата — подожди сброса.",
    "  3. Чем короче разговор, тем медленнее тратится лимит: каждый запрос "
    "тянет за собой весь разговор.",
]


def test_closing_the_quest_prints_the_three_limit_rules(entered):
    game, _ = entered  # noqa: F811
    code, out = game("ack", "2", "05-powers")
    assert code == 0, out
    assert out.splitlines() == LIMIT_SCREEN


def test_the_tool_closes_the_quest_with_the_same_rules(entered):
    """Модель закрывает квест инструментом — правила те же, слово в слово.

    Инструмент закрывает только открытый квест, поэтому четыре первых
    закрываются той же дверью, что у человека; последний экран — закрытие
    акта под правилами."""
    game, proj = entered  # noqa: F811
    w.do_plan(game, proj)
    assert game("check", "2", "01-plan")[0] == 0
    w.do_show(game, proj)
    assert game("check", "2", "02-show")[0] == 0
    w.do_memory(game, proj)
    assert game("check", "2", "03-memory")[0] == 0
    w.do_clear(game, proj)
    assert game("seen", "2", "04-clear")[0] == 0
    assert game("check", "2", "04-clear")[0] == 0
    code, out = game(cli.TOOL_CALL, "ack", "Силы")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[:len(LIMIT_SCREEN)] == LIMIT_SCREEN
    assert "Новый ранг: Падаван." in lines


def test_the_rules_are_printed_once_and_only_for_powers():
    """Другие квесты, закрытые рассказом, правил о лимите не печатают."""
    for (act, quest_id), screen in cli.ACK_SCREENS.items():
        if (act, quest_id) != (2, "05-powers"):
            assert "лимит" not in screen, quest_id
    assert cli.ACK_SCREEN_DEFAULT.count("лимит") == 0


def test_the_act_skill_reads_the_rules_from_the_screen():
    """Копия правил одна — на экране игры. Скилл их не дублирует: модель
    сказала бы их дважды или по памяти, а не с экрана."""
    skill = (ROOT / "plugin" / "skills" / "act2-pamyat-i-sily" / "SKILL.md"
             ).read_text(encoding="utf-8")
    assert "продолжить после сброса" not in skill
    assert "три правила про лимит" in skill

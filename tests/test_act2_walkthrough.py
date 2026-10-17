"""Сквозной проход Акта 2 «Память и силы» — той же дверью, что человек (#103).

Чистое сохранение → Акт 1 командами игры → `enter 2` → хуки с настоящими по
форме данными → проверки, рассказ, подтверждение → ранг Падаван → памятка.
Сохранение не засевается нигде: следы пишет хук `plugin/hooks/traces.py`
процессом, снимок строки состояния — сам скрипт `statusline.py` процессом,
закрытые квесты — команды игры.

`walk_act2` — общий проход для тестов следующих актов: к закрытому Акту 2
можно прийти только так. Конец игры — закрытый Акт 5, его проходит
`walk_act5` в `tests/test_act5_walkthrough.py`: закрытие последнего акта,
`finale`, трофей на карточке и полоса после конца стережутся там.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jedicoder import acts, cli, debrief, ranks
from jedicoder import state as st
from test_act2_checks import MEMORY_OK
from test_act2_entry import QUESTS, close_act1, game  # noqa: F401 — фикстура
from test_human_screens import machine_words
from test_show_traces import asked
from test_statusline import EXAMPLE
from test_traces import clear_end, clear_start, fire, plan_approved, plan_shown

ROOT = Path(__file__).resolve().parents[1]
STATUSLINE = ROOT / "plugin" / "lib" / "jedicoder" / "statusline.py"


def hook(game, payload):  # noqa: F811
    """Хук той же сессии, что игра: пишет в её сохранение."""
    return fire(game.state_path, payload)


def statusline_answered(game, data=None):  # noqa: F811
    """Claude Code ответил и позвал строку состояния: снимок лёг рядом с
    сохранением игры — туда же, куда его кладёт настоящая установка."""
    done = subprocess.run(
        [sys.executable, str(STATUSLINE)],
        input=json.dumps(EXAMPLE if data is None else data),
        capture_output=True, text=True, timeout=10,
        env=dict(os.environ, JEDICODER_STATE_PATH=str(game.state_path)),
    )
    assert done.returncode == 0, done.stderr
    return done


def do_plan(game, proj):  # noqa: F811
    """План показан и одобрен: Enter на первой строке."""
    hook(game, plan_shown(cwd=proj))
    hook(game, plan_approved(cwd=proj))


def do_show(game, proj):  # noqa: F811
    """Файл проекта через `@` и вставленный снимок экрана."""
    (proj / "notes.txt").write_text("молоко\n", encoding="utf-8")
    hook(game, asked("что в @notes.txt?", proj))
    hook(game, asked("[Image #1] что на снимке?", proj))


def do_memory(game, proj):  # noqa: F811
    (proj / "CLAUDE.md").write_text(MEMORY_OK, encoding="utf-8")


def do_clear(game, proj):  # noqa: F811
    """`/clear`: прежний разговор кончился, новый начался в папке проекта."""
    hook(game, clear_end(cwd=proj))
    hook(game, clear_start(cwd=proj))


def walk_act2(game, proj, screens=None):  # noqa: F811
    """Пройти Акт 2 от входа до закрытия. Акт 1 к этому времени закрыт.

    `screens` — список, в который ложится каждый экран пути по порядку.
    Возвращает экран последней команды — закрытие акта.
    """
    def step(*argv, **expect):
        code, out = game(*argv)
        assert code == expect.get("code", 0), (argv, out)
        if screens is not None:
            screens.append(out)
        return out

    step("enter", "2")
    do_plan(game, proj)
    step("check", "2", "01-plan")
    do_show(game, proj)
    step("check", "2", "02-show")
    do_memory(game, proj)
    step("check", "2", "03-memory")
    do_clear(game, proj)
    step("seen", "2", "04-clear")
    step("check", "2", "04-clear")
    # «Силы»: человек рассказал, модель спрашивает игру, с чем сверить.
    statusline_answered(game)
    step("project")
    return step("ack", "2", "05-powers")


def walk_two_acts(game, proj, screens=None):  # noqa: F811
    """Два вечера командами и хуками: Акт 1, потом Акт 2."""
    close_act1(game, proj)
    return walk_act2(game, proj, screens)


@pytest.fixture
def finished(game, project):  # noqa: F811
    """Акт 2 закрыт, третий не начат. Отдаёт (игра, папка, экраны)."""
    proj = project()
    screens = []
    walk_two_acts(game, proj, screens)
    return game, proj, screens


# --- проход ------------------------------------------------------------------

def test_novice_walks_act2_from_a_clean_save_to_padawan(game, project):  # noqa: F811
    proj = project()
    assert not game.state_path.exists()
    close_act1(game, proj)
    data = st.load(game.state_path)
    assert data["rank"] == "seeker"
    assert data[st.TRACES_KEY] == {}

    walk_act2(game, proj)

    data = st.load(game.state_path)
    assert data["rank"] == "padawan"
    assert data["acts"]["2"]["status"] == ranks.STATUS_DONE
    assert acts.all_closed(data, 2) is True
    assert sorted(data["acts"]["2"]["quests"]) == sorted(QUESTS)
    assert data["artifacts"] == ["brainstorm", "handoff"]
    assert ranks.rank_for(data) == "padawan"
    # Каждый след акта помечен: действие сделано, пока шёл его акт. Следа
    # слова хука ещё нет — он из Акта 3.
    for kind in (st.TRACE_PLAN_APPROVED, st.TRACE_FILE_SHOWN,
                 st.TRACE_IMAGE_SHOWN, st.TRACE_CLEARED):
        assert cli._trace_counts(data, kind), kind
    assert st.trace(data, st.TRACE_HOOK_WORD) is None
    # Попыток ровно по одной: ни одна проверка по дороге не провалилась.
    facts = debrief.facts(data)
    assert facts["acts_completed"] == [1, 2]
    assert facts["first_try"]["passed"] == facts["first_try"]["attempted"]


def test_the_act_stays_open_until_the_last_quest(game, project):  # noqa: F811
    proj = project()
    close_act1(game, proj)
    assert game("enter", "2")[0] == 0
    do_plan(game, proj)
    do_show(game, proj)
    do_memory(game, proj)
    for quest_id in ("01-plan", "02-show", "03-memory"):
        assert game("check", "2", quest_id)[0] == 0
    # `/clear` считается только после записанной памяти проекта.
    do_clear(game, proj)
    assert game("seen", "2", "04-clear")[0] == 0
    code, out = game("check", "2", "04-clear")
    assert code == 0
    assert "Акт 2" not in out and "ранг" not in out.lower()
    data = st.load(game.state_path)
    assert data["rank"] == "seeker"
    assert data["acts"]["2"]["status"] == ranks.STATUS_IN_PROGRESS


# --- что человек читает на пути закрытия ---------------------------------------

def test_closing_the_act_names_the_rank_and_the_game_goes_on(finished):
    _, _, screens = finished
    # Под строкой закрытия — три правила про лимит (#122), за ними акт и ранг.
    rules = len(cli.LIMIT_RULES)
    assert screens[-1].splitlines()[:5 + rules] == [
        "Квест «Силы» закрыт: ты рассказал, что увидел.",
        "",
    ] + list(cli.LIMIT_RULES) + [
        "",
        "Акт 2. Память и силы — закрыт.",
        "Новый ранг: Падаван.",
    ]
    # Впереди Акт 3: о конце игры здесь ни слова. Смотрится хвост после
    # закрытия акта: «Лимит кончается» во втором правиле — не о конце игры.
    tail = screens[-1].split("Акт 2. Память и силы — закрыт.", 1)[1]
    assert "кончается" not in tail and "ещё не написан" not in tail
    assert "finale" not in screens[-1] and "бесплатна" not in screens[-1]


def test_before_the_last_quest_the_game_tells_the_model_what_it_sees(finished):
    """Одним вызовом на пути квеста «Силы» — с чем сверить рассказ."""
    _, proj, screens = finished
    assert screens[-2].splitlines() == [
        "Проект:",
        "  Папка: {}".format(proj.resolve()),
        "",
        "Claude Code — что игра видит сама:",
        "  Модель: Opus",
        "  Уровень усилий: high",
        "  Лимит на пять часов: занято 24%",
        "  Лимит на неделю: занято 41%",
    ]


def test_the_last_quest_closes_by_words_when_the_game_sees_nothing(
        game, project):  # noqa: F811
    """Строки состояния нет — квест всё равно закрывает рассказ."""
    proj = project()
    close_act1(game, proj)
    assert game("enter", "2")[0] == 0
    do_plan(game, proj)
    do_show(game, proj)
    do_memory(game, proj)
    for quest_id in ("01-plan", "02-show", "03-memory"):
        assert game("check", "2", quest_id)[0] == 0
    do_clear(game, proj)
    assert game("seen", "2", "04-clear")[0] == 0
    assert game("check", "2", "04-clear")[0] == 0
    code, out = game("project")
    assert code == 0 and "игра этого не видит" in out
    code, out = game("ack", "2", "05-powers")
    assert code == 0, out
    assert "Новый ранг: Падаван." in out


def test_no_screen_of_act2_speaks_to_the_model(finished):
    game, _, screens = finished  # noqa: F811
    screens.append(game("status")[1])
    for screen in screens:
        assert machine_words(screen) == [], screen
        assert "Traceback" not in screen


def test_first_screen_after_act2_points_at_act3(finished):
    game, _, _ = finished  # noqa: F811
    code, out = game("status")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "Ранг: Падаван"
    start = lines.index("Карта:")
    assert lines[start:start + 6] == [
        "Карта:",
        "  Акт 1. Знакомство — пройден",
        "  Акт 2. Память и силы — пройден",
        "  Акт 3. Умения — не начат, квестов закрыто: 0/5",
        "  Акт 4. Свой продукт — не начат, квестов закрыто: 0/5",
        "  Акт 5. Три места кода — не начат, квестов закрыто: 0/5",
    ]
    head = lines.index("Приёмы: скажи Claude слова в кавычках — он применит приём.")
    assert lines[head + 1:head + 3] == [
        "  найти идею — «помоги найти идею»",
        "  начать следующий разговор с того же места — "
        "«запиши передачу»",
    ]
    assert lines[-2:] == [
        "Что дальше: начать Акт 3 «Умения» — квестов в нём 5.",
        "  Скажи Claude: «начинаем».",
    ]


def test_memo_after_act2_carries_the_handoff_and_counts_playable_acts(
        finished):
    game, proj, _ = finished  # noqa: F811
    code, out = game("scroll")
    assert code == 0, out
    assert out.splitlines()[0] == "Памятка Падавана: {}/docs/jedicoder".format(
        proj.name
    )
    assert machine_words(out) == []
    folder = proj / "docs" / "jedicoder"
    names = sorted(path.name for path in folder.iterdir())
    assert "handoff.md" in names and "brainstorm.md" in names
    assert "plan.md" not in names and "investigate.md" not in names
    assert "HANDOFF.md" in (folder / "handoff.md").read_text(encoding="utf-8")
    razbor = (folder / "razbor.md").read_text(encoding="utf-8")
    # Счёт актов — по играемым: с 2026-10-16 играются все пять.
    assert "- Закрыто актов: 2 из 5" in razbor
    assert "из 4" not in razbor
    for quest_id in QUESTS:
        assert quest_id not in razbor
    for title in ("План", "Покажи", "Память проекта", "Чистый лист", "Силы"):
        assert "| 2 | {} | 1 | да |".format(title) in razbor
    # Фраз третьего вечера в памятке ещё нет: в акт не входили.
    frazy = (folder / "frazy.md").read_text(encoding="utf-8")
    assert "ссылка на скилл" not in frazy and "чистка" not in frazy


# --- Полоса, всплывающие и карта в каждом состоянии акта ------------------------

def strip_and_map(game, content_root):  # noqa: F811
    """Что видит человек: строка «Что дальше» первого экрана, она же в
    снимке Лица, строка карты об Акте 2 и то, по чему Лицо решает о
    всплывающих (`quests_closed`, `rank`, подписи)."""
    code, out = game("status")
    assert code == 0, out
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Что дальше:"))
    step = [line.strip() for line in lines[start:start + 2]]
    code, raw = game("face", "--called")
    assert code == 0, raw
    face = json.loads(raw)
    assert face["is_game"] is True
    assert face["next"] == step
    assert face["toast_quest"] == "Квест закрыт"
    assert face["toast_rank"] == "Новый ранг: {}".format(face["rank"])
    act2 = next(line.strip() for line in lines if line.startswith("  Акт 2."))
    return step[0], step[1], act2, face["quests_closed"], face["rank"], face["say"]


def test_strip_toasts_and_map_are_true_in_every_state_of_the_act(
        game, project, content_root):  # noqa: F811
    proj = project()
    close_act1(game, proj)
    tasks = cli._quest_tasks(content_root)
    quest = "Что дальше: квест «{}» — Акт 2 «Память и силы»."
    going = "Акт 2. Память и силы — идёт, квестов закрыто: {}/5"

    def see():
        return strip_and_map(game, content_root)

    # Акт 1 закрыт, во второй не входили.
    assert see() == (
        "Что дальше: начать Акт 2 «Память и силы» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
        "Акт 2. Память и силы — не начат, квестов закрыто: 0/5",
        5, "Искатель", cli.SAY_START,
    )

    assert game("enter", "2")[0] == 0
    assert see() == (quest.format("План"), tasks[(2, "01-plan")],
                     going.format(0), 5, "Искатель", "")
    hook(game, plan_shown(cwd=proj))
    assert see()[1] == tasks[(2, "01-plan")]      # показан — не одобрен
    hook(game, plan_approved(cwd=proj))
    assert see() == (quest.format("План"), cli.STEP_PLAN_APPROVED,
                     going.format(0), 5, "Искатель", "")
    assert game("check", "2", "01-plan")[0] == 0

    assert see() == (quest.format("Покажи"), tasks[(2, "02-show")],
                     going.format(1), 6, "Искатель", "")
    do_show(game, proj)
    assert see() == (quest.format("Покажи"), cli.STEP_SHOWN,
                     going.format(1), 6, "Искатель", "")
    assert game("check", "2", "02-show")[0] == 0

    assert see() == (quest.format("Память проекта"), tasks[(2, "03-memory")],
                     going.format(2), 7, "Искатель", "")
    # Файл записан, проверка ещё не шла: игра этого сама не знает — задание.
    do_memory(game, proj)
    assert see()[1] == tasks[(2, "03-memory")]
    assert game("check", "2", "03-memory")[0] == 0

    assert see() == (quest.format("Чистый лист"), tasks[(2, "04-clear")],
                     going.format(3), 8, "Искатель", "")
    do_clear(game, proj)
    assert see()[1] == cli.STEP_NEW_TALK          # `/clear` был — рассказа нет
    assert game("seen", "2", "04-clear")[0] == 0
    assert see() == (quest.format("Чистый лист"), cli.STEP_WORDS_TAKEN,
                     going.format(3), 8, "Искатель", "")
    assert game("check", "2", "04-clear")[0] == 0

    assert see() == (quest.format("Силы"), tasks[(2, "05-powers")],
                     going.format(4), 9, "Искатель", "")
    # Игра рассказала модели, что видит сама: шаг от этого не меняется.
    statusline_answered(game)
    assert game("project")[0] == 0
    assert see()[1] == tasks[(2, "05-powers")]
    assert game("ack", "2", "05-powers")[0] == 0

    # Акт закрыт: ранг вырос — Лицо покажет подпись о ранге, а не о квесте;
    # полоса зовёт в следующий акт.
    assert see() == (
        "Что дальше: начать Акт 3 «Умения» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
        "Акт 2. Память и силы — пройден",
        10, "Падаван", cli.SAY_START,
    )


# --- рассказ, когда проверка не может посмотреть (#103) -------------------------

def test_words_are_not_taken_when_the_project_folder_is_gone(
        game, project, tmp_path):  # noqa: F811
    """Папки проекта нет — игра говорит о папке, а не «не видела разговора»:
    новый разговор был, и просить `/clear` ещё раз значило бы солгать."""
    proj = project()
    close_act1(game, proj)
    assert game("enter", "2")[0] == 0
    do_memory(game, proj)
    assert game("check", "2", "03-memory")[0] == 0
    do_clear(game, proj)
    proj.rename(tmp_path / "унесли")

    code, out = game("seen", "2", "04-clear")

    assert code == 1
    assert out.splitlines() == [
        "Папка проекта не найдена: {}".format(proj.name),
        "  Рассказ пока не записан: игра не может посмотреть в папку.",
        "  Скажи Claude, где проект лежит теперь.",
    ]
    assert "разговор" not in out and "/clear" not in out
    assert machine_words(out) == []
    data = st.load(game.state_path)
    assert "04-clear" not in data["acts"]["2"]["quests"]

    # Папку вернули — рассказ принимается: след никуда не делся.
    (tmp_path / "унесли").rename(proj)
    assert game("seen", "2", "04-clear")[0] == 0
    assert game("check", "2", "04-clear")[0] == 0


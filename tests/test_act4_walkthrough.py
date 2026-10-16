"""Сквозной проход Акта 4 «Свой продукт» — той же дверью, что человек (#119).

Чистое сохранение → Акт 1 командами игры → Акты 2 и 3 командами и хуками
(`walk_act2`, `walk_act3`) → `enter 4` → тип продукта командой игры → раздел
«Продукт» → план одобрен (хук следов процессом) → три сохранения шагов →
«Работает» обеими ветками → приёмка рассказом → ранг Страж → памятка.

Ветки две. Сайт: Claude запускает его встроенным сервером Python на
свободном порту и называет порт игре; проверка открывает адрес живым curl.
Бот: ключ берётся первым шагом сборки (#120) — Claude закрывает `.env` от
сохранений, потом кладёт в него ключ (выдуманный, по форме ключа Telegram);
шаги бота человек видит в Telegram. В «Работает» человек написал боту и
рассказал, что тот ответил, — потом проверка.

Сохранение не засевается нигде: следы пишет хук, закрытые квесты — команды
игры. Что делает Claude по словам человека — файлы и сохранения, — кладёт
тест так, как это делает Claude по замеру
(`docs/research/2026-10-14-act4-facts.md`): раздел «Продукт» в конец
`IDEA.md` и сразу в сохранение, шаги плана — по одному, с сохранением.

Сегодня это конец игры: Акт 5 ещё не написан. `walk_act4` — общий проход
для тестов «конца игры» в других файлах.
"""
import json
import os
import subprocess

import pytest

from conftest import _git
from jedicoder import acts, cli, debrief, ranks
from jedicoder import state as st
from test_act2_entry import close_act1, game  # noqa: F401 — фикстура
from test_act2_walkthrough import hook, walk_act2
from test_act3_walkthrough import walk_act3
from test_act4_checks import (
    BOT_CODE, PRODUCT_BOT, PRODUCT_SITE, TOKEN, past_the_last_save, serve,
)
from test_act4_entry import QUESTS, TITLES
from test_human_screens import machine_words
from test_traces import plan_approved

SITE, BOT = acts.PRODUCT_SITE, acts.PRODUCT_BOT
KINDS = (SITE, BOT)

#: Раздел «Продукт» по типу — как его записал Claude в замере.
PRODUCT = {SITE: PRODUCT_SITE, BOT: PRODUCT_BOT}

#: Шаги плана — по одному сохранению на шаг.
STEPS = {
    SITE: (
        ("Шаг 1: каркас страницы", {"index.html": "<h1>Кружок «Радуга»</h1>\n"}),
        ("Шаг 2: расписание", {"index.html": (
            "<h1>Кружок «Радуга»</h1>\n<table><tr><td>Пн</td></tr></table>\n"
        )}),
        ("Шаг 3: оформление", {"style.css": "h1 { color: teal }\n"}),
    ),
    BOT: (
        ("Шаг 1: бот отвечает на /start", {"bot.py": BOT_CODE}),
        ("Шаг 2: кнопка «Расписание»", {"bot.py": BOT_CODE + "# расписание\n"}),
        ("Шаг 3: запись на пробное", {
            "bot.py": BOT_CODE + "# расписание\n# запись\n",
        }),
    ),
}


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: проверки Акта 3 смотрят в неё."""
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def servers():
    """Запущенные сайты: гасятся после теста."""
    procs = []
    yield procs
    for proc in procs:
        proc.terminate()
        proc.wait(timeout=10)


# --- что делает Claude по словам человека --------------------------------------

def commit(proj, message):
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", message)


def do_what(proj, kind):
    """«Что строим»: раздел «Продукт» в конец IDEA.md — и сразу в сохранение."""
    (proj / "IDEA.md").write_text(PRODUCT[kind], encoding="utf-8")
    commit(proj, "IDEA.md: раздел «Продукт»")


def approve_plan(game, proj):  # noqa: F811
    """Человек одобрил план: Enter на первой строке экрана одобрения."""
    hook(game, plan_approved(cwd=proj))


def do_step(proj, kind, number):
    """Шаг плана сделан, человек посмотрел и сказал «дальше» — шаг сохранён."""
    message, files = STEPS[kind][number]
    for name, text in files.items():
        (proj / name).write_text(text, encoding="utf-8")
    commit(proj, message)


def do_build(proj, kind):
    for number in range(len(STEPS[kind])):
        do_step(proj, kind, number)


def do_key(proj):
    """«Вот ключ, положи его в .env»: ключ ложится в `.env`, не в сохранение."""
    (proj / ".env").write_text("BOT_TOKEN={}\n".format(TOKEN), encoding="utf-8")


def do_key_first(proj):
    """Первый шаг сборки бота (скилл акта, #120): Claude закрывает `.env` от
    сохранений и сохраняет это — только потом ключ ложится в файл."""
    ignore = proj / ".gitignore"
    before = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    if ".env" not in before.split():
        ignore.write_text(before + ".env\n", encoding="utf-8")
        commit(proj, "Закрыл .env от сохранений")
    do_key(proj)


def walk_act4(game, proj, home, kind=SITE, servers=None, screens=None):  # noqa: F811
    """Пройти Акт 4 от входа до закрытия. Акты 1–3 к этому времени закрыты.

    `kind` — тип продукта: `site` или `bot`. Сайту нужен `servers` — список,
    куда ложится запущенный сервер (гасит фикстура `servers`).
    `screens` — список, в который ложится каждый экран пути по порядку.
    Возвращает экран последней команды — закрытие акта.
    """
    assert os.environ.get("HOME") == str(home), "проверки читали бы чужой дом"

    def step(*argv, **expect):
        code, out = game(*argv)
        assert code == expect.get("code", 0), (argv, out)
        if screens is not None:
            screens.append(out)
        return out

    step("enter", "4")
    # Человек выбрал, сайт это или бот, — модель записывает тип командой.
    step("project", "type", kind)
    do_what(proj, kind)
    step("check", "4", "01-what")
    approve_plan(game, proj)
    step("check", "4", "02-plan")
    if kind == BOT:
        # Ключ — первым шагом сборки: каждый шаг бота видно в Telegram.
        do_key_first(proj)
    do_build(proj, kind)
    step("check", "4", "03-build")
    if kind == SITE:
        # Claude запустил сайт на свободном порту и назвал порт игре.
        port, proc = serve(proj)
        servers.append(proc)
        step("project", "port", str(port))
        step("check", "4", "04-run")
    else:
        # Бот перезапущен с последней сохранённой версией; человек написал
        # ему в Telegram и рассказал, что тот ответил.
        step("seen", "4", "04-run")
        step("check", "4", "04-run")
    return step("ack", "4", "05-accept")


def walk_to_the_end(game, proj, home, kind=SITE, servers=None, screens=None):  # noqa: F811
    """Вся сегодняшняя игра командами и хуками: Акты 1–4."""
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    return walk_act4(game, proj, home, kind, servers, screens)


@pytest.fixture(params=KINDS)
def finished(request, game, project, home, servers):  # noqa: F811
    """Игра пройдена до сегодняшнего конца — сайтом и ботом.

    Отдаёт (игра, папка, экраны, тип продукта)."""
    proj = project()
    screens = []
    walk_to_the_end(game, proj, home, request.param, servers, screens)
    return game, proj, screens, request.param


@pytest.fixture
def knight(game, project, home):  # noqa: F811
    """Три вечера пройдены. Отдаёт (игра, папка)."""
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    past_the_last_save(proj)
    return game, proj


# --- проход ------------------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_novice_walks_act4_from_a_clean_save_to_sentinel(
        game, project, home, servers, kind):  # noqa: F811
    """Приёмка тикета: от чистого сохранения до Стража, без засева."""
    proj = project()
    assert not game.state_path.exists()
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    assert st.load(game.state_path)["rank"] == "knight"

    walk_act4(game, proj, home, kind, servers)

    data = st.load(game.state_path)
    assert data["rank"] == "sentinel" == ranks.FINAL_RANK
    assert ranks.rank_for(data) == "sentinel"
    assert data["acts"]["4"]["status"] == ranks.STATUS_DONE
    assert acts.all_closed(data, 4) is True
    assert sorted(data["acts"]["4"]["quests"]) == sorted(QUESTS)
    assert data["artifacts"] == ["brainstorm", "handoff", "investigate", "goal"]
    assert data["project"]["type"] == kind
    facts = debrief.facts(data)
    assert facts["acts_completed"] == [1, 2, 3, 4]
    assert facts["first_try"]["passed"] == facts["first_try"]["attempted"]
    # Ключ бота не попал ни в сохранение игры, ни в сохранения проекта.
    assert TOKEN not in game.state_path.read_text(encoding="utf-8")
    log = subprocess.run(
        ["git", "log", "-p", "--all"], cwd=str(proj),
        capture_output=True, text=True, check=True,
    ).stdout
    assert "Шаг 3" in log and TOKEN not in log


def test_the_run_of_a_bot_waits_for_the_story(knight):
    """Ключ на месте, а человек ещё не написал боту — проверка не идёт."""
    game, proj = knight  # noqa: F811
    assert game("enter", "4")[0] == 0
    assert game("project", "type", BOT)[0] == 0
    do_what(proj, BOT)
    assert game("check", "4", "01-what")[0] == 0
    approve_plan(game, proj)
    assert game("check", "4", "02-plan")[0] == 0
    do_build(proj, BOT)
    assert game("check", "4", "03-build")[0] == 0

    code, out = game("check", "4", "04-run")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Работает» пока не проверяю.",
        "Сначала напиши своему боту в Telegram. Потом расскажи Claude, что он ответил.",
    ]
    # Рассказа без ключа не бывает: игра называет, что поправить.
    code, out = game("seen", "4", "04-run")
    assert code == 1
    assert out.splitlines() == [
        "Рассказ пока не записан: с ключом бота не всё на месте.",
        "Вот что поправить:",
        "  [ ] Ключ бота лежит в файле .env в корне папки проекта",
        "      Возьми ключ у @BotFather в Telegram и скажи Claude: «Вот ключ, "
        "положи его в .env».",
    ]
    data = st.load(game.state_path)
    assert (data["acts"]["4"]["quests"].get("04-run") or {}).get("attempts", 0) == 0
    assert machine_words(out) == []

    do_key(proj)
    code, out = game("seen", "4", "04-run")
    assert code == 0
    assert out.splitlines() == [
        "Записано: в квесте «Работает» ты написал боту и рассказал, что он ответил.",
    ]
    code, out = game("check", "4", "04-run")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Работает» закрыт.",
        "  [x] Ключ бота лежит в файле .env в корне папки проекта",
        "  [x] Файл .env не попадает в сохранения",
        "  [x] Ключа нет в коде и в других файлах",
        "  [x] Ключа нет в сохранениях",
    ]


def test_the_run_of_a_site_needs_no_story_but_a_port(knight, servers):
    game, proj = knight  # noqa: F811
    assert game("enter", "4")[0] == 0
    assert game("project", "type", SITE)[0] == 0
    do_what(proj, SITE)
    assert game("check", "4", "01-what")[0] == 0
    approve_plan(game, proj)
    assert game("check", "4", "02-plan")[0] == 0
    do_build(proj, SITE)
    assert game("check", "4", "03-build")[0] == 0

    code, out = game("seen", "4", "04-run")
    assert code == 1 and "рассказа не ждёт" in out
    # Порт не назван — «не смог проверить», попытка не в счёт.
    code, out = game("check", "4", "04-run")
    assert code == 1
    assert out.splitlines() == [
        "Не смог проверить: игра не знает, на каком порту работает сайт — "
        "попроси Claude назвать его игре",
        "Попытка не засчитана — это не твоя ошибка.",
    ]
    port, proc = serve(proj)
    servers.append(proc)
    assert game("project", "port", str(port))[0] == 0
    code, out = game("check", "4", "04-run")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Работает» закрыт.",
        "  [x] Сайт открывается на твоём компьютере: http://localhost:{}".format(port),
    ]
    data = st.load(game.state_path)
    assert data["acts"]["4"]["quests"]["04-run"]["attempts"] == 1


def test_without_a_type_the_run_cannot_be_judged(knight):
    game, proj = knight  # noqa: F811
    assert game("enter", "4")[0] == 0
    code, out = game("check", "4", "04-run")
    assert code == 1
    assert out.splitlines()[0] == (
        "Не смог проверить: игра не знает, сайт у тебя или бот — скажи "
        "Claude, что ты строишь"
    )
    assert machine_words(out) == []


def test_build_closes_on_three_saves_after_the_plan(knight):
    """Сохранение раздела «Продукт» — тоже сохранение после входа в акт."""
    game, proj = knight  # noqa: F811
    assert game("enter", "4")[0] == 0
    do_what(proj, SITE)
    assert game("check", "4", "01-what")[0] == 0
    approve_plan(game, proj)
    assert game("check", "4", "02-plan")[0] == 0
    do_step(proj, SITE, 0)
    code, out = game("check", "4", "03-build")
    assert code == 1
    assert "Сохранений после входа в акт: 2 из 3." in out
    do_step(proj, SITE, 1)
    code, out = game("check", "4", "03-build")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Сборка» закрыт.",
        "  [x] После входа в акт — не меньше трёх сохранений",
        "  [x] В сохранениях есть сам продукт, а не только заметки",
    ]


# --- что человек читает на пути закрытия ---------------------------------------

def test_closing_the_act_names_the_rank_and_says_the_game_pauses(finished):
    _, _, screens, _ = finished
    assert screens[-1].splitlines() == [
        "Квест «Приёмка» закрыт: ты проверил продукт сам и сказал «да».",
        "",
        "Акт 4. Свой продукт — закрыт.",
        "Новый ранг: Страж.",
        "",
        "На этом игра пока кончается: Акт 5 ещё не написан.",
        "Памятку в папку проекта положит Claude — попроси его.",
    ]
    assert "finale" not in screens[-1] and "бесплатна" not in screens[-1]
    assert "Это конец игры" not in screens[-1]


def test_the_type_is_said_in_words(finished):
    _, _, screens, kind = finished
    assert screens[1].splitlines() == [
        "Тип продукта: {}.".format(acts.PRODUCT_WORDS[kind]),
    ]


def test_no_screen_of_act4_speaks_to_the_model(finished):
    game, _, screens, _ = finished  # noqa: F811
    screens.append(game("status")[1])
    # Команды типа и порта зовёт модель: их ответ — не экран человека.
    path = [screen for screen in screens
            if not screen.startswith(("Тип продукта:", "Порт проекта:"))]
    for screen in path:
        assert machine_words(screen) == [], screen
        assert "Traceback" not in screen
        for quest_id in QUESTS:
            assert quest_id not in screen, screen
        assert TOKEN not in screen


def test_first_screen_after_the_end_word_for_word(finished):
    game, _, _, _ = finished  # noqa: F811
    code, out = game("status")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "Ранг: Страж"
    start = lines.index("Карта:")
    assert lines[start:start + 6] == [
        "Карта:",
        "  Акт 1. Знакомство — пройден",
        "  Акт 2. Память и силы — пройден",
        "  Акт 3. Умения — пройден",
        "  Акт 4. Свой продукт — пройден",
        "  Акт 5 ещё не написан",
    ]
    head = lines.index(cli.ARTIFACTS_HEAD)
    assert lines[head + 4] == (
        "  «Цель»: довести дело до работы и вовремя остановиться — «поставь "
        "цель: доведи до работы, не больше пяти попыток»"
    )
    assert lines[-2:] == [
        "Что дальше: Акт 5 ещё не написан.",
        "  Памятку в папку проекта положит Claude — попроси его.",
    ]


def test_finale_says_the_game_is_not_over_and_names_act5(finished):
    game, _, _, _ = finished  # noqa: F811
    code, out = game("finale")
    assert code == 1
    assert out.splitlines()[0] == (
        "Игра ещё не кончилась: Акт 5 ещё не написан. Твой ранг сейчас — Страж."
    )
    assert "Ближайший незакрытый" not in out
    assert "закрыто актов" not in out
    assert "http" not in out and "клуб" not in out.lower()
    assert "=== Карточка" not in out
    # Ответ читает модель: чем выдать памятку, он называет ручкой.
    assert out.splitlines()[-1] == "  scroll"
    data = st.load(game.state_path)
    assert not data.get("finale_announced")
    assert [e for e in data["pending_sync"] if e["type"] == "finale"] == []


def test_sentinel_card_carries_the_trophy_of_its_own_act(finished):
    game, _, _, _ = finished  # noqa: F811
    card = cli.render_rank_card(debrief.facts(st.load(game.state_path)))
    lines = card.splitlines()
    assert lines[0] == "=== Карточка Стража ==="
    assert lines[2] == cli.TROPHY_LINES[4]
    assert "Закрыто актов: 4 из 4." in lines
    for title in ("Знакомство", "Память и силы", "Умения", "Свой продукт"):
        assert any(line.endswith(title) for line in lines), title
    for other in (1, 2, 3, 5):
        assert cli.TROPHY_LINES[other] not in card
    assert "finale" not in card and "http" not in card


def test_memo_after_the_end_carries_the_goal_and_the_phrases(finished):
    game, proj, _, _ = finished  # noqa: F811
    code, out = game("scroll")
    assert code == 0, out
    assert out.splitlines()[0] == "Памятка Стража: {}/docs/jedicoder".format(
        proj.name
    )
    assert machine_words(out) == []
    folder = proj / "docs" / "jedicoder"
    names = sorted(path.name for path in folder.iterdir())
    for name in ("goal.md", "investigate.md", "handoff.md", "brainstorm.md",
                 "frazy.md"):
        assert name in names
    razbor = (folder / "razbor.md").read_text(encoding="utf-8")
    assert "- Закрыто актов: 4 из 4" in razbor
    assert "из 5" not in razbor
    everything = "\n".join(
        path.read_text(encoding="utf-8") for path in folder.iterdir()
    )
    assert cli.TROPHY_LINES[4] in everything
    assert TOKEN not in everything
    for quest_id in QUESTS:
        assert quest_id not in razbor
    for title in TITLES:
        assert "| 4 | {} | 1 | да |".format(title) in razbor
    # Фразы четвёртого вечера — рядом с фразами первых трёх.
    frazy = (folder / "frazy.md").read_text(encoding="utf-8")
    for row in (
        "| Хочешь сделать что-то большое: сайт, бота, новый раздел | Разбей на "
        "шаги. После каждого шага остановись и покажи, что вышло |",
        "| Шаг сломал то, что работало | Вот ошибка целиком. Сначала объясни "
        "причину, потом исправляй |",
        "| Получил ключ бота у @BotFather | Вот ключ, положи его в `.env`. В "
        "код и в сохранения его не пиши |",
    ):
        assert row in frazy, row
    assert "Сохрани. Или: сделай коммит" in frazy
    assert "Чистка. Ровно это слово" in frazy
    # Страница работает без игры: ни одного её слова.
    for word in ("квест", "Квест", "акт ", "Акт", "ранг", "Jedicoder", "jedicoder"):
        assert word not in frazy, word


def test_the_strip_after_the_end_does_not_change_when_the_memo_is_taken(finished):
    game, _, _, _ = finished  # noqa: F811
    before = strip_and_map(game)
    assert game("scroll")[0] == 0
    assert strip_and_map(game) == before


# --- Полоса, всплывающие и карта в каждом состоянии акта ------------------------

def strip_and_map(game):  # noqa: F811
    """Строка «Что дальше» первого экрана, она же в снимке Лица, строка карты
    об Акте 4 и то, по чему Лицо решает о всплывающих."""
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
    act4 = next(line.strip() for line in lines if line.startswith("  Акт 4."))
    return step[0], step[1], act4, face["quests_closed"], face["rank"], face["say"]


@pytest.mark.parametrize("kind", KINDS)
def test_strip_toasts_and_map_are_true_in_every_state_of_the_act(
        knight, content_root, servers, kind):
    game, proj = knight  # noqa: F811
    tasks = cli._quest_tasks(content_root)
    quest = "Что дальше: квест «{}» — Акт 4 «Свой продукт»."
    going = "Акт 4. Свой продукт — идёт, квестов закрыто: {}/5"

    def see():
        return strip_and_map(game)

    assert see() == (
        "Что дальше: начать Акт 4 «Свой продукт» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
        "Акт 4. Свой продукт — не начат, квестов закрыто: 0/5",
        15, "Рыцарь", cli.SAY_START,
    )

    assert game("enter", "4")[0] == 0
    assert see() == (quest.format("Что строим"), tasks[(4, "01-what")],
                     going.format(0), 15, "Рыцарь", "")
    assert game("project", "type", kind)[0] == 0
    do_what(proj, kind)
    assert see()[1] == tasks[(4, "01-what")]
    assert game("check", "4", "01-what")[0] == 0

    assert see() == (quest.format("План"), tasks[(4, "02-plan")],
                     going.format(1), 16, "Рыцарь", "")
    approve_plan(game, proj)
    assert see()[1] == cli.STEP_PLAN_APPROVED
    assert game("check", "4", "02-plan")[0] == 0

    assert see() == (quest.format("Сборка"), tasks[(4, "03-build")],
                     going.format(2), 17, "Рыцарь", "")
    do_build(proj, kind)
    assert see()[1] == tasks[(4, "03-build")]
    assert game("check", "4", "03-build")[0] == 0

    assert see() == (quest.format("Работает"), tasks[(4, "04-run")],
                     going.format(3), 18, "Рыцарь", "")
    if kind == SITE:
        port, proc = serve(proj)
        servers.append(proc)
        assert game("project", "port", str(port))[0] == 0
        assert see()[1] == tasks[(4, "04-run")]
    else:
        do_key(proj)
        assert see()[1] == tasks[(4, "04-run")]
        assert game("seen", "4", "04-run")[0] == 0
        assert see()[1] == cli.STEP_WORDS_TAKEN
    assert game("check", "4", "04-run")[0] == 0

    assert see() == (quest.format("Приёмка"), tasks[(4, "05-accept")],
                     going.format(4), 19, "Рыцарь", "")
    assert game("ack", "4", "05-accept")[0] == 0

    # Акт закрыт: ранг вырос — Лицо покажет подпись о ранге. Дальше актов нет:
    # в поле ввода ничего не предлагается.
    assert see() == (
        "Что дальше: Акт 5 ещё не написан.",
        "Памятку в папку проекта положит Claude — попроси его.",
        "Акт 4. Свой продукт — пройден",
        20, "Страж", "",
    )


# --- «Работает» ботом: чего игра не принимает -----------------------------------

@pytest.fixture
def at_run_of_a_bot(knight):
    game, proj = knight  # noqa: F811
    assert game("enter", "4")[0] == 0
    assert game("project", "type", BOT)[0] == 0
    do_what(proj, BOT)
    assert game("check", "4", "01-what")[0] == 0
    approve_plan(game, proj)
    assert game("check", "4", "02-plan")[0] == 0
    do_build(proj, BOT)
    assert game("check", "4", "03-build")[0] == 0
    return game, proj


def test_a_key_written_into_the_code_after_the_story_takes_the_story_back(
        at_run_of_a_bot):
    """Рассказ записан, а потом ключ попал в код: проверка не сходится и
    стирает рассказ — после правки рассказывают заново."""
    game, proj = at_run_of_a_bot  # noqa: F811
    do_key(proj)
    assert game("seen", "4", "04-run")[0] == 0
    (proj / "bot.py").write_text("TOKEN = '{}'\n".format(TOKEN), encoding="utf-8")
    code, out = game("check", "4", "04-run")
    assert code == 1
    assert "  [ ] Ключа нет в коде и в других файлах" in out.splitlines()
    assert TOKEN not in out
    data = st.load(game.state_path)
    assert not data["acts"]["4"]["quests"]["04-run"].get("seen")
    (proj / "bot.py").write_text(BOT_CODE, encoding="utf-8")
    code, out = game("check", "4", "04-run")
    assert code == 1 and "пока не проверяю" in out
    assert game("seen", "4", "04-run")[0] == 0
    assert game("check", "4", "04-run")[0] == 0


def test_the_bot_is_closed_by_the_tools_by_its_screen_name(at_run_of_a_bot):
    game, proj = at_run_of_a_bot  # noqa: F811
    do_key(proj)
    code, out = game(cli.TOOL_CALL, "check", "Работает")
    assert code == 1 and "пока не проверяю" in out
    code, out = game(cli.TOOL_CALL, "seen", "Работает")
    assert code == 0, out
    code, out = game(cli.TOOL_CALL, "check", "Работает")
    assert code == 0 and out.startswith("Квест «Работает» закрыт")
    code, out = game(cli.TOOL_CALL, "ack", "Приёмка")
    assert code == 0 and "Новый ранг: Страж." in out

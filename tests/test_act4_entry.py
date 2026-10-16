"""Акт 4 «Свой продукт» открыт: вход, приём «Цель», квесты «Что строим» и «План».

Той же дверью, что человек: сохранение не засевается. Акт 1 проходится
командами игры, Акты 2 и 3 — командами и хуками (`walk_act2`, `walk_act3`), и
только потом — `enter 4`.

Целиком акт здесь не проходится: сквозной проход обеими ветками — сайт и бот
— до ранга Страж и конец игры живут в `tests/test_act4_walkthrough.py`
(`walk_act4`, #119).

`IDEA.md` кладёт тест так, как его написал Claude Code в живом замере
2026-10-14 (`docs/research/2026-10-14-act4-facts.md`); одобрение плана — хук
следов процессом, на данных настоящей формы.
"""
import json
import time

import pytest

from conftest import needs_shelf

from jedicoder import acts, cli, quests, ranks
from jedicoder import state as st
from test_act2_entry import close_act1, game  # noqa: F401 — фикстура
from test_act2_walkthrough import do_plan, hook, walk_act2
from test_act3_walkthrough import walk_act3
from test_act4_checks import PRODUCT_BOT, past_the_last_save
from test_human_screens import machine_words
from test_traces import plan_approved

ACT = 4
QUESTS = ("01-what", "02-plan", "03-build", "04-run", "05-accept")
TITLES = ("Что строим", "План", "Сборка", "Работает", "Приёмка")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: проверки Акта 3 смотрят в неё."""
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def knight(game, project, home):  # noqa: F811
    """Человек прошёл три вечера. Отдаёт (игра, папка проекта)."""
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    past_the_last_save(proj)
    return game, proj


@pytest.fixture
def entered(knight):
    """Он вошёл в Акт 4. Отдаёт (игра, папка проекта)."""
    game, proj = knight  # noqa: F811
    code, out = game("enter", "4")
    assert code == 0, out
    return game, proj


def write_product(proj, text=PRODUCT_BOT):
    """Claude записал раздел «Продукт» в IDEA.md — как в замере."""
    (proj / "IDEA.md").write_text(text, encoding="utf-8")


def approve_plan(game, proj):  # noqa: F811
    """Человек одобрил план: Enter на первой строке экрана одобрения."""
    hook(game, plan_approved(cwd=proj))


def step(game):  # noqa: F811
    _, out = game("status")
    lines = out.rstrip().splitlines()
    return [line.strip() for line in lines[-2:]]


# --- реестр ------------------------------------------------------------------

def test_quest_order_declared():
    assert acts.quest_ids(ACT) == QUESTS
    assert [acts.quest_kind(ACT, quest_id) for quest_id in QUESTS] == [
        acts.KIND_SCRIPT, acts.KIND_SCRIPT, acts.KIND_SCRIPT, acts.KIND_SCRIPT,
        acts.KIND_ACK,
    ]


def test_act4_does_not_branch():
    for track in (None, acts.TRACK_CRAFTSMAN, acts.TRACK_FOUNDER):
        assert acts.quest_ids(ACT, track) == QUESTS
    assert acts.ACT_AXIS == {}


def test_registry_names_the_act_its_artifact_and_rank():
    assert ranks.ACTS[ACT] == {
        "slug": "act4-svoy-produkt", "title": "Свой продукт",
        "artifact": "goal", "rank": "sentinel",
    }
    assert ranks.MUTED_ACTS == (5,)
    assert ranks.FINAL_ACT == 4 and ranks.FINAL_RANK == "sentinel"
    assert ranks.UNLOCKED_ARTIFACTS == ()
    assert cli.ARTIFACT_NAMES["goal"] == "Цель"


def test_only_the_plan_of_act4_needs_a_fresh_trace():
    assert acts.FRESH_TRACE_QUESTS == {(4, "02-plan"): st.TRACE_PLAN_APPROVED}
    # Квест «План» второго вечера по-прежнему судит пометка, а не момент.
    assert acts.TRACE_ACTS[st.TRACE_PLAN_APPROVED] == 2
    assert not any(act == ACT for act, _ in acts.WORDS_FIRST)


def test_only_the_run_of_a_bot_waits_for_words():
    """«Работает» ждёт рассказа, только когда продукт — бот (#119)."""
    assert acts.WORDS_FIRST_FOR == {(4, "04-run"): "bot"}
    bot = {"project": {"type": "bot"}}
    assert acts.needs_words(ACT, "04-run", bot)
    for state in (None, {}, {"project": {"type": "site"}},
                  {"project": {"type": "telegram-bot"}}, {"project": "мусор"}):
        assert not acts.needs_words(ACT, "04-run", state), state
    for quest_id in QUESTS:
        if quest_id != "04-run":
            assert not acts.needs_words(ACT, quest_id, bot), quest_id
    assert acts.needs_words(1, "03-first-request")
    assert acts.needs_words(2, "04-clear", bot)


def test_every_scripted_quest_has_its_check_on_disk(quests_root):
    for quest_id in QUESTS:
        script = quests.script_path(quests_root, ranks.ACTS[ACT]["slug"], quest_id)
        scripted = acts.quest_kind(ACT, quest_id) == acts.KIND_SCRIPT
        assert script.is_file() is scripted, quest_id


def test_content_describes_the_act_as_the_registry_does(content_root):
    from jedicoder import content

    scene = next(item for item in content.load_acts(content_root) if item.act == ACT)
    assert scene.slug == "act4-svoy-produkt"
    assert scene.quests == QUESTS
    assert tuple(scene.quest_titles) == TITLES
    assert len(scene.quest_tasks) == len(QUESTS)
    assert scene.muted is False
    for task in scene.quest_tasks:
        assert "," not in task and len(task.split()) <= 15, task
    paragraphs = [part for part in scene.body.split("\n\n") if part.strip()]
    assert len(paragraphs) == 2


@needs_shelf
def test_old_act4_left_the_plugin_and_no_skill_name_repeats():
    """Прежний акт — на полке; имена скиллов и команд плагина не повторяются."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    plugin = root / "plugin"
    for gone in (
        plugin / "skills" / "act4-shchit", plugin / "skills" / "cso",
        plugin / "quests" / "act4-shchit",
        plugin / "content" / "ru" / "acts" / "act4-shchit.md",
        plugin / "content" / "ru" / "scroll" / "cso.md",
    ):
        assert not gone.exists(), gone
    assert (plugin / "skills" / "act4-svoy-produkt" / "SKILL.md").is_file()
    assert (plugin / "skills" / "goal" / "SKILL.md").is_file()
    assert (plugin / "content" / "ru" / "scroll" / "goal.md").is_file()
    for kept in ("README.md", "skill/SKILL.md", "artifact/SKILL.md"):
        assert (root / "shelf" / "act4-shchit" / kept).is_file(), kept

    skills = sorted(path.name for path in (plugin / "skills").iterdir() if path.is_dir())
    commands = sorted(path.stem for path in (plugin / "commands").glob("*.md"))
    names = skills + commands
    assert len(names) == len(set(names)), names


def test_goal_skill_has_a_lock():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "plugin" / "skills" / "goal"
            / "SKILL.md").read_text(encoding="utf-8")
    assert "cli.py\" artifact goal" in text
    assert "Замка нет" not in text


# --- вход: Акты 1–3 целиком, потом `enter 4` -----------------------------------

def test_act4_is_closed_until_act3_is_done(game, project):  # noqa: F811
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    assert game("enter", "3")[0] == 0
    code, out = game("enter", "4")
    assert code == 1
    assert "Сначала закрой Акт 3" in out
    assert "4" not in st.load(game.state_path)["acts"]
    code, out = game("artifact", "goal")
    assert code == 1 and "на входе в Акт 4" in out


def test_after_act3_the_next_step_is_act4(knight):
    game, _ = knight  # noqa: F811
    _, out = game("status")
    lines = out.splitlines()
    assert "Ранг: Рыцарь" in lines
    assert "  Акт 3. Умения — пройден" in lines
    assert "  Акт 4. Свой продукт — не начат, квестов закрыто: 0/5" in lines
    assert "  Акт 5 ещё не написан" in lines
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: начать Акт 4 «Свой продукт» — квестов в нём 5.",
        "  Скажи Claude: «начинаем».",
    ]
    assert machine_words(out) == []


def test_closing_act3_no_longer_says_the_game_pauses(game, project, home):  # noqa: F811
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    closing = walk_act3(game, proj, home)
    assert "Новый ранг: Рыцарь." in closing
    assert "ещё не написан" not in closing and "кончается" not in closing


def test_enter_act4_prints_five_quests_in_words_and_gives_the_artifact(knight):
    """Приёмка тикета: с чистого сохранения Акты 1–3 целиком → `enter 4`."""
    game, _ = knight  # noqa: F811
    code, out = game("enter", "4")

    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "Акт 4. Свой продукт — начат."
    assert lines[2] == (
        "В этом акте ты строишь из своей идеи сайт или бота — по шагам, с планом."
    )
    assert lines[4] == (
        "К концу вечера твой продукт работает на твоём компьютере, и ты "
        "принял его сам."
    )
    start = lines.index("Квесты акта (5):") + 1
    assert lines[start:start + 5] == [
        "  1. Что строим. Расскажи Claude что строишь и для кого — он задаст "
        "вопросы и запишет.",
        "  2. План. Попроси у Claude план продукта по разделу «Продукт» и "
        "одобри его.",
        "  3. Сборка. Смотри каждый шаг плана и говори «дальше» — Claude "
        "сохранит его.",
        "  4. Работает. Claude запускает продукт на твоём компьютере — открой "
        "сайт или напиши боту.",
        "  5. Приёмка. Пройди продукт как пользователь и скажи Claude «да» "
        "или что не так.",
    ]
    assert "Ранг за акт: Страж. Это следующая ступень после Рыцаря." in lines
    assert (
        "Приём этого акта — «Цель»: помогает довести дело до работы и "
        "вовремя остановиться. Скажи Claude: «поставь цель: доведи до работы, "
        "не больше пяти попыток»."
    ) in lines
    for quest_id in QUESTS:
        assert quest_id not in out
    assert "goal" not in out
    assert machine_words(out) == []

    data = st.load(game.state_path)
    assert data["current_act"] == 4
    assert data["acts"]["4"]["status"] == ranks.STATUS_IN_PROGRESS
    assert data["acts"]["4"]["started_at"]
    assert data["artifacts"] == ["brainstorm", "handoff", "investigate", "goal"]
    assert data["rank"] == "knight"


def test_goal_lock_opens_on_entry(knight):
    game, _ = knight  # noqa: F811
    code, out = game("artifact", "goal")
    assert code == 1 and "на входе в Акт 4" in out
    assert game("enter", "4")[0] == 0
    code, out = game("artifact", "goal")
    assert code == 0 and out.strip() == "Приём goal открыт."


def test_first_screen_inside_act4_names_the_quest(entered):
    game, _ = entered  # noqa: F811
    _, out = game("status")
    lines = out.splitlines()
    assert "  Акт 4. Свой продукт — идёт, квестов закрыто: 0/5" in lines
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: квест «Что строим» — Акт 4 «Свой продукт».",
        "  Расскажи Claude что строишь и для кого — он задаст вопросы и запишет.",
    ]
    assert machine_words(out) == []


def test_memo_carries_the_goal_instruction(entered):
    game, proj = entered  # noqa: F811
    code, out = game("scroll")
    assert code == 0, out
    assert (proj / "docs" / "jedicoder" / "goal.md").is_file()
    assert not (proj / "docs" / "jedicoder" / "cso.md").exists()


def test_project_screen_asks_for_the_type_and_the_port_only_in_act4(knight):
    """Тип продукта и порт спрашивает Акт 4; базу и путь деплоя — не он.

    Тип записывается словом `site` или `bot` (#119), а не именем рецепта с
    путём деплоя: подсказки про `managed` экран не печатает (ревью #118)."""
    game, _ = knight  # noqa: F811
    _, before = game("project")
    assert "Порт" not in before and "Тип продукта" not in before
    assert game("enter", "4")[0] == 0
    _, after = game("project")
    assert "  Порт: не назван" in after.splitlines()
    assert "  Тип продукта: не назван" in after.splitlines()
    for silent in ("База данных", "Путь деплоя", "managed"):
        assert silent not in after, silent
    for kind, words in (("site", "сайт"), ("bot", "Telegram-бот")):
        code, out = game("project", "type", kind)
        assert code == 0 and out.strip() == "Тип продукта: {}.".format(words)
        _, after = game("project")
        assert "  Тип продукта: {}".format(words) in after.splitlines()
        for silent in ("Путь деплоя", "managed", "рецепт"):
            assert silent not in after, silent
    data = st.load(game.state_path)
    assert data["project"]["type"] == "bot"
    assert acts.product_of(data) == "bot"
    assert data["passport"]["product_type"] == "bot"


def test_a_recipe_name_is_not_a_product_type_of_act4(entered):
    """Имя рецепта прежней игры ручка принимает, но «Работает» по нему не
    судит: сайт это или бот, оно не говорит."""
    game, _ = entered  # noqa: F811
    assert game("project", "type", "landing")[0] == 0
    assert acts.product_of(st.load(game.state_path)) is None
    code, out = game("project", "type", "квадрокоптер")
    assert code == 1 and "site" in out and "bot" in out


def test_recipe_of_a_type_of_act4_is_the_one_for_this_computer(entered):
    """Рецепт сайта и бота — «на своём компьютере» (#120): стек и грабли, без
    пути деплоя и без хостинга."""
    game, _ = entered  # noqa: F811
    for kind, title, words, stack in (
            ("site", "Сайт", "сайт", "html, css, js"),
            ("bot", "Telegram-бот", "Telegram-бот", "python")):
        assert game("project", "type", kind)[0] == 0
        code, out = game("recipe")
        assert code == 0, out
        lines = out.splitlines()
        assert lines[:2] == [
            "{} — рецепт для типа продукта «{}»".format(title, words),
            "Стек: {}".format(stack),
        ]
        for silent in ("деплой", "Путь деплоя", "managed", "хостинг", "aiogram"):
            assert silent not in out, silent
        assert "## Пять типичных грабель именно здесь" in out
    # Посмотреть рецепт по имени можно по-прежнему.
    code, out = game("recipe", "landing")
    assert code == 0 and out.splitlines()[0] == "Сайт (landing)"


# --- «Что строим» --------------------------------------------------------------

def test_what_fails_then_closes_when_the_section_is_written(entered):
    game, proj = entered  # noqa: F811
    code, out = game("check", "4", "01-what")
    assert code == 1
    assert out.splitlines()[:2] == [
        "Квест «Что строим» пока не закрыт. Не сошлось:",
        "  [ ] В IDEA.md есть раздел «Продукт»",
    ]
    assert machine_words(out) == []
    write_product(proj)
    code, out = game("check", "4", "01-what")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Что строим» закрыт.",
        "  [x] В IDEA.md есть раздел «Продукт»",
        "  [x] Записано, что это: сайт или бот",
        "  [x] Записано, для кого",
        "  [x] Записано, что продукт делает",
        "  [x] Записано, как ты поймёшь, что готово",
    ]
    data = st.load(game.state_path)
    assert acts.next_quest(data, 4) == "02-plan"
    assert data["acts"]["4"]["status"] == ranks.STATUS_IN_PROGRESS


# --- «План»: одобрен в этом акте ------------------------------------------------

@pytest.fixture
def at_plan(entered):
    game, proj = entered  # noqa: F811
    write_product(proj)
    assert game("check", "4", "01-what")[0] == 0
    return game, proj


def test_plan_of_the_second_evening_does_not_close_the_plan_of_the_fourth(at_plan):
    """Приёмка тикета: план, одобренный во втором вечере, — не план продукта."""
    game, _ = at_plan  # noqa: F811
    data = st.load(game.state_path)
    # План второго вечера на месте и годился квесту Акта 2.
    assert cli._trace_counts(data, st.TRACE_PLAN_APPROVED)
    assert st.trace_moment(data, st.TRACE_PLAN_APPROVED) is None
    assert step(game) == [
        "Что дальше: квест «План» — Акт 4 «Свой продукт».",
        "Попроси у Claude план продукта по разделу «Продукт» и одобри его.",
    ]
    code, out = game("check", "4", "02-plan")
    assert code == 1
    assert out.splitlines() == [
        "Квест «План» пока не закрыт. Не сошлось:",
        "  [ ] Claude показал план продукта, и ты его одобрил",
        "      Игра не видела плана в этом акте. Набери /plan и «Сделай то, что "
        "в разделе „Продукт“ в IDEA.md. Разбей на шаги». Прочитай план и "
        "нажми Enter на первой строке.",
    ]


def test_plan_approved_in_act4_closes_the_quest(at_plan):
    game, proj = at_plan  # noqa: F811
    approve_plan(game, proj)
    data = st.load(game.state_path)
    moment = st.trace_moment(data, st.TRACE_PLAN_APPROVED)
    assert moment is not None and moment >= cli._act_started_epoch(data, 4)
    assert step(game) == [
        "Что дальше: квест «План» — Акт 4 «Свой продукт».",
        cli.STEP_PLAN_APPROVED,
    ]
    code, out = game("check", "4", "02-plan")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «План» закрыт.",
        "  [x] Claude показал план продукта, и ты его одобрил",
    ]
    data = st.load(game.state_path)
    assert acts.next_quest(data, 4) == "03-build"


def test_plan_approved_before_entering_act4_is_not_counted(knight, monkeypatch):
    """План, одобренный Рыцарем до входа в Акт 4, — не план этого акта."""
    game, proj = knight  # noqa: F811
    approve_plan(game, proj)
    assert st.trace_moment(st.load(game.state_path), st.TRACE_PLAN_APPROVED) is None
    assert game("enter", "4")[0] == 0
    write_product(proj)
    assert game("check", "4", "01-what")[0] == 0
    assert game("check", "4", "02-plan")[0] == 1


def test_an_old_moment_from_before_the_entry_is_not_counted(at_plan):
    """Момент есть, но раньше входа в акт: так выглядит вход заново."""
    game, proj = at_plan  # noqa: F811
    approve_plan(game, proj)
    data = st.load(game.state_path)
    data["acts"]["4"]["started_at"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600)
    )
    st.save(data, game.state_path)
    assert step(game)[1] != cli.STEP_PLAN_APPROVED
    assert game("check", "4", "02-plan")[0] == 1


def test_the_plan_trace_cannot_be_faked_from_the_shell(at_plan, monkeypatch):
    game, _ = at_plan  # noqa: F811
    monkeypatch.setenv("JEDICODER_TRACE_PLAN_APPROVED", "yes")
    monkeypatch.setenv("JEDICODER_TRACE_PLAN_APPROVED_AT", "99999999999")
    monkeypatch.setenv(quests.STARTED_ENV, "0")
    assert game("check", "4", "02-plan")[0] == 1


def test_after_the_plan_is_closed_approvals_no_longer_touch_the_save(at_plan):
    game, proj = at_plan  # noqa: F811
    approve_plan(game, proj)
    assert game("check", "4", "02-plan")[0] == 0
    before = game.state_path.read_bytes()
    time.sleep(1.1)
    approve_plan(game, proj)
    assert game.state_path.read_bytes() == before


def test_act2_plan_still_works_as_before(game, project):  # noqa: F811
    """План второго вечера: пометка `in_act`, момента нет — квест закрыт."""
    proj = project()
    close_act1(game, proj)
    assert game("enter", "2")[0] == 0
    do_plan(game, proj)
    data = st.load(game.state_path)
    entry = st.trace(data, st.TRACE_PLAN_APPROVED)
    assert entry == {"date": entry["date"], st.TRACE_IN_ACT: True}
    assert game("check", "2", "01-plan")[0] == 0


# --- «Сборка», «Работает» и приёмка ------------------------------------------------

@pytest.fixture
def at_build(at_plan):
    game, proj = at_plan  # noqa: F811
    approve_plan(game, proj)
    assert game("check", "4", "02-plan")[0] == 0
    return game, proj


def test_build_without_saves_in_this_act_says_how_many_in_words(at_build):
    """Сохранение первого вечера — до входа в акт: в «Сборку» оно не идёт."""
    game, _ = at_build  # noqa: F811
    code, out = game("check", "4", "03-build")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Сборка» пока не закрыт. Не сошлось:",
        "  [ ] После входа в акт — не меньше трёх сохранений",
        "      Сохранений после входа в акт: 0 из 3. После каждого рабочего "
        "шага скажи Claude «дальше» — он сохранит шаг.",
    ]
    assert machine_words(out) == []
    data = st.load(game.state_path)
    assert data["rank"] == "knight"
    assert data["acts"]["4"]["status"] == ranks.STATUS_IN_PROGRESS


def test_accept_is_closed_by_words_and_has_no_check(entered):
    game, _ = entered  # noqa: F811
    code, out = game("check", "4", "05-accept")
    assert code == 1 and "нет проверки" in out
    code, out = game("ack", "4", "05-accept")
    assert code == 0
    assert out.splitlines() == [
        "Квест «Приёмка» закрыт: ты проверил продукт сам и сказал «да».",
    ]
    assert st.load(game.state_path)["acts"]["4"]["status"] == ranks.STATUS_IN_PROGRESS


def test_third_failure_in_act4_calls_the_magistr_in_plain_words(at_build):
    game, _ = at_build  # noqa: F811
    for _ in range(3):
        code, out = game("check", "4", "03-build")
        assert code == 1
    assert "Позови Магистра" in out
    assert "протокол" not in out and "откатись" not in out


def test_face_snapshot_follows_the_new_act(knight):
    game, _ = knight  # noqa: F811

    def face():
        code, out = game("face", "--called")
        assert code == 0, out
        return json.loads(out)

    before = face()
    assert before["next"] == [
        "Что дальше: начать Акт 4 «Свой продукт» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
    ]
    assert before["rank"] == "Рыцарь" and before["quests_closed"] == 15
    assert game("enter", "4")[0] == 0
    assert face()["next"] == [
        "Что дальше: квест «Что строим» — Акт 4 «Свой продукт».",
        "Расскажи Claude что строишь и для кого — он задаст вопросы и запишет.",
    ]


def test_tools_take_the_quests_of_act4_by_their_screen_names(entered):
    game, proj = entered  # noqa: F811
    code, out = game(cli.TOOL_CALL, "check", "План")
    assert code == 1 and "Сейчас открыт квест «Что строим»." in out
    write_product(proj)
    code, out = game(cli.TOOL_CALL, "check", "Что строим")
    assert code == 0 and out.startswith("Квест «Что строим» закрыт")

"""Акт 3 «Умения» открыт: вход, приём «Разбор поломки», квесты «Скилл» и «Где брать».

Той же дверью, что человек: сохранение не засевается. Акт 1 проходится
командами игры, Акт 2 — командами и хуками (`walk_act2`), и только потом —
`enter 3`.

Целиком акт здесь не проходится: сквозной проход до ранга Рыцарь и квесты
«Свой скилл», «Хук» и «Мод» — в `tests/test_act3_walkthrough.py` (#110).

«Скилл» и «Где брать» закрывает рассказ: в игре из сети ничего не ставится
(решение оператора 2026-10-14, #116). Машина игрока — песочная домашняя папка
теста: «Свой скилл» смотрит и в неё. Настоящий `~/.claude` эти тесты не читают.
"""
import json
import os
import time

import pytest

from jedicoder import acts, cli, quests, ranks
from jedicoder import state as st
from test_act2_entry import close_act1, game  # noqa: F401 — фикстура
from test_act2_walkthrough import walk_act2
from test_act3_checks import OWN_SKILL, personal_skill, project_skill
from test_human_screens import machine_words

ACT = 3
QUESTS = ("01-skill", "02-where", "03-own-skill", "04-hook", "05-mod")
TITLES = ("Скилл", "Где брать", "Свой скилл", "Хук", "Мод")


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: пустая, как у человека до установок.

    Достаётся каждому тесту файла: проверки акта смотрят в домашнюю папку,
    и настоящую эти тесты читать не должны.
    """
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def padawan(game, project):  # noqa: F811
    """Человек прошёл два вечера. Отдаёт (игра, папка проекта)."""
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    return game, proj


@pytest.fixture
def entered(padawan, home):
    """Он вошёл в Акт 3. Отдаёт (игра, папка проекта, домашняя папка)."""
    game, proj = padawan  # noqa: F811
    code, out = game("enter", "3")
    assert code == 0, out
    return game, proj, home


def entered_later(game, seconds=3600):  # noqa: F811
    """Сдвинуть запись о входе в акт вперёд: личные скиллы окажутся старше.

    Так выглядит скилл «для всех проектов», поставленный до акта. У человека
    между установкой и входом проходят минуты, в тесте — та же секунда, и
    расстояние ставится явно.
    """
    data = st.load(game.state_path)
    data["acts"]["3"]["started_at"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds)
    )
    st.save(data, game.state_path)


# --- реестр ------------------------------------------------------------------

def test_quest_order_declared():
    assert acts.quest_ids(ACT) == QUESTS
    # Два рассказа, две проверки и рассказ (#116).
    assert [acts.quest_kind(ACT, quest_id) for quest_id in QUESTS] == [
        acts.KIND_ACK, acts.KIND_ACK, acts.KIND_SCRIPT, acts.KIND_SCRIPT,
        acts.KIND_ACK,
    ]


def test_act3_does_not_branch():
    for track in (None, acts.TRACK_CRAFTSMAN, acts.TRACK_FOUNDER):
        assert acts.quest_ids(ACT, track) == QUESTS


def test_registry_names_the_act_its_artifact_and_rank():
    assert ranks.ACTS[ACT] == {
        "slug": "act3-umeniya", "title": "Умения",
        "artifact": "investigate", "rank": "knight",
    }
    assert ranks.MUTED_ACTS == ()
    assert not ranks.is_muted(ACT)
    assert ranks.FINAL_ACT == 5 and ranks.FINAL_RANK == "master"


def test_no_quest_of_act3_waits_for_words_before_a_check():
    """Ворот «рассказ раньше проверки» в акте нет: проверки «Скилла» больше
    нет, а остальным квестам рассказ раньше проверки не нужен."""
    for quest_id in QUESTS:
        assert not acts.needs_words(ACT, quest_id), quest_id
    assert not any(act == ACT for act, _ in acts.WORDS_FIRST)
    assert not any(act == ACT for act, _ in cli.WORDS_FIRST_SCREENS)
    # Ворота прежних актов на месте.
    assert acts.needs_words(1, "03-first-request")
    assert acts.needs_words(2, "04-clear")


def test_every_scripted_quest_has_its_check_on_disk(quests_root):
    for quest_id in QUESTS:
        script = quests.script_path(quests_root, ranks.ACTS[ACT]["slug"], quest_id)
        scripted = acts.quest_kind(ACT, quest_id) == acts.KIND_SCRIPT
        assert script.is_file() is scripted, quest_id


def test_content_describes_the_act_as_the_registry_does(content_root):
    from jedicoder import content

    scene = next(item for item in content.load_acts(content_root) if item.act == ACT)
    assert scene.slug == "act3-umeniya"
    assert scene.quests == QUESTS
    assert tuple(scene.quest_titles) == TITLES
    assert len(scene.quest_tasks) == len(QUESTS)
    assert scene.muted is False
    for task in scene.quest_tasks:
        assert "," not in task and len(task.split()) <= 15, task
    paragraphs = [part for part in scene.body.split("\n\n") if part.strip()]
    assert len(paragraphs) == 2


def test_old_act3_left_the_plugin_and_no_skill_name_repeats():
    """Прежний акт — на полке; имена скиллов и команд плагина не повторяются."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    plugin = root / "plugin"
    assert not (plugin / "skills" / "act3-pervaya-krov").exists()
    assert not (plugin / "quests" / "act3-pervaya-krov").exists()
    assert not (plugin / "content" / "ru" / "acts" / "act3-pervaya-krov.md").exists()
    assert (plugin / "skills" / "act3-umeniya" / "SKILL.md").is_file()
    # Приём прежнего акта остался в игре: он приём нового.
    assert (plugin / "skills" / "investigate" / "SKILL.md").is_file()
    assert (plugin / "content" / "ru" / "scroll" / "investigate.md").is_file()

    skills = sorted(path.name for path in (plugin / "skills").iterdir() if path.is_dir())
    commands = sorted(path.stem for path in (plugin / "commands").glob("*.md"))
    names = skills + commands
    assert len(names) == len(set(names)), names


# --- вход: Акты 1 и 2 целиком, потом `enter 3` -------------------------------

def test_act3_is_closed_until_act2_is_done(game, project):  # noqa: F811
    close_act1(game, project())
    assert game("enter", "2")[0] == 0
    code, out = game("enter", "3")
    assert code == 1
    assert "Сначала закрой Акт 2" in out
    data = st.load(game.state_path)
    assert "3" not in data["acts"]
    assert game("artifact", "investigate")[0] == 1


def test_after_act2_the_next_step_is_act3(padawan):
    game, _ = padawan  # noqa: F811
    _, out = game("status")
    lines = out.splitlines()
    assert "Ранг: Падаван" in lines
    assert "  Акт 2. Память и силы — пройден" in lines
    assert "  Акт 3. Умения — не начат, квестов закрыто: 0/5" in lines
    assert "  Акт 4. Свой продукт — не начат, квестов закрыто: 0/5" in lines
    assert "  Акт 5. Три места кода — не начат, квестов закрыто: 0/5" in lines
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: начать Акт 3 «Умения» — квестов в нём 5.",
        "  Скажи Claude: «начинаем».",
    ]
    assert machine_words(out) == []


def test_closing_act2_no_longer_says_the_game_pauses(game, project):  # noqa: F811
    proj = project()
    close_act1(game, proj)
    closing = walk_act2(game, proj)
    assert "Новый ранг: Падаван." in closing
    assert "ещё не написан" not in closing


def test_enter_act3_prints_five_quests_in_words_and_gives_the_artifact(padawan, home):
    """Приёмка тикета: с чистого сохранения Акты 1 и 2 целиком → `enter 3`."""
    game, _ = padawan  # noqa: F811
    code, out = game("enter", "3")

    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "Акт 3. Умения — начат."
    assert lines[2] == (
        "В этом акте ты учишь Claude новым умениям: узнаёшь, где брать "
        "готовые, и делаешь своё."
    )
    assert lines[4] == (
        "К концу вечера Claude знает твоё правило работы и сам записывает "
        "передачу по слову."
    )
    assert "Квесты акта (5):" in lines
    start = lines.index("Квесты акта (5):") + 1
    assert lines[start:start + 5] == [
        "  1. Скилл. Открой список своих скиллов и расскажи Claude о нём.",
        "  2. Где брать. Узнай у Claude о поиске и установке скиллов — потом "
        "перескажи своими словами.",
        "  3. Свой скилл. Продиктуй Claude одно своё правило работы — он "
        "сделает из него скилл.",
        "  4. Хук. Попроси Claude сделать хук на слово «чистка» и попробуй "
        "это слово.",
        "  5. Мод. Найди на экране Claude Code строку о моде игры и расскажи "
        "о ней.",
    ]
    assert "Ранг за акт: Рыцарь. Это следующая ступень после Падавана." in lines
    assert (
        "Приём этого акта — «Разбор поломки»: помогает найти причину, "
        "когда что-то сломалось. "
        "Скажи Claude: «помоги разобраться, почему сломалось»."
    ) in lines
    # Человеку — слова: ни кодов квестов, ни имён ручек, ни имени приёма.
    for quest_id in QUESTS:
        assert quest_id not in out
    assert "investigate" not in out
    assert machine_words(out) == []

    data = st.load(game.state_path)
    assert data["current_act"] == 3
    assert data["acts"]["3"]["status"] == ranks.STATUS_IN_PROGRESS
    assert data["acts"]["3"]["started_at"]
    assert data["artifacts"] == ["brainstorm", "handoff", "investigate"]
    assert data["rank"] == "padawan"


def test_investigate_lock_opens_on_entry(padawan, home):
    game, _ = padawan  # noqa: F811
    code, out = game("artifact", "investigate")
    assert code == 1 and "на входе в Акт 3" in out
    assert game("enter", "3")[0] == 0
    code, out = game("artifact", "investigate")
    assert code == 0 and out.strip() == "Приём investigate открыт."


def test_first_screen_inside_act3_names_the_quest(entered):
    game, _, _ = entered  # noqa: F811
    _, out = game("status")
    lines = out.splitlines()
    assert "  Акт 3. Умения — идёт, квестов закрыто: 0/5" in lines
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: квест «Скилл» — Акт 3 «Умения».",
        "  Открой список своих скиллов и расскажи Claude о нём.",
    ]
    assert machine_words(out) == []


def test_memo_carries_the_investigate_instruction(entered):
    game, proj, _ = entered  # noqa: F811
    code, out = game("scroll")
    assert code == 0, out
    assert (proj / "docs" / "jedicoder" / "investigate.md").is_file()


# --- квесты «Скилл» и «Где брать»: рассказ ----------------------------------

def test_skill_has_no_check_and_closes_by_the_story(entered):
    """Человек открыл `/skills` и рассказал, что увидел. Проверить игре нечего."""
    game, _, home = entered  # noqa: F811
    code, out = game("check", "3", "01-skill")
    assert code == 1 and "нет проверки" in out
    code, out = game("seen", "3", "01-skill")
    assert code == 1 and "рассказа не ждёт" in out
    code, out = game("ack", "3", "01-skill")
    assert code == 0, out
    assert out.splitlines() == ["Квест «Скилл» закрыт: ты рассказал, что увидел."]
    assert machine_words(out) == []
    data = st.load(game.state_path)
    assert acts.is_closed(data, 3, "01-skill")
    assert acts.next_quest(data, 3) == "02-where"
    assert data["acts"]["3"]["status"] == ranks.STATUS_IN_PROGRESS
    # На машине игрока ничего не появилось: игра ничего не ставила.
    assert not (home / ".claude").exists()


def test_where_closes_by_retelling_the_rule(entered):
    game, _, _ = entered  # noqa: F811
    assert game("ack", "3", "01-skill")[0] == 0
    _, status = game("status")
    assert status.rstrip().splitlines()[-2:] == [
        "Что дальше: квест «Где брать» — Акт 3 «Умения».",
        "  Узнай у Claude о поиске и установке скиллов — потом перескажи "
        "своими словами.",
    ]
    code, out = game("check", "3", "02-where")
    assert code == 1 and "нет проверки" in out
    code, out = game("ack", "3", "02-where")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Где брать» закрыт: ты пересказал правило своими словами.",
    ]
    assert machine_words(out) == []
    data = st.load(game.state_path)
    assert acts.next_quest(data, 3) == "03-own-skill"
    assert data["acts"]["3"]["status"] == ranks.STATUS_IN_PROGRESS


# --- «Свой скилл»: момент входа в акт ----------------------------------------

def test_entry_moment_cannot_be_faked_from_the_shell(at_own_skill, monkeypatch):
    """Момент входа приходит только от команды игры.

    Игра момента не знает (запись не читается) и переменную не ставит. Тогда
    приставка `JEDICODER_ACT_STARTED=0` перед командой не должна дойти до
    проверки: с нулём любой личный скилл, стоявший до игры, стал бы «своим».
    """
    game, _, home = at_own_skill  # noqa: F811
    folder = personal_skill(home, "davno-stoit", OWN_SKILL)
    long_ago = time.time() - 86400
    os.utime(str(folder / "SKILL.md"), (long_ago, long_ago))
    data = st.load(game.state_path)
    data["acts"]["3"]["started_at"] = "вчера"
    st.save(data, game.state_path)
    monkeypatch.setenv(quests.STARTED_ENV, "0")
    code, out = game("check", "3", "03-own-skill")
    assert code == 1
    assert "[ ] В папке проекта лежит твой скилл" in out


def test_personal_skill_made_before_the_act_is_not_ones_own(at_own_skill):
    game, _, home = at_own_skill  # noqa: F811
    personal_skill(home, "davno-stoit", OWN_SKILL)
    entered_later(game)
    code, out = game("check", "3", "03-own-skill")
    assert code == 1 and "[ ] В папке проекта лежит твой скилл" in out


def test_personal_skill_made_in_the_act_closes_the_quest(at_own_skill):
    game, _, home = at_own_skill  # noqa: F811
    personal_skill(home, "moi", OWN_SKILL)
    assert game("check", "3", "03-own-skill")[0] == 0


def test_unreadable_entry_moment_leaves_the_project_folder_judged(at_own_skill):
    """Запись о входе правлена руками — личные скиллы не смотрятся, а скилл
    в папке проекта по-прежнему закрывает квест: это не повод отказывать."""
    game, proj, home = at_own_skill  # noqa: F811
    personal_skill(home, "moi", OWN_SKILL)
    data = st.load(game.state_path)
    data["acts"]["3"]["started_at"] = "вчера"
    st.save(data, game.state_path)
    code, out = game("check", "3", "03-own-skill")
    assert code == 1 and "[ ] В папке проекта лежит твой скилл" in out
    project_skill(proj, "moi", OWN_SKILL)
    assert game("check", "3", "03-own-skill")[0] == 0


# --- квест «Свой скилл»: что читает человек, пока скилла нет --------------------

@pytest.fixture
def at_own_skill(entered):
    """Два рассказа позади, открыт «Свой скилл». Отдаёт (игра, папка, дом)."""
    game, proj, home = entered  # noqa: F811
    assert game("ack", "3", "01-skill")[0] == 0
    assert game("ack", "3", "02-where")[0] == 0
    return game, proj, home


def test_own_skill_names_what_to_say_and_the_act_stays_open(at_own_skill):
    """Два квеста закрыты рассказом — своего скилла ещё нет."""
    game, _, _ = at_own_skill  # noqa: F811
    code, out = game("check", "3", "03-own-skill")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Свой скилл» пока не закрыт. Не сошлось:",
        "  [ ] В папке проекта лежит твой скилл",
        "      Назови Claude одно своё правило и скажи: «Сделай из этого "
        "правила скилл для этого проекта».",
    ]
    assert machine_words(out) == []
    _, status = game("status")
    assert "  Акт 3. Умения — идёт, квестов закрыто: 2/5" in status.splitlines()
    data = st.load(game.state_path)
    assert data["rank"] == "padawan"


def test_mod_is_closed_by_words_and_has_no_check(entered):
    game, _, _ = entered  # noqa: F811
    code, out = game("check", "3", "05-mod")
    assert code == 1 and "нет проверки" in out
    code, out = game("ack", "3", "05-mod")
    assert code == 0 and out.startswith("Квест «Мод» закрыт")
    # Акт при этом открыт: четыре квеста впереди.
    assert st.load(game.state_path)["acts"]["3"]["status"] == ranks.STATUS_IN_PROGRESS


def test_third_failure_in_act3_calls_the_magistr_in_plain_words(at_own_skill):
    game, _, _ = at_own_skill  # noqa: F811
    for _ in range(3):
        code, out = game("check", "3", "03-own-skill")
        assert code == 1
    assert "Позови Магистра" in out
    assert "протокол" not in out and "откатись" not in out


def test_face_snapshot_follows_the_new_act(padawan, home):
    game, _ = padawan  # noqa: F811

    def face():
        code, out = game("face", "--called")
        assert code == 0, out
        return json.loads(out)

    before = face()
    assert before["next"] == [
        "Что дальше: начать Акт 3 «Умения» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
    ]
    assert before["rank"] == "Падаван" and before["quests_closed"] == 10
    assert game("enter", "3")[0] == 0
    after = face()
    assert after["next"] == [
        "Что дальше: квест «Скилл» — Акт 3 «Умения».",
        "Открой список своих скиллов и расскажи Claude о нём.",
    ]


def test_tools_take_the_quests_of_act3_by_their_screen_names(entered):
    """Инструменты игры зовут квест словами, как на экране."""
    game, _, _ = entered  # noqa: F811
    code, out = game(cli.TOOL_CALL, "check", "Скилл")
    assert code == 1 and "нет проверки" in out
    # Название не того квеста, что открыт, ничего не закрывает.
    code, out = game(cli.TOOL_CALL, "ack", "Где брать")
    assert code == 1 and "Сейчас открыт квест «Скилл»." in out
    assert game(cli.TOOL_CALL, "ack", "Скилл")[0] == 0
    code, out = game(cli.TOOL_CALL, "ack", "Где брать")
    assert code == 0 and out.startswith("Квест «Где брать» закрыт")

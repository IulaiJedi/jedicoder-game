"""Акт 1 «Знакомство» проходится целиком через CLI — той же дверью, что человек.

Состояние не засевается ни разу: всё, что делает тест, делает и живой
новичок — называет папку, кладёт в неё файлы и зовёт CLI. Трек не
спрашивается: у акта нет развилки.
"""
import pytest

from conftest import _git
from jedicoder import acts, cli, ranks
from jedicoder import state as st

IDEA = """# Идея

## Делаю сегодня
Страницу с расписанием кружка для родителей нашей группы.

## Не сегодня
Запись на занятия, оплата, личный кабинет.
"""

SCRIPTED = ("01-folder", "02-idea", "03-first-request", "04-save")
ACK = "05-stop-undo"
# Квест, проверка которого ждёт слов человека: он открыл то, что получилось,
# и рассказал, что увидел (acts.WORDS_FIRST).
WORDS_FIRST = "03-first-request"

# Готовая папка новичка, закрывшего Акт 1, — для тестов, которым пройденный
# первый акт нужен предпосылкой. Собирается фабрикой `project` из conftest:
# project(files=ACT1_FILES, **ACT1_PROJECT). Дальше — close_act1, той же
# дверью: засев предпосылки записью в сохранение запрещён (CLAUDE.md).
ACT1_FILES = {"IDEA.md": IDEA, "index.html": "<h1>Расписание</h1>\n"}
ACT1_PROJECT = {"gitignore": ".env\n", "git": True, "commits": 1}


def close_act1(jc):
    """Пройти Акт 1 через CLI. `jc(*argv)` возвращает код возврата.

    Папка к этому моменту названа (`project path`) и собрана из ACT1_FILES.
    """
    assert jc("enter", "1") == 0
    for quest_id in SCRIPTED:
        if quest_id == WORDS_FIRST:
            assert jc("seen", "1", quest_id) == 0
        assert jc("check", "1", quest_id) == 0, (
            "квест Акта 1 {} не закрылся".format(quest_id)
        )
    assert jc("ack", "1", ACK) == 0


@pytest.fixture
def game(tmp_path, content_root, quests_root, capsys):
    """Чистая установка: сохранения ещё нет, его создаёт первая команда."""
    state_path = tmp_path / "state.json"

    def jc(*argv):
        code = cli.main(
            list(argv), state_path=state_path, content_root=content_root,
            quests_root=quests_root,
        )
        return code, capsys.readouterr().out

    jc.state_path = state_path
    return jc


def do_idea(proj):
    (proj / "IDEA.md").write_text(IDEA, encoding="utf-8")


def do_first_request(proj):
    (proj / "index.html").write_text("<h1>Расписание</h1>\n", encoding="utf-8")


def do_save(proj, ignore_env=True):
    (proj / ".gitignore").write_text(
        ".env\n" if ignore_env else "node_modules\n", encoding="utf-8"
    )
    _git(proj, "init", "-q")
    _git(proj, "config", "user.email", "novice@example.test")
    _git(proj, "config", "user.name", "Novice")
    _git(proj, "config", "commit.gpgsign", "false")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "первое сохранение")


STEPS = {"02-idea": do_idea, "03-first-request": do_first_request,
         "04-save": do_save}


def walk_scripted(jc, proj):
    for quest_id in SCRIPTED:
        if quest_id in STEPS:
            STEPS[quest_id](proj)
        if quest_id == WORDS_FIRST:
            assert jc("seen", "1", quest_id)[0] == 0
        code, out = jc("check", "1", quest_id)
        assert code == 0, "квест {} не закрылся: {}".format(quest_id, out)


def test_novice_walks_act1_via_cli(game, project):
    proj = project()

    assert game("project", "path", str(proj))[0] == 0
    code, out = game("enter", "1")
    assert code == 0, out
    walk_scripted(game, proj)

    data = st.load(game.state_path)
    assert data["acts"]["1"]["status"] == ranks.STATUS_IN_PROGRESS
    assert data["rank"] == "youngling"

    code, out = game("ack", "1", ACK)
    assert code == 0, out
    assert "Новый ранг: Искатель." in out

    data = st.load(game.state_path)
    assert data["acts"]["1"]["status"] == ranks.STATUS_DONE
    assert data["rank"] == "seeker"
    assert data["first_try"] == {"passed": 4, "attempted": 4}


def test_enter_does_not_ask_for_track(game, project):
    """Развилки у акта нет: вход открыт без ответа «для кого продукт»."""
    code, out = game("enter", "1")
    assert code == 0, out
    assert "для себя" not in out and "для людей" not in out
    assert "track" not in out


def test_enter_gives_brainstorm_and_lists_five_quests(game):
    code, out = game("enter", "1")
    assert code == 0
    assert "Акт 1. Знакомство — начат." in out
    assert "Приём этого акта: /jedicoder:brainstorm" in out
    assert "Ранг за акт: Искатель." in out
    assert "Квесты акта (5):" in out
    # Человеку — номер, название и задание; коды квестов знает скилл акта.
    for quest_id in SCRIPTED + (ACK,):
        assert quest_id not in out
    assert "  5. Стоп и отмена. Останови Claude на ходу и верни всё назад." in out
    assert st.load(game.state_path)["artifacts"] == ["brainstorm"]


def test_registry_and_cutscene_agree(content_root):
    """Пять квестов без развилки: четыре проверки и одно подтверждение."""
    assert acts.quest_ids(1) == SCRIPTED + (ACK,)
    assert [acts.quest_kind(1, quest) for quest in acts.quest_ids(1)] == (
        [acts.KIND_SCRIPT] * 4 + [acts.KIND_ACK]
    )
    assert ranks.ACTS[1]["slug"] == "act1-znakomstvo"
    assert ranks.ACTS[1]["rank"] == "seeker"
    assert ranks.ACTS[1]["artifact"] == "brainstorm"


def test_first_quest_fails_until_folder_is_named(game, project):
    """Запись папки — первый шаг: без неё квест 01 не закрыть."""
    assert game("enter", "1")[0] == 0
    code, out = game("check", "1", "01-folder")
    assert code == 1
    assert "Папка проекта записана" in out
    assert "Скажи Claude, в какой папке будет твой проект." in out
    assert "project path" not in out

    assert game("project", "path", str(project()))[0] == 0
    code, out = game("check", "1", "01-folder")
    assert code == 0, out


def test_later_quests_cannot_be_checked_before_folder_is_named(game):
    """Без названной папки проверка пошла бы по папке запуска — чужой.

    Квест «Первый запрос» здесь же: его ворота «сначала открой и расскажи»
    без папки молчат — совет открыть то, чего нет, был бы не о том.
    """
    assert game("enter", "1")[0] == 0
    for quest_id in ("03-first-request", "04-save"):
        code, out = game("check", "1", quest_id)
        assert code == 1
        assert "Не смог проверить" in out
        assert "сначала закрой квест «Папка»" in out
        assert "Попытка не засчитана" in out
        quest = st.load(game.state_path)["acts"]["1"]["quests"]
        assert quest.get(quest_id, {}).get("status") != ranks.STATUS_DONE


def test_act_stays_open_until_stop_and_undo_is_acknowledged(game, project):
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    walk_scripted(game, proj)

    code, out = game("status")
    assert "  Акт 1. Знакомство — идёт, квестов закрыто: 4/5" in out.splitlines()
    assert "Ранг: Юнлинг" in out


def test_scripted_quest_cannot_be_acknowledged(game, project):
    """Исход скриптового квеста решает exit-код, а не слово."""
    assert game("project", "path", str(project()))[0] == 0
    assert game("enter", "1")[0] == 0
    code, out = game("ack", "1", "04-save")
    assert code == 1
    assert "У квеста «Сохранение» есть проверка. Словами его не закрыть" in out
    assert st.load(game.state_path)["acts"]["1"]["quests"].get("04-save", {}).get(
        "status") != ranks.STATUS_DONE


def test_stop_and_undo_has_no_script(game):
    assert game("enter", "1")[0] == 0
    code, out = game("check", "1", ACK)
    assert code == 1
    assert "У квеста «Стоп и отмена» нет проверки." in out


def test_game_ends_with_act1_and_rank_seeker():
    assert ranks.playable_acts() == [1]
    assert ranks.FINAL_ACT == 1
    assert ranks.FINAL_RANK == "seeker"


@pytest.mark.parametrize("act", [2, 3, 4, 5])
def test_later_acts_refuse_entry_in_plain_words(game, project, act):
    """Закрывший Акт 1 слышит «готовится», а не трейсбек и не «выбери трек»."""
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    walk_scripted(game, proj)
    assert game("ack", "1", ACK)[0] == 0
    before = st.load(game.state_path)

    code, out = game("enter", str(act))

    assert code == 1
    assert out.strip() == (
        "Акт {} ещё не написан. Игра пока заканчивается Актом 1.".format(act)
    )
    # Прежнее имя акта не звучит: состав и имена изменятся. И к финалу отказ
    # не отсылает — финала, пока акты готовятся, нет.
    assert ranks.ACTS[act]["title"] not in out
    assert "finale" not in out
    after = st.load(game.state_path)
    assert str(act) not in after["acts"]
    assert after["current_act"] == before["current_act"]
    assert after["artifacts"] == ["brainstorm"]


def test_closing_act1_says_the_game_ends_here(game, project):
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    walk_scripted(game, proj)
    code, out = game("ack", "1", ACK)
    assert "Акт 1. Знакомство — закрыт." in out
    # Игра не кончилась — значит, ни финала, ни карточки: только памятка.
    # Словами: кладёт её Claude, ручку `scroll` он знает из скилла.
    assert "finale" not in out
    assert "Памятку в папку проекта положит Claude — попроси его." in out
    # Честно про то, что дальше: акты впереди есть, они готовятся. Прежняя
    # строка — «конец игры — той, что бесплатна» — читалась бы как «дальше
    # платно», а это неправда: Акты 2–5 остаются в бесплатной игре.
    assert "На этом игра пока кончается: следующие акты ещё не написаны." in out
    assert "бесплатна" not in out



def closed_act1(game, project):
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    walk_scripted(game, proj)
    assert game("ack", "1", ACK)[0] == 0
    return proj


def test_finale_is_not_a_finale_while_acts_are_in_preparation(game, project):
    """Один вечер — не конец игры: ни страницы финала, ни клуба, ни события."""
    closed_act1(game, project)
    code, out = game("finale")

    assert code == 1
    assert "Игра ещё не кончилась: Акты 2–5 ещё не написаны." in out
    # Счёт «1 из 1» рядом с «акты готовятся» звучал бы как «всё пройдено».
    assert "Твой ранг сейчас — Искатель." in out
    assert "закрыто актов" not in out
    assert "/finale" not in out and "http" not in out
    assert "клуб" not in out.lower()
    assert "=== Карточка" not in out
    assert "scroll" in out
    data = st.load(game.state_path)
    assert not data.get("finale_announced")
    assert [e for e in data["pending_sync"] if e["type"] == "finale"] == []


def test_seeker_card_carries_its_own_trophy_and_no_finale_page(game, project):
    """Карточка ложится в памятку. Трофей — про этот акт (прогон 2026-10-08:
    Искателю одного вечера она говорила «сервер твой»), а двери в финал нет."""
    from jedicoder import debrief

    closed_act1(game, project)
    card = cli.render_rank_card(debrief.facts(st.load(game.state_path)))
    assert "Карточка Искателя" in card
    assert "Закрыто актов: 1 из 1." in card
    assert cli.TROPHY_LINES[1] in card
    assert "сервер" not in card and "Щит" not in card
    assert "finale" not in card and "http" not in card



def test_next_step_after_act1_offers_only_the_memo(game, project):
    closed_act1(game, project)
    _, out = game("status")
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: следующие акты ещё не написаны.",
        "  Памятку в папку проекта положит Claude — попроси его.",
    ]
    assert "finale" not in out



def test_map_names_acts_in_preparation_by_one_line(game):
    """Прежние имена выключенных актов человеку не показываются."""
    code, out = game("status")
    assert code == 0
    lines = out.splitlines()
    assert "  Акты 2–5 ещё не написаны" in lines
    assert len([line for line in lines if "не написан" in line]) == 1
    for act in (2, 3, 4, 5):
        assert ranks.ACTS[act]["title"] not in out



def test_third_failed_attempt_in_act1_speaks_plainly(game, project):
    """Общий протокол зовёт «откатиться на рабочий коммит» и «начать новый
    чат» — новичок первого вечера не слышал ни того, ни другого."""
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    assert game("check", "1", "01-folder")[0] == 0
    for _ in range(2):
        code, out = game("check", "1", "02-idea")
        assert code == 1 and "Третья попытка" not in out
    code, out = game("check", "1", "02-idea")
    assert code == 1
    tail = out.split("Третья попытка.", 1)[1]
    assert "Остановись" in tail
    assert "/jedicoder:magistr" in tail
    for word in ("коммит", "чат", "протокол", "откат"):
        assert word not in tail, word

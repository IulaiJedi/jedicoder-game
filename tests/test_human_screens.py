"""Экраны игры читает человек: слова, а не команды для модели (#83).

Прогон новичком 2026-10-08: первый экран в жизни человека печатал
`project path <путь>` и `enter 1`, список квестов — `01-folder` и
`ack 1 05-stop-undo`. В Голокроне человек видит вывод игры своими глазами.

Шов. Всё, что игра печатает на пути прохождения, — человеку: первый экран,
вход в акт, проверка, закрытие квеста и акта. Имена ручек и коды квестов
модель берёт из скилла акта. Исключение одно: ответ на вызов, которого в
игре нет (нет такой команды, акта, квеста, не хватает аргументов), —
он адресован тому, кто ошибся в вызове, и ручку называет.

Каждый тест ходит через CLI, той же дверью, что человек.
"""
import re
import sys
from pathlib import Path

import pytest

from jedicoder import acts, cli, ranks
from jedicoder import state as st
from test_act1_walkthrough import ACK, IDEA, do_first_request, do_idea, do_save

HOOKS = Path(__file__).resolve().parents[1] / "plugin" / "hooks"

# Имя ручки CLI отдельным латинским словом. `/jedicoder:brainstorm` — не
# ручка, а команда, которую человек набирает сам: её отсекает двоеточие.
# Косая черта отсекает куски путей.
COMMAND = re.compile(
    r"(?<![\w/:.\-])(?:{})(?![\w/.\-])".format("|".join(cli.SUBCOMMANDS))
)
QUEST_IDS = sorted({
    quest_id for entries in acts.QUESTS_BY_ACT.values() for quest_id, _, _ in entries
})


def machine_words(text):
    """Что на экране адресовано модели, а не человеку."""
    found = COMMAND.findall(text)
    found += [quest_id for quest_id in QUEST_IDS if quest_id in text]
    return found


@pytest.fixture
def game(tmp_path, content_root, quests_root, capsys):
    state_path = tmp_path / "state.json"

    def jc(*argv):
        code = cli.main(
            list(argv), state_path=state_path, content_root=content_root,
            quests_root=quests_root,
        )
        return code, capsys.readouterr().out

    jc.state_path = state_path
    return jc


# --- Первый экран чистой установки -----------------------------------------

def test_first_screen_of_a_clean_install_word_for_word(game):
    code, out = game("status")
    assert code == 0
    assert out == (
        "Ранг: Юнлинг — так в игре зовут новичка. Ранг растёт за пройденные "
        "акты.\n"
        "\n"
        "Папка проекта ещё не названа.\n"
        "  Без неё игра не проверит квесты.\n"
        "  Назвать её — первый квест: скажешь Claude, где лежит твой проект.\n"
        "\n"
        "Карта:\n"
        "  Акт 1. Знакомство — не начат, квестов закрыто: 0/5\n"
        "  Акты 2–5 ещё не написаны\n"
        "\n"
        "Что дальше: начать Акт 1 «Знакомство» — квестов в нём 5.\n"
        "  Скажи Claude: «начинаем».\n"
    )


def test_first_screen_has_no_commands_and_no_quest_codes(game):
    _, out = game("status")
    assert machine_words(out) == []
    assert "<" not in out and ">" not in out


def test_first_screen_does_not_scare_with_a_password_file(game):
    """У человека, который ничего не сделал, файла с паролями нет."""
    _, out = game("status")
    assert "парол" not in out


def test_empty_counters_are_not_on_the_first_screen(game):
    _, out = game("status")
    for word in ("Приём", "XP", "Очки", "Серия", "С первой попытки", "Штраф"):
        assert word not in out, word


def test_only_the_novice_rank_is_explained(game, project):
    proj = project()
    walk_act1(game, proj)
    _, out = game("status")
    assert "Ранг: Искатель\n" in out


def test_counters_are_explained_where_they_first_appear(game, project):
    proj = project()
    walk_act1(game, proj)
    _, out = game("status")
    lines = out.splitlines()

    def line(prefix):
        return next(item for item in lines if item.startswith(prefix))

    assert line("Очки:") == (
        "Очки: 100 — за закрытые квесты и новые слова; ранг дают акты, "
        "а не очки"
    )
    assert "XP" not in out
    assert line("Приёмы:") == (
        "Приёмы: найти идею. Скажи Claude: «помоги найти идею» — он применит приём."
    )
    assert line("С первой попытки:") == (
        "С первой попытки: 1 из 4 — квесты, где проверка сошлась сразу"
    )
    assert machine_words(out) == []


def _vague_request(game, monkeypatch):
    """Штраф начисляет хук — та же дверь, которой он приходит к человеку."""
    sys.path.insert(0, str(HOOKS))
    import vague_prompt

    monkeypatch.setenv("JEDICODER_STATE_PATH", str(game.state_path))
    # Штраф — только в игровой сессии (#97): сначала человек зовёт игру.
    assert vague_prompt.react(
        {"prompt": "/jedicoder:start", "session_id": "S-game"}
    ) is None
    assert vague_prompt.react(
        {"prompt": "сделай мне сайт", "session_id": "S-game"}
    ) is not None


def test_penalties_say_what_they_are_and_what_they_are_for(game, monkeypatch):
    """Число без истории человек не читает (живой проход 2026-10-09).

    «Штрафы: 1» стояло на первом экране голым, а на вопрос «за что?» модель
    отвечала, что истории этого числа не знает: правило не объяснять за
    игру у неё есть, а объяснения у игры не было.
    """
    assert game("status")[0] == 0
    _vague_request(game, monkeypatch)
    _, out = game("status")
    lines = out.splitlines()
    at = lines.index("Штрафы: 1 — счёт промахов; очков не отнимают")
    assert lines[at + 1] == "  1 — запрос без подробностей"
    assert machine_words(out) == []


def test_lost_folder_is_named_without_a_command(game, project):
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    proj.rmdir()
    _, out = game("status")
    assert "Папка проекта не найдена: {}".format(proj.name) in out.splitlines()
    assert str(proj.parent) not in out
    assert "  Игра смотрит туда и не сможет проверить квесты." in out
    assert "  Скажи Claude, где проект лежит теперь." in out
    assert machine_words(out) == []


# --- Вход в акт -------------------------------------------------------------

def test_enter_screen_word_for_word(game):
    code, out = game("enter", "1")
    assert code == 0
    assert out == (
        "Акт 1. Знакомство — начат.\n"
        "\n"
        "В этом акте ты знакомишься с Claude Code и делаешь первую версию "
        "своей затеи.\n"
        "\n"
        "К концу вечера ты увидишь результат, сохранишь его и сумеешь "
        "отменить лишнее.\n"
        "\n"
        "Квесты акта (5):\n"
        "  1. Папка. Назови папку своего проекта.\n"
        "  2. Идея на вечер. Выбери одно дело на этот вечер и отложи остальное.\n"
        "  3. Первый запрос. Попроси Claude сделать первую версию и посмотри на неё.\n"
        "  4. Сохранение. Попроси Claude сохранить сделанное.\n"
        "  5. Стоп и отмена. Останови Claude на ходу и верни всё назад.\n"
        "\n"
        "Ранг за акт: Искатель. Это следующая ступень после Юнлинга.\n"
        "Приём этого акта помогает найти идею. Скажи Claude: «помоги найти идею».\n"
    )
    assert machine_words(out) == []


def test_cutscene_comes_before_the_quest_list(game):
    """Катсцена — две фразы, дальше список квестов (language.md)."""
    _, out = game("enter", "1")
    assert out.index("В этом акте") < out.index("Квесты акта")


def test_next_step_names_the_quest_and_its_task(game):
    assert game("enter", "1")[0] == 0
    _, out = game("status")
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: квест «Папка» — Акт 1 «Знакомство».",
        "  Назови папку своего проекта.",
    ]


# --- Весь акт: ни одной команды и ни одного кода на экране ------------------

def walk_act1(game, proj, screens=None):
    """Пройти Акт 1 той же дверью; собрать всё, что игра напечатала."""
    screens = [] if screens is None else screens

    def step(*argv, expect=0):
        code, out = game(*argv)
        assert code == expect, "{}: {}".format(argv, out)
        screens.append(out)
        return out

    step("status")
    step("enter", "1")
    step("check", "1", "01-folder", expect=1)
    step("project", "path", str(proj))
    step("check", "1", "01-folder")
    step("check", "1", "02-idea", expect=1)
    do_idea(proj)
    step("check", "1", "02-idea")
    step("check", "1", "03-first-request", expect=1)
    do_first_request(proj)
    step("seen", "1", "03-first-request")
    step("check", "1", "03-first-request")
    step("check", "1", "04-save", expect=1)
    do_save(proj)
    step("status")
    step("check", "1", "04-save")
    step("check", "1", ACK, expect=1)
    step("ack", "1", "04-save", expect=1)
    step("ack", "1", ACK)
    step("status")
    return screens


def test_no_screen_of_act1_speaks_to_the_model(game, project):
    proj = project()
    for screen in walk_act1(game, proj):
        assert machine_words(screen) == [], screen


# --- Второй прогон новичком (#87): путь, пугающие слова, значки --------------

#: Что пугало или не читалось на экранах второго прогона 2026-10-08.
FRIGHTENING = (
    "не защитит", "удал", "стёр", "стир",   # первый экран: от чего?
    "парол", "ключи доступа", ".env",   # паролей в первый вечер нет
    "в интернет",
    "XP",
    "[·]", "[>]",            # значки карты без расшифровки
)


def test_no_screen_of_act1_shows_the_full_folder_path(game, project):
    """Папка зовётся именем: дорогу из косых черт новичок читал как ошибку."""
    proj = project()
    screens = walk_act1(game, proj)
    assert any("Папка проекта: {}".format(proj.name) in s for s in screens)
    for screen in screens:
        assert str(proj.parent) not in screen, screen


def test_no_screen_of_a_clean_walk_frightens(game, project):
    proj = project()
    for screen in walk_act1(game, proj):
        for phrase in FRIGHTENING:
            assert phrase not in screen, (phrase, screen)


def test_map_speaks_in_words_not_marks(game, project):
    proj = project()
    screens = walk_act1(game, proj)
    assert "  Акт 1. Знакомство — не начат, квестов закрыто: 0/5" in screens[0]
    assert "  Акт 1. Знакомство — идёт, квестов закрыто: 3/5" in screens[-6]
    assert "  Акт 1. Знакомство — пройден" in screens[-1]
    assert "  Акты 2–5 ещё не написаны" in screens[-1]


def test_best_streak_is_shown_only_when_it_differs(game):
    game("status")
    data = st.load(game.state_path)
    data["streak"] = {"current": 1, "best": 1}
    st.save(data, game.state_path)
    _, out = game("status")
    assert (
        "Серия сохранений: 1 — дней подряд, когда работа была сохранена"
        in out.splitlines()
    )
    data = st.load(game.state_path)
    data["streak"] = {"current": 1, "best": 4}
    st.save(data, game.state_path)
    _, out = game("status")
    assert (
        "Серия сохранений: 1 (лучшая 4) — дней подряд, когда работа была "
        "сохранена" in out.splitlines()
    )


def test_returning_seeker_is_not_promised_a_rank_he_has(game, project):
    proj = project()
    walk_act1(game, proj)
    _, out = game("enter", "1")
    assert "Ранг за акт: Искатель. Он у тебя уже есть." in out.splitlines()


def test_folder_that_is_not_there_is_refused_by_name(game, tmp_path):
    code, out = game("project", "path", str(tmp_path / "net-takoy"))
    assert code == 1
    assert out == "Не найдена папка: net-takoy\n"


def test_project_screen_keeps_the_full_path_for_the_model(game, project):
    """Полный путь нужен для дела в одном месте — модели, чтобы работать."""
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    code, out = game("project")
    assert code == 0
    assert out == "Проект:\n  Папка: {}\n".format(proj.resolve())


def test_project_screen_is_silent_about_what_nobody_asked_yet(game):
    """База данных, порт и путь деплоя — вопросы актов, которых ещё нет."""
    _, out = game("project")
    assert out == "Проект:\n  Папка: не названа\n"


def test_project_screen_still_shows_what_was_named(game):
    assert game("project", "port", "8000")[0] == 0
    _, out = game("project")
    assert "  Порт: 8000" in out.splitlines()


# --- Квест «Сохранение»: служебные строки молчат, пока сошлись (#87) --------

def _up_to_save(game, project):
    proj = _up_to_first_request(game, project)
    do_first_request(proj)
    assert game("seen", "1", "03-first-request")[0] == 0
    assert game("check", "1", "03-first-request")[0] == 0
    return proj


def test_closed_save_quest_shows_only_what_the_person_did(game, project):
    proj = _up_to_save(game, project)
    do_save(proj)
    code, out = game("check", "1", "04-save")
    assert code == 0
    assert out == (
        "Квест «Сохранение» закрыт.\n"
        "  [x] В папке проекта заведён git — он хранит сохранения\n"
        "  [x] Есть первое сохранение — коммит\n"
    )


def test_unsaved_project_is_not_told_about_passwords(game, project):
    """Ничего не сохранено: строки-сторожа молчат, говорить им не о чем."""
    _up_to_save(game, project)
    code, out = game("check", "1", "04-save")
    assert code == 1
    for phrase in ("парол", ".env", "ключ"):
        assert phrase not in out, out


def test_guard_line_speaks_calmly_when_it_fails(game, project):
    """Сохранение есть, а настройка на будущее не сделана — строка видна."""
    proj = _up_to_save(game, project)
    do_save(proj, ignore_env=False)
    code, out = game("check", "1", "04-save")
    assert code == 1
    assert out == (
        "Квест «Сохранение» пока не закрыт. Не сошлось:\n"
        "  [ ] Файл для паролей закрыт от сохранений\n"
        "      Это настройка на будущее: пароли в сохранения попадать не "
        "должны. Попроси Claude её доделать.\n"
    )


def test_third_failed_attempt_has_no_commands_either(game, project):
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    assert game("check", "1", "01-folder")[0] == 0
    for _ in range(3):
        _, out = game("check", "1", "02-idea")
    assert "Третья попытка" in out
    assert machine_words(out) == []


def test_quest_screens_name_quests_by_title(game, project):
    proj = project()
    screens = walk_act1(game, proj)
    joined = "\n".join(screens)
    assert "Квест «Папка» закрыт." in joined
    assert "Квест «Идея на вечер» пока не закрыт. Не сошлось:" in joined
    assert "Квест «Стоп и отмена» закрыт: ты рассказал, что увидел." in joined
    assert "У квеста «Стоп и отмена» нет проверки." in joined
    assert "У квеста «Сохранение» есть проверка." in joined


def test_closing_the_act_asks_claude_for_the_memo(game, project):
    proj = project()
    out = walk_act1(game, proj)[-2]
    assert out.splitlines()[-5:] == [
        "Акт 1. Знакомство — закрыт.",
        "Новый ранг: Искатель.",
        "",
        "На этом игра пока кончается: следующие акты ещё не написаны.",
        "Памятку в папку проекта положит Claude — попроси его.",
    ]


def test_wrong_call_still_names_the_handle(game):
    """Ответ на вызов, которого нет, — тому, кто ошибся в вызове."""
    assert game("enter", "1")[0] == 0
    code, out = game("check", "1", "99-net")
    assert code == 1 and "01-folder" in out
    code, out = game("check", "1")
    assert code == 1 and "check" in out


# --- Квест «Папка»: засчитывается то, что в нём делается --------------------

def _record_by_launch(game, proj, monkeypatch):
    """Папку записывает приложение на старте сессии — раньше первой команды."""
    sys.path.insert(0, str(HOOKS))
    import session_start

    monkeypatch.setenv("JEDICODER_STATE_PATH", str(game.state_path))
    monkeypatch.setenv(session_start.PROJECT_DIR_VAR, str(proj))
    session_start.record_launch()
    assert st.load(game.state_path)["project"]["path"] == str(proj.resolve())


def test_folder_quest_waits_for_the_person_to_name_the_folder(
        game, project, monkeypatch):
    """Приложение записало папку заранее — квест этим ещё не сделан."""
    proj = project()
    _record_by_launch(game, proj, monkeypatch)
    assert game("enter", "1")[0] == 0

    code, out = game("check", "1", "01-folder")
    assert code == 1
    assert "  [ ] Папку проекта назвал ты сам" in out
    assert "      Скажи Claude, в какой папке лежит твой проект." in out

    assert game("project", "path", str(proj))[0] == 0
    code, out = game("check", "1", "01-folder")
    assert code == 0, out


def test_naming_another_folder_later_does_not_count_for_the_first(
        game, project, tmp_path, monkeypatch):
    """Названа одна папка, а записана потом другая — назвать надо эту."""
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    other = tmp_path / "drugaya"
    other.mkdir()
    data = st.load(game.state_path)
    data["project"]["path"] = str(other)
    st.save(data, game.state_path)
    assert game("enter", "1")[0] == 0
    assert game("check", "1", "01-folder")[0] == 1


def test_naming_the_folder_says_so_in_plain_words(game, project):
    proj = project()
    code, out = game("project", "path", str(proj))
    assert code == 0
    assert out == "Папка проекта записана: {}\n".format(proj.name)


# --- Квест «Первый запрос»: сначала слова человека, потом проверка ----------

def _up_to_first_request(game, project):
    proj = project(files={"IDEA.md": IDEA})
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    assert game("check", "1", "01-folder")[0] == 0
    assert game("check", "1", "02-idea")[0] == 0
    return proj


def test_first_request_does_not_close_before_the_person_looked(game, project):
    """Код в папке есть — но страницу ещё никто не открыл."""
    proj = _up_to_first_request(game, project)
    do_first_request(proj)

    code, out = game("check", "1", "03-first-request")
    assert code == 1
    assert out == (
        "Квест «Первый запрос» пока не проверяю.\n"
        "Сначала посмотри на то, что получилось, и расскажи Claude, что увидел.\n"
    )
    quest = st.load(game.state_path)["acts"]["1"]["quests"].get("03-first-request", {})
    assert quest.get("status") != ranks.STATUS_DONE
    # Отказ — не попытка: человек ничего не провалил.
    assert quest.get("attempts", 0) == 0
    assert st.load(game.state_path)["xp"] == 40


def test_first_request_closes_after_the_person_said_what_they_saw(game, project):
    proj = _up_to_first_request(game, project)
    do_first_request(proj)
    code, out = game("seen", "1", "03-first-request")
    assert code == 0
    assert out == (
        "Записано: ты посмотрел на то, что получилось в квесте «Первый "
        "запрос», и рассказал, что увидел.\n"
    )
    code, out = game("check", "1", "03-first-request")
    assert code == 0, out
    assert st.load(game.state_path)["first_try"] == {"passed": 3, "attempted": 3}


def test_words_alone_do_not_close_the_first_request(game, project):
    """Исход решает проверка: слова открывают ей дорогу, но не заменяют."""
    proj = _up_to_first_request(game, project)
    do_first_request(proj)
    assert game("seen", "1", "03-first-request")[0] == 0
    quest = st.load(game.state_path)["acts"]["1"]["quests"]["03-first-request"]
    assert quest["status"] != ranks.STATUS_DONE
    (proj / "index.html").unlink()
    code, out = game("check", "1", "03-first-request")
    assert code == 1
    assert "Квест «Первый запрос» пока не закрыт. Не сошлось:" in out


def test_seen_is_only_for_quests_that_wait_for_words(game, project):
    _up_to_first_request(game, project)
    code, out = game("seen", "1", "04-save")
    assert code == 1
    assert "Квест «Сохранение» рассказа не ждёт" in out
    code, out = game("seen", "1")
    assert code == 1


def test_seen_needs_a_started_act(game):
    code, out = game("seen", "1", "03-first-request")
    assert code == 1
    assert "Акт 1 ещё не начат" in out


def test_words_are_not_taken_before_there_is_anything_to_open(game, project):
    """Рассказ раньше результата — не рассказ: открывать ещё нечего."""
    _up_to_first_request(game, project)
    code, out = game("seen", "1", "03-first-request")
    assert code == 1
    assert out == (
        "Смотреть пока не на что: в папке проекта ещё нет первой версии.\n"
        "Сначала попроси Claude её сделать.\n"
    )
    quest = st.load(game.state_path)["acts"]["1"]["quests"].get("03-first-request", {})
    assert not quest.get("seen") and quest.get("attempts", 0) == 0


def test_words_do_not_outlive_a_failed_check(game, project):
    """Проверка не сошлась — результат переделывают, и смотреть надо заново."""
    proj = _up_to_first_request(game, project)
    do_first_request(proj)
    assert game("seen", "1", "03-first-request")[0] == 0
    (proj / "index.html").unlink()
    assert game("check", "1", "03-first-request")[0] == 1
    do_first_request(proj)
    code, out = game("check", "1", "03-first-request")
    assert code == 1 and "пока не проверяю" in out

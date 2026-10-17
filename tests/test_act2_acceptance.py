"""Правки по проходу приёмщика (#114): памятка новой игры, подпись «с первой
попытки» и Полоса после `/clear`.

Приёмщик прошёл Акт 2 новичком и получил памятку, в которой страница
`roadmap.md` говорила голосом прежней игры: «адреса у продукта пока нет», «для
себя или для рынка», клуб по подписке. Новая игра ни о чём таком не спрашивает.

Все тесты ходят той же дверью, что человек: команды игры и хуки, памятка —
командой `scroll` в настоящую папку проекта.
"""
import json

import pytest

from pathlib import Path

from jedicoder import cli, content, ranks, scroll
from test_act2_entry import close_act1, game  # noqa: F401 — фикстура
from test_act2_walkthrough import (
    do_clear, do_memory, do_plan, do_show, walk_two_acts,
)

#: Слова прежней игры, которых в памятке новичка быть не может: о треке, рынке,
#: клубе и адресе продукта новая игра не спрашивает, а очки зовёт словом.
OLD_GAME_WORDS = (
    "трек", "Трек", "рынк", "клуб", "Клуб", "Адрес", "адрес", "XP",
)


def not_written():
    """Как игра говорит о ненаписанных актах — её же словами."""
    return cli.preparing_phrase(ranks.muted_after(ranks.FINAL_ACT))


def memo(game, proj):  # noqa: F811
    """Взять памятку и прочитать её всю: {имя файла: текст}."""
    code, out = game("scroll")
    assert code == 0, out
    folder = proj / "docs" / "jedicoder"
    return dict(
        (path.name, path.read_text(encoding="utf-8"))
        for path in sorted(folder.iterdir())
    )


@pytest.fixture
def seeker(game, project):  # noqa: F811
    proj = project()
    close_act1(game, proj)
    return game, proj


@pytest.fixture
def padawan(game, project):  # noqa: F811
    proj = project()
    walk_two_acts(game, proj)
    return game, proj


# --- памятка: ни слова прежней игры ---------------------------------------------

@pytest.mark.parametrize("who", ("seeker", "padawan"))
def test_memo_carries_no_word_of_the_previous_game(who, request):
    game, proj = request.getfixturevalue(who)  # noqa: F811
    pages = memo(game, proj)
    # Инструкция приёма написана автором раньше и вычитана отдельно; страницы,
    # которые собирает игра, — все остальные.
    own = dict(
        (name, text) for name, text in pages.items()
        if name not in ("brainstorm.md", "handoff.md")
    )
    assert scroll.ROADMAP_NAME in own
    for name, text in own.items():
        for word in OLD_GAME_WORDS:
            assert word not in text, (name, word)


def test_padawan_roadmap_says_what_is_done_and_what_is_ahead(padawan):
    game, proj = padawan  # noqa: F811
    page = memo(game, proj)[scroll.ROADMAP_NAME]
    assert page.splitlines()[0] == "# Что пройдено и что впереди"
    assert "- Акт 1 «Знакомство» — ранг Искатель." in page
    assert "- Акт 2 «Память и силы» — ранг Падаван." in page
    # С 2026-10-16 ненаписанных актов нет (спека #123): впереди — все три
    # оставшихся по именам, без строки о ненаписанном и без сроков.
    assert "- Акт 5 «Три места кода» — ещё не пройден." in page
    assert not_written() == ""
    assert "не написан" not in page and "Сроков игра не называет" not in page
    assert "скоро" not in page.lower()


def test_padawan_roadmap_names_what_is_not_written_while_an_act_is_muted(
        padawan, last_act_muted):
    """Механика выключенного акта цела: строка о ненаписанном — словами игры."""
    game, proj = padawan  # noqa: F811
    page = memo(game, proj)[scroll.ROADMAP_NAME]
    # Те же слова, что печатает игра на первом экране и в ответ на `finale`.
    assert not_written() + ". Сроков игра не называет." in page
    # Имён выключенных актов нет.
    for number in ranks.MUTED_ACTS:
        assert ranks.ACTS[number]["title"] not in page


def test_seeker_roadmap_names_the_open_act_ahead(seeker):
    game, proj = seeker  # noqa: F811
    page = memo(game, proj)[scroll.ROADMAP_NAME]
    done, ahead = page.split("## Впереди")
    assert "- Акт 1 «Знакомство» — ранг Искатель." in done
    assert "Память и силы" not in done
    assert "- Акт 2 «Память и силы» — ещё не пройден." in ahead
    assert "- Акт 5 «Три места кода» — ещё не пройден." in ahead


def test_memo_taken_before_any_act_does_not_invent_a_passed_act(game, project):  # noqa: F811
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    page = memo(game, proj)[scroll.ROADMAP_NAME]
    done, ahead = page.split("## Впереди")
    assert "ранг" not in done
    assert "Акт 1 «Знакомство»" in ahead


def test_index_names_the_roadmap_by_what_is_in_it(padawan):
    game, proj = padawan  # noqa: F811
    index = memo(game, proj)[scroll.INDEX_NAME]
    assert "- **roadmap.md** — что пройдено и что впереди." in index
    assert "три шага" not in index


def test_index_says_who_puts_the_memo(padawan):
    """Человек команду не набирает: он просит Claude словами."""
    game, proj = padawan  # noqa: F811
    index = memo(game, proj)[scroll.INDEX_NAME]
    assert "набираешь" not in index
    assert "Памятку кладёт сюда Claude, когда ты его просишь." in index


def test_memo_does_not_carry_a_technique_nobody_gave(padawan):
    game, proj = padawan  # noqa: F811
    pages = memo(game, proj)
    assert "goal.md" not in pages
    assert "goal" not in pages[scroll.INDEX_NAME]
    assert "handoff.md" in pages and "brainstorm.md" in pages


def test_old_roadmap_comes_back_with_the_act_that_asks_for_the_address(
        game, project, monkeypatch):  # noqa: F811
    """Тексты прежней игры не удалены: они ждут акта, которому принадлежат, —
    того, что спрашивает адрес продукта (`cli.ROADMAP_ACT`). С 2026-10-16
    такого акта нет: адрес спрашивал прежний «Выход в свет», он на полке.

    Приём «Цель» (`goal`) с 2026-10-14 выдаётся на входе в Акт 4 (спека #117)
    и в памятку человека, не входившего туда, не идёт
    (tests/test_act4_entry.py)."""
    assert cli.ROADMAP_ACT is None
    monkeypatch.setattr(cli, "ROADMAP_ACT", 5)
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    pages = memo(game, proj)
    assert "goal.md" not in pages
    assert "Шаг 1" in pages[scroll.ROADMAP_NAME]
    assert "три шага, чтобы довести продукт до людей" in pages[scroll.INDEX_NAME]


def test_every_technique_without_a_lock_names_a_known_act():
    """Приём без замка, которого нет в перечне, лёг бы в памятку с первого дня."""
    assert set(cli.UNLOCKED_ARTIFACT_ACTS) == set(ranks.UNLOCKED_ARTIFACTS)
    assert set(cli.UNLOCKED_ARTIFACT_ACTS.values()) <= set(ranks.ACTS)


def test_points_are_called_points_in_the_card_and_the_debrief(padawan):
    game, proj = padawan  # noqa: F811
    pages = memo(game, proj)
    xp = json.loads(game.state_path.read_text(encoding="utf-8"))["xp"]
    assert xp > 0
    assert "Очки: {}".format(xp) in pages[scroll.RANK_CARD_NAME].splitlines()
    razbor = pages[scroll.DEBRIEF_NAME].splitlines()
    assert "## Словарь и очки" in razbor
    assert "- Очки: {}".format(xp) in razbor


# --- «с первой попытки»: число объяснено ----------------------------------------

def test_debrief_explains_what_the_first_try_line_counts(padawan):
    """Десять квестов закрыто, а в строке «8 из 8»: Магистру гадать нельзя."""
    game, proj = padawan  # noqa: F811
    razbor = memo(game, proj)[scroll.DEBRIEF_NAME].splitlines()
    assert "- Закрыто квестов: 10" in razbor
    line = razbor.index(
        "- С первой попытки: 8 из 8 — в счёте только квесты с проверкой"
    )
    assert razbor[line + 1] == (
        "  - Квесты без проверки, которые закрывает рассказ, в этот счёт "
        "не входят"
    )


def test_first_screen_explains_what_the_first_try_line_counts(padawan):
    game, _ = padawan  # noqa: F811
    code, out = game("status")
    assert code == 0
    assert (
        "С первой попытки: 8 из 8 — проверка сошлась сразу; в счёте только "
        "квесты с проверкой"
    ) in out.splitlines()


# --- вход в акт: пять квестов одной строкой --------------------------------------

def test_the_skill_names_the_quests_of_the_evening_as_the_game_does(content_root):
    """Список игры на экране свёрнут, и квесты называет Claude — теми же
    именами: переименуют квест в акте, строка скилла обязана пойти следом."""
    skill = (
        Path(__file__).resolve().parents[1]
        / "plugin" / "skills" / "act2-pamyat-i-sily" / "SKILL.md"
    ).read_text(encoding="utf-8")
    act = next(a for a in content.load_acts(content_root) if a.act == 2)
    line = " ".join(skill.split("> Сегодня пять квестов:")[1].split("\n\n")[0].split())
    line = line.replace("> ", "")
    names = ["«{}»".format(title) for title in act.quest_titles]
    assert line == "{} и {}.".format(", ".join(names[:-1]), names[-1])


# --- Полоса после `/clear` ---------------------------------------------------------

def strip(game):  # noqa: F811
    """Вторая строка «Что дальше» — с первого экрана и из снимка Лица."""
    code, out = game("status")
    assert code == 0, out
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Что дальше:"))
    code, raw = game("face", "--called")
    assert code == 0, raw
    assert json.loads(raw)["next"] == [line.strip() for line in lines[start:start + 2]]
    return lines[start + 1].strip()


@pytest.fixture
def at_clear(game, project, content_root):  # noqa: F811
    """Открыт квест «Чистый лист»: память проекта уже записана."""
    proj = project()
    close_act1(game, proj)
    assert game("enter", "2")[0] == 0
    do_plan(game, proj)
    assert game("check", "2", "01-plan")[0] == 0
    do_show(game, proj)
    assert game("check", "2", "02-show")[0] == 0
    do_memory(game, proj)
    assert game("check", "2", "03-memory")[0] == 0
    return game, proj, cli._quest_tasks(content_root)[(2, "04-clear")]


def test_strip_after_clear_no_longer_asks_for_the_handoff(at_clear):
    game, proj, task = at_clear  # noqa: F811
    assert strip(game) == task
    do_clear(game, proj)
    assert strip(game) == (
        "Новый разговор начат. Дальше — вопрос «на чём остановились?» и "
        "рассказ об ответе Claude."
    )
    assert game("seen", "2", "04-clear")[0] == 0
    assert strip(game) == cli.STEP_WORDS_TAKEN
    assert game("check", "2", "04-clear")[0] == 0


def test_clear_before_the_memory_quest_does_not_change_the_strip(
        game, project, content_root):  # noqa: F811
    """След без пометки проверке не уходит — и Полоса о нём молчит."""
    proj = project()
    close_act1(game, proj)
    assert game("enter", "2")[0] == 0
    do_plan(game, proj)
    assert game("check", "2", "01-plan")[0] == 0
    do_show(game, proj)
    assert game("check", "2", "02-show")[0] == 0
    do_clear(game, proj)                      # раньше записи памяти проекта
    do_memory(game, proj)
    assert game("check", "2", "03-memory")[0] == 0
    assert strip(game) == cli._quest_tasks(content_root)[(2, "04-clear")]

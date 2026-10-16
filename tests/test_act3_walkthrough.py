"""Сквозной проход Акта 3 «Умения» — той же дверью, что человек (#110).

Чистое сохранение → Акт 1 командами игры → Акт 2 командами и хуками
(`walk_act2`) → `enter 3` → два рассказа («Скилл» и «Где брать»: из сети
ничего не ставится, #116) → свой скилл и хук — их файлы кладёт тест так, как
их кладёт Claude по замерам (`docs/research/2026-10-13-act3-skills-hooks-mods.md`,
раздел «Замеры #110»), хук следов зовётся процессом на данных настоящей формы
→ две проверки → рассказ о моде → ранг Рыцарь → памятка.

Сохранение не засевается нигде: след пишет хук `plugin/hooks/traces.py`,
закрытые квесты — команды игры. Машина игрока — песочная домашняя папка
теста; настоящий `~/.claude` эти тесты не читают.

`walk_act3` — общий проход для тестов следующих актов: к закрытому Акту 3
можно прийти только так. Конец игры сегодня — закрытый Акт 4, его проходит
`walk_act4` в `tests/test_act4_walkthrough.py`: слова «игра пока кончается»,
`finale`, трофей на карточке и полоса после конца стережутся там.
"""
import json
import os
import time
from pathlib import Path

import pytest

from jedicoder import acts, cli, debrief, ranks
from jedicoder import state as st
from test_act2_entry import close_act1, game  # noqa: F401 — фикстура
from test_act2_walkthrough import hook, walk_act2
from test_act3_checks import project_skill
from test_act3_entry import QUESTS, TITLES
from test_human_screens import machine_words
from test_show_traces import asked

CONTENT = Path(__file__).resolve().parents[1] / "plugin" / "content" / "ru"

#: Свой скилл — как его написал Claude в замере (ж): папка латиницей, блок
#: `---` с именем и описанием, тело с правилом.
OWN_SKILL_NAME = "otchet-o-pravke"
OWN_SKILL_MD = (
    "---\n"
    "name: otchet-o-pravke\n"
    "description: Отчёт после правки страницы. Используй каждый раз, когда "
    "изменил index.html, — сразу после правки.\n"
    "---\n"
    "\n"
    "# Отчёт после правки страницы\n"
    "\n"
    "После каждой правки страницы скажи одной фразой, что изменилось на вид "
    "и как это открыть.\n"
)

#: Настройки проекта с хуком — как их записал Claude в замере (з).
HOOK_SETTINGS = {
    "hooks": {
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/chistka.sh"',
                    }
                ]
            }
        ]
    }
}

HOOK_SCRIPT = (
    "#!/usr/bin/env bash\n"
    "# Хук UserPromptSubmit: по слову «чистка» просит записать передачу.\n"
    "python3 -c 'import sys; print(1)'\n"
)


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: пустая, как у человека до установок."""
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


# --- что делает Claude по словам человека --------------------------------------

def do_own_skill(proj):
    """Квест «Свой скилл»: Claude одним `Write` кладёт скилл в папку проекта."""
    return project_skill(proj, OWN_SKILL_NAME, OWN_SKILL_MD)


def make_hook(proj):
    """Claude записал хук: скрипт и настройки проекта (замер (з))."""
    hooks = proj / ".claude" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "chistka.sh").write_text(HOOK_SCRIPT, encoding="utf-8")
    (proj / ".claude" / "settings.json").write_text(
        json.dumps(HOOK_SETTINGS, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def say_the_word(game, proj, prompt="чистка"):  # noqa: F811
    """Человек набрал слово: запрос доходит до хука игры как есть."""
    hook(game, asked(prompt, proj))


def write_handoff(proj, age=0):
    """Claude записал передачу. `age` — на сколько секунд раньше «сейчас»."""
    path = proj / "HANDOFF.md"
    path.write_text("# Передача\n\nСделано: скилл и хук.\n", encoding="utf-8")
    if age:
        moment = time.time() - age
        os.utime(str(path), (moment, moment))
    return path


def do_hook(game, proj):  # noqa: F811
    """Квест «Хук»: хук записан, слово сказано, передача записана."""
    make_hook(proj)
    say_the_word(game, proj)
    write_handoff(proj)


def walk_act3(game, proj, home, screens=None):  # noqa: F811
    """Пройти Акт 3 от входа до закрытия. Акты 1 и 2 к этому времени закрыты.

    `home` — домашняя папка, в которую смотрят проверки (`HOME` теста).
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

    step("enter", "3")
    # «Скилл» и «Где брать» закрывает рассказ: человек посмотрел свои скиллы и
    # пересказал правило. Машину игры не трогают — ставить нечего.
    step("ack", "3", "01-skill")
    step("ack", "3", "02-where")
    do_own_skill(proj)
    step("check", "3", "03-own-skill")
    do_hook(game, proj)
    step("check", "3", "04-hook")
    # «Мод»: человек рассказал, модель спрашивает игру инструментом — мод ли
    # дал ей этот инструмент.
    step(cli.TOOL_CALL, "folder")
    return step("ack", "3", "05-mod")


def walk_to_the_end(game, proj, home, screens=None):  # noqa: F811
    """Вся сегодняшняя игра командами и хуками: Акты 1, 2 и 3."""
    close_act1(game, proj)
    walk_act2(game, proj)
    return walk_act3(game, proj, home, screens)


@pytest.fixture
def finished(game, project, home):  # noqa: F811
    """Игра пройдена до сегодняшнего конца. Отдаёт (игра, папка, экраны)."""
    proj = project()
    screens = []
    walk_to_the_end(game, proj, home, screens)
    return game, proj, screens


@pytest.fixture
def at_hook(game, project, home):  # noqa: F811
    """Три квеста акта закрыты, открыт «Хук». Отдаёт (игра, папка)."""
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    assert game("enter", "3")[0] == 0
    assert game("ack", "3", "01-skill")[0] == 0
    assert game("ack", "3", "02-where")[0] == 0
    do_own_skill(proj)
    assert game("check", "3", "03-own-skill")[0] == 0
    return game, proj


# --- проход ------------------------------------------------------------------

def test_novice_walks_act3_from_a_clean_save_to_knight(game, project, home):  # noqa: F811
    proj = project()
    assert not game.state_path.exists()
    close_act1(game, proj)
    walk_act2(game, proj)
    data = st.load(game.state_path)
    assert data["rank"] == "padawan"
    assert st.trace(data, st.TRACE_HOOK_WORD) is None

    walk_act3(game, proj, home)

    data = st.load(game.state_path)
    assert data["rank"] == "knight"
    assert ranks.rank_for(data) == "knight"
    assert data["acts"]["3"]["status"] == ranks.STATUS_DONE
    assert acts.all_closed(data, 3) is True
    assert sorted(data["acts"]["3"]["quests"]) == sorted(QUESTS)
    assert data["artifacts"] == ["brainstorm", "handoff", "investigate"]
    for kind in st.TRACE_KINDS:
        assert cli._trace_counts(data, kind), kind
    facts = debrief.facts(data)
    assert facts["acts_completed"] == [1, 2, 3]
    assert facts["first_try"]["passed"] == facts["first_try"]["attempted"]
    # Машина игрока не тронута: ни скилла из сети, ни списка плагинов.
    assert not (home / ".claude").exists()
    assert sorted(path.name for path in (proj / ".claude" / "skills").iterdir()) \
        == [OWN_SKILL_NAME]


def test_skill_and_where_close_by_the_story_in_words(finished):
    """Два первых квеста закрывает рассказ — и слова экрана о нём разные:
    в «Скилле» человек посмотрел, в «Где брать» — пересказал правило."""
    _, _, screens = finished
    assert screens[1].splitlines() == [
        "Квест «Скилл» закрыт: ты рассказал, что увидел.",
    ]
    assert screens[2].splitlines() == [
        "Квест «Где брать» закрыт: ты пересказал правило своими словами.",
    ]


def test_the_words_of_the_request_never_reach_the_save(at_hook):
    game, proj = at_hook  # noqa: F811
    make_hook(proj)
    say_the_word(game, proj, "чистка, пожалуйста: тайное-слово-человека")
    raw = game.state_path.read_text(encoding="utf-8")
    assert "тайное-слово-человека" not in raw and "истка" not in raw
    assert st.trace(st.load(game.state_path), st.TRACE_HOOK_WORD) is not None


def test_the_act_stays_open_until_the_last_quest(at_hook):
    game, proj = at_hook  # noqa: F811
    do_hook(game, proj)
    code, out = game("check", "3", "04-hook")
    assert code == 0, out
    assert "Акт 3" not in out and "ранг" not in out.lower()
    data = st.load(game.state_path)
    assert data["rank"] == "padawan"
    assert data["acts"]["3"]["status"] == ranks.STATUS_IN_PROGRESS


# --- что человек читает на пути закрытия ---------------------------------------

def test_own_skill_and_hook_close_with_their_lines_in_words(finished):
    _, _, screens = finished
    assert screens[3].splitlines() == [
        "Квест «Свой скилл» закрыт.",
        "  [x] В папке проекта лежит твой скилл",
        "  [x] У скилла есть описание: когда его применять",
        "  [x] В скилле записано само правило",
    ]
    assert screens[4].splitlines() == [
        "Квест «Хук» закрыт.",
        "  [x] Хук записан в настройках Claude Code",
        "  [x] Слово «чистка» сказано, когда хук уже был",
        "  [x] После слова записана передача",
    ]


def test_before_the_last_quest_the_game_tells_the_model_about_its_mod(finished):
    """Экран позван инструментом игры — инструменты даёт мод: он работает."""
    _, proj, screens = finished
    lines = screens[-2].splitlines()
    assert lines[:4] == [
        "Проект:",
        "  Папка: {}".format(proj.resolve()),
        "",
        "Claude Code — что игра видит сама:",
    ]
    assert lines[-1] == (
        "  Мод игры: работает — игра сейчас отвечает через него."
    )


def test_called_by_a_command_the_game_does_not_claim_to_see_its_mod(finished):
    """Той же командой в терминале игра о моде не знает — так и говорит."""
    game, _, _ = finished  # noqa: F811
    code, out = game("project")
    assert code == 0
    assert out.splitlines()[-1] == (
        "  Мод игры: игра этого не видит — сейчас она отвечает не через мод."
    )
    assert "работает" not in out


def test_the_mod_line_waits_for_act3(game, project):  # noqa: F811
    """До входа в Акт 3 слово «мод» человеку не звучало — строки нет."""
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    for argv in (("project",), (cli.TOOL_CALL, "folder")):
        code, out = game(*argv)
        assert code == 0 and "Мод игры" not in out


def test_closing_the_act_names_the_rank_and_nothing_more(finished):
    """Игра дальше идёт: Акт 4 открыт, слов о конце нет (они — в Акте 4)."""
    _, _, screens = finished
    assert screens[-1].splitlines() == [
        "Квест «Мод» закрыт: ты рассказал, что увидел.",
        "",
        "Акт 3. Умения — закрыт.",
        "Новый ранг: Рыцарь.",
    ]


def test_no_screen_of_act3_speaks_to_the_model(finished):
    game, _, screens = finished  # noqa: F811
    screens.append(game("status")[1])
    for screen in screens:
        assert machine_words(screen) == [], screen
        assert "Traceback" not in screen
        for quest_id in QUESTS:
            assert quest_id not in screen, screen


def test_knight_card_counts_the_closed_acts_and_has_no_trophy_yet(finished):
    """Трофей — у конца игры (Акт 4); Рыцарю — только закрытое."""
    game, _, _ = finished  # noqa: F811
    card = cli.render_rank_card(debrief.facts(st.load(game.state_path)))
    lines = card.splitlines()
    assert lines[0] == "=== Карточка Рыцаря ==="
    assert "Закрыто актов: 3 из 4." in lines
    for title in ("Знакомство", "Память и силы", "Умения"):
        assert any(line.endswith(title) for line in lines), title
    for trophy in cli.TROPHY_LINES.values():
        assert trophy not in card
    assert "В карточке только закрытое" in card
    assert "finale" not in card and "http" not in card


def test_memo_of_the_third_evening_carries_the_technique_and_the_phrases(finished):
    game, proj, _ = finished  # noqa: F811
    code, out = game("scroll")
    assert code == 0, out
    assert out.splitlines()[0] == "Памятка Рыцаря: {}/docs/jedicoder".format(
        proj.name
    )
    assert machine_words(out) == []
    folder = proj / "docs" / "jedicoder"
    names = sorted(path.name for path in folder.iterdir())
    for name in ("investigate.md", "handoff.md", "brainstorm.md", "frazy.md"):
        assert name in names
    razbor = (folder / "razbor.md").read_text(encoding="utf-8")
    assert "- Закрыто актов: 3 из 4" in razbor
    assert "из 5" not in razbor
    everything = "\n".join(
        path.read_text(encoding="utf-8") for path in folder.iterdir()
    )
    for trophy in cli.TROPHY_LINES.values():
        assert trophy not in everything
    for quest_id in QUESTS:
        assert quest_id not in razbor
    for title in TITLES:
        assert "| 3 | {} | 1 | да |".format(title) in razbor
    # Фразы третьего вечера — рядом с фразами первых двух.
    frazy = (folder / "frazy.md").read_text(encoding="utf-8")
    assert (
        "| Нашёл в интернете скилл | Вот ссылка на скилл. Проверь; если "
        "полезный — скажи чем и установи |"
    ) in frazy
    assert (
        "| Скилл нужен только в этом проекте | Вот ссылка на скилл. Проверь; "
        "если полезный — скажи чем и установи в этот проект |"
    ) in frazy
    # Скиллов из сети в игре нет: фразы про скилл, которого человек не ставил,
    # на странице нет.
    assert "Impeccable" not in frazy
    assert (
        "| Пора начать разговор заново, а хук на слово «чистка» уже сделан | "
        "Чистка. Ровно это слово: Claude сам запишет передачу в `HANDOFF.md`. "
        "Команду `/clear` потом набираешь сам |"
    ) in frazy
    assert "Сохрани. Или: сделай коммит" in frazy
    # Страница работает без игры: ни одного её слова.
    for word in ("квест", "Квест", "акт ", "Акт", "ранг", "Jedicoder", "jedicoder"):
        assert word not in frazy, word


# --- Полоса, всплывающие и карта в каждом состоянии акта ------------------------

def strip_and_map(game):  # noqa: F811
    """Строка «Что дальше» первого экрана, она же в снимке Лица, строка карты
    об Акте 3 и то, по чему Лицо решает о всплывающих."""
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
    act3 = next(line.strip() for line in lines if line.startswith("  Акт 3."))
    return step[0], step[1], act3, face["quests_closed"], face["rank"], face["say"]


def test_strip_toasts_and_map_are_true_in_every_state_of_the_act(
        game, project, home, content_root):  # noqa: F811
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    tasks = cli._quest_tasks(content_root)
    quest = "Что дальше: квест «{}» — Акт 3 «Умения»."
    going = "Акт 3. Умения — идёт, квестов закрыто: {}/5"

    def see():
        return strip_and_map(game)

    assert see() == (
        "Что дальше: начать Акт 3 «Умения» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
        "Акт 3. Умения — не начат, квестов закрыто: 0/5",
        10, "Падаван", cli.SAY_START,
    )

    assert game("enter", "3")[0] == 0
    assert see() == (quest.format("Скилл"), tasks[(3, "01-skill")],
                     going.format(0), 10, "Падаван", "")
    assert game("ack", "3", "01-skill")[0] == 0

    assert see() == (quest.format("Где брать"), tasks[(3, "02-where")],
                     going.format(1), 11, "Падаван", "")
    assert game("ack", "3", "02-where")[0] == 0

    assert see() == (quest.format("Свой скилл"), tasks[(3, "03-own-skill")],
                     going.format(2), 12, "Падаван", "")
    do_own_skill(proj)
    assert see()[1] == tasks[(3, "03-own-skill")]
    assert game("check", "3", "03-own-skill")[0] == 0

    assert see() == (quest.format("Хук"), tasks[(3, "04-hook")],
                     going.format(3), 13, "Падаван", "")
    make_hook(proj)
    assert see()[1] == tasks[(3, "04-hook")]      # хук записан — слова не было
    say_the_word(game, proj)
    assert see() == (quest.format("Хук"), cli.STEP_WORD_SAID,
                     going.format(3), 13, "Падаван", "")
    write_handoff(proj)
    assert game("check", "3", "04-hook")[0] == 0

    assert see() == (quest.format("Мод"), tasks[(3, "05-mod")],
                     going.format(4), 14, "Падаван", "")
    assert game(cli.TOOL_CALL, "folder")[0] == 0
    assert see()[1] == tasks[(3, "05-mod")]
    assert game("ack", "3", "05-mod")[0] == 0

    # Акт закрыт: ранг вырос — Лицо покажет подпись о ранге, а не о квесте.
    # Дальше — Акт 4, и в поле ввода снова «начинаем».
    assert see() == (
        "Что дальше: начать Акт 4 «Свой продукт» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
        "Акт 3. Умения — пройден",
        15, "Рыцарь", cli.SAY_START,
    )


def test_the_strip_after_the_end_does_not_change_when_the_memo_is_taken(finished):
    game, _, _ = finished  # noqa: F811
    before = strip_and_map(game)
    assert game("scroll")[0] == 0
    assert strip_and_map(game) == before


# --- квест «Хук»: что не закрывает ---------------------------------------------

def test_the_word_before_the_hook_is_made_is_not_counted(at_hook):
    """Просьба сделать хук сама называет слово — хука тогда ещё нет."""
    game, proj = at_hook  # noqa: F811
    say_the_word(game, proj, "Сделай хук: когда я пишу слово «чистка», запиши передачу")
    make_hook(proj)
    write_handoff(proj)
    code, out = game("check", "3", "04-hook")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Хук» пока не закрыт. Не сошлось:",
        "  [ ] Слово «чистка» сказано, когда хук уже был",
        "      Набери одно слово: «чистка». Claude должен сам записать передачу.",
    ]
    assert machine_words(out) == []


def test_the_word_without_a_handoff_after_it_does_not_close_the_quest(at_hook):
    """Слово сказано, а передача старая: хук не отработал."""
    game, proj = at_hook  # noqa: F811
    make_hook(proj)
    write_handoff(proj, age=3600)
    say_the_word(game, proj)
    code, out = game("check", "3", "04-hook")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Хук» пока не закрыт. Не сошлось:",
        "  [ ] После слова записана передача",
        "      Слово сказано, а передачи после него нет. Попроси Claude "
        "найти, почему хук не сработал, и набери «чистка» снова.",
    ]
    # Проверка не сошлась: полоса не зовёт ту же проверку, а возвращается
    # к заданию — пока слово не скажут заново.
    task = cli._quest_tasks(CONTENT)[(3, "04-hook")]
    assert strip_and_map(game)[1] == task
    # Починили и сказали слово снова — передача легла, квест закрывается.
    say_the_word(game, proj)
    assert strip_and_map(game)[1] == cli.STEP_WORD_SAID
    write_handoff(proj)
    assert game("check", "3", "04-hook")[0] == 0


def test_a_later_mention_of_the_word_does_not_undo_a_handoff_already_written(
        at_hook):
    """«Я же сказал чистка» после сработавшего хука квест не отбирает."""
    game, proj = at_hook  # noqa: F811
    make_hook(proj)
    say_the_word(game, proj)
    write_handoff(proj)
    before = st.trace(st.load(game.state_path), st.TRACE_HOOK_WORD)
    say_the_word(game, proj, "я же сказал: чистка! проверь квест")
    assert st.trace(st.load(game.state_path), st.TRACE_HOOK_WORD) == before
    assert game("check", "3", "04-hook")[0] == 0


def test_the_hook_trace_cannot_be_faked_from_the_shell(at_hook, monkeypatch):
    game, proj = at_hook  # noqa: F811
    make_hook(proj)
    write_handoff(proj)
    monkeypatch.setenv("JEDICODER_TRACE_HOOK_WORD", "yes")
    monkeypatch.setenv("JEDICODER_TRACE_HOOK_WORD_AT", "0")
    code, out = game("check", "3", "04-hook")
    assert code == 1
    assert "[ ] Слово «чистка» сказано, когда хук уже был" in out


def test_after_the_quest_is_closed_the_word_no_longer_touches_the_save(finished):
    """Слово остаётся рабочим словом человека: игра за ним больше не следит."""
    game, proj, _ = finished  # noqa: F811
    write_handoff(proj, age=7200)
    before = (game.state_path.stat().st_mtime_ns, game.state_path.read_bytes())
    say_the_word(game, proj)
    assert (game.state_path.stat().st_mtime_ns,
            game.state_path.read_bytes()) == before

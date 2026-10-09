"""Скилл Акта 1 «Знакомство» — то, что модель говорит новичку (#83).

Экраны игры печатают слова, а не ручки (tests/test_human_screens.py), поэтому
скилл — единственное место, откуда модель берёт код квеста и команду. Здесь
же прибит порядок, который движок проверить не может, и решения оператора
о словах первого квеста.
"""
import re
from pathlib import Path

import pytest

from jedicoder import acts, content

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
SKILL = PLUGIN / "skills" / "act1-znakomstvo" / "SKILL.md"
TEXT_SUFFIXES = (".md", ".py", ".sh", ".json", ".txt")


@pytest.fixture(scope="module")
def skill():
    return SKILL.read_text(encoding="utf-8")


def section(text, heading):
    """Тело раздела `## heading…` до следующего заголовка того же уровня."""
    match = re.search(
        r"^## {}[^\n]*\n(.*?)(?=^## |\Z)".format(re.escape(heading)),
        text, re.MULTILINE | re.DOTALL,
    )
    assert match, "нет раздела «{}»".format(heading)
    return match.group(1)


def test_skill_maps_every_screen_title_to_its_quest_code(skill, content_root):
    """Игра зовёт квест по названию — код и ручку модель находит здесь."""
    scene = next(item for item in content.load_acts(content_root) if item.act == 1)
    table = section(skill, "Квесты")
    for quest_id, title in zip(scene.quests, scene.quest_titles):
        row = next(
            (line for line in table.splitlines() if "`{}`".format(quest_id) in line),
            None,
        )
        assert row is not None, quest_id
        assert "«{}»".format(title) in row, row
        handle = "ack" if acts.quest_kind(1, quest_id) == acts.KIND_ACK else "check"
        assert "`{} 1 {}`".format(handle, quest_id) in row, row


def test_isolated_machine_phrase_is_gone_everywhere():
    """Решение оператора 2026-10-08: фраза убирается отовсюду."""
    hits = [
        path.relative_to(ROOT).as_posix()
        for path in sorted(PLUGIN.rglob("*"))
        if path.is_file() and path.suffix in TEXT_SUFFIXES
        and "изолированн" in path.read_text(encoding="utf-8").lower()
    ]
    assert hits == []


def test_first_quest_is_the_folder_and_one_phrase_about_the_mode(skill):
    """Три режима, Shift+Tab и памятка проекта — материал следующего акта."""
    quest = section(skill, "Квест 01")
    for gone in ("Shift+Tab", "CLAUDE.md", "`.claude`", "режим плана", "обычный"):
        assert gone not in quest, gone
    assert "режиме без вопросов" in quest
    assert "Так делают только в папке проекта" in quest


def test_launch_command_is_said_only_to_those_without_the_mode(skill):
    assert skill.count("--dangerously-skip-permissions") == 1
    quest = section(skill, "Квест 01")
    before, after = quest.split("--dangerously-skip-permissions")
    # Команда стоит под условием «режим другой», а не в общем тексте.
    condition = before.rfind("Только если")
    assert condition != -1, "команда запуска обязана стоять под условием"
    assert "\n## " not in before[condition:]


def test_person_does_not_look_for_the_mode_line(skill):
    """Второй прогон 2026-10-08: строку внизу окна новичок не нашёл.

    Режим называет игра — Claude Code сообщает его хукам, контракт печатает.
    Действия «найди и прочитай английскую строку» в квесте нет.
    """
    quest = " ".join(section(skill, "Квест 01").split())
    for gone in ("bypass permissions", "низ окна", "прочитает тебе", "Прочитал её",
                 "Строку не нашёл"):
        assert gone not in quest, gone
    assert "Режим Claude Code" in quest and "контракт" in quest
    # Три исхода: игра знает «без вопросов», знает другой, не знает.
    for case in ("без вопросов.", "другой", "неизвестен"):
        assert "«Режим Claude Code: {}".format(case) in quest or (
            "«Режим Claude Code игре {}".format(case) in quest
        ), case


def test_mode_is_not_claimed_when_the_game_does_not_know_it(skill):
    quest = section(skill, "Квест 01")
    unknown = quest[quest.index("игре неизвестен"):]
    unknown = unknown[:unknown.index("**4. Проверка")]
    assert "не утверждай" in unknown
    assert "Ты работаешь в режиме без вопросов" not in unknown


def test_mistake_is_explained_calmly(skill):
    """«Ошибку Claude тоже сделает без спроса» пугало и не говорило, что
    сломается. Смысл: ошибка возможна, поэтому у проекта своя папка, а
    сохранение вернёт всё назад. «Ошибка останется внутри папки» не
    обещаем: сторож ловит только удаление мимо папки, не любую правку."""
    quest = " ".join(section(skill, "Квест 01").split())
    assert "Ошибку Claude тоже сделает без спроса" not in quest
    assert "Ошибка останется внутри папки проекта" not in quest
    assert "Поэтому у проекта своя папка: в ней нет ничего, кроме проекта." in quest
    assert "сохранение вернёт всё назад" in quest


def test_claude_opens_the_first_version_himself(skill):
    """«Открой файл index.html» — новичок не знает, как дойти до папки."""
    quest = section(skill, "Квест 03")
    flat = " ".join(quest.split())
    assert "открой результат сам" in flat
    # Три системы: Linux, macOS и Linux внутри Windows.
    for opener in ("`xdg-open", "`open ", "`wslview", "`explorer.exe", "`cmd.exe /c start"):
        assert opener in quest, opener
    # Порядок в Linux внутри Windows — тот же, что у движка (cli._openers).
    assert quest.index("`wslview") < quest.index("`explorer.exe") < quest.index(
        "`cmd.exe /c start")
    # Сначала открывает Claude, запасной путь словами — только потом.
    opened = flat.index("открой результат сам")
    fallback = flat.index("Не открылось")
    asked = flat.index("что он увидел")
    assert opened < fallback < asked
    assert "покажи, как открыть" not in flat


def test_first_request_has_a_worked_example(skill):
    """«Как я пойму, что готово?» без примера новичок пропустил."""
    quest = " ".join(section(skill, "Квест 03").split())
    question = quest.index("Как я пойму, что готово?")
    example = quest.index("> Пример.")
    assert question < example
    assert "Готово, когда" in quest[example:]


def test_passwords_are_not_said_on_the_first_evening(skill):
    """`.env` в `.gitignore` модель кладёт молча; слова человеку — без него."""
    quest = section(skill, "Квест 04")
    said = "\n".join(
        line for line in quest.splitlines() if line.startswith(">")
    )
    for word in ("парол", ".env", "ключ", "интернет"):
        assert word not in said, word
    assert "Новых слов два: коммит и git" in quest
    assert "`.gitignore`" in quest and "молча" in quest
    assert "копируют в интернет" not in quest


def test_folder_is_named_inside_the_first_quest(skill):
    """Запись папки — действие квеста, а не шаг до входа в акт."""
    before = section(skill, "Перед началом")
    assert "project path" not in before
    quest = section(skill, "Квест 01")
    assert quest.index("project path") < quest.index("check 1 01-folder")


def test_first_request_is_checked_after_the_person_looked(skill):
    quest = section(skill, "Квест 03")
    asked = quest.index("что он увидел")
    seen = quest.index("seen 1 03-first-request")
    check = quest.index("check 1 03-first-request")
    assert asked < seen < check


def test_objection_is_only_for_quests_where_something_is_formulated(skill):
    how = section(skill, "Как вести каждый квест")
    assert "только в квестах 02 и 03" in how


def test_skill_has_no_dead_steps(skill):
    """Вопрос про Книгу до первого ранга игра не печатает — и шага про него нет."""
    before = " ".join(section(skill, "Перед началом").split())
    assert "book" not in before and "Книг" not in before
    # Катсцена описана там, где её печатает игра: до списка квестов.
    assert before.index("две фразы") < before.index("список квестов")


def test_rewind_menu_is_named_as_the_person_will_see_it(skill):
    """Меню отката английское: подписи — из документации Claude Code."""
    quest = section(skill, "Квест 05")
    for label in ("Restore code and conversation", "Restore conversation",
                  "Restore code", "Never mind"):
        assert "«{}»".format(label) in quest, label
    assert "`/rewind`" in quest


def test_rewind_menu_says_which_keys_to_press(skill):
    """Замер живого меню 2026-10-09 (Claude Code 2.1.295): курсор списка стоит
    на строке «(current)», а не на запросе; во втором окне выбран первый пункт,
    «Restore code» — третий. Проверено руками: вверх до запроса, Enter, два раза
    вниз, Enter — файл вернулся. Без клавиш новичок застрянет."""
    quest = " ".join(section(skill, "Квест 05").split())
    assert "Стрелкой вверх" in quest
    assert "стрелку вниз два раза" in quest
    assert "Interrupted" in quest

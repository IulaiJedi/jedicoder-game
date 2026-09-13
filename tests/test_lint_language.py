"""Правила простого языка в линтере — веха «Простой язык» (спека #64, тикет #65).

Пять правил, каждое своим прибором в `scripts/lint_content.py`:

- (а) фраза длиннее SENTENCE_MAX слов — `long_sentences`;
- (б) запрещённые образы метафоры — `forbidden_images`;
- (в) катсцена длиннее CUTSCENE_SENTENCES_MAX фраз — `sentence_count`;
- (г) слова, которым рано звучать до первого ранга — `early_words_problems`;
- (д) карточка термина длиннее CARD_LINES_MAX строк — `card_line_count`.

Функции чистые и тестируются на строках. Сборка держится списком `LEGACY`:
единицы, ещё не переписанные под правила, перечислены явно, и снимок здесь
прибивает, что список только убывает. Сам документ правил —
`plugin/content/ru/language.md`; таблица замен и список образов в нём
сверяются с константами линтера, чтобы автор и прибор читали одно и то же.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lint_content  # noqa: E402

from test_lint_content import (  # noqa: E402
    RECIPE, RULE, TERM, act_text, build, default_acts, lint_synth,
    skills_with, term_with_body,
)

ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_DOC = ROOT / "plugin" / "content" / "ru" / "language.md"
BEHAVIOR_DOC = ROOT / "plugin" / "content" / "ru" / "behavior.md"


def words(count):
    """Фраза ровно из count слов, без точки в конце."""
    return " ".join("слово{}".format(i) for i in range(count))


# --- (а) Фраза до SENTENCE_MAX слов. ----------------------------------

def test_sentence_limit_is_fifteen():
    assert lint_content.SENTENCE_MAX == 15


def test_sentence_at_limit_passes():
    assert lint_content.long_sentences(words(15) + ".") == []


def test_sentence_over_limit_detected():
    text = words(16) + "."
    assert lint_content.long_sentences(text) == [text]


def test_backticks_do_not_count_as_words():
    """Пути и команды в обратных кавычках — не слова: `python3 -m pytest -q`
    добавляет ноль к счёту, а точки внутри не режут фразу."""
    text = words(14) + " `python3 -m pytest -q --tb=short` `a.b.c` ещё."
    assert lint_content.long_sentences(text) == []


def test_ellipsis_ends_a_sentence():
    text = words(10) + "… " + words(10) + "."
    assert lint_content.long_sentences(text) == []


@pytest.mark.parametrize("stop", [".", "!", "?"])
def test_each_stop_ends_a_sentence(stop):
    text = words(10) + stop + " " + words(10) + "."
    assert lint_content.long_sentences(text) == []


def test_dashes_and_markup_are_not_words():
    """Тире, звёздочки жирного и служебные комментарии слов не добавляют."""
    text = "**" + words(13) + "** — " + words(2) + ". <!-- lint:novelty-ok: x -->"
    assert lint_content.long_sentences(text) == []


def test_list_items_and_headings_are_separate_phrases():
    """Пункт списка без точки — своя фраза, а заголовок — не фраза вовсе."""
    text = (
        "# " + words(20) + "\n\n"
        "- " + words(10) + "\n"
        "- " + words(10) + "\n"
    )
    assert lint_content.long_sentences(text) == []


def test_dash_list_items_are_separate_phrases():
    """Список через тире — тоже список: пункты не склеиваются в одну фразу."""
    text = "Что бывает:\n— " + words(10) + "\n— " + words(10) + "\n"
    assert lint_content.long_sentences(text) == []


def test_fenced_and_indented_code_is_not_text():
    text = (
        "Набери команду.\n\n```\n" + words(20) + "\n```\n\n"
        "    " + words(20) + "\n\nГотово.\n"
    )
    assert lint_content.long_sentences(text) == []
    assert lint_content.sentence_count(text) == 2


def test_long_phrase_in_cutscene_detected(tmp_path):
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, body=words(16) + ". " + "Коротко. " * 30))
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
        act_files=broken,
    )
    problems = lint_synth(tmp_path, legacy={})
    assert any(
        "катсцена act1-poisk-boli" in p and "16 слов" in p for p in problems
    )


def test_long_phrase_in_recipe_detected(tmp_path):
    long_recipe = RECIPE.format(recipe="ppp").replace(
        "Тело рецепта.", words(16) + "."
    )
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", long_recipe)],
    )
    problems = lint_synth(tmp_path, legacy={})
    assert any("рецепт ppp" in p and "16 слов" in p for p in problems)


def test_long_phrase_in_skill_quote_detected(tmp_path):
    content_dir = tmp_path / "content"
    skills_dir = skills_with(
        tmp_path / "skills",
        [("act1", "# Скилл\n\n> " + words(16) + ".\n")],
    )
    build(
        content_dir,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(content_dir, skills_root=skills_dir, legacy={})
    assert any("врезка act1" in p and "16 слов" in p for p in problems)


# --- (б) Запрещённые образы. --------------------------------------------

@pytest.mark.parametrize("text", [
    "Меч остаётся рукоятью.",
    "первым дают не меч",
    "Иначе Сила пишет то, что ей вздумается.",
    "Прогони Ситх-ревьюера.",
    "Очко Тёмной стороны.",
    "тёмная сторона растёт",
    "светлая сторона",
    "джедай не спешит",
])
def test_forbidden_image_detected(text):
    assert lint_content.forbidden_images(text) != []


@pytest.mark.parametrize("text", [
    "мечта о продукте",
    "замечать ошибки",
    "сила привычки",
    "суперсила падавана",
    "Кодекс Джедайкодера",
    "тёмная тема редактора",
])
def test_similar_words_are_not_images(text):
    assert lint_content.forbidden_images(text) == []


def test_image_case_is_matched_by_character_class():
    """Регистр кириллицы задаётся классом символов, а не lower(): складывание
    регистра кириллицы зависит от локали, а локаль — лотерея."""
    assert lint_content.forbidden_images("Меч.") == ["Меч"]
    assert lint_content.forbidden_images("меч.") == ["меч"]


def test_image_in_cutscene_detected(tmp_path):
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, body="Первым дают не меч. " * 15))
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
        act_files=broken,
    )
    problems = lint_synth(tmp_path, legacy={})
    assert any(
        "катсцена act1-poisk-boli" in p and "образ" in p and "меч" in p
        for p in problems
    )


def test_image_in_whole_skill_file_detected(tmp_path):
    """Образ ловится во всём SKILL.md, а не только во врезках: модель
    пересказывает и обычный текст скилла."""
    content_dir = tmp_path / "content"
    skills_dir = skills_with(
        tmp_path / "skills",
        [("plan", "# Скилл\n\nИначе Сила пишет что вздумается.\n")],
    )
    build(
        content_dir,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(content_dir, skills_root=skills_dir, legacy={})
    assert any("SKILL plan" in p and "Сила" in p for p in problems)


def test_language_ok_marker_silences_one_rule(tmp_path):
    """Маркер по образцу lint:novelty-ok: декларация с причиной, на файл, на
    одно правило. Соседнее правило он не глушит."""
    content_dir = tmp_path / "content"
    skills_dir = skills_with(
        tmp_path / "skills",
        [("plan",
          "<!-- lint:language-ok: images — цитата из эпиграфа, оператор одобрил -->\n"
          "# Скилл\n\nИначе Сила пишет что вздумается.\n\n> " + words(16) + ".\n")],
    )
    build(
        content_dir,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(content_dir, skills_root=skills_dir, legacy={})
    assert not any("Сила" in p for p in problems)
    assert any("врезка plan" in p and "16 слов" in p for p in problems)


def test_remark_marker_lives_in_frontmatter(tmp_path):
    """Реплике комментарий в теле запрещён — маркер ставится строкой
    фронтматтера, и линтер читает его оттуда."""
    from test_lint_content import default_remarks

    remarks = [
        (name, text) for name, text in default_remarks() if name != "dark_side.md"
    ]
    remarks.append((
        "dark_side.md",
        "---\nevent: dark_side\n"
        "# <!-- lint:language-ok: images — реплика про старое имя счётчика -->\n"
        "---\n\nПервый вариант.\n\nСила подвела меня.\n\nТретий вариант.\n",
    ))
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
        remark_files=remarks,
    )
    problems = lint_synth(tmp_path, legacy={})
    assert not any("реплика dark_side" in p and "Сила" in p for p in problems)


def test_unknown_language_ok_rule_is_a_problem(tmp_path):
    content_dir = tmp_path / "content"
    skills_dir = skills_with(
        tmp_path / "skills",
        [("plan", "<!-- lint:language-ok: nonsense — нет такого -->\n# Скилл\n")],
    )
    build(
        content_dir,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(content_dir, skills_root=skills_dir, legacy={})
    assert any("language-ok" in p and "nonsense" in p for p in problems)


# --- (в) Катсцена — две фразы. -----------------------------------------

def test_cutscene_limit_is_two():
    assert lint_content.CUTSCENE_SENTENCES_MAX == 2


def test_sentence_count():
    assert lint_content.sentence_count("Раз. Два! Три? Четыре… Пять") == 5
    assert lint_content.sentence_count("# Заголовок\n\nОдна. Две.\n") == 2
    assert lint_content.sentence_count("") == 0


def test_cutscene_of_two_sentences_is_clean(tmp_path):
    two = ("Здесь мы ищем чужую боль, за которую люди готовы платить "
           "временем, вниманием или деньгами. Без такой боли строить нечего, "
           "поэтому собственная идея подождёт до конца первого акта игры.")
    fixed = list(default_acts())
    # Две фразы; тело короче ACT_BODY_MIN — это другой кейс с другим словом.
    fixed[0] = (fixed[0][0], act_text(1, body=two))
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
        act_files=fixed,
    )
    problems = lint_synth(tmp_path, legacy={})
    assert not any("фраз" in p and "act1-poisk-boli" in p for p in problems)


def test_cutscene_of_three_sentences_detected(tmp_path):
    three = "Коротко и ясно про боль. " * 3 + "х" * lint_content.ACT_BODY_MIN
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, body=three))
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
        act_files=broken,
    )
    problems = lint_synth(tmp_path, legacy={})
    assert any(
        "катсцена act1-poisk-boli" in p and "4 фраз" in p for p in problems
    )


# --- (г) До первого ранга не звучат Книга, бот, привязка, клуб… ---------

def test_first_rank_position_is_act_one():
    assert lint_content.FIRST_RANK_POSITION == 1


@pytest.mark.parametrize("text", [
    "Очко Тёмной стороны",
    "первый артефакт игры",
    "возьми Свиток",
    "открой Книгу",
    "в клубе",
    "бот потока ждёт",
    "Бот потока выдаст ключ.",
    "ключ привязки",
])
def test_early_word_detected(text):
    assert lint_content.early_words(text) != []


@pytest.mark.parametrize("text", [
    "книжка с рецептами",
    "Telegram-бот для бабушки",
    "клубника",
    "штрафы растут",
])
def test_similar_words_are_not_early(text):
    assert lint_content.early_words(text) == []


def test_early_words_problems_respect_position():
    units = [
        ("узел start", 0, "Открой Книгу."),
        ("SKILL акта 1", 1, "Возьми Свиток."),
        ("катсцена act2", 2, "Возьми Свиток."),
    ]
    problems = lint_content.early_words_problems(units)
    assert len(problems) == 2
    assert any("узел start" in p and "Книгу" in p for p in problems)
    assert any("SKILL акта 1" in p and "Свиток" in p for p in problems)
    assert not any("act2" in p for p in problems)


def test_early_word_in_act1_term_card_detected(tmp_path):
    body = "**ххх** — очко Тёмной стороны.\n\n**Зачем нужно:** чтобы было.\n"
    term = term_with_body("xxx", body).replace("act: 2", "act: 1")
    build(
        tmp_path,
        terms=[("a.md", term)],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path, legacy={})
    assert any("карточка xxx" in p and "рано" in p for p in problems)


def test_early_word_in_act2_term_card_is_fine(tmp_path):
    body = "**ххх** — очко Тёмной стороны.\n\n**Зачем нужно:** чтобы было.\n"
    build(
        tmp_path,
        terms=[("a.md", term_with_body("xxx", body))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path, legacy={})
    assert not any("карточка xxx" in p and "рано" in p for p in problems)


# --- (д) Карточка термина — две строки после заголовка. -----------------

def test_card_limit_is_two_lines():
    assert lint_content.CARD_LINES_MAX == 2


def test_example_limit_is_the_sentence_limit():
    """Загрузчик меряет example тем же числом, что линтер — фразу."""
    from jedicoder import content
    assert content.EXAMPLE_WORDS_MAX == lint_content.SENTENCE_MAX


def test_card_line_count():
    assert lint_content.card_line_count("✦ Новое слово: X (+5 XP)\nчто\nпример") == 2
    assert lint_content.card_line_count("✦ Новое слово: X (+5 XP)\nчто\nзачем\nпроверь") == 3
    assert lint_content.card_line_count("✦ Новое слово: X (+5 XP)") == 0


def test_long_card_detected():
    """Правило меряет итоговую строку карточки, а не файл: рендер без
    `example` печатает определение, «зачем» и «проверь себя» — три строки,
    и card_line_count их считает. Термин поставки без примера не грузится
    вовсе (test_term_without_example_is_rejected_by_the_loader), поэтому
    Term здесь собран руками — как в сохранении от плагина новее."""
    from jedicoder import content as content_mod

    render_card = lint_content._load_render_card()
    term = content_mod.Term(
        term="xxx", title="xxx", aliases=("xxx",), act=2, category="git",
        xp=5, body=(
            "**xxx** — определение.\n\n**Зачем нужно:** чтобы было.\n\n"
            "**Проверь, что понял:** понял?\n"
        ), path=Path("/dev/null"),
    )
    card = "\n\n".join(render_card(term).split("\n"))
    assert lint_content.card_line_count(card) == 3
    assert not lint_content.card_has_example(card)


def test_two_line_card_is_clean(tmp_path):
    body = "**xxx** — определение.\n\n**Зачем нужно:** чтобы было.\n"
    text = term_with_body("xxx", body).replace(
        "xp: 5\n", "xp: 5\nexample: Пример из жизни.\n"
    )
    build(
        tmp_path,
        terms=[("a.md", text)],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path, legacy={})
    assert not any("карточка xxx" in p and "строк" in p for p in problems)


def test_term_without_example_is_rejected_by_the_loader(tmp_path):
    """Нет `example` — термин не грузится вовсе: поле обязательное с #72.

    Линтер называет причину словом example, как и правило card до этого:
    термин без примера не проскочит как чистый ни одной дверью.
    """
    body = "**ххх** — определение.\n\n**Зачем нужно:** чтобы было.\n"
    build(
        tmp_path,
        terms=[("a.md", term_with_body("xxx", body, example=None))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path, legacy={})
    assert any("a.md" in p and "example" in p for p in problems)


def test_term_with_example_renders_clean_card(tmp_path):
    """Определение и пример — карточка в две строки, ни одной находки."""
    body = (
        "**xxx** — сохранённое состояние, к которому можно вернуться.\n\n"
        "**Зачем нужно:** чтобы было.\n\n**Проверь, что понял:** понял?\n"
    )
    text = term_with_body("xxx", body).replace(
        "xp: 5\n", "xp: 5\nexample: Сохранил игру перед боссом — можно вернуться.\n"
    )
    build(
        tmp_path,
        terms=[("a.md", text)],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path, legacy={})
    assert not any("карточка xxx" in p for p in problems)


# --- LEGACY: единицы, ещё не переписанные. -------------------------------

def test_legacy_unit_is_not_checked(tmp_path):
    body = (
        "**ххх** — " + words(16) + ".\n\n**Зачем нужно:** чтобы было.\n\n"
        "**Проверь, что понял:** понял?\n"
    )
    build(
        tmp_path,
        terms=[("a.md", term_with_body("xxx", body))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    legacy = {"карточка xxx": ("sentence", "card")}
    problems = lint_synth(tmp_path, legacy=legacy)
    assert not any("карточка xxx" in p for p in problems)


def test_legacy_covers_only_named_rules(tmp_path):
    body = (
        "**ххх** — " + words(15) + ".\n\n**Зачем нужно:** чтобы было.\n\n"
        "**Проверь, что понял:** понял?\n"
    )
    build(
        tmp_path,
        terms=[("a.md", term_with_body("xxx", body))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path, legacy={"карточка xxx": ("card",)})
    assert any("карточка xxx" in p and "16 слов" in p for p in problems)
    assert not any("карточка xxx" in p and "строк" in p for p in problems)


def test_legacy_rules_are_known():
    for label, rules in lint_content.LEGACY.items():
        for rule in rules:
            assert rule in lint_content.LANGUAGE_RULES, (label, rule)


def test_legacy_entries_are_still_needed(content_root):
    """Единица, которую уже переписали, из списка убирается, а не висит:
    иначе список перестаёт говорить, сколько работы осталось."""
    found = set(
        (label, rule)
        for label, rule, _ in lint_content.language_findings(content_root)
    )
    stale = [
        (label, rule)
        for label, rules in sorted(lint_content.LEGACY.items())
        for rule in rules
        if (label, rule) not in found
    ]
    assert stale == []


# Список исключений опустел тикетом #72: каждая единица поставки меряется
# всеми пятью правилами. Снимка больше нет — добавить в LEGACY что-либо
# значит вернуть исключение, и этот тест падает на первой же записи.
def test_legacy_is_empty():
    assert lint_content.LEGACY == {}


def test_real_content_has_no_language_findings(content_root):
    """Поставка чиста без единого исключения: находок правил языка нет."""
    assert lint_content.language_findings(content_root) == []


# --- (е) Приём зовётся с приставкой плагина: /jedicoder:<имя>. -----------
#
# Голого `/brainstorm` в Claude Code нет — команды плагина живут только как
# `/jedicoder:<имя>`; новичок в прогоне 2026-09-13 набрал `/brainstorm` и не
# нашёл. Имена берутся из реестра приёмов плюс `magistr`: седьмой приём
# попадёт под правило сам.

def test_prefix_rule_is_known():
    assert lint_content.RULE_PREFIX in lint_content.LANGUAGE_RULES


@pytest.mark.parametrize("name", list(lint_content.PREFIXED_COMMANDS))
def test_bare_command_detected(name):
    assert lint_content.bare_commands("Позови /{} и жди.".format(name)) == ["/" + name]


def test_prefixed_command_passes():
    text = "Позови `/jedicoder:brainstorm` или /jedicoder:goal и жди."
    assert lint_content.bare_commands(text) == []


def test_bare_command_in_code_span_detected():
    """Обратные кавычки не спасают: падаван копирует команду из них."""
    assert lint_content.bare_commands("Набери `/plan` сам.") == ["/plan"]


def test_urls_and_paths_are_not_commands():
    text = (
        "Адрес https://домен/deploy и файл docs/jedicoder/plan.md, "
        "ручка `artifact plan`, квест `01-deploy`, Telegram-команда /start."
    )
    assert lint_content.bare_commands(text) == []


def test_bare_command_in_rule_detected(tmp_path):
    rule = RULE.format(rule="rrr").replace("Тело правила.", "Позови /brainstorm.")
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", rule)],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path, legacy={})
    assert any("правило rrr" in p and "/brainstorm" in p and "jedicoder:" in p
               for p in problems)


def test_bare_command_in_skill_detected(tmp_path):
    content_dir = tmp_path / "content"
    skills_dir = skills_with(
        tmp_path / "skills", [("act1", "# Скилл\n\nПозови /plan.\n")],
    )
    build(
        content_dir,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(content_dir, skills_root=skills_dir, legacy={})
    assert any("SKILL act1" in p and "/plan" in p for p in problems)


def test_language_doc_names_the_prefix():
    assert "/jedicoder:" in LANGUAGE_DOC.read_text(encoding="utf-8")


# --- Памятка и дорожная карта меряются теми же правилами. ------------------

def test_instructions_and_roadmaps_are_language_units(content_root):
    """Инструкции памятки и карты читаются вне игры, и линтер их меряет:
    длина фразы, образы, приставка. Слова до ранга — нет: «клуб» на карте
    законен, это финал."""
    units = lint_content._language_units(
        content_root, lint_content.DEFAULT_SKILLS_ROOT,
        lint_content.DEFAULT_COMMANDS_ROOT, [], [], [], [], [], [],
        lint_content.content.load_instructions(content_root),
        lint_content.content.load_roadmaps(content_root),
    )
    labels = {label: rules for label, _, _, _, rules in units}
    assert "инструкция plan" in labels and "карта founder" in labels
    for label in ("инструкция plan", "карта founder"):
        assert lint_content.RULE_SENTENCE in labels[label]
        assert lint_content.RULE_EARLY not in labels[label]


def test_long_phrase_in_instruction_detected(tmp_path):
    instruction = (
        "---\nartifact: plan\ntitle: Как\nsummary: Коротко.\n---\n"
        "## Что это\n\n" + words(16) + ".\n"
    )
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
        instruction_files=[("plan.md", instruction)],
    )
    problems = lint_synth(tmp_path, legacy={})
    assert any("инструкция plan" in p and "16 слов" in p for p in problems)


# --- Документ правил и контракт. ------------------------------------------

def test_language_doc_exists_and_is_short():
    text = LANGUAGE_DOC.read_text(encoding="utf-8")
    assert len(text.split()) <= 600, "документ читается за минуту"


def test_language_doc_lists_every_forbidden_image():
    text = LANGUAGE_DOC.read_text(encoding="utf-8")
    for name, _ in lint_content.FORBIDDEN_IMAGES:
        assert name in text, name


def test_language_doc_lists_every_early_word():
    text = LANGUAGE_DOC.read_text(encoding="utf-8")
    for name, _ in lint_content.EARLY_WORDS:
        assert name in text, name


@pytest.mark.parametrize("old,new", [
    ("Тёмная сторона", "штрафы"),
    ("артефакт", "приём"),
    ("Свиток", "памятка"),
])
def test_language_doc_has_replacement_table(old, new):
    text = LANGUAGE_DOC.read_text(encoding="utf-8")
    row = [line for line in text.splitlines()
           if line.startswith("|") and old in line and new in line]
    assert row, "нет строки таблицы замен {} → {}".format(old, new)


def test_language_doc_states_the_limits():
    text = LANGUAGE_DOC.read_text(encoding="utf-8")
    assert "lint:language-ok" in text
    assert "LEGACY" in text
    assert str(lint_content.SENTENCE_MAX) in text


def test_language_doc_is_not_loaded_as_content(content_root):
    """language.md лежит в корне content/ru и ни одним загрузчиком не
    читается: термином, правилом или рецептом он стать не может."""
    from jedicoder import content as content_mod

    names = set()
    for loader in (
        content_mod.load_terms, content_mod.load_rules, content_mod.load_recipes,
        content_mod.load_acts, content_mod.load_remarks,
        content_mod.load_instructions, content_mod.load_roadmaps,
        content_mod.load_onboarding,
    ):
        names.update(item.path.name for item in loader(content_root))
    assert "language.md" not in names


def test_behavior_refers_to_language_doc():
    assert "language.md" in BEHAVIOR_DOC.read_text(encoding="utf-8")


def test_rule_seven_is_one_question_with_an_example():
    """Правило 7 переписано под новый размер возражения: один вопрос в
    две-три строки с примером ответа, без «Стоп» (ADR-0014)."""
    text = BEHAVIOR_DOC.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("7. "))
    end = next(i for i, line in enumerate(lines) if line.startswith("8. "))
    rule = "\n".join(lines[start:end])
    # Окрик — «Стоп.» или «Стоп!» в примере; упоминание слова в запрете
    # («без «Стоп»») — не окрик, а сам запрет.
    assert not re.search(r"Стоп[.!]", rule)
    assert "пример" in rule
    assert "две-три строки" in rule

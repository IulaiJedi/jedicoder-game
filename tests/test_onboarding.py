"""Дерево Акта 0 под линтером.

Проверяется **прибор**, а не поставка: каждый тест портит синтетическое
дерево во временной папке и требует, чтобы линтер покраснел. Поставку
прибором меряет `test_shipped_onboarding_is_clean` — один тест на всё,
потому что зелёная поставка ничего не доказывает про прибор. Отдельно от
него стоят именные стражи состава (раздел «Поставка: один вопрос»):
линтер меряет форму дерева, а форма ничего не говорит о том, какие шаги в
нём стоят и где.

Почему это вообще есть. Узел без выхода и кнопка в несуществующий узел —
тупик, из которого человек выбирается закрытием бота. Найти такое на живом
человеке нельзя: он второй раз не придёт. Значит либо обход дерева здесь,
либо не находится вовсе.

Строитель дерева берётся из `test_lint_content`, а не пишется свой: два
независимых строителя валидного контента разъедутся молча, и тогда красный
тест здесь будет означать «строители разошлись», а не «прибор работает».
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from test_lint_content import build, lint_synth

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "scripts" / "export_onboarding.py"

# Третья дверь Акта 0 (D-06): та же инструкция в markdown. Единственная из
# трёх производных, которая живёт в этом же репозитории, — и единственная,
# чью свежесть можно держать тестом, а не приёмкой.
INSTALL_MD = ROOT / "docs" / "act0-install.md"

# Второй репозиторий: там живут обе производные текста Акта 0 — модуль бота и
# модуль сайта. Путь берётся из окружения, потому что чужой репозиторий лежит
# рядом только на машине автора, а тест обязан быть зелёным и там, где его нет.
SITE_ROOT_ENV = "JEDICODER_SITE_ROOT"
SITE_ROOT_DEFAULT = Path.home() / "projects" / "jedicoder_Appstore"

# Потребители вывода генератора в TypeScript. Оба — байт в байт один и тот же
# файл: форма модуля общая, разные у них только адреса.
TS_CONSUMERS = (
    Path("jedicoder_academy_bot") / "src" / "act0.generated.ts",
    Path("src") / "data" / "act0.ts",
)

sys.path.insert(0, str(ROOT / "scripts"))

import lint_content  # noqa: E402

NODE = (
    "---\n"
    "node: {node}\n"
    "title: {node}\n"
    "order: {order}\n"
    "section: install\n"
    "{extra}"
    "---\n"
    "{body}\n"
)


def node_text(node, order, options=(), option_titles=None, body="Тело узла."):
    extra = ""
    if options:
        titles = (
            ['"кнопка {}"'.format(target) for target in options]
            if option_titles is None
            else option_titles
        )
        extra += "options: [{}]\n".format(", ".join(options))
        extra += "option_titles: [{}]\n".format(", ".join(titles))
    return NODE.format(node=node, order=order, extra=extra, body=body)


def onboarding(root, nodes):
    """Записать дерево в root/onboarding. nodes — пары (имя файла, текст)."""
    directory = root / "onboarding"
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in nodes:
        (directory / name).write_text(text, encoding="utf-8")
    return root


def good_tree():
    """start → middle → done. Опора для остальных тестов."""
    return [
        ("10.md", node_text("start", 10, options=["middle"])),
        ("20.md", node_text("middle", 20, options=["done"])),
        ("30.md", node_text("done", 30)),
    ]


def synth(tmp_path, nodes):
    build(tmp_path)
    onboarding(tmp_path, nodes)
    return lint_synth(tmp_path)


# --- Опора и поставка ------------------------------------------------

def test_good_tree_is_clean(tmp_path):
    assert synth(tmp_path, good_tree()) == []


def test_no_onboarding_directory_is_not_a_problem(tmp_path):
    """Синтетическое дерево без Акта 0 линтер не роняет.

    Иначе каждый тест правил 1–3 пришлось бы обкладывать онбордингом, и
    прибор начал бы требовать контента, которого у него не просили.
    """
    build(tmp_path)
    assert lint_synth(tmp_path) == []


def test_shipped_onboarding_is_clean(content_root):
    from jedicoder import content

    items = content.load_onboarding(content_root)
    assert items, "поставка потеряла Акт 0"
    assert lint_content._onboarding_problems(items) == []


# --- Поставка: где играть спрашивают один раз -------------------------
#
# Именные стражи того же рода, что ACT0_TERMS в test_content.py: линтер
# меряет форму дерева, а не то, какие шаги в нём стоят и в каком порядке.
# Миров, в которых запускают игру, три — терминал, приложение Claude и
# Голокрон, — и ни один из них человеку не предлагают дважды.
#
# Вопросов при этом два, и они разные. Голокрон ставит машину сам, поэтому
# про него спрашивают в начале, сразу после системы: предложить его после
# установки значило бы сначала заставить человека сделать руками ровно то,
# за чем он бы и скачал приложение. Терминал и приложение Claude — вопрос
# про запуск, и он стоит в конце, когда игра уже стоит.
#
# Чего здесь больше нет: Голокрона отдельным шагом после первого запуска.
# Тогда про способ игры спрашивали дважды об одном и том же — сначала
# «терминал или приложение», потом «а вот ещё одно окно под ту же игру».

WHERE_NODE = "where-to-play"
GOLOKRON_NODE = "golokron"
GOLOKRON_URL = "https://jedicoder.store/golokron"
# Два шага мимо предупреждения SmartScreen — то, что человек ищет глазами в
# момент испуга. Подписи кнопок Windows приводятся дословно, в «ёлочках».
SMARTSCREEN_STEPS = ("«Подробнее»", "«Выполнить в любом случае»")
# Три мира, в которых запускают игру. Порядок — тот, в каком их предлагают:
# сначала Голокрон в начале пути, потом терминал и приложение Claude в конце.
WORLDS = (GOLOKRON_NODE, "project-folder", "app-project")
# Две двери последнего вопроса, в порядке кнопок: первым стоит тот мир, в
# котором человек уже находится, — терминал (он начинается с папки продукта).
HAND_WORLDS = ("project-folder", "app-project")
INSTALL_NODE = "plugin-install"
# Разбор «такой команды нет» — общий для всех трёх миров: первый запуск игры
# стоит теперь в каждом из них.
NO_COMMAND_NODE = "no-command"
LINK_SECTION = "link"
TROUBLE_SECTION = "trouble"


# Узлы, на которых предлагают приложение. Их два, потому что развилка стоит
# сразу после определения системы, а формулировка у Windows и Linux разная:
# на Windows приложение снимает ещё и установку Linux внутри Windows.
FORK_NODES = ("windows", "linux")
MACOS_NODE = "macos"
# Шаги установки, которых на ветке приложения быть не должно: установка
# Claude Code и установка самой игры. Их делает Подготовка внутри Голокрона.
INSTALL_STEPS = ("install-linux", "plugin-install")


def _flow_edges(by_node, name):
    """Переходы узла по потоку: разбор поломок не в счёт — это дорога назад."""
    return [
        target
        for target in by_node[name].options
        if by_node[target].section != TROUBLE_SECTION
    ]


def _steps_to(by_node, start, finish):
    """Число шагов от start до finish по потоку; None — не дойти.

    Обход в ширину, потому что мерить надо кратчайший путь: длинная дорога
    в обход ничего не говорит о том, сколько сообщений прочитает человек.
    """
    seen = {start: 0}
    queue = [start]
    while queue:
        name = queue.pop(0)
        if name == finish:
            return seen[name]
        for target in _flow_edges(by_node, name):
            if target not in seen:
                seen[target] = seen[name] + 1
                queue.append(target)
    return None


def _reach_all(by_node, start):
    """Всё, куда можно попасть из start, включая разбор поломок.

    Отдельно от `_flow_from` нарочно. Ветку мерить надо по потоку, а вот
    «сюда не попасть никогда» — только по всему графу: дорога в чужую дверь
    через разбор поломок остаётся дорогой, и человек по ней ходит.
    """
    seen = set()
    queue = [start]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        queue.extend(by_node[name].options)
    return seen


def shipped_nodes(content_root):
    from jedicoder import content

    return {item.node: item for item in content.load_onboarding(content_root)}


def the_link_node(by_node):
    """Единственный узел раздела link — конец пути, по которому бот выдаёт ключ.

    Уникальность утверждается здесь, а не распаковкой кортежа: второй узел
    раздела обязан упасть с именами обоих, а не с голым ValueError.
    """
    link = [item for item in by_node.values() if item.section == LINK_SECTION]
    assert len(link) == 1, "узлов раздела link не один: {}".format(
        ", ".join(item.node for item in link)
    )
    return link[0]


def test_the_last_question_offers_both_ways_to_launch(content_root):
    """Последний вопрос — где запускать: терминал и приложение Claude.

    Порядок значим: человек читает кнопки сверху вниз, и первым стоит тот
    мир, в котором он уже находится, — терминал.

    Голокрона здесь нет и быть не может. Сюда доходит только тот, кто ставил
    руками, а значит уже отказался от приложения в начале пути; кнопка на
    него здесь читалась бы как «а теперь начни заново».
    """
    by_node = shipped_nodes(content_root)
    assert WHERE_NODE in by_node, "в поставке нет вопроса «где играть»"
    assert by_node[WHERE_NODE].options == HAND_WORLDS


def _flow_from(by_node, start):
    """Узлы, достижимые из двери по потоку: без разбора поломок.

    Разбор поломок возвращает человека в его же мир — это дорога назад, а не
    продолжение ветки; считать его значило бы мерить всё дерево. Больше
    ничего из обхода не изъято: изъятие узла прячет ровно то, что тест и
    ищет, — путь, которым человек попадает не туда.
    """
    seen = set()
    queue = [start]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        for target in _flow_edges(by_node, name):
            queue.append(target)
    return seen


def test_every_world_leads_to_the_key_and_not_to_another_world(content_root):
    """Выбрал дверь — идёшь ею до ключа; в соседнюю можно только через вопрос.

    Прежде обе ветки первого запуска вели в Голокрон, и человек, уже
    выбравший терминал, получал второе предложение сменить мир. Именно это и
    было «спрашивают дважды».
    """
    by_node = shipped_nodes(content_root)
    link = the_link_node(by_node)
    for world in WORLDS:
        assert world in by_node, "в поставке нет двери '{}'".format(world)
        reached = _flow_from(by_node, world)
        assert link.node in reached, "из двери '{}' не дойти до ключа".format(world)
        leaked = sorted((set(WORLDS) & reached) - {world})
        assert not leaked, "из двери '{}' попадаешь в чужую: {}".format(
            world, ", ".join(leaked)
        )


def test_every_world_has_a_way_out_when_the_game_does_not_answer(content_root):
    """В каждой двери есть выход в разбор «такой команды нет».

    Первый запуск игры теперь стоит в каждом из трёх миров, а значит, в
    каждом же и может не найтись команды. Дверь без этого выхода вела бы к
    ключу при нерабочей игре — и человек ушёл бы с ним ни с чем.
    """
    by_node = shipped_nodes(content_root)
    for world in WORLDS:
        branch = _flow_from(by_node, world)
        assert any(NO_COMMAND_NODE in by_node[name].options for name in branch), (
            "из двери '{}' некуда пойти с «такой команды нет»".format(world)
        )


def test_no_path_offers_the_same_world_twice(content_root):
    """Мир предлагают один раз за проход; разбор поломок не в счёт.

    Ветки разбора возвращают человека в его же мир, и это дорога назад, а не
    второй вопрос. Второй вопрос — это когда один и тот же мир попадается на
    кнопке дважды: так было, пока первый запуск в терминале и в приложении
    вёл в Голокрон.

    Развилок про Голокрон две — своя для Windows и своя для Linux, потому
    что на Windows приложение снимает ещё и установку Linux внутри Windows,
    и сказать это надо разными словами. Человек проходит ровно одну из них,
    и меряется это так: если два узла предлагают один и тот же мир, из
    одного не должно быть дороги в другой.
    """
    by_node = shipped_nodes(content_root)
    for world in WORLDS:
        offers = sorted(
            item.node
            for item in by_node.values()
            if world in item.options and item.section != TROUBLE_SECTION
        )
        assert offers, "мир '{}' не предлагают нигде".format(world)
        for name in offers:
            met = sorted((set(offers) - {name}) & _flow_from(by_node, name))
            assert not met, (
                "мир '{}' предлагают дважды на одном пути: '{}', а следом "
                "'{}'".format(world, name, ", ".join(met))
            )


def test_the_app_is_offered_right_after_the_system_and_before_install(content_root):
    """Место первого вопроса: сразу за системой и до любого шага установки.

    В этом весь смысл ранней развилки. Прежде человек на Windows ставил
    руками Linux внутри Windows, Claude Code и игру — ровно то, что
    Подготовка делает сама, — и только в конце узнавал, что приложение
    вообще есть.

    «Сразу за системой» меряется переходом с корня: до развилки нет ни
    одного узла, кроме вопроса о системе. Порядок чтения на сайте и в
    markdown держит поле order.
    """
    by_node = shipped_nodes(content_root)
    root = min(by_node.values(), key=lambda item: item.order)
    for fork in FORK_NODES:
        assert fork in by_node, "в поставке нет развилки '{}'".format(fork)
        assert fork in root.options, (
            "на развилку '{}' не попасть прямо с вопроса о системе".format(fork)
        )
        for step in INSTALL_STEPS:
            assert by_node[fork].order < by_node[step].order, (
                "развилку '{}' читают позже шага '{}'".format(fork, step)
            )


def test_the_launch_question_stands_after_the_game_is_installed(content_root):
    """Место второго вопроса: сразу после установки игры и до обустройства.

    Порядок кнопок в боте задают переходы, порядок чтения на сайте и в
    markdown — поле order; тест держит оба, чтобы человек на сайте не
    прочитал про свою дверь раньше, чем ему предложат выбрать.
    """
    by_node = shipped_nodes(content_root)
    assert by_node[INSTALL_NODE].options == (WHERE_NODE,), (
        "после установки игры спрашивают не про то"
    )
    question = by_node[WHERE_NODE]
    assert by_node[INSTALL_NODE].order < question.order
    for world in HAND_WORLDS:
        assert question.order < by_node[world].order, world
    assert question.order < the_link_node(by_node).order


def test_golokron_step_names_download_page_and_smartscreen_path(content_root):
    """Адрес страницы загрузки и два шага мимо предупреждения — дословно.

    Адрес закреплён спекой сайта раньше, чем появилась страница; подписи
    кнопок Windows — ровно те, что человек увидит на экране. Остальное в
    узле — текст, и его правдивость меряется не тестом, а глазами.
    """
    text = lint_content.visible_text(shipped_nodes(content_root)[GOLOKRON_NODE].body)
    assert GOLOKRON_URL in text
    for label in SMARTSCREEN_STEPS:
        assert label in text, "в узле нет шага {}".format(label)
    assert "Windows" in text


# --- Ранняя развилка: приложение вместо установки руками ---------------
#
# Голокрон ставит Linux внутри Windows, Claude Code и саму игру сам, по
# кнопке и на глазах. Значит предлагать его надо ДО того, как человек
# проделает те же шаги руками, а его ветка обязана быть короткой — иначе
# это не короткий путь, а второй такой же. Мерить это глазами нельзя:
# длина ветки видна только обходом дерева.

def test_the_app_branch_is_shorter_than_installing_by_hand(content_root):
    """От развилки до ключа приложением — короче, чем руками.

    Это и есть смысл ранней развилки: человек на Windows руками проходит
    ровно те шаги, которые Подготовка делает сама. Если ветка приложения не
    короче, развилка не сэкономила ничего и стоит зря.
    """
    by_node = shipped_nodes(content_root)
    link = the_link_node(by_node)
    for fork in FORK_NODES:
        assert fork in by_node, "в поставке нет развилки '{}'".format(fork)
        item = by_node[fork]
        assert GOLOKRON_NODE in item.options, (
            "на развилке '{}' не предлагают приложение".format(fork)
        )
        # Считаем от самой развилки, а не от двери: единица — это нажатие
        # кнопки, и человек его тоже читает.
        door = _steps_to(by_node, GOLOKRON_NODE, link.node)
        assert door is not None, "из приложения не дойти до ключа"
        by_app = door + 1
        hands = [
            _steps_to(by_node, target, link.node)
            for target in item.options
            if target != GOLOKRON_NODE
        ]
        assert hands and None not in hands, (
            "с развилки '{}' руками до ключа не дойти".format(fork)
        )
        by_hand = min(hands) + 1
        assert by_app < by_hand, (
            "с развилки '{}' приложением {} шагов, руками {} — не короче".format(
                fork, by_app, by_hand
            )
        )


def test_the_app_branch_carries_no_install_steps(content_root):
    """На ветке приложения нет установки Claude Code и игры.

    Ровно эти два шага Подготовка делает сама. Оставить их на ветке значило
    бы попросить человека сделать руками то, за чем он и скачал приложение.
    """
    by_node = shipped_nodes(content_root)
    branch = _flow_from(by_node, GOLOKRON_NODE)
    intruders = sorted(set(INSTALL_STEPS) & branch)
    assert not intruders, "на ветке приложения остались шаги установки: {}".format(
        ", ".join(intruders)
    )


def test_macos_never_meets_the_app(content_root):
    """С macOS в Голокрон не попасть ни одной дорогой — его под macOS нет.

    Прежде ветка Голокрона висела общей, и человека на маке уводили в неё, а
    выбираться он должен был кнопкой «я на macOS». Дверь, из которой сразу
    надо выходить, — не дверь.

    Меряется по ВСЕМУ графу, включая разбор поломок: ровно там дорога и
    нашлась в первый раз — `macos → … → no-command → «Есть — я в Голокроне»`.
    Обход по одному потоку её не видел, то есть прятал именно то, что тест
    и обязан искать.
    """
    by_node = shipped_nodes(content_root)
    assert MACOS_NODE in by_node
    assert GOLOKRON_NODE not in _reach_all(by_node, MACOS_NODE), (
        "с macOS всё ещё можно прийти в Голокрон"
    )


def test_link_node_is_unique_and_terminal(content_root):
    """Ограничение бота, продиктовавшее место Голокрона.

    Бот выдаёт ключ по разделу узла: второй узел раздела link завёл бы
    строку падавана дважды за проход, а кнопка у конца пути — узел после
    ключа. До сих пор это знал только тест бота в другом репозитории —
    коммит c9c3f9e этого репозитория так и записал: «дефект нашли тесты
    бота, а не свои». Здесь то же правило стоит у источника, чтобы
    следующий узел «после ключа» краснел до генератора, а не после выкатки.
    """
    link = the_link_node(shipped_nodes(content_root))
    assert link.options == (), "у конца пути появились кнопки"


# --- Связность дерева -------------------------------------------------

def test_link_to_missing_node_detected(tmp_path):
    nodes = [
        ("10.md", node_text("start", 10, options=["nowhere"])),
        ("30.md", node_text("done", 30)),
    ]
    problems = synth(tmp_path, nodes)
    assert any("nowhere" in p and "такого узла нет" in p for p in problems)


def test_unreachable_node_detected(tmp_path):
    """Узел есть, а дойти до него нельзя — падаван его не увидит."""
    nodes = good_tree() + [("40.md", node_text("orphan", 40))]
    problems = synth(tmp_path, nodes)
    assert any("orphan" in p and "не добраться" in p for p in problems)


def test_node_without_exit_detected(tmp_path):
    """Петля без терминала: переходы есть, а закончить путь нельзя."""
    nodes = [
        ("10.md", node_text("start", 10, options=["loop"])),
        ("20.md", node_text("loop", 20, options=["start"])),
    ]
    problems = synth(tmp_path, nodes)
    assert any("не выйти" in p for p in problems)
    # Названы оба узла петли, а не один: чинить придётся её целиком.
    assert len([p for p in problems if "не выйти" in p]) == 2


def test_terminal_node_alone_is_clean(tmp_path):
    """Дерево из одного терминального узла — вырожденное, но не битое."""
    assert synth(tmp_path, [("10.md", node_text("start", 10))]) == []


# --- Уникальность и форма идентификатора ------------------------------

def test_duplicate_order_detected(tmp_path):
    """Одинаковый order — порядок узлов и выбор корня неопределены."""
    nodes = [
        ("10.md", node_text("start", 10, options=["done"])),
        ("20.md", node_text("done", 10)),
    ]
    problems = synth(tmp_path, nodes)
    assert any("order 10" in p and "повторяется" in p for p in problems)


def test_duplicate_node_id_detected(tmp_path):
    nodes = [
        ("10.md", node_text("start", 10)),
        ("20.md", node_text("start", 20)),
    ]
    problems = synth(tmp_path, nodes)
    assert any("'start'" in p and "повторяется" in p for p in problems)


def test_too_long_node_id_detected(tmp_path):
    """Идентификатор с префиксом обязан влезать в callback_data Telegram."""
    long_id = "a" * (lint_content.ONBOARDING_NODE_MAX + 1)
    problems = synth(tmp_path, [("10.md", node_text(long_id, 10))])
    named = [p for p in problems if "callback_data" in p]
    assert len(named) == 1
    assert str(lint_content.ONBOARDING_NODE_MAX) in named[0]


def test_node_id_at_limit_is_clean(tmp_path):
    """Потолок включительный — тот же смысл, что у длины и бюджета."""
    at_limit = "a" * lint_content.ONBOARDING_NODE_MAX
    assert synth(tmp_path, [("10.md", node_text(at_limit, 10))]) == []


@pytest.mark.parametrize("bad", ["Start", "с-кириллицей", "with_underscore", "-leading"])
def test_bad_node_id_pattern_detected(tmp_path, bad):
    problems = synth(tmp_path, [("10.md", node_text(bad, 10))])
    assert any("не по шаблону" in p for p in problems)


# --- Длина сообщения --------------------------------------------------

def test_long_node_body_detected(tmp_path):
    """Узел — это одно сообщение бота, и стена текста запрещена ему так же."""
    body = "я" * (lint_content.VERBATIM_MAX + 1)
    problems = synth(tmp_path, [("10.md", node_text("start", 10, body=body))])
    assert any(
        "узел start" in p and str(lint_content.VERBATIM_MAX + 1) in p
        for p in problems
    )


def test_node_body_at_limit_is_clean(tmp_path):
    body = "я" * lint_content.VERBATIM_MAX
    assert synth(tmp_path, [("10.md", node_text("start", 10, body=body))]) == []


def test_shipped_nodes_are_under_limit(content_root):
    """Живой предмет проверки: тела узлов поставки под потолком."""
    from jedicoder import content

    longest = max(
        lint_content.visible_length(item.body)
        for item in content.load_onboarding(content_root)
    )
    assert longest <= lint_content.VERBATIM_MAX


# --- Схема ------------------------------------------------------------

def test_options_and_titles_mismatch_detected(tmp_path):
    """Кнопка без адреса или адрес без кнопки — битая структура узла."""
    text = node_text("start", 10, options=["done"], option_titles=['"а"', '"б"'])
    problems = synth(tmp_path, [("10.md", text), ("30.md", node_text("done", 30))])
    assert any("разъехались" in p for p in problems)


def test_unknown_section_detected(tmp_path):
    text = node_text("start", 10).replace("section: install", "section: выдумка")
    assert any("section" in p for p in synth(tmp_path, [("10.md", text)]))


def test_missing_required_field_detected(tmp_path):
    """Узел без order: молча потерять текст нельзя, загрузка обязана упасть."""
    text = node_text("start", 10).replace("order: 10\n", "")
    assert any("order" in p for p in synth(tmp_path, [("10.md", text)]))


def test_empty_body_detected(tmp_path):
    text = node_text("start", 10, body="")
    assert any("пустое тело" in p for p in synth(tmp_path, [("10.md", text)]))


def test_probe_survives_load(content_root):
    """Поле probe необязательное, но там, где оно есть, оно доезжает."""
    from jedicoder import content

    probes = [i.probe for i in content.load_onboarding(content_root) if i.probe]
    assert probes, "ни один узел поставки не несёт проверочной команды"


def test_order_sorts_the_load(tmp_path):
    """Загрузчик отдаёт узлы по order, а не по имени файла."""
    from jedicoder import content

    onboarding(tmp_path, [
        ("zzz.md", node_text("start", 10, options=["done"])),
        ("aaa.md", node_text("done", 30)),
    ])
    assert [i.node for i in content.load_onboarding(tmp_path)] == ["start", "done"]


# --- Генератор --------------------------------------------------------

def run_export(*args):
    return subprocess.run(
        [sys.executable, str(EXPORT)] + [str(arg) for arg in args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def test_export_of_shipped_content_is_clean():
    result = run_export()
    out = result.stdout.decode("utf-8")
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert "export const act0Steps" in out
    assert "export const ACT0_ROOT" in out


def test_export_carries_every_node_and_its_text(content_root):
    import json

    from jedicoder import content

    out = run_export().stdout.decode("utf-8")
    for item in content.load_onboarding(content_root):
        assert json.dumps(item.node) in out, "нет узла {}".format(item.node)
        assert json.dumps(
            lint_content.visible_text(item.body), ensure_ascii=False
        ) in out


def test_export_strips_service_comments(content_root):
    """Маркер правила 3 человеку не доезжает — ни в игре, ни в боте.

    Дефект живой: маркер стоит в теле узла установки, и без вырезания он
    уехал бы человеку первым же сообщением Акта 0.
    """
    out = run_export().stdout.decode("utf-8")
    assert "lint:novelty-ok" not in out


def test_export_of_broken_tree_fails_and_prints_nothing(tmp_path):
    onboarding(tmp_path, [("10.md", node_text("start", 10, options=["nowhere"]))])
    result = run_export(tmp_path)
    assert result.returncode == 1
    assert result.stdout == b"", "генератор выпустил модуль с тупиком"
    assert "nowhere".encode("utf-8") in result.stderr


def test_export_of_missing_directory_fails_without_traceback(tmp_path):
    result = run_export(tmp_path / "нет-такой-папки")
    assert result.returncode == 1
    assert result.stdout == b""
    assert b"Traceback" not in result.stderr


# --- Второй формат вывода: markdown -----------------------------------

def test_export_md_of_shipped_content_is_clean():
    result = run_export("--format", "md")
    assert result.returncode == 0, result.stderr.decode("utf-8")
    out = result.stdout.decode("utf-8")
    assert out.startswith("<!-- Сгенерировано")
    assert "## Не получилось" in out


def test_export_md_carries_every_node_and_its_text(content_root):
    from jedicoder import content

    out = run_export("--format", "md").stdout.decode("utf-8")
    for item in content.load_onboarding(content_root):
        assert '<a id="node-{}"></a>'.format(item.node) in out
        assert "### {}".format(item.title) in out
        assert lint_content.visible_text(item.body) in out


def test_export_md_has_no_dead_links():
    """Развилка обязана вести в существующий якорь.

    В боте связность держит `_onboarding_problems`, но там переход — это
    кнопка, а здесь адрес внутри файла: сам якорь ставит генератор, и
    ошибиться он может отдельно от контента.
    """
    out = run_export("--format", "md").stdout.decode("utf-8")
    anchors = set(re.findall(r'<a id="node-([a-z0-9-]+)"></a>', out))
    links = set(re.findall(r"\]\(#node-([a-z0-9-]+)\)", out))
    assert links, "в markdown не оказалось ни одной развилки"
    assert links - anchors == set()


def test_export_md_puts_trouble_after_the_flow(content_root):
    """Разбор поломок — глава внизу, а не вперемешку с основным потоком."""
    from jedicoder import content

    out = run_export("--format", "md").stdout.decode("utf-8")
    border = out.index("## Не получилось")
    for item in content.load_onboarding(content_root):
        at = out.index('<a id="node-{}"></a>'.format(item.node))
        assert (at > border) == (item.section == "trouble"), item.node


def test_shipped_install_md_matches_generator():
    """Закоммиченный markdown совпадает с выводом генератора.

    Красный тест здесь означает ровно одно: кто-то правил производную вместо
    источника. Чинится перевыпуском, а не правкой файла.
    """
    result = run_export("--format", "md")
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert INSTALL_MD.is_file(), "производная пропала: {}".format(INSTALL_MD)
    assert INSTALL_MD.read_text(encoding="utf-8") == result.stdout.decode("utf-8"), (
        "docs/act0-install.md разошёлся с генератором. Перевыпустить:\n"
        "  python3 scripts/export_onboarding.py --format md > docs/act0-install.md"
    )


@pytest.mark.parametrize("args", [
    ("--format", "выдумка"),
    ("--format",),
    ("--format=json",),
    ("--нет-такого-ключа",),
])
def test_unknown_format_fails_and_prints_nothing(args):
    result = run_export(*args)
    assert result.returncode == 1
    assert result.stdout == b"", "генератор выпустил что-то в неизвестном формате"
    assert b"Traceback" not in result.stderr


def test_default_format_is_still_typescript():
    """Вызов без ключа отдаёт модуль бота — второй формат его не подвинул."""
    assert "export const act0Steps" in run_export().stdout.decode("utf-8")
    assert "--format" not in run_export().stdout.decode("utf-8")


# --- Производные во втором репозитории --------------------------------

def site_root():
    """Корень репозитория сайта и бота, либо skip.

    Честная граница этого теста: он ходит в ЧУЖОЙ репозиторий, которого на
    большинстве машин нет. Пропуск здесь — не мягкость, а единственный
    вариант, при котором suite остаётся зелёным у того, кто клонировал один
    плагин. Ровно поэтому долг №14 не считается закрытым: на машине без
    второго репозитория расхождение по-прежнему не ловится ничем, и его
    ловит diff в приёмке.
    """
    root = Path(os.environ.get(SITE_ROOT_ENV, str(SITE_ROOT_DEFAULT)))
    if not root.is_dir():
        pytest.skip(
            "нет репозитория сайта ({}); путь задаётся переменной {}".format(
                root, SITE_ROOT_ENV
            )
        )
    return root


@pytest.mark.parametrize("relpath", TS_CONSUMERS, ids=lambda p: p.name)
def test_shipped_ts_derivative_matches_generator(relpath):
    """Закоммиченная копия совпадает с выводом генератора.

    Копий текста Акта 0 три, и правится он в одном месте. Прошлый раз, когда
    один текст жил в двух репозиториях, они разошлись молча и говорили
    разными словами несколько часов.
    """
    path = site_root() / relpath
    assert path.is_file(), "производная пропала: {}".format(path)
    result = run_export()
    assert result.returncode == 0, result.stderr.decode("utf-8")
    expected = result.stdout.decode("utf-8")
    actual = path.read_text(encoding="utf-8")
    assert actual == expected, (
        "{} разошёлся с генератором. Перевыпустить:\n"
        "  python3 scripts/export_onboarding.py > {}".format(relpath, path)
    )

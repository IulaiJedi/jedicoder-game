#!/usr/bin/env python3
"""Линтер контент-ядра.

Запуск: python3 scripts/lint_content.py [plugin/content/ru]

Главная проверка — непересечение алиасов между терминами. Если два термина
делят алиас, хук подсветки откроет падавану не тот термин, и это не видно
глазами при ревью — только линтером.

## Границы прибора

Текст игры делится на три категории, и линтер видит только две из них.

**A. Дословно падавану** — катсцены актов, правила Кодекса, карточки лута,
блоки цитат `> …` во врезках скиллов. Этот текст доезжает до падавана
буква в букву, и линтер меряет его **точно**.

**B. Модель пересказывает** — тела рецептов, `behavior.md`, остальной текст
`SKILL.md`. Здесь линтер меряет **источник**, а не пересказ: длинный рецепт
— причина длинного пересказа, но не он сам.

**C. Импровизация модели** — всё, что модель говорит падавану от себя, а это
большая часть разговора. **Прибора нет вовсе.** У квеста статического текста
может не быть ни строчки, и ни счёт терминов, ни счёт символов по нашим
файлам ничего про речь модели не доказывают.

Отсюда прямое следствие, которое нельзя забыть: **зелёный линтер не
доказывает, что падаван не получил стены текста и не услышал восемь новых
слов за квест.** Он доказывает ровно одно — что этого нет в наших файлах и
что регрессия не вернётся молча. Речь модели проверяется только живым
прогоном.
"""
import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugin" / "lib"))

from jedicoder import acts  # noqa: E402
from jedicoder import content  # noqa: E402
from jedicoder import frontmatter  # noqa: E402
from jedicoder import ranks  # noqa: E402

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "plugin" / "content" / "ru"

# Врезки живут не в контент-ядре, а в скиллах, поэтому корень отдельный.
# Он не выводится из content_root: тесты подсовывают синтетический контент
# во временную папку, и «сосед сверху» у неё — общая папка pytest, куда
# соседний тест мог положить что угодно.
DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[1] / "plugin" / "skills"

# Слэш-команды — тоже не контент-ядро, и корень у них третий. start.md
# читается падаваном раньше всего остального, поэтому без него правило 3
# не видит самого громкого места игры — первого экрана.
DEFAULT_COMMANDS_ROOT = Path(__file__).resolve().parents[1] / "plugin" / "commands"

# Карточку лута меряем тем же кодом, которым её печатает хук. Своя копия
# рендера разошлась бы с тем, что видит падаван, и прибор начал бы мерить
# не то. Хук лежит в plugin/hooks, а не в lib, поэтому грузим по пути.
LOOT_HOOK = Path(__file__).resolve().parents[1] / "plugin" / "hooks" / "lexicon_loot.py"

BEHAVIOR_FILE = "behavior.md"

WIKI_LINK = re.compile(r"\[\[([^\]|]+)")

TERM_SECTION = "**Зачем"
RULE_SECTION = "**Что делать"

# Минимальная длина катсцены. Маркера обязательной секции у неё нет —
# катсцена сплошная проза, — поэтому от «пропала половина текста» защищает
# длина. Порог с большим запасом: самая короткая катсцена поставки — 494
# символа, случайно его не пробить, а вырезанный абзац уронит.
ACT_BODY_MIN = 200

# Потолок длины дословного текста, в символах. Число живёт здесь и в
# behavior.md; расхождение ловится тестом — менять его в одном месте нельзя.
VERBATIM_MAX = 900

# Потолок новых терминов на один квест. Тот же включительный смысл, что у
# длины: ровно три — норма, четвёртый — дефект.
NOVELTY_MAX = 3

QUOTE_LINE = re.compile(r"^\s*>\s?(.*)$")

# HTML-комментарий падавану не доезжает никогда: markdown его не рисует, а
# модель его не пересказывает — это служебная пометка для нас. Поэтому в
# счёт длины он не идёт. Иначе маркеры правила 3 сами раздували бы текст,
# который правило 1 меряет, и починка одного правила ломала бы другое.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)

# Маркеры исключений правила 3. Их два, и они про разное.
#
# Регион skip … skip-end — это **справочник, а не употребление**: список
# подкоманд, таблица актов, блок команд. Падаван читает там имена вещей, а
# не знакомится со словами.
#
# Маркер novelty-ok — это **декларация, а не доказательство**: линтер не
# умеет прочитать пояснение и не притворяется, что умеет. Что он даёт —
# невозможность добавить слово молча: маркер ставится руками и обязан
# нести причину в том же комментарии.
#
# Исключать файл целиком нельзя ни тем, ни другим способом: именно это
# спрятало бы настоящий дефект внутри в остальном справочного файла.
NOVELTY_SKIP_OPEN = "<!-- lint:novelty-skip -->"
NOVELTY_SKIP_CLOSE = "<!-- lint:novelty-skip-end -->"
NOVELTY_OK = re.compile(r"<!--\s*lint:novelty-ok:\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

# Позиция рецептов в потоке падавана: рецепт читается в квесте 01-recipe
# Акта 2, то есть раньше всего остального Акта 2 и позже всего Акта 1.
RECIPE_POSITION = 2

# Позиция реплик Магистра — по событию, которое их вызывает: где событие
# впервые возможно, там реплика впервые и звучит. События хуков (Тёмная
# сторона, серия коммитов, открытый термин) случаются с первой сессии, до
# входа в акт, — позиция 0, строже всех. События движка начинаются с входа
# в Акт 1. Деплой и финал — ручки Акта 5 (`project url`, `finale`).
# Реплика одна на событие, а не на акт, поэтому quest_completed, звучащий и
# в Акте 5, меряется по Акту 1: слово, которого падаван первого акта ещё
# не слышал, ему в реплике не положено.
REMARK_POSITION = {
    "act_started": 1,
    "quest_completed": 1,
    "quest_failed": 1,
    "rank_up": 1,
    "term_unlocked": 0,
    "dark_side": 0,
    "streak_updated": 0,
    "product_deployed": 5,
    "finale": 5,
}

# Минимум вариантов реплики Магистра на одно событие. Из спеки Голокрона:
# «три-четыре варианта» — Голокрон выбирает вариант по порядковому номеру
# события за сессию, и с двумя вариантами Магистр повторялся бы через раз.
# Потолка нет: критерий приёмки говорит только «не меньше трёх».
REMARK_MIN = 3

# Идентификатор узла Акта 0 едет в `callback_data` Telegram с префиксом
# игровой ветки, а у `callback_data` потолок 64 байта. Шаблон держит
# идентификатор в ASCII, поэтому символы и байты здесь — одно и то же, а
# длина оставляет запас на префикс любой разумной длины.
ONBOARDING_NODE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ONBOARDING_NODE_MAX = 40


def ordered_corpus(content_root, skills_root=None, commands_root=None):
    """Тексты игры в том порядке, в каком их встречает падаван.

    Кортеж (подпись, позиция, путь). Позиция 0 — то, что читается до
    любого акта; позиция N — тексты акта N. Список отсортирован по
    позиции устойчивой сортировкой, поэтому порядок внутри позиции — тот,
    в котором он объявлен здесь, и от запуска к запуску не меняется.

    Корни параметризованы по той же причине, по которой параметризован
    skills_root у правила 1: тесты подсовывают синтетический контент во
    временную папку, а прибитый к поставке список сканировал бы боевые
    файлы чужими алиасами и падал бы мимо цели.
    """
    content_root = Path(content_root)
    skills_root = DEFAULT_SKILLS_ROOT if skills_root is None else Path(skills_root)
    commands_root = (
        DEFAULT_COMMANDS_ROOT if commands_root is None else Path(commands_root)
    )
    # Акт 0 стоит первым и позицией 0 не по вежливости, а по факту: его
    # читает человек, у которого плагина ещё нет вовсе. Всё, что игра
    # объясняет актами, для него ещё не прозвучало, поэтому слово из любого
    # акта здесь — опережающее употребление.
    corpus = []
    onboarding_dir = content_root / "onboarding"
    if onboarding_dir.is_dir():
        for path in sorted(onboarding_dir.glob("*.md")):
            corpus.append(("узел Акта 0 " + path.stem, 0, path))
    corpus += [
        ("start.md", 0, commands_root / "start.md"),
        ("core/SKILL.md", 0, skills_root / "core" / "SKILL.md"),
        (BEHAVIOR_FILE, 0, content_root / BEHAVIOR_FILE),
    ]
    for number in sorted(ranks.ACTS):
        slug = ranks.ACTS[number]["slug"]
        corpus.append(
            ("катсцена акта {}".format(number), number,
             content_root / "acts" / (slug + ".md"))
        )
        corpus.append(
            ("SKILL акта {}".format(number), number,
             skills_root / slug / "SKILL.md")
        )
    recipes_dir = content_root / "recipes"
    if recipes_dir.is_dir():
        for path in sorted(recipes_dir.glob("*.md")):
            corpus.append(
                ("рецепт " + path.stem, RECIPE_POSITION, path)
            )
    remarks_dir = content_root / "magistr"
    if remarks_dir.is_dir():
        for path in sorted(remarks_dir.glob("*.md")):
            # Файл с чужим именем позиции не имеет — берёт строжайшую;
            # само имя загрузчик и линтер отвергнут отдельно.
            corpus.append((
                "реплика Магистра " + path.stem,
                REMARK_POSITION.get(path.stem, 0),
                path,
            ))
    return sorted(corpus, key=lambda item: item[1])


def lint(content_root, skills_root=None, corpus=None):
    """Вернуть список проблем. Пустой список — контент чистый."""
    problems = []
    terms = _safe(content.load_terms, content_root, problems)
    rules = _safe(content.load_rules, content_root, problems)
    recipes = _safe(content.load_recipes, content_root, problems)
    # act_items, а не acts: имя модуля с реестром квестов занято импортом.
    act_items = _safe(content.load_acts, content_root, problems)
    onboarding = _safe(content.load_onboarding, content_root, problems)
    remarks = _safe(content.load_remarks, content_root, problems)
    if problems:
        return problems

    problems += _behavior_problems(content_root)
    problems += _duplicate_ids(terms, "term")
    problems += _duplicate_ids(rules, "rule")
    problems += _duplicate_ids(recipes, "recipe")
    problems += _duplicate_ids(remarks, "event")
    problems += _alias_collisions(terms)
    problems += _act_problems(act_items)
    problems += _onboarding_problems(onboarding)
    problems += _remark_problems(remarks)
    problems += _length_problems(
        act_items, rules, recipes, terms, onboarding, remarks,
        DEFAULT_SKILLS_ROOT if skills_root is None else Path(skills_root),
    )
    problems += _novelty_problems(terms)
    problems += _early_use_problems(
        terms,
        ordered_corpus(content_root, skills_root) if corpus is None else corpus,
    )

    known = set()
    for item in terms:
        known.add(item.term)
    for item in rules:
        known.add(item.rule)
    for item in recipes:
        known.add(item.recipe)
    for item in act_items:
        known.add(item.slug)

    for term in terms:
        for target in term.related:
            if target not in known:
                problems.append(
                    "{}: related указывает на несуществующий '{}'".format(
                        term.path.name, target
                    )
                )
        if TERM_SECTION not in term.body:
            problems.append(
                "{}: нет обязательной секции '{}'".format(term.path.name, TERM_SECTION)
            )

    for rule in rules:
        if RULE_SECTION not in rule.body:
            problems.append(
                "{}: нет обязательной секции '{}'".format(rule.path.name, RULE_SECTION)
            )

    for item in list(terms) + list(rules) + list(recipes) + list(act_items):
        for link in WIKI_LINK.findall(item.body):
            if link.strip() not in known:
                problems.append(
                    "{}: ссылка [[{}]] никуда не ведёт".format(
                        item.path.name, link.strip()
                    )
                )

    return problems


def _behavior_problems(content_root):
    """Проверить behavior.md — файл, с которого начинается каждый скилл.

    Раньше линтер читал только lexicon/codex/recipes и на битом behavior.md
    печатал «Контент чистый», а падаван получал трейсбек на первой же команде.
    """
    path = Path(content_root) / BEHAVIOR_FILE
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ["{}: файл не найден или не читается".format(BEHAVIOR_FILE)]
    except UnicodeDecodeError:
        return ["{}: файл не в UTF-8".format(BEHAVIOR_FILE)]
    try:
        _, body = frontmatter.parse(text)
    except frontmatter.FrontmatterError as exc:
        return ["{}: фронтматтер не разбирается — {}".format(BEHAVIOR_FILE, exc)]
    if not body.strip():
        return ["{}: тело контракта пустое".format(BEHAVIOR_FILE)]
    return []


def _safe(loader, content_root, problems):
    try:
        return loader(content_root)
    except content.ContentError as exc:
        problems.append(str(exc))
        return []


def _duplicate_ids(items, attr):
    seen = {}
    problems = []
    for item in items:
        key = getattr(item, attr)
        if key in seen:
            problems.append(
                "{}: {} '{}' повторяется, уже есть в {}".format(
                    item.path.name, attr, key, seen[key]
                )
            )
        else:
            seen[key] = item.path.name
    return problems


def _alias_collisions(terms):
    owners = {}
    problems = []
    for term in terms:
        for alias in term.aliases:
            key = str(alias).strip().lower()
            if key in owners and owners[key] != term.term:
                problems.append(
                    "алиас '{}' делят термины '{}' и '{}' — подсветка сломается".format(
                        alias, owners[key], term.term
                    )
                )
            else:
                owners[key] = term.term
    return problems


def act_axis(number):
    """Ось развилки акта словом схемы контента: 'deploy' или 'track'.

    В движке ось трека безымянна — акт, не названный в acts.ACT_AXIS,
    ветвится по треку, — и имя ей даётся здесь, один раз. Генератор сайта и
    тесты берут его отсюда, а не держат по своей копии условия.
    """
    if acts.ACT_AXIS.get(number) == acts.AXIS_DEPLOY:
        return "deploy"
    return "track"


def _act_problems(items):
    """Сверить катсцены с реестрами движка поле в поле.

    Маркера обязательной секции у катсцены нет, и выдумывать его не надо:
    сильнее любого маркера здесь перекрёстная сверка. Сегодня slug, title,
    rank и artifact живут в двух местах — в ranks.ACTS (истина движка) и во
    фронтматтере (истина книги), а список квестов — в acts.QUESTS_BY_ACT и
    там же во фронтматтере. Разъехаться они могут молча, при полностью
    зелёном суите: книга покажет чужой ранг или чужой список квестов, и
    никто не заметит. Линтер делает это дублирование сверенным.

    Самоописание акта — ветка каждого квеста, ось развилки и русское имя
    ранга — дублирование того же рода: метка ветки стоит на квесте в
    acts.QUESTS_BY_ACT, ось — в acts.ACT_AXIS, имя ранга — в
    ranks.RANK_TITLES. Поля заведены, чтобы Голокрон и сайт собирали доску
    квестов из них, не зная движка, поэтому расхождение — доска, обещающая
    падавану чужие квесты. Сверяется позиция в позицию.
    """
    problems = []

    seen = {}
    for item in items:
        if item.act in seen:
            problems.append(
                "{}: акт {} повторяется, уже есть в {}".format(
                    item.path.name, item.act, seen[item.act]
                )
            )
        else:
            seen[item.act] = item.path.name

    missing = sorted(set(ranks.ACTS) - set(seen))
    if missing:
        problems.append(
            "нет файлов катсцен для актов: {}".format(
                ", ".join(str(number) for number in missing)
            )
        )
    extra = sorted(set(seen) - set(ranks.ACTS))
    if extra:
        problems.append(
            "катсцены есть у актов, которых нет в ranks.ACTS: {}".format(
                ", ".join(str(number) for number in extra)
            )
        )

    for item in items:
        name = item.path.name
        info = ranks.ACTS.get(item.act)
        if info is not None:
            for field in ("slug", "title", "rank", "artifact"):
                mine = getattr(item, field)
                theirs = info[field]
                if mine != theirs:
                    problems.append(
                        "{}: {} '{}' расходится с ranks.ACTS[{}] — там '{}'".format(
                            name, field, mine, item.act, theirs
                        )
                    )
        # Имя ранга сверяется по rank из фронтматтера, а не из ranks.ACTS:
        # расхождение самого rank уже названо выше, и второе сообщение про
        # него же только запутало бы. Неизвестный rank отсеял загрузчик.
        rank_title = ranks.RANK_TITLES.get(item.rank)
        if rank_title is not None and item.rank_title != rank_title:
            problems.append(
                "{}: rank_title '{}' расходится с ranks.RANK_TITLES['{}'] — "
                "там '{}'".format(name, item.rank_title, item.rank, rank_title)
            )
        axis = act_axis(item.act)
        if item.axis != axis:
            problems.append(
                "{}: axis '{}' расходится с acts.ACT_AXIS — там '{}'".format(
                    name, item.axis, axis
                )
            )
        if item.slug != item.path.stem:
            problems.append(
                "{}: slug '{}' не совпадает с именем файла".format(name, item.slug)
            )
        if len(item.body) < ACT_BODY_MIN:
            problems.append(
                "{}: катсцена короче {} символов — похоже, пропала секция".format(
                    name, ACT_BODY_MIN
                )
            )
        registry = acts.QUESTS_BY_ACT.get(item.act)
        if registry is not None:
            expected = tuple(quest_id for quest_id, _, _ in registry)
            if item.quests != expected:
                problems.append(
                    "{}: quests расходится с acts.QUESTS_BY_ACT[{}] — там {}".format(
                        name, item.act, list(expected)
                    )
                )
            expected_branches = tuple(branch for _, _, branch in registry)
            if item.quest_branches != expected_branches:
                problems.append(
                    "{}: quest_branches расходится с acts.QUESTS_BY_ACT[{}] — "
                    "там {}".format(name, item.act, list(expected_branches))
                )
        if len(item.quest_titles) != len(item.quests):
            problems.append(
                "{}: подписей {}, а квестов {} — списки разъехались".format(
                    name, len(item.quest_titles), len(item.quests)
                )
            )
        if len(item.quest_branches) != len(item.quests):
            problems.append(
                "{}: веток {}, а квестов {} — списки разъехались".format(
                    name, len(item.quest_branches), len(item.quests)
                )
            )
        for title in item.quest_titles:
            if not str(title).strip():
                problems.append("{}: пустая подпись квеста".format(name))

    return problems


def _onboarding_problems(items):
    """Связность дерева Акта 0: тупик, ссылка в пустоту, недостижимый узел.

    Это и есть настоящий класс ошибок дерева диалога, и ловится он только
    обходом. Узел без выхода или кнопка в несуществующий узел — тупик, из
    которого человек выбирается закрытием бота; на живом человеке такое
    находить нельзя, потому что он второй раз не придёт.

    **Чего эта функция НЕ меряет и почему это надо сказать вслух (D-03):**
    бюджет трёх новых слов на Акт 0 линтером не меряется вовсе. Правило 2
    (`_novelty_problems`) считает термины по полю `quest`, а квестов у Акта 0
    нет и быть не может — исход квеста решает exit-код `check.sh`, а Акт 0
    ничего не засчитывает. Бюджет Акта 0 держится именным списком-стражем в
    тестах (заводит план 01.4-03) и ревью, а не этим прибором.
    """
    problems = []
    if not items:
        return problems

    by_node = {}
    for item in items:
        name = item.path.name
        if item.node in by_node:
            problems.append(
                "{}: узел '{}' повторяется, уже есть в {}".format(
                    name, item.node, by_node[item.node].path.name
                )
            )
        else:
            by_node[item.node] = item
        if not ONBOARDING_NODE.match(str(item.node)):
            problems.append(
                "{}: идентификатор '{}' не по шаблону — строчная латиница, "
                "цифры и дефис".format(name, item.node)
            )
        elif len(item.node) > ONBOARDING_NODE_MAX:
            problems.append(
                "{}: идентификатор '{}' длиной {}, потолок {} — с префиксом "
                "он не влезет в callback_data".format(
                    name, item.node, len(item.node), ONBOARDING_NODE_MAX
                )
            )
        # Дубль схемной проверки из content.py, и он не мёртвый: тесты зовут
        # эту функцию напрямую собранными объектами, минуя загрузчик.
        if len(item.options) != len(item.option_titles):
            problems.append(
                "{}: переходов {}, а подписей {} — списки разъехались".format(
                    name, len(item.options), len(item.option_titles)
                )
            )
        for title in item.option_titles:
            if not str(title).strip():
                problems.append("{}: пустая подпись кнопки".format(name))

    seen_order = {}
    for item in items:
        if item.order in seen_order:
            problems.append(
                "{}: order {} повторяется, уже есть в {} — порядок узлов "
                "неопределён".format(
                    item.path.name, item.order, seen_order[item.order]
                )
            )
        else:
            seen_order[item.order] = item.path.name

    for item in items:
        for target in item.options:
            if target not in by_node:
                problems.append(
                    "{}: переход в '{}', а такого узла нет".format(
                        item.path.name, target
                    )
                )

    # Корень — узел с наименьшим order. Тот же корень возьмёт генератор:
    # разойтись они не могут, потому что правило одно и записано здесь.
    root = min(items, key=lambda entry: entry.order)
    reached = _onboarding_reach(by_node, root.node)
    orphans = sorted(set(by_node) - reached)
    if orphans:
        problems.append(
            "от корня '{}' не добраться до узлов: {} — падаван их не "
            "увидит".format(root.node, ", ".join(orphans))
        )

    for name in sorted(by_node):
        if not _onboarding_has_exit(by_node, name):
            problems.append(
                "{}: из узла '{}' не выйти — путь не заканчивается".format(
                    by_node[name].path.name, name
                )
            )

    return problems


def _onboarding_reach(by_node, start):
    """Множество узлов, достижимых из start. Обход в ширину, без рекурсии."""
    reached = set()
    queue = [start]
    while queue:
        current = queue.pop()
        if current in reached or current not in by_node:
            continue
        reached.add(current)
        queue.extend(by_node[current].options)
    return reached


def _onboarding_has_exit(by_node, start):
    """Достижим ли из start хотя бы один терминальный узел.

    Терминальный — узел без переходов. Узел, из которого можно ходить вечно
    и ни разу не выйти, — это и есть петля-тупик: формально переходы есть,
    а закончить путь нельзя.
    """
    for name in _onboarding_reach(by_node, start):
        if not by_node[name].options:
            return True
    return False


def _remark_problems(items):
    """Состав реплик Магистра: файл на каждое событие сцены.

    Голокрон подбирает реплику по типу события, и файла на событие у него
    нет — событие происходит молча: доска перекрасится, Магистр промолчит.
    На стороне Голокрона это не ошибка (старый плагин без реплик — штатный
    случай), поэтому дыру в поставке обязан видеть линтер, а не падаван.
    """
    problems = []
    seen = set(item.event for item in items)
    missing = [event for event in content.MAGISTR_EVENTS if event not in seen]
    if missing:
        problems.append(
            "нет файлов реплик Магистра для событий: {}".format(", ".join(missing))
        )
    for item in items:
        name = item.path.name
        # Читателей два — по имени файла и по полю event, — и оба обязаны
        # найти одно и то же: иначе событие остаётся без реплики молча.
        if item.event != item.path.stem:
            problems.append(
                "{}: event '{}' не совпадает с именем файла".format(name, item.event)
            )
        if len(item.variants) < REMARK_MIN:
            problems.append(
                "{}: вариантов {}, минимум {} — Магистр повторялся бы через "
                "раз".format(name, len(item.variants), REMARK_MIN)
            )
        seen_variants = set()
        for number, text in enumerate(item.variants, 1):
            # Копия строки — вариант по счёту, но не по смыслу: минимум
            # иначе обходился бы копированием.
            if text in seen_variants:
                problems.append("{}: вариант №{} повторяется".format(name, number))
            seen_variants.add(text)
            # Панель сцены печатает строку как есть, markdown её не прячет:
            # комментарий доедет до падавана буква в букву. Маркеры линтера
            # для реплик ставятся во фронтматтере строкой-комментарием.
            if "<!--" in text:
                problems.append(
                    "{}: вариант №{} содержит служебный комментарий — падаван "
                    "увидит его буква в букву; маркеры линтера ставятся во "
                    "фронтматтере".format(name, number)
                )
    return problems


# Кэш модуля хука: его просят два правила (1 — за render_card, 3 — за
# _alias_pattern), а грузить один и тот же файл дважды незачем. Список, а не
# global: одно место записи, и None «не загрузился» отличается от «ещё не
# пробовали».
_LOOT_MODULE = []


def _loot_module():
    """Модуль хука лута, загруженный один раз за прогон. None — не вышло."""
    if _LOOT_MODULE:
        return _LOOT_MODULE[0]
    module = None
    try:
        spec = importlib.util.spec_from_file_location(
            "jedicoder_lexicon_loot", str(LOOT_HOOK)
        )
        if spec is not None and spec.loader is not None:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 — причина не важна, важен факт
        module = None
    _LOOT_MODULE.append(module)
    return module


def _load_render_card():
    """Достать render_card из хука лута. None — если не вышло."""
    return getattr(_loot_module(), "render_card", None)


def _load_alias_pattern():
    """Достать _alias_pattern из хука лута. None — если не вышло.

    Своего матчера здесь нет намеренно: `\\b` вокруг «.env» встал бы после
    точки и ловил бы «file.env». Хук уже решил это лукэраундами, и правило 3
    обязано мерить ровно тем же, чем хук подсвечивает.
    """
    return getattr(_loot_module(), "_alias_pattern", None)


def _quote_blocks(text):
    """Блоки цитат `> …`: непрерывная череда строк с маркером — один блок.

    Пустая строка или строка обычного текста закрывает блок, как и в
    markdown: две цитаты через абзац — два сообщения, а не одно.
    """
    blocks = []
    current = []
    for line in text.split("\n"):
        match = QUOTE_LINE.match(line)
        if match is not None:
            current.append(match.group(1).strip())
        elif current:
            blocks.append(" ".join(part for part in current if part).strip())
            current = []
    if current:
        blocks.append(" ".join(part for part in current if part).strip())
    return blocks


def _skill_quote_units(skills_root):
    """Пары (подпись, текст) для врезок всех SKILL.md."""
    units = []
    root = Path(skills_root)
    if not root.is_dir():
        return units
    for path in sorted(root.glob("**/SKILL.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, block in enumerate(_quote_blocks(text), 1):
            units.append(("врезка {} №{}".format(path.parent.name, number), block))
    return units


def visible_text(text):
    """То, что реально доедет до падавана: без служебных комментариев.

    Выделена из `visible_length` и публична по той же причине: генератор
    Акта 0 отправляет тело узла человеку буква в букву, и своя копия
    вырезания разошлась бы с прибором молча — линтер мерил бы одно, а бот
    слал другое. Случай не гипотетический: маркер правила 3 в теле узла
    установки уехал бы человеку первым же сообщением.
    """
    return HTML_COMMENT.sub("", text).strip()


def visible_length(text):
    """Длина того, что реально доедет до падавана, в символах.

    Служебные HTML-комментарии (маркеры правила 3) в счёт не идут: markdown
    их не рисует, модель их не пересказывает. Функция публичная, чтобы
    тесты мерили тем же, чем меряет линтер, — своя копия расчёта разошлась
    бы с прибором молча.
    """
    return len(visible_text(text))


def _length_problems(act_items, rules, recipes, terms, onboarding, remarks,
                     skills_root):
    """Правило 1: дословный текст не длиннее VERBATIM_MAX символов.

    Меряем символы, а не байты: потолок про читаемость, а 'Тёмная сторона'
    — это 14 символов и 26 байт. Все файлы content/ru в NFC, комбинирующих
    последовательностей нет, поэтому len() честен и на кириллице.

    Единицы измерения — только категория A (дословно падавану) плюс тела
    рецептов из категории B. Про категорию C см. «Границы прибора» в
    докстринге модуля: её здесь нет и быть не может.

    Узел Акта 0 — самая дословная из всех единиц: это буквально одно
    сообщение бота, отправленное байт в байт. Потолок для него не
    заимствован по аналогии, а тот же самый — правило «не выдавай стену
    текста» из behavior.md действует на бота ровно так же, как на речь
    модели. Число берётся из VERBATIM_MAX; третьей копии числа нет.

    Реплика Магистра — тоже категория A: панель сцены печатает вариант
    буква в букву. Единица измерения — вариант, а не файл: падаван видит
    одну строку за раз.
    """
    problems = []
    units = []
    for item in act_items:
        units.append(("катсцена " + item.slug, item.body))
    for item in rules:
        units.append(("правило " + item.rule, item.body))
    for item in recipes:
        units.append(("рецепт " + item.recipe, item.body))
    for item in onboarding:
        units.append(("узел " + item.node, item.body))
    for item in remarks:
        for number, text in enumerate(item.variants, 1):
            units.append(("реплика {} №{}".format(item.event, number), text))

    render_card = _load_render_card()
    if render_card is None:
        problems.append(
            "не удалось загрузить render_card из {} — карточки лута не "
            "измерены".format(LOOT_HOOK)
        )
    else:
        for term in terms:
            units.append(("карточка " + term.term, render_card(term)))

    units += _skill_quote_units(skills_root)

    for label, text in units:
        size = visible_length(text)
        if size > VERBATIM_MAX:
            problems.append(
                "{}: {} символов, потолок {} — падаван получит стену "
                "текста".format(label, size, VERBATIM_MAX)
            )
    return problems


def _novelty_problems(terms):
    """Правило 2: не больше NOVELTY_MAX новых терминов на один квест.

    **Поле quest — декларация, а не механизм.** Хук лута
    (`lexicon_loot.find_terms`) фильтрует термины по `t.act <= current_act`
    и про квесты не знает: карточка выпадет там, где слово прозвучало, а не
    там, где мы обещали его ввести. Настоящий рычаг плотности — состав пула
    акта; правило 2 пришивает к этому рычагу обещание, которое иначе некому
    проверить. Делать хук квесто-зависимым не надо: фильтрация по квесту
    потеряла бы термины, чей квест падаван прошёл быстро.

    Термин без quest не считается вовсе — поле необязательное, и Акты 4-5
    в охват аудита языка не входят.
    """
    problems = []
    buckets = {}
    for term in terms:
        quest = getattr(term, "quest", "")
        if not quest:
            continue
        entries = acts.QUESTS_BY_ACT.get(term.act) or ()
        known = [quest_id for quest_id, _, _ in entries]
        if quest not in known:
            problems.append(
                "{}: quest '{}' нет в акте {} — есть {}".format(
                    term.path.name, quest, term.act, ", ".join(known)
                )
            )
            continue
        buckets.setdefault((term.act, quest), []).append(term.term)
    # Порядок детерминирован: корзины по ключу, имена внутри по алфавиту.
    for key in sorted(buckets):
        names = sorted(buckets[key])
        if len(names) > NOVELTY_MAX:
            problems.append(
                "акт {}, квест {}: {} новых терминов при потолке {} — "
                "{}".format(key[0], key[1], len(names), NOVELTY_MAX,
                            ", ".join(names))
            )
    return problems


def _strip_novelty_regions(text):
    """Вырезать регионы-справочники. Вернуть (текст, есть_незакрытый).

    Незакрытый открывающий маркер **ничего не вырезает**: хвост файла
    остаётся на месте, а вызывающий получает флаг и печатает проблему.
    Молчаливое вырезание до конца файла было бы худшим из возможных
    поведений — оно отключило бы правило целиком, и никто бы не заметил.
    """
    parts = []
    rest = text
    unclosed = False
    while True:
        start = rest.find(NOVELTY_SKIP_OPEN)
        if start < 0:
            parts.append(rest)
            break
        end = rest.find(NOVELTY_SKIP_CLOSE, start)
        if end < 0:
            unclosed = True
            parts.append(rest)
            break
        parts.append(rest[:start])
        rest = rest[end + len(NOVELTY_SKIP_CLOSE):]
    return "".join(parts), unclosed


def _novelty_ok_slugs(text):
    """Слаги из всех маркеров lint:novelty-ok этого файла.

    Маркер действует на файл целиком, а не на строку: строчная точность
    потребовала бы разбирать markdown, а выигрыш нулевой — файлов в корпусе
    два десятка, и лишний маркер виден глазами при ревью.
    """
    return set(NOVELTY_OK.findall(text))


def _early_use_problems(terms, corpus):
    """Правило 3: слово не звучит раньше акта, в котором объясняется.

    Гранулярность — акт, а не квест, и это не упрощение, а единственный
    честный вариант: статические файлы поактовые, а `## Квест NN` есть не у
    каждого квеста. Выдумывать квестовую гранулярность разбором заголовков
    регулярками — признак беды, а не решение.

    Правило **не требует**, чтобы термин где-то встречался. Шесть терминов
    (interface, script, localhost, subagent, dependencies, hook) намеренно не
    лежат ни в одном нашем файле: они заведены под лут, чтобы хук поймал их в
    речи модели. Правило, требующее присутствия, заставило бы впихнуть слова
    в тексты и убило бы замер.

    Сообщается **первое** незамаскированное вхождение каждого термина, а не
    все: чинится всё равно первое, а маскировка первого открывает следующее —
    поэтому линтер гоняется до зелёного, а не один раз.
    """
    problems = []
    alias_pattern = _load_alias_pattern()
    if alias_pattern is None:
        return [
            "не удалось загрузить _alias_pattern из {} — правило 3 не "
            "работало".format(LOOT_HOOK)
        ]

    scanned = []
    for label, position, path in corpus:
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError:
            # Файла нет — пропускаем молча. Корпус описывает поставку целиком,
            # а линтер гоняют и по синтетическому дереву без половины файлов.
            continue
        except UnicodeDecodeError:
            problems.append("{}: файл не в UTF-8".format(label))
            continue
        stripped, unclosed = _strip_novelty_regions(raw)
        if unclosed:
            problems.append(
                "{}: маркер {} открыт и не закрыт — регион не вырезан, "
                "закройте его {}".format(
                    label, NOVELTY_SKIP_OPEN, NOVELTY_SKIP_CLOSE
                )
            )
        scanned.append((label, position, stripped, _novelty_ok_slugs(raw)))

    known = set(term.term for term in terms)
    for label, _, _, slugs in scanned:
        for slug in sorted(slugs):
            if slug not in known:
                problems.append(
                    "{}: маркер lint:novelty-ok называет '{}', а такого "
                    "термина нет".format(label, slug)
                )

    for term in sorted(terms, key=lambda item: (item.act, item.term)):
        for label, position, text, slugs in scanned:
            if term.term in slugs:
                # Разрешено вручную: ищем дальше, а не считаем это первым
                # вхождением — иначе маркер прятал бы и следующие файлы.
                continue
            hits = [alias for alias in term.aliases
                    if alias_pattern(alias).search(text)]
            if not hits:
                continue
            if position < term.act:
                problems.append(
                    "{}: акт {}, а слово впервые звучит в {} (позиция {}) — "
                    "{}".format(
                        term.term, term.act, label, position, ", ".join(hits)
                    )
                )
            break
    return problems


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(argv[0]) if argv else DEFAULT_ROOT
    problems = lint(root)
    if not problems:
        print("Контент чистый: {}".format(root))
        return 0
    print("Проблемы в контенте ({}):".format(root))
    for problem in problems:
        print("  - {}".format(problem))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

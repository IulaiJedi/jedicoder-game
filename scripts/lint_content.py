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

## Правила простого языка (спека #64)

Шесть правил из `content/ru/language.md` — фраза до SENTENCE_MAX слов,
запрещённые образы, катсцена в две фразы, слова не раньше первого ранга,
карточка в две строки, приём с приставкой `/jedicoder:` — меряются теми же единицами категории A плюс телами
рецептов; образы и ранние слова ищутся ещё и в скиллах, `start.md` и
`behavior.md` целиком, потому что модель пересказывает их падавану. Единицы,
ещё не переписанные под правила, перечислены в `LEGACY` явно: список только
убывает, и снимок в тестах это держит. Маркер `lint:language-ok` устроен как
`lint:novelty-ok` — декларация с причиной, на файл, на одно правило.
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

# Минимальная длина катсцены. Верх держит правило `cutscene` (две фразы,
# language.md), поэтому нижний порог ловит только пустое или обрезанное
# тело: две фразы короче 60 символов не бывает. Катсцены Актов 2–5 до
# переписывания (#72) длиннее, и потерю абзаца в них порог не заметит —
# долг №13 в CLAUDE.md.
ACT_BODY_MIN = 60

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


def lint(content_root, skills_root=None, corpus=None, legacy=None,
         commands_root=None):
    """Вернуть список проблем. Пустой список — контент чистый.

    `legacy` — список исключений правил языка; None — поставочный LEGACY,
    пустой словарь — проверять всё (так тесты и считают, что в списке
    ничего лишнего).
    """
    problems = []
    terms = _safe(content.load_terms, content_root, problems)
    rules = _safe(content.load_rules, content_root, problems)
    recipes = _safe(content.load_recipes, content_root, problems)
    # act_items, а не acts: имя модуля с реестром квестов занято импортом.
    act_items = _safe(content.load_acts, content_root, problems)
    onboarding = _safe(content.load_onboarding, content_root, problems)
    remarks = _safe(content.load_remarks, content_root, problems)
    instructions = _safe(content.load_instructions, content_root, problems)
    roadmaps = _safe(content.load_roadmaps, content_root, problems)
    if problems:
        return problems

    problems += _behavior_problems(content_root)
    problems += _duplicate_ids(terms, "term")
    problems += _duplicate_ids(rules, "rule")
    problems += _duplicate_ids(recipes, "recipe")
    problems += _duplicate_ids(remarks, "event")
    problems += _duplicate_ids(instructions, "artifact")
    problems += _duplicate_ids(roadmaps, "track")
    problems += _alias_collisions(terms)
    problems += _act_problems(act_items)
    problems += _onboarding_problems(onboarding)
    problems += _remark_problems(remarks)
    problems += _instruction_problems(instructions)
    problems += _roadmap_problems(roadmaps)
    problems += _length_problems(
        act_items, rules, recipes, terms, onboarding, remarks,
        DEFAULT_SKILLS_ROOT if skills_root is None else Path(skills_root),
    )
    problems += _novelty_problems(terms)
    problems += _early_use_problems(
        terms,
        ordered_corpus(content_root, skills_root) if corpus is None else corpus,
    )
    problems += _language_problems(
        _language_units(
            content_root,
            DEFAULT_SKILLS_ROOT if skills_root is None else Path(skills_root),
            DEFAULT_COMMANDS_ROOT if commands_root is None else Path(commands_root),
            terms, rules, recipes, act_items, onboarding, remarks,
            instructions, roadmaps,
        ),
        LEGACY if legacy is None else legacy,
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


def _instruction_problems(items):
    """Состав инструкций артефактов: файл на каждый артефакт реестра.

    Линтер сверяет **состав**, а не текст. Понятна ли инструкция, годится
    ли она коллеге падавана и не проговорилась ли она словом игры — это
    читает автор, и прибора для этого нет. А вот дыра в составе не видна
    глазами вовсе: Свиток соберётся на файл короче, промолчит об этом, и
    заметит человек, у которого инструкции уже нет.

    Реестр берётся из движка (ranks.ALL_ARTIFACTS) — второго списка имён в
    проекте быть не должно, иначе новый артефакт появится в одном перечне
    и не появится в другом.

    Ни VERBATIM_MAX, ни правило новизны сюда не применяются намеренно:
    инструкцию человек читает у себя в проекте и в своём темпе, а не
    слышит репликой в терминале. Потолок реплики запретил бы полноценный
    текст ровно там, где он и нужен.
    """
    problems = []
    known = set(ranks.ALL_ARTIFACTS)
    seen = set(item.artifact for item in items)
    missing = [name for name in ranks.ALL_ARTIFACTS if name not in seen]
    if missing:
        problems.append(
            "нет инструкций для артефактов: {}".format(", ".join(missing))
        )
    for item in items:
        name = item.path.name
        if item.artifact not in known:
            problems.append(
                "{}: artifact '{}' — такого артефакта в игре нет, "
                "инструкция обещает несуществующее".format(name, item.artifact)
            )
        elif item.artifact != item.path.stem:
            problems.append(
                "{}: artifact '{}' не совпадает с именем файла".format(
                    name, item.artifact
                )
            )
    return problems


def _roadmap_problems(items):
    """Состав дорожных карт: карта на каждый трек и одна для не выбравшего.

    Проверяется состав, а не текст, — по той же причине, что у инструкций:
    годится ли карта, читает автор, а прибора для этого нет. Зато дыра в
    составе не видна вовсе. Движок ищет карту по слагу трека из сохранения,
    не нашёл — молчит, и Свиток выдаётся на файл короче; заметит это
    человек, у которого карты уже нет.

    Реестр треков берётся из движка (acts.TRACKS) — второго списка имён в
    проекте быть не должно. Карта TRACK_ANY в реестр не входит и входить не
    может: это не третья дорога через игру, а карта для того, кто дорогу
    ещё не выбрал, — а Свиток выдаётся на любом ранге, в том числе до
    выбора.
    """
    problems = []
    # Реестр движка, а не копия схемы: линтер импортирует acts и обязан
    # сверять состав с ним. Совпадение самой копии (content.ROADMAP_TRACKS)
    # держит тест сверки.
    expected = tuple(acts.TRACKS) + (content.TRACK_ANY,)
    seen = set(item.track for item in items)
    missing = [track for track in expected if track not in seen]
    if missing:
        problems.append(
            "нет дорожных карт для треков: {}".format(", ".join(missing))
        )
    for item in items:
        name = item.path.name
        if item.track not in expected:
            problems.append(
                "{}: track '{}' — такого трека в игре нет, карта не "
                "достанется никому".format(name, item.track)
            )
        elif item.track != item.path.stem:
            problems.append(
                "{}: track '{}' не совпадает с именем файла".format(
                    name, item.track
                )
            )
        if "{url}" not in item.lead_url:
            problems.append(
                "{}: в lead_url нет '{{url}}' — эта строка звучит, когда "
                "адрес продукта известен, и обязана его называть".format(name)
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


def _load_example_prefix():
    """Префикс строки примера из хука лута (EXAMPLE_PREFIX). None — не вышло.

    По этой строке правило card видит, что у термина есть `example`:
    меряется итоговая карточка, а не файл, и литерал живёт в одном месте —
    в хуке, который её печатает.
    """
    return getattr(_loot_module(), "EXAMPLE_PREFIX", None)


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


# --- Правила простого языка (спека #64, тикет #65). ----------------------
#
# Пределы живут здесь и в content/ru/language.md; тесты сверяют, что
# документ называет те же числа и те же слова, что и прибор.

# Потолок длины фразы в словах. Включительный: ровно 15 — норма, 16 — дефект.
SENTENCE_MAX = 15

# Катсцена акта — две фразы: что делаем и зачем; дальше список квестов.
CUTSCENE_SENTENCES_MAX = 2

# Карточка нового слова в терминале — две строки после заголовка: что это
# и пример. «Зачем» и «проверь себя» остаются на Полке и в Книге.
CARD_LINES_MAX = 2

# Позиция, на которой падаван получает первый ранг: закрытие первого
# играемого акта. Всё, что читается на этой позиции и раньше, — до ранга.
FIRST_RANK_POSITION = min(ranks.playable_acts())

# Идентификаторы правил — ими помечаются исключения в LEGACY и в маркере.
RULE_SENTENCE = "sentence"
RULE_IMAGES = "images"
RULE_CUTSCENE = "cutscene"
RULE_EARLY = "early"
RULE_CARD = "card"
RULE_PREFIX = "prefix"
LANGUAGE_RULES = (
    RULE_SENTENCE, RULE_IMAGES, RULE_CUTSCENE, RULE_EARLY, RULE_CARD, RULE_PREFIX,
)
# Правила для текста, который модель пересказывает (скиллы, start.md,
# behavior.md): длину фразы там не меряем — меряем источник, а не пересказ.
PROSE_RULES = (RULE_IMAGES, RULE_EARLY, RULE_PREFIX)

# Маркер-исключение по образцу lint:novelty-ok: действует на файл целиком,
# на одно названное правило, и обязан нести причину в том же комментарии.
LANGUAGE_OK = re.compile(r"<!--\s*lint:language-ok:\s*([a-z]+)")

# Запрещённые образы метафоры. Регистр первой буквы — классом символов, а
# не lower(): складывание регистра кириллицы зависит от локали. Границы
# слова `\b` в Python идут по Unicode и кириллицу понимают: «мечта» и
# «замечать» под «меч» не попадают. «Сила» запрещена только как имя, с
# заглавной: «сила привычки» — обычное слово. «Джедайкодер» — имя игры,
# и лукахед его выпускает.
FORBIDDEN_IMAGES = (
    ("меч", r"\b[Мм]еч(?:а|у|ом|е|и|ей|ам|ами|ах)?\b"),
    ("рукоять", r"\b[Рр]укоят\w*"),
    ("Сила", r"\bСил(?:а|ы|е|у|ой|ою)\b"),
    ("джедай", r"\b[Дд]жеда(?!йкодер)\w*"),
    ("ситх", r"\b[Сс]итх\w*"),
    ("Тёмная сторона", r"\b[Тт][её]мн\w*\s+сторон\w*"),
    ("светлая сторона", r"\b[Сс]ветл\w*\s+сторон\w*"),
)

# Слова, которым рано звучать до первого ранга (ADR-0014): Книга и привязка
# — одним предложением после ранга Искатель, клуб — только в финале;
# «Тёмная сторона», «артефакт» и «Свиток» заменены штрафами, приёмом и
# памяткой везде, но в ранних текстах их отсутствие держится и этим правилом.
EARLY_WORDS = (
    ("Тёмная сторона", r"\b[Тт][её]мн\w*\s+сторон\w*"),
    ("артефакт", r"\b[Аа]ртефакт\w*"),
    ("Свиток", r"\b[Сс]вит(?:ок|к[а-я]+)\b"),
    ("Книга", r"\b[Кк]ниг(?:а|и|е|у|ой|ою)\b"),
    ("клуб", r"\b[Кк]луб(?:а|е|у|ом|ы|ов|ам|ами|ах)?\b"),
    ("бот потока", r"\b[Бб]от\w*\s+потока\b"),
    ("привязка", r"\b[Пп]ривязк\w*"),
)

# Приёмы зовутся с приставкой плагина: голого `/brainstorm` в Claude Code
# нет, команды плагина живут только как `/jedicoder:<имя>`, и новичок в
# прогоне 2026-09-13 набрал `/brainstorm` и не нашёл. Имена — реестр приёмов
# плюс `magistr`: седьмой приём попадёт под правило сам. Слэш, перед которым
# стоит буква, двоеточие или другой слэш, — путь или адрес
# (`docs/jedicoder/plan.md`, `https://домен/deploy`), а не команда; слово
# после имени (`/planet`) отрезается границей. Обратные кавычки не
# спасают: падаван копирует команду из них.
PREFIXED_COMMANDS = tuple(ranks.ALL_ARTIFACTS) + ("magistr",)
BARE_COMMAND = re.compile(
    r"(?<![\w:/])/(?:{})(?![\w:-])".format(
        "|".join(re.escape(name) for name in PREFIXED_COMMANDS)
    )
)

# Разметка, по которой текст режется на фразы. Код и адреса ссылок
# маскируются символами той же длины: точки внутри `a.b` фразу не режут,
# а слова внутри не считаются — и при этом фраза для отчёта вырезается из
# оригинала, а не из маски.
CODE_SPAN = re.compile(r"`[^`\n]+`")
MD_LINK_TARGET = re.compile(r"\]\([^)\s]*\)")
HEADING_LINE = re.compile(r"^\s{0,3}#{1,6}\s")
LIST_MARKER = re.compile(r"^\s*(?:[-*+—]|\d+[.)])\s+")
FENCE_LINE = re.compile(r"^\s{0,3}(?:```|~~~)")
INDENTED_CODE = re.compile(r"^(?: {4}|\t)")
QUOTE_MARKER = re.compile(r"^\s*>\s?")
TABLE_LINE = re.compile(r"^\s*\|")
PHRASE_END = re.compile(r"[.!?…]+[»”\")\]]*(?=\s|$)")
WORD = re.compile(r"\w")

# Единицы, ещё не переписанные под правила языка: подпись единицы →
# правила, которые для неё пока не проверяются. Список опустел тикетом #72
# и остаётся пустым: тест в tests/test_lint_language.py падает на любой
# записи. Исключение по делу — маркер lint:language-ok на файл, с причиной.
LEGACY = {}


def _mask(text):
    """Скрыть код и адреса ссылок под символами той же длины."""
    def blank(match):
        return "\x00" * len(match.group(0))
    return MD_LINK_TARGET.sub(blank, CODE_SPAN.sub(blank, text))


def _blocks(text):
    """Куски текста, внутри которых фраза может продолжаться.

    Абзац — один кусок; пункт списка (в том числе через тире) и строка
    таблицы — свои куски, потому что точки в конце у них обычно нет, а фразы
    разные; заголовок — не фраза вовсе, это подпись. Блоки кода — в
    ограде из кавычек или с отступом в четыре пробела — не текст: команды и
    вывод терминала словами не считаются, как и код в обратных кавычках.
    """
    blocks = []
    current = []
    in_fence = False

    def close():
        if current:
            blocks.append(" ".join(current))
            del current[:]

    for line in visible_text(text).split("\n"):
        stripped = line.strip()
        if FENCE_LINE.match(line):
            close()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped or HEADING_LINE.match(line):
            close()
            continue
        if INDENTED_CODE.match(line) and not current:
            continue
        if TABLE_LINE.match(line):
            close()
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            blocks.append(" ".join(cell for cell in cells if cell))
            continue
        marker = LIST_MARKER.match(line)
        if marker is not None:
            close()
            current.append(line[marker.end():].strip())
            continue
        quote = QUOTE_MARKER.match(line)
        if quote is not None:
            line = line[quote.end():]
        current.append(line.strip())
    close()
    return blocks


def phrases(text):
    """Фразы текста: режутся по `.`, `!`, `?`, `…` вне кода и ссылок."""
    result = []
    for block in _blocks(text):
        masked = _mask(block)
        start = 0
        for match in PHRASE_END.finditer(masked):
            if WORD.search(masked[start:match.end()]):
                result.append(block[start:match.end()].strip())
            start = match.end()
        if WORD.search(masked[start:]):
            result.append(block[start:].strip())
    return result


def word_count(phrase):
    """Слова фразы — по пробелам; код, ссылки и знаки без букв не в счёт."""
    return sum(1 for token in _mask(phrase).split() if WORD.search(token))


def long_sentences(text, limit=SENTENCE_MAX):
    """Фразы длиннее limit слов, в порядке текста."""
    return [phrase for phrase in phrases(text) if word_count(phrase) > limit]


def sentence_count(text):
    """Сколько фраз в тексте — по тем же правилам разреза."""
    return len(phrases(text))


def _matches(text, patterns):
    """Найденные образцы в порядке списка, каждое написание один раз."""
    masked = _mask(visible_text(text))
    hits = []
    for _, pattern in patterns:
        for match in re.finditer(pattern, masked):
            found = match.group(0)
            if found not in hits:
                hits.append(found)
    return hits


def forbidden_images(text, patterns=FORBIDDEN_IMAGES):
    """Образы метафоры, найденные в тексте, как они написаны."""
    return _matches(text, patterns)


def early_words(text, patterns=EARLY_WORDS):
    """Слова, которым рано звучать до первого ранга, как они написаны."""
    return _matches(text, patterns)


def bare_commands(text):
    """Приёмы, названные без приставки плагина: `/plan` вместо `/jedicoder:plan`."""
    return BARE_COMMAND.findall(text)


def early_words_problems(units, patterns=EARLY_WORDS,
                         first_rank_position=FIRST_RANK_POSITION):
    """Правило (г) на единицах (подпись, позиция, текст): проблемы строками."""
    problems = []
    for label, position, text in units:
        if position > first_rank_position:
            continue
        for hit in early_words(text, patterns):
            problems.append(
                "{}: «{}» звучит рано — на позиции {} падаван ещё без ранга, "
                "и это слово ему не объяснено".format(label, hit, position)
            )
    return problems


def card_line_count(rendered):
    """Строки карточки после заголовка «✦ Новое слово»; пустые не в счёт."""
    lines = [line for line in rendered.split("\n") if line.strip()]
    return max(len(lines) - 1, 0)


def card_has_example(rendered, prefix=None):
    """Есть ли в карточке строка примера — та, что печатается из `example`."""
    prefix = _load_example_prefix() if prefix is None else prefix
    if not prefix:
        return True  # хук не загрузился — об этом уже сказано отдельно
    return any(line.strip().startswith(prefix) for line in rendered.split("\n"))


def _skill_position(name):
    """Позиция скилла в потоке: акт по слагу или по имени приёма, иначе 0.

    Ноль — строжайшая позиция, и она же честная для core и magistr: оба
    доступны с первой сессии.
    """
    for number, info in ranks.ACTS.items():
        if name in (info["slug"], info["artifact"]):
            return number
    return 0


def _read_or_empty(path):
    """Текст файла; нечитаемый — пустая строка, о нём скажет _unreadable."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _language_units(content_root, skills_root, commands_root,
                    terms, rules, recipes, act_items, onboarding, remarks,
                    instructions=(), roadmaps=()):
    """Единицы правил языка: (подпись, позиция, текст, путь, правила).

    Категория A и тела рецептов меряются всеми правилами, что к ним
    применимы; врезки скиллов — только длиной фразы, потому что образы и
    ранние слова ищутся в SKILL.md целиком: модель пересказывает и обычный
    текст скилла, не только цитату. Карточка термина меряется тем же
    render_card, которым печатается, — правило (д) про итоговую строку.
    """
    verbatim = (RULE_SENTENCE, RULE_IMAGES, RULE_EARLY, RULE_PREFIX)
    units = []
    for item in act_items:
        units.append((
            "катсцена " + item.slug, item.act, item.body, item.path,
            verbatim + (RULE_CUTSCENE,),
        ))
    for item in rules:
        # Правило Кодекса о штрафах показывает хук с первой сессии.
        position = 0 if item.dark_side else item.act
        units.append(("правило " + item.rule, position, item.body, item.path, verbatim))
    for item in recipes:
        units.append(("рецепт " + item.recipe, RECIPE_POSITION, item.body, item.path, verbatim))
    for item in onboarding:
        units.append(("узел " + item.node, 0, item.body, item.path, verbatim))
    # Памятка и дорожная карта читаются вне игры (человеком без плагина),
    # поэтому слова до ранга там не меряются — «клуб» на карте законен, это
    # финал; длина фразы, образы и приставка — меряются.
    for item in instructions:
        units.append((
            "инструкция " + item.artifact, len(ranks.ACTS), item.body, item.path,
            (RULE_SENTENCE, RULE_IMAGES, RULE_PREFIX),
        ))
    for item in roadmaps:
        units.append((
            "карта " + item.track, len(ranks.ACTS), item.body, item.path,
            (RULE_SENTENCE, RULE_IMAGES, RULE_PREFIX),
        ))
    for item in remarks:
        position = REMARK_POSITION.get(item.event, 0)
        for number, text in enumerate(item.variants, 1):
            units.append((
                "реплика {} №{}".format(item.event, number), position, text,
                item.path, verbatim,
            ))
    render_card = _load_render_card()
    if render_card is not None:
        for term in terms:
            # Строки карточки — отдельные абзацы: терминал печатает их как
            # есть, и продолжением одной фразы соседняя строка не является.
            card = "\n\n".join(render_card(term).split("\n"))
            units.append((
                "карточка " + term.term, term.act, card, term.path,
                verbatim + (RULE_CARD,),
            ))
    skills_root = Path(skills_root)
    if skills_root.is_dir():
        for path in sorted(skills_root.glob("**/SKILL.md")):
            name = path.parent.name
            position = _skill_position(name)
            raw = _read_or_empty(path)
            units.append(("SKILL " + name, position, raw, path, PROSE_RULES))
            for number, block in enumerate(_quote_blocks(raw), 1):
                units.append((
                    "врезка {} №{}".format(name, number), position, block, path,
                    (RULE_SENTENCE,),
                ))
    for label, path in (
        ("start.md", Path(commands_root) / "start.md"),
        (BEHAVIOR_FILE, Path(content_root) / BEHAVIOR_FILE),
    ):
        if path.is_file():
            units.append((label, 0, _read_or_empty(path), path, PROSE_RULES))
    return units


def _language_findings(units):
    """Находки правил языка без учёта LEGACY: (подпись, правило, текст)."""
    findings = []
    allowed_by_path = {}
    for label, position, text, path, applicable in units:
        if path not in allowed_by_path:
            names = set(LANGUAGE_OK.findall(_read_or_empty(path)))
            for name in sorted(names - set(LANGUAGE_RULES)):
                findings.append((
                    label, "marker",
                    "{}: маркер lint:language-ok называет правило '{}', а "
                    "правила такие: {}".format(
                        Path(path).name, name, ", ".join(LANGUAGE_RULES)
                    ),
                ))
            allowed_by_path[path] = names
        allowed = allowed_by_path[path]
        rules = [rule for rule in applicable if rule not in allowed]
        if RULE_SENTENCE in rules:
            for phrase in long_sentences(text):
                findings.append((label, RULE_SENTENCE,
                    "{}: фраза из {} слов при пределе {} — «{}»".format(
                        label, word_count(phrase), SENTENCE_MAX, _clip(phrase)
                    )))
        if RULE_IMAGES in rules:
            for hit in forbidden_images(text):
                findings.append((label, RULE_IMAGES,
                    "{}: образ метафоры «{}» — объяснения пишутся без "
                    "образов (language.md)".format(label, hit)))
        if RULE_CUTSCENE in rules:
            count = sentence_count(text)
            if count > CUTSCENE_SENTENCES_MAX:
                findings.append((label, RULE_CUTSCENE,
                    "{}: {} фраз при пределе {} — катсцена это две фразы и "
                    "список квестов".format(label, count, CUTSCENE_SENTENCES_MAX)))
        if RULE_EARLY in rules:
            for problem in early_words_problems([(label, position, text)]):
                findings.append((label, RULE_EARLY, problem))
        if RULE_PREFIX in rules:
            for hit in bare_commands(text):
                findings.append((label, RULE_PREFIX,
                    "{}: приём назван без приставки — «{}»; в Claude Code "
                    "команда плагина это /jedicoder:{} (language.md)".format(
                        label, hit, hit.lstrip("/"))))
        if RULE_CARD in rules:
            count = card_line_count(text)
            if count > CARD_LINES_MAX:
                findings.append((label, RULE_CARD,
                    "{}: {} строк после заголовка при пределе {} — карточка в "
                    "терминале это что-это и пример".format(
                        label, count, CARD_LINES_MAX)))
            if not card_has_example(text):
                findings.append((label, RULE_CARD,
                    "{}: нет поля example — вторая строка карточки в "
                    "терминале, пример из жизни (language.md)".format(label)))
    return findings


def _clip(phrase, limit=70):
    """Начало фразы для отчёта: автор найдёт её поиском, а строка не разбухнет."""
    phrase = " ".join(phrase.split())
    return phrase if len(phrase) <= limit else phrase[:limit].rstrip() + "…"


def _language_problems(units, legacy):
    """Находки правил языка минус LEGACY, строками для отчёта."""
    return [
        message
        for label, rule, message in _language_findings(units)
        if rule not in legacy.get(label, ())
    ]


def language_findings(content_root, skills_root=None, commands_root=None):
    """Все находки правил языка по поставке, без LEGACY: (подпись, правило, текст).

    Публична для теста, который держит LEGACY честным: каждая пара из
    списка обязана всё ещё находиться, иначе она давно снята.
    """
    content_root = Path(content_root)
    return _language_findings(_language_units(
        content_root,
        DEFAULT_SKILLS_ROOT if skills_root is None else Path(skills_root),
        DEFAULT_COMMANDS_ROOT if commands_root is None else Path(commands_root),
        content.load_terms(content_root),
        content.load_rules(content_root),
        content.load_recipes(content_root),
        content.load_acts(content_root),
        content.load_onboarding(content_root),
        content.load_remarks(content_root),
        _optional(content.load_instructions, content_root),
        _optional(content.load_roadmaps, content_root),
    ))


def _optional(loader, content_root):
    """Раздел, которого у синтетического дерева может не быть: тогда пусто.

    Состав и схему разделов держит lint(); здесь только тексты."""
    try:
        return loader(content_root)
    except (OSError, content.ContentError):
        return ()


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

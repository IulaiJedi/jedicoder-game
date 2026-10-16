"""Загрузка контент-ядра: термины, правила Кодекса, рецепты, катсцены актов,
узлы онбординга (Акт 0), реплики Магистра, инструкции артефактов,
дорожные карты.

Валидация здесь строгая и падает на первой ошибке: контент — часть
поставки, битый файл должен ловиться линтером в CI, а не на машине
падавана посреди акта.
"""
import re
from dataclasses import dataclass
from pathlib import Path

from .frontmatter import FrontmatterError, parse

CATEGORIES = ("git", "server", "ai", "product", "web", "security", "money")
SEVERITIES = ("high", "medium", "low")
DEPLOY_PATHS = ("managed", "vps")

# Разделы Акта 0. Акт 0 не имеет номера квеста и в ranks.ACTS не входит
# (D-10): движок акта с номером 0 не знает, и добавление ключа задело бы
# ranks.ACTS, QUESTS_BY_ACT и export_acts.py. Раздел — это единственная
# разметка, по которой узел можно опознать без разбора дерева.
ONBOARDING_SECTIONS = ("install", "check", "trouble", "first-session", "link")

TERM_REQUIRED = ("term", "title", "aliases", "act", "category", "xp", "example")
RULE_REQUIRED = ("rule", "title", "act", "severity", "xp")
RECIPE_REQUIRED = ("recipe", "title", "stack", "deploy_path")
ACT_REQUIRED = (
    "act", "slug", "title", "rank", "rank_title", "artifact", "axis", "muted",
    "quests", "quest_titles", "quest_branches",
)
# options и option_titles в обязательные НЕ входят: терминальный узел — узел
# без выхода, и требовать у него список переходов значило бы запретить дереву
# заканчиваться.
ONBOARDING_REQUIRED = ("node", "title", "order", "section")
# У реплики одно поле метаданных — событие. Заголовка нет намеренно: его
# никто не читает, а заметка о том, когда реплика звучит, живёт во
# фронтматтере строкой-комментарием `# …`, которую парсер пропускает.
REMARK_REQUIRED = ("event",)

# Инструкция артефакта: имя артефакта, заголовок и строка для оглавления.
# Список имён артефактов здесь НЕ объявляется, и это отличие от ACT_RANKS и
# MAGISTR_EVENTS сознательное: те копии малы и заморожены, а реестр
# артефактов живёт в ranks.py и растёт вместе с игрой. Копия расходилась бы
# с ним молча. Состав раздела сверяет с реестром линтер — он ranks и так
# импортирует; загрузчику остаётся схема.
INSTRUCTION_REQUIRED = ("artifact", "title", "summary")

# Дорожная карта: три шага, чтобы довести продукт до людей. Карта на трек,
# плюс одна на того, кто трек ещё не выбрал, — её слаг TRACK_ANY, и он
# нарочно не похож на слаг трека: это не третья дорога через игру, а карта
# для того, у кого дороги пока нет.
#
# Слаги треков объявлены ЗДЕСЬ копией, а не импортом из acts.py, — по той же
# причине, что ACT_RANKS и BRANCHES_BY_AXIS: acts.py берёт из content.py
# (DEPLOY_PATHS), и обратный импорт перевернул бы слоистость. Совпадение с
# acts.TRACKS держит тест сверки, а состав самого раздела — линтер.
#
# `lead` и `lead_url` — две вводные строки на выбор: адрес продукта известен
# или нет. Обе во фронтматтере, а не в теле, потому что обе — одна строка;
# подставляет адрес движок, потому что адрес лежит в сохранении.
TRACK_ANY = "any"
ROADMAP_TRACKS = ("craftsman", "founder", TRACK_ANY)
ROADMAP_REQUIRED = ("track", "title", "lead", "lead_url")

# События сцены, на которые у Магистра есть реплика: те же слова, что в
# очереди state.EVENT_TYPES, без служебных (state.SILENT_EVENTS: привязка к
# боту и выдача Свитка — не события пути, сцена на них не отзывается).
# Копия, а не импорт, по причине ACT_RANKS: content.py — нижний слой схемы,
# совпадение держит тест.
MAGISTR_EVENTS = (
    "act_started", "quest_completed", "quest_failed", "rank_up",
    "term_unlocked", "dark_side", "streak_updated", "product_deployed",
    "finale",
)

# Допустимые ранги объявлены ЗДЕСЬ, а не импортированы из ranks.py:
# content.py — нижний слой схемы, из него берёт acts.py (DEPLOY_PATHS), и
# обратный импорт перевернул бы слоистость. Совпадение с ranks.RANK_TITLES
# держит линтер, а не импорт.
ACT_RANKS = ("seeker", "padawan", "knight", "sentinel", "master")

# Самоописание акта: ось развилки и ветка каждого квеста. Те же слова, что
# в реестре движка (acts.TRACKS, acts.DEPLOYS, acts.BRANCH_BOTH,
# acts.AXIS_DEPLOY), и по той же причине, что ACT_RANKS, объявлены здесь, а
# не импортированы: acts.py берёт из content.py, обратный импорт запрещён.
# Совпадение словарей держат линтер и тест сверки, а не импорт. Ради этого
# поля и заведены: чтобы Голокрон и сайт собирали доску квестов из
# контента, не зная реестра движка.
AXES = ("track", "deploy")
# Ветки, допустимые на каждой оси: общая both плюс имена выбора падавана по
# этой оси — трек или путь деплоя. Ветка чужой оси — ошибка схемы, а не
# просто незнакомое слово: у одного акта не бывает квестов, ветвящихся по
# разным осям (см. acts.ACT_AXIS), и читатель без движка обязан это знать
# из самой схемы.
BRANCHES_BY_AXIS = {
    "track": ("both", "craftsman", "founder"),
    "deploy": ("both",) + DEPLOY_PATHS,
}

MIN_ACT = 0
MAX_ACT = 5

# Пример из жизни в карточке термина — одна фраза не длиннее, чем фраза по
# правилам языка (language.md, «Размеры»; в линтере — SENTENCE_MAX).
EXAMPLE_WORDS_MAX = 15
_WORD = re.compile(r"\w")
# Команды в обратных кавычках словами не считаются (language.md, правило 2)
# — тот же счёт, что у линтера: два прибора на одно число разойдутся молча.
_CODE_SPAN = re.compile(r"`[^`\n]+`")
# Конец фразы, за которым идёт следующая: «. Слово». Многоточие внутри
# фразы — тоже конец: пример на две фразы не помещается во вторую строку.
_NEXT_PHRASE = re.compile(r'[.!?…]+[»”")\]]*\s+\S')


class ContentError(ValueError):
    """Файл контента не проходит валидацию схемы."""


@dataclass(frozen=True)
class Term:
    term: str
    title: str
    aliases: tuple
    act: int
    category: str
    xp: int
    body: str
    path: Path
    rank: str = ""
    related: tuple = ()
    # Точка введения: id квеста внутри act. Необязательное и объявляется
    # последним среди необязательных — позиционные вызовы Term(...) не поедут.
    # В TERM_REQUIRED не входит: Акты 4-5 в охват аудита языка не включены,
    # обязательность заставила бы проставить поле всем 55 терминам.
    quest: str = ""
    # Пример из жизни для карточки в терминале — вторая из двух строк
    # (language.md, «Размеры»). Одна фраза до EXAMPLE_WORDS_MAX слов.
    # В TERM_REQUIRED с тикета #72: все термины поставки его несут, и термин
    # без примера не доедет до карточки. Значение по умолчанию — для тестов,
    # которые собирают Term руками.
    example: str = ""


@dataclass(frozen=True)
class Rule:
    rule: str
    title: str
    act: int
    severity: str
    xp: int
    body: str
    path: Path
    dark_side: bool = False


@dataclass(frozen=True)
class Recipe:
    recipe: str
    title: str
    stack: tuple
    deploy_path: str
    body: str
    path: Path
    reference_repo: str = ""


@dataclass(frozen=True)
class Act:
    act: int
    slug: str
    title: str
    rank: str
    rank_title: str
    artifact: str
    axis: str
    # Акт выключен: в игру не пускает, человеку о нём говорят «готовится».
    # Истина — ranks.MUTED_ACTS, здесь её копия для читателей без движка
    # (Голокрон); совпадение держит линтер.
    muted: bool
    quests: tuple
    quest_titles: tuple
    # Ветка каждого квеста, по одной на позицию quests: both — в обеих
    # ветках оси, иначе имя трека (ось track) или пути деплоя (ось deploy).
    quest_branches: tuple
    body: str
    path: Path
    # Задание каждого квеста — одна фраза простыми словами, по одной на
    # позицию quests. Пусто у акта, которому заданий ещё не написали:
    # выключенные акты перестраиваются. Наличие у играбельного держит линтер.
    quest_tasks: tuple = ()


@dataclass(frozen=True)
class Onboarding:
    """Узел дерева Акта 0 — ровно одно сообщение бота и его кнопки.

    Схема нарочно плоская: скаляры и списки скаляров, потому что большего
    свой парсер фронтматтера не умеет и уметь не должен.

    Пара options / option_titles — тот же приём, что quests / quest_titles у
    актов, и с тем же ограничением: **в подписи кнопки не может быть
    запятой**. Долг №12 — `_scalar_or_list` режет inline-список по запятой
    ДО снятия кавычек, поэтому "Кому это, наконец, нужно" разорвётся на три
    куска. Ограничение обходится текстом подписи, а не парсером.
    """
    node: str
    title: str
    order: int
    section: str
    body: str
    path: Path
    probe: str = ""
    options: tuple = ()
    option_titles: tuple = ()


@dataclass(frozen=True)
class Remark:
    """Реплики Магистра на одно событие сцены — файл на событие.

    Варианты лежат в теле, а не в inline-списке фронтматтера, и это не
    вкус: в реплике есть запятые, а `_scalar_or_list` режет список по
    запятой до снятия кавычек (долг №12). Один вариант — один абзац тела и
    ровно одна физическая строка: реплика доезжает до падавана дословно,
    одной строкой на панели, и перенос внутри неё — сломанная строка, а не
    стиль. Голокрон выбирает вариант по порядковому номеру события за
    сессию, поэтому порядок вариантов — порядок абзацев.
    """
    event: str
    variants: tuple
    path: Path


@dataclass(frozen=True)
class Roadmap:
    """Дорожная карта одного трека — что делать с продуктом дальше.

    Живёт в `roadmap/`, файл на трек, имя файла — слаг трека. От инструкции
    отличается адресатом наоборот: инструкцию человек показывает коллеге,
    карту читает только он сам, и она говорит про его продукт, а не про
    приём работы.

    `lead` и `lead_url` — вводная строка на два случая: адреса у продукта
    нет и адрес есть. В `lead_url` стоит `{url}`, и подставляет его тот,
    кто печатает.
    """
    track: str
    title: str
    lead: str
    lead_url: str
    body: str
    path: Path


@dataclass(frozen=True)
class Phrases:
    """Готовые фразы одного акта для страницы памятки — «когда → что сказать».

    Живут в `phrases/`, файл на акт. Тело — строки таблицы, по строке на
    фразу: `| когда | что сказать |`. Заголовок страницы и шапку таблицы
    дописывает Свиток; слов игры в строках нет — памятка читается без
    плагина.
    """
    act: int
    rows: tuple
    path: Path


@dataclass(frozen=True)
class Instruction:
    """Инструкция артефакта — текст, который человек уносит из игры.

    Живёт в `scroll/`, файл на артефакт, имя файла — имя артефакта.
    Отличается от скилла того же имени не оформлением, а адресатом: скилл
    написан для модели и говорит словами игры, инструкция читается
    человеком и его коллегой на машине, где игра не установлена. Поэтому
    слов игры в ней нет вовсе — это её главное свойство, и держит его тест,
    а не схема.

    `summary` — строка для оглавления, одна на инструкцию. Поле заведено,
    чтобы оглавление собиралось из написанного автором, а не сочинялось
    заново тем, кто его печатает.
    """
    artifact: str
    title: str
    summary: str
    body: str
    path: Path


def load_terms(content_root):
    return _load_dir(Path(content_root) / "lexicon", _build_term)


def load_rules(content_root):
    return _load_dir(Path(content_root) / "codex", _build_rule)


def load_recipes(content_root):
    return _load_dir(Path(content_root) / "recipes", _build_recipe)


def load_acts(content_root):
    return _load_dir(Path(content_root) / "acts", _build_act)


def load_onboarding(content_root):
    """Узлы Акта 0 в порядке поля order.

    Отсутствие папки — не ошибка, а пустой список: линтер гоняют и по
    синтетическому дереву, где онбординга нет вовсе, и падать там ему не на
    чем. Пустоту поставки ловит не загрузчик, а генератор — он отказывается
    выпускать модуль без единого узла.
    """
    items = _load_dir(
        Path(content_root) / "onboarding", _build_onboarding, optional=True
    )
    return sorted(items, key=lambda item: item.order)


def load_remarks(content_root):
    """Реплики Магистра, по объекту на событие, в порядке имён файлов."""
    return _load_dir(Path(content_root) / "magistr", _build_remark)


def remarks_by_event(content_root):
    """Реплики по типу события: словарь event → Remark.

    Ключ — то же слово, что у события в очереди state.EVENT_TYPES:
    читатель, получивший событие, берёт реплику этим словом, а не листает
    список. Два файла на одно событие сюда не доедут — их отвергает линтер
    до поставки.
    """
    return {item.event: item for item in load_remarks(content_root)}


def load_phrases(content_root):
    """Готовые фразы по актам, в порядке номеров. Папки нет — пустой список:
    страница фраз часть памятки, а не её условие."""
    items = _load_dir(
        Path(content_root) / "phrases", _build_phrases, optional=True
    )
    return sorted(items, key=lambda item: item.act)


def load_roadmaps(content_root):
    """Дорожные карты, в порядке имён файлов."""
    return _load_dir(Path(content_root) / "roadmap", _build_roadmap)


def roadmaps_by_track(content_root):
    """Карты по слагу трека: словарь track → Roadmap.

    Ключ — то же слово, что в acts.TRACKS и в сохранении падавана; карту
    для не выбравшего трек держит ключ TRACK_ANY. Два файла на один трек
    сюда не доедут — их отвергает линтер до поставки.
    """
    return {item.track: item for item in load_roadmaps(content_root)}


def load_instructions(content_root):
    """Инструкции артефактов, в порядке имён файлов."""
    return _load_dir(Path(content_root) / "scroll", _build_instruction)


def instructions_by_artifact(content_root):
    """Инструкции по имени артефакта: словарь artifact → Instruction.

    Ключ — то же слово, что в ranks.ALL_ARTIFACTS: тот, кто собирает
    Свиток, берёт инструкцию именем артефакта, а не позицией в списке. Два
    файла на один артефакт сюда не доедут — их отвергает линтер до поставки.
    """
    return {item.artifact: item for item in load_instructions(content_root)}


def _load_dir(directory, build, optional=False):
    if not directory.is_dir():
        if optional:
            return []
        raise ContentError("нет папки {}".format(directory))
    items = []
    for path in sorted(directory.glob("*.md")):
        try:
            meta, body = parse(path.read_text(encoding="utf-8"))
        except FrontmatterError as exc:
            raise ContentError("{}: {}".format(path, exc))
        items.append(build(meta, body, path))
    return items


def _require(meta, keys, path):
    missing = [
        key for key in keys
        if key not in meta or meta[key] is None or meta[key] == "" or meta[key] == []
    ]
    if missing:
        raise ContentError(
            "{}: нет обязательных полей: {}".format(path, ", ".join(missing))
        )


def _require_body(body, path):
    if not body:
        raise ContentError("{}: пустое тело".format(path))


def _require_choice(meta, key, allowed, path):
    if meta[key] not in allowed:
        raise ContentError(
            "{}: {} '{}' не из списка {}".format(path, key, meta[key], allowed)
        )


def _require_list(meta, key, path):
    if not isinstance(meta[key], list):
        raise ContentError("{}: {} должен быть списком".format(path, key))


def _require_act(meta, path):
    act = meta["act"]
    if not isinstance(act, int) or not MIN_ACT <= act <= MAX_ACT:
        raise ContentError(
            "{}: act должен быть целым {}..{}, получено {!r}".format(
                path, MIN_ACT, MAX_ACT, act
            )
        )


def _require_example(meta, path):
    """Поле example — одна непустая фраза до EXAMPLE_WORDS_MAX слов.

    Наличие поля держит _require по TERM_REQUIRED; здесь — форма.
    """
    example = meta["example"]
    if not isinstance(example, str):
        raise ContentError(
            "{}: example должен быть строкой — одной фразой, примером из "
            "жизни; получено {!r}".format(path, example)
        )
    if not example.strip():
        raise ContentError(
            "{}: example пуст — вторая строка карточки в терминале, пример "
            "из жизни; убери поле или напиши фразу".format(path)
        )
    words = sum(
        1 for token in _CODE_SPAN.sub(" ", example).split() if _WORD.search(token)
    )
    if words > EXAMPLE_WORDS_MAX:
        raise ContentError(
            "{}: example из {} слов при пределе {} — это одна строка "
            "карточки в терминале, режь до одной фразы".format(
                path, words, EXAMPLE_WORDS_MAX
            )
        )
    if _NEXT_PHRASE.search(example.strip()):
        raise ContentError(
            "{}: example — одна фраза, а не несколько: вторая строка "
            "карточки в терминале".format(path)
        )


def _quest_tasks(meta, path):
    """Задания квестов: по одной фразе на квест, либо поля нет вовсе.

    Счёт слов и «одна фраза» — те же, что у example термина: задание
    печатается одной строкой списка квестов.
    """
    if "quest_tasks" not in meta:
        return ()
    _require_list(meta, "quest_tasks", path)
    tasks = meta["quest_tasks"]
    if len(tasks) != len(meta["quests"]):
        raise ContentError(
            "{}: заданий quest_tasks {}, а квестов {}. В задании не может "
            "быть запятой: парсер режет список по запятым раньше, чем "
            "снимает кавычки".format(path, len(tasks), len(meta["quests"]))
        )
    for task in tasks:
        if not isinstance(task, str) or not task.strip():
            raise ContentError(
                "{}: quest_tasks — пустое задание или не строка: {!r}".format(
                    path, task
                )
            )
        words = sum(
            1 for token in _CODE_SPAN.sub(" ", task).split() if _WORD.search(token)
        )
        if words > EXAMPLE_WORDS_MAX:
            raise ContentError(
                "{}: quest_tasks — задание из {} слов при пределе {}: "
                "{!r}".format(path, words, EXAMPLE_WORDS_MAX, task)
            )
        if _NEXT_PHRASE.search(task.strip()):
            raise ContentError(
                "{}: quest_tasks — задание это одна фраза, а не несколько: "
                "{!r}".format(path, task)
            )
    return tuple(tasks)


def _build_term(meta, body, path):
    _require(meta, TERM_REQUIRED, path)
    _require_body(body, path)
    _require_list(meta, "aliases", path)
    _require_choice(meta, "category", CATEGORIES, path)
    _require_act(meta, path)
    _require_example(meta, path)
    return Term(
        term=meta["term"],
        title=meta["title"],
        aliases=tuple(meta["aliases"]),
        act=meta["act"],
        category=meta["category"],
        xp=meta["xp"],
        body=body,
        path=path,
        rank=meta.get("rank") or "",
        related=tuple(meta.get("related") or ()),
        quest=meta.get("quest") or "",
        example=meta.get("example") or "",
    )


def _build_rule(meta, body, path):
    _require(meta, RULE_REQUIRED, path)
    _require_body(body, path)
    _require_choice(meta, "severity", SEVERITIES, path)
    _require_act(meta, path)
    return Rule(
        rule=meta["rule"],
        title=meta["title"],
        act=meta["act"],
        severity=meta["severity"],
        xp=meta["xp"],
        body=body,
        path=path,
        dark_side=bool(meta.get("dark_side", False)),
    )


def _build_act(meta, body, path):
    _require(meta, ACT_REQUIRED, path)
    _require_body(body, path)
    _require_act(meta, path)
    _require_choice(meta, "rank", ACT_RANKS, path)
    _require_choice(meta, "axis", AXES, path)
    # Строго булево: «yes» парсер прочёл бы непустой строкой, то есть истиной.
    if not isinstance(meta["muted"], bool):
        raise ContentError(
            "{}: muted должен быть true или false, получено {!r}".format(
                path, meta["muted"]
            )
        )
    _require_list(meta, "quests", path)
    _require_list(meta, "quest_titles", path)
    _require_list(meta, "quest_branches", path)
    # Ветка — из словаря своей оси, а не любая строка: опечатка в метке или
    # ветка чужой оси не уронила бы ничего, квест просто не попал бы ни в одну
    # ветку доски и исчез молча.
    allowed = BRANCHES_BY_AXIS[meta["axis"]]
    unknown = [
        branch for branch in meta["quest_branches"] if branch not in allowed
    ]
    if unknown:
        raise ContentError(
            "{}: quest_branches {} не из веток оси '{}' {}".format(
                path, unknown, meta["axis"], allowed
            )
        )
    return Act(
        act=meta["act"],
        slug=meta["slug"],
        title=meta["title"],
        rank=meta["rank"],
        rank_title=meta["rank_title"],
        artifact=meta["artifact"],
        axis=meta["axis"],
        muted=meta["muted"],
        quests=tuple(meta["quests"]),
        quest_titles=tuple(meta["quest_titles"]),
        quest_branches=tuple(meta["quest_branches"]),
        body=body,
        path=path,
        quest_tasks=_quest_tasks(meta, path),
    )


def _build_onboarding(meta, body, path):
    _require(meta, ONBOARDING_REQUIRED, path)
    _require_body(body, path)
    _require_choice(meta, "section", ONBOARDING_SECTIONS, path)
    if not isinstance(meta["order"], int):
        raise ContentError(
            "{}: order должен быть целым, получено {!r}".format(path, meta["order"])
        )
    options = meta.get("options") or []
    option_titles = meta.get("option_titles") or []
    if options:
        _require_list(meta, "options", path)
    if option_titles:
        _require_list(meta, "option_titles", path)
    # Схемная, а не древесная проверка: разъехавшиеся списки — это узел,
    # у которого кнопка без адреса или адрес без кнопки, то есть структура
    # уже битая. Связность дерева меряет линтер.
    if len(options) != len(option_titles):
        raise ContentError(
            "{}: переходов {}, а подписей {} — списки разъехались".format(
                path, len(options), len(option_titles)
            )
        )
    return Onboarding(
        node=meta["node"],
        title=meta["title"],
        order=meta["order"],
        section=meta["section"],
        body=body,
        path=path,
        probe=meta.get("probe") or "",
        options=tuple(options),
        option_titles=tuple(option_titles),
    )


def _build_recipe(meta, body, path):
    _require(meta, RECIPE_REQUIRED, path)
    _require_body(body, path)
    _require_list(meta, "stack", path)
    _require_choice(meta, "deploy_path", DEPLOY_PATHS, path)
    return Recipe(
        recipe=meta["recipe"],
        title=meta["title"],
        stack=tuple(meta["stack"]),
        deploy_path=meta["deploy_path"],
        body=body,
        path=path,
        reference_repo=meta.get("reference_repo") or "",
    )


def _build_remark(meta, body, path):
    _require(meta, REMARK_REQUIRED, path)
    _require_body(body, path)
    _require_choice(meta, "event", MAGISTR_EVENTS, path)
    return Remark(
        event=meta["event"],
        variants=_split_variants(body, path),
        path=path,
    )


def _build_phrases(meta, body, path):
    _require(meta, ("act",), path)
    _require_body(body, path)
    act = meta["act"]
    if not isinstance(act, int) or isinstance(act, bool):
        raise ContentError("{}: act должен быть числом".format(path))
    rows = tuple(line.strip() for line in body.splitlines() if line.strip())
    for row in rows:
        # Строка таблицы из двух ячеек: «| когда | что сказать |».
        if not (row.startswith("|") and row.endswith("|")
                and row.count("|") == 3):
            raise ContentError(
                "{}: строка не из двух ячеек таблицы: {}".format(path, row)
            )
    return Phrases(act=act, rows=rows, path=path)


def _build_roadmap(meta, body, path):
    _require(meta, ROADMAP_REQUIRED, path)
    _require_body(body, path)
    # Слаг трека проверяется здесь, а не только линтером: карту ищут по нему
    # словарём, и опечатка в поле оставила бы падавана без карты молча —
    # он получил бы общую карту вместо своей и ничего бы не заметил.
    _require_choice(meta, "track", ROADMAP_TRACKS, path)
    unknown = sorted(key for key in meta if key not in ROADMAP_REQUIRED)
    if unknown:
        raise ContentError(
            "{}: неизвестные поля: {} — у карты ровно четыре поля, и "
            "значение каждого занимает одну строку".format(
                path, ", ".join(unknown)
            )
        )
    return Roadmap(
        track=meta["track"],
        title=meta["title"],
        lead=meta["lead"],
        lead_url=meta["lead_url"],
        body=body,
        path=path,
    )


def _build_instruction(meta, body, path):
    _require(meta, INSTRUCTION_REQUIRED, path)
    _require_body(body, path)
    # Необязательных полей у инструкции нет, поэтому схема закрытая — и это
    # не педантизм. Значение обязано быть одной физической строкой:
    # свёрнутых скаляров парсер не умеет. Перенос с отступом он отвергает
    # сам, а перенос БЕЗ отступа, во второй строке которого есть
    # двоеточие, разбирается как новый ключ — `summary` доезжает обрезанным,
    # и оглавление собирается из половины фразы, ни на что не пожаловавшись.
    # Закрытая схема — единственная форма, в которой этот обрыв виден.
    unknown = sorted(key for key in meta if key not in INSTRUCTION_REQUIRED)
    if unknown:
        raise ContentError(
            "{}: неизвестные поля: {} — у инструкции ровно три поля, и "
            "значение каждого занимает одну строку".format(
                path, ", ".join(unknown)
            )
        )
    return Instruction(
        artifact=meta["artifact"],
        title=meta["title"],
        summary=meta["summary"],
        body=body,
        path=path,
    )


def _split_variants(body, path):
    """Абзацы тела — по одному варианту на каждый, пустые строки между.

    Абзац из двух строк — ошибка, а не два варианта и не один склеенный:
    загрузчик не угадывает, где автор хотел разрыв. Иначе привычный перенос
    по 80 колонок, которым набран весь остальной контент, молча отдал бы
    падавану половину фразы.
    """
    variants = []
    paragraph = []
    for raw in body.split("\n") + [""]:
        line = raw.strip()
        if line:
            paragraph.append(line)
        elif paragraph:
            if len(paragraph) > 1:
                raise ContentError(
                    "{}: вариант №{} занимает не одну строку, а {} — реплика "
                    "пишется одной строкой, между репликами пустая строка".format(
                        path, len(variants) + 1, len(paragraph)
                    )
                )
            variants.append(paragraph[0])
            paragraph = []
    return tuple(variants)

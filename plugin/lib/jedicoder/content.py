"""Загрузка контент-ядра: термины, правила Кодекса, рецепты, катсцены актов,
узлы онбординга (Акт 0).

Валидация здесь строгая и падает на первой ошибке: контент — часть
поставки, битый файл должен ловиться линтером в CI, а не на машине
падавана посреди акта.
"""
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

TERM_REQUIRED = ("term", "title", "aliases", "act", "category", "xp")
RULE_REQUIRED = ("rule", "title", "act", "severity", "xp")
RECIPE_REQUIRED = ("recipe", "title", "stack", "deploy_path")
ACT_REQUIRED = ("act", "slug", "title", "rank", "artifact", "quests", "quest_titles")
# options и option_titles в обязательные НЕ входят: терминальный узел — узел
# без выхода, и требовать у него список переходов значило бы запретить дереву
# заканчиваться.
ONBOARDING_REQUIRED = ("node", "title", "order", "section")

# Допустимые ранги объявлены ЗДЕСЬ, а не импортированы из ranks.py:
# content.py — нижний слой схемы, из него берёт acts.py (DEPLOY_PATHS), и
# обратный импорт перевернул бы слоистость. Совпадение с ranks.RANK_TITLES
# держит линтер, а не импорт.
ACT_RANKS = ("seeker", "padawan", "knight", "sentinel", "master")

MIN_ACT = 0
MAX_ACT = 5


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
    artifact: str
    quests: tuple
    quest_titles: tuple
    body: str
    path: Path


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


def _build_term(meta, body, path):
    _require(meta, TERM_REQUIRED, path)
    _require_body(body, path)
    _require_list(meta, "aliases", path)
    _require_choice(meta, "category", CATEGORIES, path)
    _require_act(meta, path)
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
    _require_list(meta, "quests", path)
    _require_list(meta, "quest_titles", path)
    return Act(
        act=meta["act"],
        slug=meta["slug"],
        title=meta["title"],
        rank=meta["rank"],
        artifact=meta["artifact"],
        quests=tuple(meta["quests"]),
        quest_titles=tuple(meta["quest_titles"]),
        body=body,
        path=path,
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

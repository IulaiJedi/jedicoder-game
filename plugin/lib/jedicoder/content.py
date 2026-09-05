"""Загрузка контент-ядра: термины, правила Кодекса, рецепты, катсцены актов,
узлы онбординга (Акт 0), реплики Магистра.

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
ACT_REQUIRED = (
    "act", "slug", "title", "rank", "rank_title", "artifact", "axis",
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

# События сцены, на которые у Магистра есть реплика: те же слова, что в
# очереди state.EVENT_TYPES, без linked — привязка к боту не событие пути, и
# сцена на неё не отзывается. Копия, а не импорт, по причине ACT_RANKS:
# content.py — нижний слой схемы, совпадение держит тест.
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
    rank_title: str
    artifact: str
    axis: str
    quests: tuple
    quest_titles: tuple
    # Ветка каждого квеста, по одной на позицию quests: both — в обеих
    # ветках оси, иначе имя трека (ось track) или пути деплоя (ось deploy).
    quest_branches: tuple
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
    _require_choice(meta, "axis", AXES, path)
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
        quests=tuple(meta["quests"]),
        quest_titles=tuple(meta["quest_titles"]),
        quest_branches=tuple(meta["quest_branches"]),
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


def _build_remark(meta, body, path):
    _require(meta, REMARK_REQUIRED, path)
    _require_body(body, path)
    _require_choice(meta, "event", MAGISTR_EVENTS, path)
    return Remark(
        event=meta["event"],
        variants=_split_variants(body, path),
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

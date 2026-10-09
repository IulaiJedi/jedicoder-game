"""Реестр квестов по актам: порядок прохождения и что закрыто.

Порядок здесь — единственный источник правды. Скилл акта не выдумывает
последовательность, а спрашивает next_quest.

Состав акта зависит от трека падавана. Метка трека стоит на самом квесте,
а не в отдельном реестре на трек: общие квесты объявлены один раз, и им
неоткуда разъехаться при правке одной из веток.

Осей развилки две: трек падавана (Акт 5) и путь деплоя (Акт 4).
Ось — свойство акта (ACT_AXIS), метка ветки стоит на квесте; общее
значение «в обеих ветках» — BRANCH_BOTH.
"""
from .content import DEPLOY_PATHS
from .quests import KIND_ACK, KIND_SCRIPT
from .ranks import ACTS, STATUS_DONE

TRACK_BOTH = "both"
TRACK_CRAFTSMAN = "craftsman"
TRACK_FOUNDER = "founder"
# Слова трека для падавана: имена craftsman/founder — ручки CLI, модель их
# не произносит (прогон новичком 2026-09-13: «Трек: craftsman» ушёл на экран).
# Один словарь на движок: печатают его и CLI, и страница Разбора.
TRACK_WORDS = {TRACK_CRAFTSMAN: "для себя", TRACK_FOUNDER: "для людей"}

# Треки, которые может выбрать падаван. TRACK_BOTH сюда не входит: это
# свойство квеста, а не выбор человека.
TRACKS = (TRACK_CRAFTSMAN, TRACK_FOUNDER)

# Общее значение «квест в обеих ветках» — одно на любую ось. TRACK_BOTH
# остаётся рабочим именем той же строки: реестры Актов 1–3 и их тесты
# написаны на нём.
BRANCH_BOTH = TRACK_BOTH

# Вторая ось развилки: путь деплоя. Значения — из схемы контента
# (content.DEPLOY_PATHS), а не свои: рецепт, ручка CLI и реестр квестов
# обязаны говорить на одном языке.
DEPLOYS = DEPLOY_PATHS
DEPLOY_MANAGED, DEPLOY_VPS = DEPLOYS

AXIS_DEPLOY = "deploy"

# Ось развилки акта: по какому выбору падавана фильтруется состав. Ось —
# свойство акта, а не квеста: у одного акта не бывает квестов, ветвящихся
# по разным осям. Не перечислен — ось трека.
ACT_AXIS = {4: AXIS_DEPLOY}

# Акт 1 «Знакомство» не ветвится: один вечер, одна дорога для всех. Прежний
# состав с развилкой по треку лежит на полке (shelf/act1-poisk-boli/).
ACT1_QUESTS = (
    ("01-folder", KIND_SCRIPT, TRACK_BOTH),
    ("02-idea", KIND_SCRIPT, TRACK_BOTH),
    ("03-first-request", KIND_SCRIPT, TRACK_BOTH),
    ("04-save", KIND_SCRIPT, TRACK_BOTH),
    ("05-stop-undo", KIND_ACK, TRACK_BOTH),
)

ACT2_QUESTS = (
    ("01-recipe", KIND_SCRIPT, TRACK_BOTH),
    ("02-claude-md", KIND_SCRIPT, TRACK_BOTH),
    ("03-db-schema", KIND_SCRIPT, TRACK_BOTH),
    ("04-git-init", KIND_SCRIPT, TRACK_BOTH),
    ("05-env-guard", KIND_SCRIPT, TRACK_BOTH),
    ("06-pipeline", KIND_ACK, TRACK_BOTH),
)

ACT3_QUESTS = (
    ("01-launch", KIND_SCRIPT, TRACK_BOTH),
    ("02-feature", KIND_SCRIPT, TRACK_BOTH),
    ("03-break", KIND_SCRIPT, TRACK_BOTH),
    ("04-fix", KIND_SCRIPT, TRACK_BOTH),
    ("05-decisions", KIND_SCRIPT, TRACK_BOTH),
    ("06-context7", KIND_SCRIPT, TRACK_BOTH),
    ("07-git-safety", KIND_SCRIPT, TRACK_BOTH),
    ("08-skill", KIND_SCRIPT, TRACK_BOTH),
    ("09-loop-protocol", KIND_ACK, TRACK_BOTH),
    ("10-boss", KIND_SCRIPT, TRACK_BOTH),
)

ACT4_QUESTS = (
    ("01-remote", KIND_SCRIPT, BRANCH_BOTH),
    ("02-rotation", KIND_ACK, BRANCH_BOTH),
    ("03m-secrets", KIND_SCRIPT, DEPLOY_MANAGED),
    ("04m-guard", KIND_ACK, DEPLOY_MANAGED),
    ("03v-user", KIND_SCRIPT, DEPLOY_VPS),
    ("04v-firewall", KIND_SCRIPT, DEPLOY_VPS),
    ("05v-hygiene", KIND_ACK, DEPLOY_VPS),
)

ACT5_QUESTS = (
    ("01-deploy", KIND_SCRIPT, TRACK_BOTH),
    ("02-domain", KIND_SCRIPT, TRACK_BOTH),
    ("03-ssl", KIND_SCRIPT, TRACK_BOTH),
    ("04-health", KIND_SCRIPT, TRACK_BOTH),
    ("05-goal", KIND_ACK, TRACK_BOTH),
    ("06c-use", KIND_ACK, TRACK_CRAFTSMAN),
    ("06f-publish", KIND_SCRIPT, TRACK_FOUNDER),
)

QUESTS_BY_ACT = {
    1: ACT1_QUESTS,
    2: ACT2_QUESTS,
    3: ACT3_QUESTS,
    4: ACT4_QUESTS,
    5: ACT5_QUESTS,
}


class UnknownActError(ValueError):
    """Для акта не объявлен список квестов."""


class TrackRequiredError(UnknownActError):
    """Состав акта зависит от трека, а трек не выбран.

    Наследуется от UnknownActError, чтобы существующие обработчики не
    пропустили её мимо, но CLI ловит её отдельно и предлагает выбрать трек.
    """


class DeployRequiredError(UnknownActError):
    """Состав акта зависит от пути деплоя, а путь не назван.

    Наследуется от UnknownActError по той же причине, что и
    TrackRequiredError: обработчик, не знающий про новую ось, обязан
    деградировать до «квесты недоступны», а не до трейсбека.
    """


def track_of(state):
    """Трек падавана из паспорта или None. Мусор трактуется как отсутствие."""
    return _chosen(state, "passport", "track", TRACKS)


def deploy_of(state):
    """Путь деплоя из state.project или None. Мусор — как отсутствие."""
    return _chosen(state, "project", "deploy_path", DEPLOYS)


def _chosen(state, section, key, allowed):
    """Выбор падавана из раздела сохранения; всё незнакомое — None.

    Мусором может оказаться не только значение, но и раздел целиком:
    паспорт или проект, правленные руками, бывают строкой, и .get у неё
    отвечает трейсбеком. Обещание «мусор — как отсутствие» обязано
    покрывать оба случая, иначе оно не обещание.
    """
    section_data = (state or {}).get(section)
    if not isinstance(section_data, dict):
        return None
    value = section_data.get(key)
    return value if value in allowed else None


def branch_of(state, act):
    """Выбор падавана по оси данного акта: трек или путь деплоя."""
    if ACT_AXIS.get(act) == AXIS_DEPLOY:
        return deploy_of(state)
    return track_of(state)


def filter_by_track(entries, track):
    """Идентификаторы квестов трека в порядке объявления.

    Общие квесты (TRACK_BOTH) попадают всегда. Если акт ветвится, а трек не
    выбран — ошибка, а не половина акта: половинчатая карта врёт падавану о
    том, сколько ему осталось.
    """
    branches = any(entry[2] != TRACK_BOTH for entry in entries)
    if branches and track not in TRACKS:
        raise TrackRequiredError(
            "Состав этого акта зависит от трека, а трек не выбран."
        )
    return tuple(
        quest_id for quest_id, _, quest_track in entries
        if quest_track == TRACK_BOTH or quest_track == track
    )


def filter_by_deploy(entries, deploy):
    """Идентификаторы квестов ветки деплоя в порядке объявления.

    Правила те же, что у трека: общие квесты попадают всегда; акт
    ветвится, а путь не назван — ошибка, а не половина акта.
    """
    branches = any(entry[2] != BRANCH_BOTH for entry in entries)
    if branches and deploy not in DEPLOYS:
        raise DeployRequiredError(
            "Состав этого акта зависит от пути деплоя, а путь не назван."
        )
    return tuple(
        quest_id for quest_id, _, branch in entries
        if branch == BRANCH_BOTH or branch == deploy
    )


def _entries(act):
    if act not in ACTS:
        raise UnknownActError("нет акта {}".format(act))
    if act not in QUESTS_BY_ACT:
        raise UnknownActError(
            "для акта {} ещё не объявлены квесты".format(act)
        )
    return QUESTS_BY_ACT[act]


def quest_ids(act, branch=None):
    entries = _entries(act)
    if ACT_AXIS.get(act) == AXIS_DEPLOY:
        return filter_by_deploy(entries, branch)
    return filter_by_track(entries, branch)


def all_quest_ids(act):
    """Все квесты акта в порядке объявления, по обе стороны развилки сразу.

    Отличие от quest_ids — в вопросе, на который отвечает функция. quest_ids
    отвечает «что проходить», и без выбора падавана такого ответа нет:
    половинчатая карта врёт ему о том, сколько осталось. Здесь вопрос другой
    — «в каком порядке перечислять то, что уже записано в сохранении», и
    выбор на него не влияет: у сменившего трек в состоянии лежат квесты
    обоих треков, и они его история, а не его список дел.
    """
    return tuple(entry[0] for entry in _entries(act))


def quest_kind(act, quest_id):
    """Вид квеста. Трек не нужен: идентификаторы уникальны внутри акта."""
    for candidate, kind, _ in QUESTS_BY_ACT.get(act, ()):
        if candidate == quest_id:
            return kind
    raise UnknownActError(
        "в акте {} нет квеста {}".format(act, quest_id)
    )


#: Квесты со скриптом, у которых сначала идут слова человека, а потом
#: проверка. Скрипт видит файлы, но не знает, открыл ли их кто-нибудь:
#: «Первый запрос» закрывался, как только в папке появлялся код, — до того,
#: как страницу увидел человек (прогон 2026-10-08). Исход по-прежнему решает
#: exit-код проверки; слова лишь открывают ей дорогу.
WORDS_FIRST = frozenset({(1, "03-first-request")})


def needs_words(act, quest_id):
    """Ждёт ли квест рассказа человека до проверки."""
    return (act, quest_id) in WORDS_FIRST


def _closed(state, act, quest_id):
    entry = (state.get("acts") or {}).get(str(act)) or {}
    quest = (entry.get("quests") or {}).get(quest_id) or {}
    return quest.get("status") == STATUS_DONE


def is_closed(state, act, quest_id):
    """Закрыт ли квест — по записи в сохранении."""
    return _closed(state, act, quest_id)


def next_quest(state, act, branch=None):
    for quest_id in quest_ids(act, branch):
        if not _closed(state, act, quest_id):
            return quest_id
    return None


def all_closed(state, act, branch=None):
    return next_quest(state, act, branch) is None


def closed_count(state, act, branch=None):
    """Сколько квестов ТЕКУЩЕЙ ветки закрыто.

    Считать все закрытые записи нельзя: после смены ветки в состоянии
    остаются квесты старой ветки, и карта показала бы 3/7, где одна из
    троек в новый список не входит.
    """
    return sum(
        1 for quest_id in quest_ids(act, branch)
        if _closed(state, act, quest_id)
    )

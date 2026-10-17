"""Реестр квестов по актам: порядок прохождения и что закрыто.

Порядок здесь — единственный источник правды. Скилл акта не выдумывает
последовательность, а спрашивает next_quest.

Состав акта зависит от трека падавана. Метка трека стоит на самом квесте,
а не в отдельном реестре на трек: общие квесты объявлены один раз, и им
неоткуда разъехаться при правке одной из веток.

Осей развилки две: трек падавана (прежний Акт 5 «Выход в свет») и путь
деплоя (прежний Акт 4 «Щит»); оба акта на полке — shelf/act5-vyhod-v-svet/ и
shelf/act4-shchit/. Сегодня ни один акт не ветвится, механика цела. Ось —
свойство акта (ACT_AXIS), метка ветки стоит на квесте; общее значение «в
обеих ветках» — BRANCH_BOTH.
"""
from . import state as st
from .content import DEPLOY_PATHS
from .quests import KIND_ACK, KIND_SCRIPT
from .ranks import ACTS, STATUS_DONE, STATUS_IN_PROGRESS

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
#
# Путём деплоя ветвился прежний Акт 4 «Щит»; он на полке (спека #117), и
# сегодня ни один акт по этой оси не ветвится. Механика цела: вернётся акт
# с серверами — вернётся и строка здесь.
ACT_AXIS = {}

# Акт 1 «Знакомство» не ветвится: один вечер, одна дорога для всех. Прежний
# состав с развилкой по треку лежит на полке (shelf/act1-poisk-boli/).
ACT1_QUESTS = (
    ("01-folder", KIND_SCRIPT, TRACK_BOTH),
    ("02-idea", KIND_SCRIPT, TRACK_BOTH),
    ("03-first-request", KIND_SCRIPT, TRACK_BOTH),
    ("04-save", KIND_SCRIPT, TRACK_BOTH),
    ("05-stop-undo", KIND_ACK, TRACK_BOTH),
)

# Акт 2 «Память и силы» (спека #99) не ветвится, как и первый. Три квеста из
# пяти судят то, чего нет в папке проекта: режим плана, показанный файл,
# чистый лист. Их проверки получают след готовым, переменными окружения
# (ADR-0020); прежний состав «Чертежа» лежит на полке (shelf/act2-chertezh/).
ACT2_QUESTS = (
    ("01-plan", KIND_SCRIPT, TRACK_BOTH),
    ("02-show", KIND_SCRIPT, TRACK_BOTH),
    ("03-memory", KIND_SCRIPT, TRACK_BOTH),
    ("04-clear", KIND_SCRIPT, TRACK_BOTH),
    ("05-powers", KIND_ACK, TRACK_BOTH),
)

# Акт 3 «Умения» (спека #108) не ветвится. Из сети в нём ничего не ставится
# (решение оператора 2026-10-14, #116): «Скилл» и «Где брать» закрывает
# рассказ. «Свой скилл» и «Хук» судят и машину игрока вне папки проекта —
# личные скиллы и настройки Claude Code в домашней папке
# (`quests/_lib/machine.sh`). Прежний состав «Первой крови» лежит на полке
# (shelf/act3-pervaya-krov/).
ACT3_QUESTS = (
    ("01-skill", KIND_ACK, TRACK_BOTH),
    ("02-where", KIND_ACK, TRACK_BOTH),
    ("03-own-skill", KIND_SCRIPT, TRACK_BOTH),
    ("04-hook", KIND_SCRIPT, TRACK_BOTH),
    ("05-mod", KIND_ACK, TRACK_BOTH),
)

# Акт 4 «Свой продукт» (спека #117) не ветвится: сайт или бот — выбор
# человека, а не другой состав акта. «Что строим» судит раздел «Продукт» в
# IDEA.md; «План» — след одобренного плана, сделанный в этом акте
# (FRESH_TRACE_QUESTS ниже); «Сборка» — сохранения после входа в акт.
# «Работает» — один квест на оба типа продукта: проверка сама выбирает, что
# судить, по типу, записанному командой игры (`product_of`), а у бота до неё
# идёт рассказ (`WORDS_FIRST_FOR`). Прежний «Щит» с развилкой по пути деплоя
# лежит на полке (shelf/act4-shchit/).
ACT4_QUESTS = (
    ("01-what", KIND_SCRIPT, TRACK_BOTH),
    ("02-plan", KIND_SCRIPT, TRACK_BOTH),
    ("03-build", KIND_SCRIPT, TRACK_BOTH),
    ("04-run", KIND_SCRIPT, TRACK_BOTH),
    ("05-accept", KIND_ACK, TRACK_BOTH),
)

# Акт 5 «Три места кода» (спека #123) не ветвится. «GitHub» закрывает
# рассказ: Claude подключил компьютер к аккаунту и назвал его, человек
# подтвердил. «Приватный репозиторий» судит `origin` проекта и ответ GitHub
# без входа: закрытого хранилища чужим не видно. «Одна версия» — сохранение
# после входа в акт, чистое дерево и та же версия в ветке `origin/<ветка>`.
# «Чужой сервис» — сначала рассказ, что продукт теперь умеет (WORDS_FIRST),
# потом проверка, что ключ не ушёл ни в сохранения, ни на GitHub. «Третье
# место» — сервер и домен словами, его тоже закрывает рассказ. Прежний «Выход
# в свет» с развилкой по треку лежит на полке (shelf/act5-vyhod-v-svet/).
ACT5_QUESTS = (
    ("01-github", KIND_ACK, TRACK_BOTH),
    ("02-private", KIND_SCRIPT, TRACK_BOTH),
    ("03-sync", KIND_SCRIPT, TRACK_BOTH),
    ("04-service", KIND_SCRIPT, TRACK_BOTH),
    ("05-server", KIND_ACK, TRACK_BOTH),
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


#: Тип продукта Акта 4 «Свой продукт»: сайт или Telegram-бот (спека #117).
#: Записывает его `project type`, в поле `project.type` сохранения — то же
#: поле, куда прежняя игра клала имя рецепта (`landing`, `telegram-bot`,
#: `web-service`): рецепты прежних актов остаются рабочими значениями ручки,
#: но квест «Работает» знает только эти два.
PRODUCT_SITE = "site"
PRODUCT_BOT = "bot"
PRODUCT_KINDS = (PRODUCT_SITE, PRODUCT_BOT)
#: Тип продукта словами человека.
PRODUCT_WORDS = {PRODUCT_SITE: "сайт", PRODUCT_BOT: "Telegram-бот"}
#: Рецепт типа продукта (`content/ru/recipes/`): стек и грабли «на своём
#: компьютере» (#120). Путь деплоя у рецепта остаётся полем прежней игры и
#: для этих типов не печатается.
PRODUCT_RECIPES = {PRODUCT_SITE: "landing", PRODUCT_BOT: "telegram-bot"}


def track_of(state):
    """Трек падавана из паспорта или None. Мусор трактуется как отсутствие."""
    return _chosen(state, "passport", "track", TRACKS)


def product_of(state):
    """Тип продукта Акта 4 — `site`, `bot` или None. Мусор — как отсутствие.

    Имя рецепта прежней игры в том же поле — тоже None: какой проверкой
    судить «Работает», оно не говорит.
    """
    return _chosen(state, "project", "type", PRODUCT_KINDS)


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
#:
#: «Чистый лист» Акта 2 — тот же случай: след говорит, что `/clear` был, но
#: не говорит, спросил ли человек после него про проект и что услышал.
#:
#: «Чужой сервис» Акта 5 — тоже: проверка видит, что ключ не утёк, но чужой
#: сервис не зовёт и не знает, заработал ли он. Что продукт теперь умеет,
#: знает только человек, который это увидел.
SERVICE_QUEST = (5, "04-service")

WORDS_FIRST = frozenset({
    (1, "03-first-request"), (2, "04-clear"), SERVICE_QUEST,
})

#: Квест «Работает» Акта 4.
RUN_QUEST = (4, "04-run")

#: Квесты, которые ждут слов человека не всегда, а при одном типе продукта:
#: квест → тип. Сайт проверка открывает сама — адрес отвечает или нет. Бота
#: она открыть не может: он сам забирает сообщения. Что бот ответил, знает
#: только человек, написавший ему в Telegram (спека #117).
WORDS_FIRST_FOR = {RUN_QUEST: PRODUCT_BOT}


#: Квест «Память проекта». По нему меряется `/clear`: квесту «Чистый лист»
#: нужен новый разговор после того, как память записана.
MEMORY_QUEST = (2, "03-memory")

#: Квест «Чистый лист».
CLEAR_QUEST = (2, "04-clear")

#: Квест «Силы»: человек рассказывает о модели и лимите, а игра отдаёт
#: модели то, что видит сама, — с чем рассказ сверить (`cli.render_powers`).
POWERS_QUEST = (2, "05-powers")


#: Квест «Хук»: по слову «чистка» Claude сам записывает передачу.
HOOK_QUEST = (3, "04-hook")

#: Квест «Мод»: человек рассказывает про строку о моде, а игра отдаёт модели
#: то, что знает о своём моде сама (`cli.render_mod`).
MOD_QUEST = (3, "05-mod")


#: След → акт, чьи квесты его судят (ADR-0020 в репозитории сайта). След
#: годится проверке, только если сделан, пока этот акт идёт. Следа `cleared`
#: здесь нет: его пометка — не акт, а записанная память проекта.
TRACE_ACTS = {
    st.TRACE_PLAN_APPROVED: 2,
    st.TRACE_FILE_SHOWN: 2,
    st.TRACE_IMAGE_SHOWN: 2,
    st.TRACE_HOOK_WORD: HOOK_QUEST[0],
}


#: Квест «План» Акта 4: план продукта одобрен в этом акте (#118).
PRODUCT_PLAN_QUEST = (4, "02-plan")

#: Квесты, которым нужен след, сделанный после входа в их акт: квест → след.
#: Пометка `in_act` ставится один раз навсегда, и у плана она про Акт 2:
#: план второго вечера квест четвёртого не закрывает. Для таких квестов хук
#: пишет следу момент — последнее одобрение, пока квест открыт
#: (`traces.moment_for`), — а проверка сверяет его с моментом входа в акт
#: (`JEDICODER_ACT_STARTED`).
FRESH_TRACE_QUESTS = {PRODUCT_PLAN_QUEST: st.TRACE_PLAN_APPROVED}


def fresh_trace_open(state, kind):
    """Ждёт ли свежего следа этого вида открытый квест идущего акта."""
    for (act, quest_id), wanted in FRESH_TRACE_QUESTS.items():
        if (wanted == kind and in_progress(state, act)
                and not is_closed(state, act, quest_id)):
            return True
    return False


def trace_in_act(state, kind):
    """Идёт ли сейчас акт, чьи квесты судят этот след."""
    act = TRACE_ACTS.get(kind)
    return act is not None and in_progress(state, act)


def in_progress(state, act):
    """Идёт ли акт: в него вошли и он не закрыт. Мусор — как «не идёт»."""
    known = state.get("acts") if isinstance(state, dict) else None
    entry = known.get(str(act)) if isinstance(known, dict) else None
    return isinstance(entry, dict) and entry.get("status") == STATUS_IN_PROGRESS


def needs_words(act, quest_id, state=None):
    """Ждёт ли квест рассказа человека до проверки.

    `state` нужен квестам из `WORDS_FIRST_FOR`: ждут ли они слов, решает
    тип продукта из сохранения. Не передали или тип не назван — не ждут:
    проверка сама скажет, что типа нет.
    """
    if (act, quest_id) in WORDS_FIRST:
        return True
    kind = WORDS_FIRST_FOR.get((act, quest_id))
    return kind is not None and product_of(state) == kind


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

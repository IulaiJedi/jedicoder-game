"""Состояние падавана: чтение, атомарная запись, миграции.

Живёт в ~/.jedicoder/state.json — глобально, а не в проекте, потому что
падаван меняет проекты, а прогресс терять нельзя.

Путь всюду остаётся параметром, и вызывающий обязан его передавать: тест,
забывший это сделать, писал бы в сохранение разработчика. Умолчание, если
путь всё-таки не передан, считает state_path() — она читает
JEDICODER_STATE_PATH, и её же зовут хуки, чтобы обе половины игры видели
один файл.
"""
import contextlib
import itertools
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: работаем без взаимного исключения
    fcntl = None

SCHEMA_VERSION = 4

# Первая версия схемы перестроенной игры (спека #75): под номером 1 новый
# акт, прежние выключены. Всё, что ниже, писала прежняя игра, и с новым
# порядком актов оно несовместимо — такое сохранение не мигрирует, а уходит
# в архив целиком (start_over). Отдельной константой, а не SCHEMA_VERSION:
# следующая обычная миграция поднимет версию схемы, а граница игр останется
# на месте.
#
# Признак — версия схемы, а не отдельное поле, по двум причинам. Версию
# игра писала всегда, значит прежнее сохранение опознаётся по тому, что в
# нём уже есть, без догадок по составу актов. И откат плагина обязан быть
# громким: прежний плагин на сохранении новой игры показал бы её Акт 1 под
# прежним именем и с прежними квестами — migrate в нём бросает StateError
# на версии новее своей, и это честнее молчаливой путаницы.
REBUILT_GAME_SCHEMA = 4

STATE_DIR = Path.home() / ".jedicoder"
STATE_PATH = STATE_DIR / "state.json"
PLUGIN_ROOT_PATH = STATE_DIR / "plugin_root"

def state_path():
    """Куда игра пишет сохранение падавана.

    Единственное место, где этот путь считается: и движок, и хуки берут
    его отсюда. Двумя копиями одной строки они разошлись бы молча, а
    расщеплённое состояние — хуки в одном файле, движок в другом — и есть
    тот самый долг №0, ради которого функция появилась.

    Значение читается при КАЖДОМ вызове, а не один раз на импорте: хук
    запускается отдельным процессом с чужим окружением, а тест выставляет
    переменную после того, как модуль уже загружен. Посчитанный на импорте
    путь оба получили бы устаревшим — ровно та ошибка, которую правка
    закрывает.

    Переменной нет или она пуста — прежний ~/.jedicoder/state.json, до
    байта.

    Тильда раскрывается, и это не удобство: в settings.json и в CI нет
    оболочки, которая сделала бы это за нас, а НЕраскрытая тильда — это
    относительный путь. Текущая папка у движка (проект падавана) и у хука
    (откуда запущен Claude Code) разные, значит одно и то же значение
    развело бы их по разным файлам — то самое расщепление, ради которого
    функция и появилась.

    Относительный путь так и остаётся относительным — текущей папки на
    момент вызова, со всеми последствиями выше. Это выбор того, кто задал
    переменную; угадывать за него якорь не наше дело.
    """
    override = os.environ.get("JEDICODER_STATE_PATH")
    if not override:
        return STATE_PATH
    try:
        return Path(override).expanduser()
    except RuntimeError:
        # `~несуществующий` раскрывать не во что. Берём путь как есть:
        # закон хуков запрещает падать, а падаван увидит свою опечатку
        # папкой с тильдой в имени, а не потерянным прогрессом.
        return Path(override)


def _target(path):
    """Путь, с которым работает вызов: переданный или умолчание.

    Одно место на все три двери (load, save, update_state): разъехавшиеся
    умолчания дали бы чтение из одного файла и запись в другой.
    """
    return Path(state_path() if path is None else path)


RANK_YOUNGLING = "youngling"

# Одноразовое объяснение: игра перестроена, прежнее сохранение в архиве.
# Ключ латиницей, как и всё в JSON; текст для падавана живёт в cli.py —
# он единственный, кто печатает.
NOTICE_GAME_REBUILT = "game_rebuilt"


class StateError(RuntimeError):
    """Состояние нельзя использовать: например, оно новее плагина."""


def new_padawan_id():
    return "local-" + uuid.uuid4().hex[:8]


PENDING_SYNC_CAP = 500

EVENT_TYPES = (
    "linked", "act_started", "quest_completed", "quest_failed", "rank_up",
    "term_unlocked", "dark_side", "streak_updated", "product_deployed",
    "finale", "scroll_issued",
)

# События, на которые сцена не отзывается и реплики Магистра не нужно:
# привязка к боту — факт про бота, а не про путь падавана; выдача Свитка —
# служебный сигнал для письма бота через неделю, а не событие пути. Реплики
# Магистра (content.MAGISTR_EVENTS) — это EVENT_TYPES без этого списка, и
# совпадение держит тест.
SILENT_EVENTS = ("linked", "scroll_issued")


def new_client_id():
    return uuid.uuid4().hex


def now_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def enqueue_event(state, event_type, act=None, quest=None, payload=None):
    """Положить событие прогресса в очередь для бота потока.

    Очередь ограничена: непривязанный падаван копит события всю игру, и
    состояние не имеет права расти без предела — старые выпадают первыми,
    бот собирает строку по накопленным итогам, а не по дельтам.
    """
    event = {
        "client_id": new_client_id(),
        "type": event_type,
        "act": act,
        "quest": quest,
        "at": now_utc(),
        "payload": payload or {},
    }
    queue = state.setdefault("pending_sync", [])
    queue.append(event)
    if len(queue) > PENDING_SYNC_CAP:
        del queue[: len(queue) - PENDING_SYNC_CAP]
    return event


# Типы нарушений, за которые хуки начисляют Тёмную сторону. Перечень один
# на всю игру: Разбор читает эти же имена, и второй список разошёлся бы с
# этим молча. Новый повод добавляется сюда, а не рядом.
#
# Имена вынесены в константы, а не оставлены литералами на местах вызова:
# хуки лежат в другой папке, и опечатка в строке доехала бы до журнала
# молча, а опечатка в имени константы падает сразу.
DARK_ENV_STAGED = "env_staged"              # .env отправлен в индекс git
DARK_RM_OUTSIDE_PROJECT = "rm_outside_project"   # rm -rf мимо папки проекта
DARK_ROOT_LOGIN = "root_login"              # вход на сервер под root
DARK_VAGUE_PROMPT = "vague_prompt"          # заказ по настроению вместо задачи

DARK_SIDE_KINDS = (
    DARK_ENV_STAGED,
    DARK_RM_OUTSIDE_PROJECT,
    DARK_ROOT_LOGIN,
    DARK_VAGUE_PROMPT,
)

# Штраф словами человека первого вечера, по типу. Эти слова стоят на первом
# экране под счётом и в сообщении хука в момент начисления: число и его
# история обязаны называться одинаково. В памятке те же типы названы рабочим
# языком (scroll.DARK_SIDE_TITLES) — её читают позже и без игры.
DARK_SIDE_WORDS = {
    DARK_ENV_STAGED: "файл с паролями едва не попал в сохранение",
    DARK_RM_OUTSIDE_PROJECT: "удаление мимо папки проекта",
    DARK_ROOT_LOGIN: "вход на сервер главным пользователем",
    DARK_VAGUE_PROMPT: "запрос без подробностей",
}


def streak_line(current, best):
    """Серия сохранений одной строкой — на первом экране и после сохранения.

    «Сохранений», а не «коммитов»: строка звучит раньше, чем человек получил
    слово «коммит». «Лучшая» — только когда она отличается: «1 (лучшая 1)»
    читалось как повтор (второй прогон 2026-10-08).
    """
    return (
        "Серия сохранений: {}{} — дней подряд, когда работа была "
        "сохранена".format(
            current, " (лучшая {})".format(best) if best != current else ""
        )
    )


def today_utc():
    """Календарная дата UTC, без времени: журнал хранит день, не момент.

    UTC, а не локальное время, — тем же выбором, что и серия коммитов
    (`commit_pulse.today_utc`): в Разборе даты журнала и даты серии стоят
    рядом, и разъехаться на сутки у полуночи им нельзя. Цена — падаван с
    большим офсетом у полуночи увидит вчерашнее число.
    """
    return time.strftime("%Y-%m-%d", time.gmtime())


def record_dark_side(state, kind, count=1, today=None):
    """Записать очки Тёмной стороны в журнал: тип нарушения и дата.

    Одна запись на очко, поэтому отправка `.env` (два очка) оставляет две
    записи: только так число записей сходится со счётчиком, а Разбор
    считает по журналу то же, что падаван видит в статусе.

    Команда падавана не хранится никогда (ADR-0011 в репозитории сайта): в
    ней бывают пути, домены и ключи, а журнал уезжает в Свиток и может
    попасть в публичный репозиторий человека.

    Предела у журнала нет намеренно, в отличие от очереди событий: кап
    молча разошёлся бы со счётчиком, а по этому равенству считает Разбор.
    Запись весит полсотни байт и появляется только на пойманном опасном
    действии — это не поток событий, который копится сам.
    """
    log = state.get("dark_side_log")
    if not isinstance(log, list):
        # Мусор в поле (правка руками) — то же правило, что у счётчика:
        # начинаем журнал заново, но не падаем на глазах у падавана.
        log = []
        state["dark_side_log"] = log
    date = today or today_utc()
    for _ in range(int(count)):
        log.append({"type": kind, "date": date})
    return log


def dark_side_entries(state):
    """Разобранные записи журнала Тёмной стороны, от старых к новым.

    Читатель прощающий: сохранение правят руками, и Разбор обязан отдать
    то, что понял, а не упасть. Тип не сверяется с DARK_SIDE_KINDS
    намеренно — записи, сделанные плагином новее, должны переживать откат,
    а не исчезать из журнала.

    Записей может быть МЕНЬШЕ, чем очков в счётчике, и это не ошибка: у
    того, кто играл до появления журнала, очки есть, а записей нет, и
    задним числом их не восстановить (команду никогда не хранили). Тот,
    кто печатает Разбор, обязан считать по журналу и не выдавать разницу
    за ноль.
    """
    log = state.get("dark_side_log")
    if not isinstance(log, list):
        return []
    entries = []
    for item in log:
        if not isinstance(item, dict):
            continue
        kind, date = item.get("type"), item.get("date")
        if isinstance(kind, str) and kind and isinstance(date, str) and date:
            entries.append({"type": kind, "date": date})
    return entries


# Следы — действия человека, которых проверка не видит в папке проекта
# (ADR-0020 в репозитории сайта): пишет хук игровой сессии, судит проверка.
# Перечень имён один на всю игру, как у штрафов выше: хуки лежат в другой
# папке, и опечатка в строке доехала бы до сохранения молча. Имя следа —
# оно же хвост переменной, которой команда игры отдаёт его проверке
# (`JEDICODER_TRACE_<ИМЯ>`), поэтому менять его можно только вместе с ней.
TRACE_PLAN_APPROVED = "plan_approved"   # Claude показал план, человек одобрил
TRACE_FILE_SHOWN = "file_shown"         # файл проекта показан через @
TRACE_IMAGE_SHOWN = "image_shown"       # картинка показана
TRACE_CLEARED = "cleared"               # разговор начат заново: /clear
TRACE_HOOK_WORD = "hook_word"           # слово «чистка» при записанном хуке

TRACE_KINDS = (
    TRACE_PLAN_APPROVED,
    TRACE_FILE_SHOWN,
    TRACE_IMAGE_SHOWN,
    TRACE_CLEARED,
    TRACE_HOOK_WORD,
)

#: Ключ сохранения: «имя следа → запись». Запись — день первого раза и
#: пометки. Ключ необязательный: нет его или в нём мусор — следов нет.
TRACES_KEY = "traces"

#: Пометка следа `cleared`: к моменту `/clear` память проекта уже была
#: записана (квест закрыт). Ставит тот, кто пишет след; проверке квеста
#: «Чистый лист» отдаётся только помеченный.
TRACE_AFTER_MEMORY = "after_memory"

#: Пометка следов плана, файла, картинки и слова хука: действие сделано,
#: когда акт, чьи квесты его ждут, начат и не закрыт. План, одобренный в игровой
#: сессии до входа в акт, — тоже след, но квест акта он не закрывает.
TRACE_IN_ACT = "in_act"

#: След → пометка, без которой проверка его не получает. Ставит пометку
#: тот, кто пишет след, в момент записи; позже она только появляется —
#: когда действие повторили уже в нужное время.
TRACE_MARK = {
    TRACE_PLAN_APPROVED: TRACE_IN_ACT,
    TRACE_FILE_SHOWN: TRACE_IN_ACT,
    TRACE_IMAGE_SHOWN: TRACE_IN_ACT,
    TRACE_CLEARED: TRACE_AFTER_MEMORY,
    TRACE_HOOK_WORD: TRACE_IN_ACT,
}

#: Момент следа, секундами эпохи. Нужен следу, после которого проверка ждёт
#: чего-то на диске: квест «Хук» сверяет с ним время записи передачи. В
#: отличие от дня и пометок момент может сдвинуться вперёд — когда действие
#: повторили; решает это тот, кто пишет след.
TRACE_AT = "at"


def record_trace(state, kind, marks=None, today=None, at=None):
    """Записать след. True — сохранение изменилось.

    След — о прошлом: было или не было. Повтор действия записи не меняет,
    и файл из-за него не переписывается; стирать след некому — ни
    несошедшаяся проверка, ни закрытый квест его не трогают.

    `marks` — пометки записи (`{TRACE_AFTER_MEMORY: True}`). Пометка только
    появляется: `/clear` после записи памяти не перестаёт быть таким оттого,
    что следом был ещё один.

    `at` — момент следа секундами эпохи (`TRACE_AT`); None — момент не
    трогается. Не целое число — ошибка вызывающего.

    Имя не из перечня — ошибка вызывающего, а не данные: падает сразу.
    Команда человека и текст запроса сюда не попадают никогда, как и в
    журнал штрафов (ADR-0011 в репозитории сайта).
    """
    if kind not in TRACE_KINDS:
        raise ValueError("нет такого следа: {!r}".format(kind))
    if at is not None and (isinstance(at, bool) or not isinstance(at, int)):
        # До первой правки: ошибка вызывающего не оставляет след наполовину.
        raise ValueError("момент следа — целые секунды: {!r}".format(at))
    known = state.get(TRACES_KEY)
    if not isinstance(known, dict):
        # Мусор в поле (правка руками) — начинаем заново, как у журнала.
        known = state[TRACES_KEY] = {}
    entry = known.get(kind)
    changed = False
    if not isinstance(entry, dict):
        entry = known[kind] = {"date": today or today_utc()}
        changed = True
    for name, value in (marks or {}).items():
        if value is True and entry.get(name) is not True:
            entry[name] = True
            changed = True
    if at is not None and entry.get(TRACE_AT) != at:
        entry[TRACE_AT] = at
        changed = True
    return changed


def trace_moment(state, kind):
    """Момент следа секундами эпохи либо None: следа или момента нет.

    Мусор в поле (правка руками) читается как «момента нет».
    """
    entry = trace(state, kind)
    moment = entry.get(TRACE_AT) if entry else None
    if isinstance(moment, bool) or not isinstance(moment, int) or moment < 0:
        return None
    return moment


def trace(state, kind):
    """Запись следа из сохранения либо None, когда следа нет.

    Единственное чтение следов: литерал имени на месте вызова запрещён,
    как у `DARK_SIDE_KINDS`. Читатель прощающий — сохранение правят руками,
    а зовут его и первый экран, и снимок Лица: мусор читается как «следа
    нет». Отдаётся копия.
    """
    known = state.get(TRACES_KEY) if isinstance(state, dict) else None
    if not isinstance(known, dict):
        return None
    entry = known.get(kind) if isinstance(kind, str) else None
    return dict(entry) if isinstance(entry, dict) else None


#: Режимы разрешений Claude Code, как он сам называет их хукам в поле
#: `permission_mode` (документация, раздел hooks). Список закрытый: незнакомое
#: слово читается как «не знаю», а не как «какой-то режим».
PERMISSION_MODE_FREE = "bypassPermissions"   # в текстах — «режим без вопросов»
PERMISSION_MODES = (
    "default", "plan", "acceptEdits", "auto", "dontAsk", PERMISSION_MODE_FREE,
)


def permission_mode(state):
    """Режим, который Claude Code назвал хуку последним, либо None.

    Поле необязательное: его нет у того, кто играл до этой правки, и у того,
    чей Claude Code режим хукам не передаёт. Мусор читается как отсутствие —
    сказать человеку «ты в режиме без вопросов» можно только по бесспорному.
    """
    return _known_mode(
        state.get("permission_mode") if isinstance(state, dict) else None
    )


def _known_mode(value):
    """Имя режима из закрытого списка либо None: и список, и словарь в поле
    нехешируемы, поэтому сначала тип, потом вхождение."""
    if isinstance(value, str) and value in PERMISSION_MODES:
        return value
    return None


def note_permission_mode(state, reported):
    """Записать режим из данных хука. True — сохранение изменилось.

    Режим не назван или назван незнакомо — прежнее знание стирается:
    устаревшее хуже отсутствующего, игра сказала бы человеку неправду.
    """
    known = _known_mode(reported)
    if known is None:
        if "permission_mode" not in state:
            return False
        del state["permission_mode"]
        return True
    if state.get("permission_mode") == known:
        return False
    state["permission_mode"] = known
    return True


def default_state(padawan_id=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "padawan_id": padawan_id,
        "link_key": None,
        "cohort": None,
        "passport": {},
        "rank": RANK_YOUNGLING,
        "xp": 0,
        "dark_side": 0,
        "streak": {"current": 0, "best": 0, "last_commit_date": None},
        "first_try": {"passed": 0, "attempted": 0},
        "current_act": 1,
        "acts": {},
        "artifacts": [],
        "lexicon_unlocked": [],
        # Слова, найденные хуком лута сверх одной карточки за ход: не больше
        # двух ждут своего хода по одному (lexicon_loot.pick_cards,
        # MAX_QUEUE). Ключ плоский —
        # старое сохранение получит пустой список на первом же load через
        # merged.update(data), без NESTED_DEFAULTS и без бампа SCHEMA_VERSION.
        "lexicon_queue": [],
        "project": {},
        "pending_sync": [],
        "notices": [],
        # Журнал Тёмной стороны: одна запись на очко, тип и дата (ADR-0011
        # в репозитории сайта).
        # Ключ плоский, значение — список, поэтому старое сохранение получает
        # пустой журнал на первом же load через merged.update(data), без
        # NESTED_DEFAULTS (там сливаются словари) и без бампа SCHEMA_VERSION:
        # кода миграции задача не требует, а поднятая версия превратила бы в
        # кирпич состояние того, кто откатит плагин.
        "dark_side_log": [],
        # Следы (ADR-0020 в репозитории сайта): «имя → запись», пишут хуки
        # игровой сессии (`record_trace`), читает `trace`. Ключ плоский —
        # старое сохранение получит пустую форму на первом же load, без
        # бампа SCHEMA_VERSION, тем же способом, что журнал выше.
        TRACES_KEY: {},
        # Отпечатки выданного Свитка: «имя файла в docs/jedicoder →
        # {sha256, date}». Отвечают на один вопрос — лежит ли сейчас в папке
        # ровно то, что игра туда положила; не совпало, значит файл правил
        # человек, и переписывать его нельзя (ADR-0009 в репозитории сайта).
        # Ключ плоский, поэтому старое сохранение получит пустую форму на
        # первом же load через merged.update(data), без NESTED_DEFAULTS и без
        # бампа SCHEMA_VERSION — тем же способом, что dark_side_log выше.
        "scroll": {"files": {}},
        # Разбор Магистра: текст, написанный поверх фактов прохождения, и
        # отпечаток той самой страницы фактов. Движок модель не зовёт,
        # поэтому текст приезжает командой `debrief write` и ждёт здесь
        # ближайшей выдачи Свитка (ADR-0010 в репозитории сайта). Отпечаток
        # хранится рядом не для истории: страница фактов меняется от каждого
        # закрытого квеста, и по нему видно, тем ли числам текст отвечает.
        # Ключ плоский — старое сохранение получит форму на первом же load
        # через merged.update(data), тем же способом, что dark_side_log и
        # scroll выше.
        "debrief": {"text": "", "facts": ""},
        # Книга (сайт): открывать ли вкладку с разворотом главы на входе в акт.
        # Ключи плоские намеренно. migrate() сливает с дефолтами только те
        # вложенные словари, что перечислены в NESTED_DEFAULTS, — вложенная
        # форма потребовала бы правки этого списка, а плоскую подхватывает
        # merged.update(data) на первом же load. Поэтому и SCHEMA_VERSION не
        # поднимается: старые state.json получат дефолты сами, а поднятая
        # версия превратила бы в кирпич состояние того, кто откатит плагин
        # (migrate бросает StateError при version > SCHEMA_VERSION).
        "book_open": None,     # None — не ответил; True/False — ответ падавана
        "book_asked": False,   # вопрос уже напечатан хотя бы раз
        # Куда ушло сохранение прежней игры (start_over): путь к архиву или
        # None у того, кто прежней игры не видел. Хранится, а не только
        # печатается: первый экран называет его один раз, а найти свой
        # прежний путь человек может захотеть и через месяц.
        "previous_save": None,
    }


def backup_path(path):
    return Path(str(path) + ".bak")


def corrupt_path(path):
    return Path(str(path) + ".corrupt")


def _read_dict(path):
    """Содержимое файла словарём либо None: файла нет или в нём не то."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load(path=None):
    # Умолчание считается на вызове, а не на импорте: значение по
    # умолчанию у аргумента застыло бы навсегда и не увидело бы
    # JEDICODER_STATE_PATH.
    path = _target(path)
    # Обычный случай — файл на месте и это новая игра — читается без замка,
    # как и раньше. Всё остальное меняет диск или может застать чужую
    # перемену на середине, поэтому идёт под замком:
    #  - прежняя игра уходит в архив (start_over), и хук с командой,
    #    встретившие её разом, не должны начать две новые игры;
    #  - файла нет или он не читается — возможно, другой процесс в эту
    #    секунду между переименованием прежнего файла и записью нового.
    #    Поверивший пустоте получил бы игру без переноса и записал бы её
    #    поверх настоящей, а «восстановление» унесло бы настоящую в сторону.
    data = _read_dict(path)
    if data is not None and not is_previous_game(data):
        return migrate(data)
    if not path.parent.is_dir():
        # Нет и папки — нет ни игры, ни чужой перемены, и чтение не заводит
        # папку ради замка.
        return default_state()
    with _locked(path):
        return _load_under_lock(path)


def peek(path=None):
    """Сохранение новой игры только на чтение — либо None.

    Вторая дверь рядом с `load`, и нужна она одному читателю — Лицу: снимку
    (`cli.py face`) и разделу с контрактом (`cli.py contract --section`).
    Модуль зовёт их после каждого хода в любой сессии
    на машине, где стоит плагин, а `load` на пустом месте берёт замок, на
    испорченном файле уносит его в сторону, на сохранении прежней игры
    начинает новую. Ничего из этого Полоса делать не вправе: чинит и
    переносит команда игры, которую позвал человек.

    None — показать нечего: файла нет, он не читается, его писала прежняя
    игра или плагин новее нашего. Диск не трогается ни в одном случае, замок
    не берётся. Прочитанное на середине чужой записи исключено тем же, чем у
    `load`: запись атомарна, файл подменяется целиком.

    Писать прочитанное отсюда обратно нельзя: переход между играми прошёл бы
    мимо — для записи есть `load` и `update_state`.
    """
    data = _read_dict(_target(path))
    if data is None or is_previous_game(data):
        return None
    try:
        return migrate(data)
    except (StateError, TypeError, ValueError, AttributeError):
        # Плагин старше сохранения либо вложенное поле правили руками и
        # форма его не та: `migrate` форме верит.
        return None


def _load_under_lock(path):
    """Прочитать сохранение; замок состояния уже у вызывающего.

    Сохранение прежней игры дальше этой функции не проходит: кто бы ни
    встретил его первым — команда, хук, строка состояния, — получает новую
    игру, а прежний файл уходит в архив (start_over). Дверь одна на всех,
    поэтому и исход один.
    """
    if not path.exists():
        return default_state()
    data = _read_dict(path)
    if data is None:
        data = _recover(path)
        if data is None:
            return default_state()
    if is_previous_game(data):
        return start_over(path, data)
    return migrate(data)


def _recover(path):
    """Испорченный файл — в сторону; вернуть резервную копию либо None."""
    try:
        path.replace(corrupt_path(path))
    except OSError:
        pass
    backup = backup_path(path)
    return _read_dict(backup) if backup.exists() else None


def is_previous_game(data):
    """Писала ли это сохранение прежняя игра — до перестройки актов.

    Только по прямому признаку: версия схемы числом ниже границы. Файл без
    версии игра не писала никогда — он собран руками, и чей он, неизвестно;
    такой читается как обычно, а не уезжает в архив по догадке.

    Число — любое: правленое руками `3.0` — та же прежняя игра, и мимо
    архива под видом новой она пройти не должна. bool числом не считается.
    """
    version = data.get("schema_version")
    if isinstance(version, bool) or not isinstance(version, (int, float)):
        return False
    return version < REBUILT_GAME_SCHEMA


ARCHIVE_MARK = ".arhiv-"


def archive(path=None):
    """Убрать сохранение в архив рядом; вернуть путь архива или None.

    Один код на оба случая: `reset` по слову человека и прежняя игра при
    первой встрече (start_over). Файл переименовывается, а не копируется:
    содержимое остаётся до байта тем же. Резервная копия `.bak` едет следом
    с тем же хвостом — рядом с новой игрой она подняла бы прежнюю при первом
    же восстановлении.

    В имени — дата и время по UTC. Занято — добавляются секунды, занято и
    так — номер: архив не затирает архив никогда, сколько бы раз подряд ни
    звали.

    Основного файла нет, а копия есть (его унесло восстановление) — архивом
    становится копия, и возвращается её путь. Нет ни того, ни другого — None.

    Идёт под замком состояния: имя выбирается и занимается одним окном, и
    хук не пишет в файл, который в эту секунду переименовывают.
    """
    path = _target(path)
    with _locked(path):
        return _archive_under_lock(path)


def _archive_under_lock(path):
    backup = backup_path(path)
    now = time.gmtime()
    second = time.strftime("%Y-%m-%d-%H%M%S", now)
    tails = itertools.chain(
        [time.strftime("%Y-%m-%d-%H%M", now), second],
        ("{}-{}".format(second, number) for number in itertools.count(2)),
    )
    for tail in tails:
        target = path.with_name(path.name + ARCHIVE_MARK + tail)
        target_backup = Path(str(target) + ".bak")
        if not target.exists() and not target_backup.exists():
            break
    moved = None
    if path.exists():
        os.replace(str(path), str(target))
        moved = target
    if backup.exists():
        os.replace(str(backup), str(target_backup))
        moved = moved or target_backup
    return moved


def _carried_over(previous):
    """Что переезжает из прежней игры в новую: всё, что не про прохождение.

    Человек и его связь с ботом (`padawan_id`, `link_key`, `cohort`) — иначе
    код от бота пришлось бы вводить заново, а приложение Голокрон показало
    бы уже игравшему шаг первого запуска. Ответ про Книгу — вопрос задан
    человеку, а не игре. Папка проекта — без неё сторож не стережёт файл с
    паролями (#81); остальное в разделе проекта отвечало на вопросы прежних
    актов.

    Акты, ранг, приёмы, XP, штрафы, словарь, серия и очередь событий не
    переезжают: это и есть прежний путь, он лежит в архиве целиком.

    Значение не той формы не переезжает вовсе: сохранение правят руками, а
    новая игра не должна начинаться с чужого мусора.
    """
    carried = {}
    for key in ("padawan_id", "link_key", "cohort"):
        value = previous.get(key)
        if isinstance(value, str) and value:
            carried[key] = value
    if isinstance(previous.get("book_open"), bool):
        carried["book_open"] = previous["book_open"]
    if previous.get("book_asked") is True:
        carried["book_asked"] = True
    project = previous.get("project")
    folder = project.get("path") if isinstance(project, dict) else None
    if isinstance(folder, str) and folder:
        carried["project"] = {"path": folder}
    return carried


def _has_something_to_lose(previous):
    """Было ли в прежнем сохранении хоть что-то, о чём стоит сказать.

    Сохранение мог завести и хук — на старте сессии, до первой команды.
    Человеку, который в прежнюю игру не играл, строка «пройденное не
    перешло» была бы неправдой.
    """
    return any(previous.get(key) for key in (
        "acts", "xp", "dark_side", "lexicon_unlocked", "artifacts",
    ))


def start_over(path, previous):
    """Прежняя игра — в архив, на её месте новая; вернуть новую.

    Зовётся под замком состояния (_load_under_lock). Новое сохранение
    пишется здесь же,
    а не оставляется вызывающему: команда, которая только читает, иначе
    оставила бы человека без файла, следующая начала бы игру уже без
    переноса и без объяснения — молча.

    Ровно один раз держится самим файлом: новое сохранение несёт версию
    новой игры, и is_previous_game на нём больше не сработает.

    Ошибка диска летит наверх как есть. Хук по своему закону промолчит и
    ничего не запишет — прежний файл либо на месте, либо уже в архиве, и в
    обоих случаях цел.
    """
    fresh = default_state()
    fresh.update(_carried_over(previous))
    where = archive(path)
    fresh["previous_save"] = str(where) if where else None
    if _has_something_to_lose(previous):
        add_notice(fresh, NOTICE_GAME_REBUILT)
    save(fresh, path)
    return fresh


def save(data, path=None):
    path = _target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup_path(path).write_bytes(path.read_bytes())

    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    handle, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".state-", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def lock_path(path):
    return Path(str(path) + ".lock")


def _acquire_lock(path):
    """Взять эксклюзивную файловую блокировку рядом с состоянием.

    Не удалось (нет fcntl на платформе, нет прав на директорию, файловая
    система не умеет flock) — не повод падать или блокировать падавана:
    тот же закон хуков, что и везде, только применённый к самой защите от
    гонки, а не к тому, что она защищает. Возвращаем None, вызывающий
    работает дальше без взаимного исключения — как до этого фикса.
    """
    if fcntl is None:
        return None
    target_lock = lock_path(path)
    try:
        target_lock.parent.mkdir(parents=True, exist_ok=True)
        handle = open(str(target_lock), "a")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except OSError:
        return None
    return handle


def _release_lock(handle):
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        handle.close()
    except OSError:
        pass


# Замки, которые этот поток уже держит. flock не повторно-входим: второй
# open того же файла в том же процессе встал бы в очередь за самим собой и
# повис навсегда. С тех пор как load берёт замок сам (прежняя игра, пустое
# место), вызов load или archive из тела update_state стал бы таким
# зависанием — в хуке это остановленная сессия падавана.
_held = threading.local()


@contextlib.contextmanager
def _locked(path):
    """Замок состояния на время блока; уже взятый этим потоком — не берётся."""
    key = os.path.abspath(str(path))
    held = getattr(_held, "paths", None)
    if held is None:
        held = _held.paths = set()
    if key in held:
        yield
        return
    handle = _acquire_lock(path)
    held.add(key)
    try:
        yield
    finally:
        held.discard(key)
        _release_lock(handle)


@contextlib.contextmanager
def update_state(path=None):
    """Загрузить состояние, дать изменить, сохранить — одним окном под
    файловой блокировкой. Любой read-modify-write состояния обязан идти
    отсюда. Сохранение не происходит, если тело with подняло исключение.
    """
    target = _target(path)
    with _locked(target):
        data = _load_under_lock(target)
        yield data
        save(data, target)


NESTED_DEFAULTS = ("streak", "first_try")


def add_notice(data, key):
    """Поставить одноразовое сообщение падавану.

    Список, а не одно поле: следующее сообщение допишется, не затерев
    чужое ещё не показанное — молчаливая потеря сообщения и есть тот самый
    дефект, ради которого механика заводится. Повтор не дублируется.
    """
    notices = data.get("notices")
    if not isinstance(notices, list):
        notices = []
    if key not in notices:
        notices.append(key)
    data["notices"] = notices
    return data


def migrate(data):
    """Дотянуть сохранение новой игры до текущей формы.

    Сохранение прежней игры сюда не доходит: его уносит в архив _load, и
    миграций через границу игр нет — прогресс не переносится (спека #75,
    решение 7). Прежние шаги 1→2 и 2→3 правили акты прежней игры и ушли
    вместе с ней.
    """
    version = data.get("schema_version", 0)
    if version > SCHEMA_VERSION:
        raise StateError(
            "состояние версии {} новее плагина ({}) — обнови плагин".format(
                version, SCHEMA_VERSION
            )
        )
    merged = default_state()
    merged.update(data)
    for key in NESTED_DEFAULTS:
        base = default_state()[key]
        base.update(merged.get(key) or {})
        merged[key] = base
    merged["schema_version"] = SCHEMA_VERSION
    return merged

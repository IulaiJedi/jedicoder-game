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
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: работаем без взаимного исключения
    fcntl = None

from .ranks import STATUS_DONE, STATUS_IN_PROGRESS, rank_for

SCHEMA_VERSION = 3

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

# Одноразовое объяснение от миграции: Акт 1 перестал закрываться словом.
# Ключ латиницей, как и всё в JSON; текст для падавана живёт в cli.py —
# он единственный, кто печатает.
NOTICE_ACT1_REAL = "act1_became_real"

# Переоткрытый квест — то же самое, что «квест, который просто ещё не
# пройден»: то же значение, которым ranks.enter_act и quests._quest_entry
# помечают свежие акты и квесты. Импортируем константу, а не дублируем
# строку "in_progress": ranks.py уже единственный источник правды для
# статусов (quests.py и acts.py берут их оттуда же), и бесшумный разъезд
# значений сломал бы artifacts_for и карту статуса без единой ошибки.
STATUS_REOPENED = STATUS_IN_PROGRESS


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
    }


def backup_path(path):
    return Path(str(path) + ".bak")


def corrupt_path(path):
    return Path(str(path) + ".corrupt")


def load(path=None):
    # Умолчание считается на вызове, а не на импорте: значение по
    # умолчанию у аргумента застыло бы навсегда и не увидело бы
    # JEDICODER_STATE_PATH.
    path = _target(path)
    if not path.exists():
        return default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _recover(path)
    if not isinstance(data, dict):
        return _recover(path)
    return migrate(data)


def _recover(path):
    try:
        path.replace(corrupt_path(path))
    except OSError:
        pass
    backup = backup_path(path)
    if backup.exists():
        try:
            data = json.loads(backup.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = None
        if isinstance(data, dict):
            return migrate(data)
    return default_state()


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


@contextlib.contextmanager
def update_state(path=None):
    """Загрузить состояние, дать изменить, сохранить — одним окном под
    файловой блокировкой. Любой read-modify-write состояния обязан идти
    отсюда. Сохранение не происходит, если тело with подняло исключение.
    """
    target = _target(path)
    handle = _acquire_lock(target)
    try:
        data = load(target)
        yield data
        save(data, target)
    finally:
        _release_lock(handle)


NESTED_DEFAULTS = ("streak", "first_try")


def add_notice(data, key):
    """Поставить одноразовое сообщение падавану.

    Список, а не одно поле: следующая миграция допишет своё, не затерев
    чужое ещё не показанное — молчаливая потеря сообщения и есть тот самый
    дефект, ради которого механика заводится. Повтор не дублируется:
    миграция крутится на каждом load, пока файл не переписан версией 2.
    """
    notices = data.get("notices")
    if not isinstance(notices, list):
        notices = []
    if key not in notices:
        notices.append(key)
    data["notices"] = notices
    return data


def _migrate_v1_to_v2(data):
    """Снять ack-закрытие квеста 01-idea.

    В версии 1 Акт 1 был заглушкой из одного ack-квеста, и 01-idea значил
    «падаван подтвердил, что идея есть». В версии 2 тот же идентификатор
    значит «research/IDEA.md написан и содержит три части формулы». Оставить
    старое закрытие в силе — значит закрыть Акт 1 без единой строчки IDEA.md,
    при том что следующий квест (02-one-evening) режет именно эту идею: это
    ложный проход ровно того рода, ради которого игра меряет исход
    exit-кодом, а не мнением модели или падавана о себе.

    Закрытие без пометки acknowledged (то есть сделанное проверкой check.sh)
    не трогаем: работа сделана по-настоящему, терять её нельзя ни при каком
    повороте — это правило схемы миграций, а не только этого перехода.
    """
    act = (data.get("acts") or {}).get("1")
    if not act:
        return data
    quest = (act.get("quests") or {}).get("01-idea")
    if not quest or quest.get("acknowledged") is not True:
        return data
    quest["status"] = STATUS_REOPENED
    quest.pop("acknowledged", None)
    if act.get("status") == STATUS_DONE:
        act["status"] = STATUS_REOPENED
        act.pop("completed_at", None)
        # rank — записанное поле, не производное: без пересчёта здесь падаван
        # увидел бы на первом же status ранг «Искатель», выданный за Акт 1,
        # который эта же миграция только что вернула в in_progress. rank_for
        # смотрит только на acts, поэтому его можно звать до слияния с
        # дефолтами, не дожидаясь остальной формы состояния.
        data["rank"] = rank_for(data)
        # Ровно здесь у падавана отбирается видимое: закрытый акт и ранг —
        # у прошедшего дальше честно это два ранга сразу. Решение верное,
        # но молчание превращает его в поломку игры на глазах человека.
        # Ветка одна и та же не случайно: сообщение ставится там, где
        # есть потеря, и не ставится там, где её нет.
        add_notice(data, NOTICE_ACT1_REAL)
    return data


QUEST_RENAMES_V3 = (("1", "02-hutt-filter", "02-one-evening"),)


def _migrate_v2_to_v3(data):
    """Переименовать идентификатор квеста 02 Акта 1.

    Прежний идентификатор нёс имя из франшизы, и холодный прогон 2026-08-06
    замерил механизм дословно: игра печатает идентификатор, падаван набирает
    его же, модель читает латинский слаг, узнаёт отсылку и восстанавливает
    выпиленную метафору из собственных знаний. Слово прозвучало трижды при
    нулевых вхождениях в поставке — вычистить контент оказалось недостаточно.

    Почему версия поднимается, хотя двумя экранами выше (default_state,
    book_open/book_asked) стоит комментарий, читающийся как запрет на бампы.
    Различитель один: нужна ли функция миграции. Там дотягивались два плоских
    ключа, и merged.update(data) плюс default_state() делали это без единой
    строки кода — бамп не покупал ничего, а рисковал откатом. Здесь вложенный
    ключ сам себя не переименует: NESTED_DEFAULTS содержит только streak и
    first_try, acts в слияние не входит. Раз нужен код — нужен и страж версии:
    безусловное переименование крутилось бы на каждом load вечно и не
    оставляло бы отметки, по которой следующая миграция отличит «до» от
    «после». И отказ при откате обязан быть громким: без бампа старый плагин
    молча показал бы закрытый Акт 1 с неначатым квестом 02, а это ровно тот
    противоречивый зелёный экран, дороже которого честный отказ.

    add_notice не ставится намеренно: миграция ничего видимого не отбирает —
    статус, попытки, статус акта, ранг и XP переезжают целиком. Сообщение
    ставится там, где есть потеря, и не ставится там, где её нет.

    Очередь pending_sync переименовывается вместе с состоянием: это аутбокс,
    а не журнал, бот этих строк ещё не видел. Уже отправленные события лежат
    в таблице events бота — другой репозиторий, отсюда их не переписать.
    """
    acts_map = data.get("acts")
    if not isinstance(acts_map, dict):
        acts_map = {}
    for act_key, old_id, new_id in QUEST_RENAMES_V3:
        act = acts_map.get(act_key)
        if isinstance(act, dict):
            quests = act.get("quests")
            # Новый ключ уже на месте — старый не переезжает поверх него:
            # иначе переименование затёрло бы работу, сделанную после
            # обновления плагина.
            if isinstance(quests, dict) and old_id in quests:
                if new_id not in quests:
                    quests[new_id] = quests[old_id]
                del quests[old_id]
        # Поле act у события не сверяется: все 38 идентификаторов квестов
        # уникальны в пределах игры (прибито тестом), поэтому совпадения
        # по quest достаточно, а лишняя сверка типа (1 против "1") дала бы
        # непереименованное событие — то есть испорченную книгу — на ровном
        # месте.
        for event in data.get("pending_sync") or []:
            if isinstance(event, dict) and event.get("quest") == old_id:
                event["quest"] = new_id
    return data


def migrate(data):
    version = data.get("schema_version", 0)
    if version > SCHEMA_VERSION:
        raise StateError(
            "состояние версии {} новее плагина ({}) — обнови плагин".format(
                version, SCHEMA_VERSION
            )
        )
    if version < 2:
        data = _migrate_v1_to_v2(data)
    if version < 3:
        data = _migrate_v2_to_v3(data)
    merged = default_state()
    merged.update(data)
    for key in NESTED_DEFAULTS:
        base = default_state()[key]
        base.update(merged.get(key) or {})
        merged[key] = base
    merged["schema_version"] = SCHEMA_VERSION
    return merged

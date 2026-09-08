"""Факты Разбора: числа прохождения, посчитанные из сохранения.

Первый из двух слоёв Разбора (ADR-0010 в репозитории сайта): факты печатает
движок, текст поверх них пишет Магистр и не вправе назвать ни одного числа
иначе. Поэтому здесь нет ни одной строки для человека — только числа,
списки и признаки; как их произнести, решает тот, кто печатает.

Модуль без I/O, по образцу ranks.py: сохранение приходит параметром, внутри
ни диска, ни сети, ни процессов. Часы читаются в одном месте и только когда
дату не передали (days_in_path у не дошедшего до финала) — по тем же часам
UTC, по которым журнал ставит свои даты.

Читатель прощающий: сохранение правят руками, а плагин откатывают на версию
назад. Разбор обязан отдать то, что понял, а не упасть на глазах у падавана
и не потерять молча то, чего не узнал.
"""
from datetime import datetime

from . import acts as acts_mod
from . import ranks
from . import state as st

STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATE_FORMAT = "%Y-%m-%d"

# Порог, с которого квест считается тяжёлым: одна попытка — это «прошёл», а
# не «дался тяжело». Ack-квест закрывается вообще без проверки и тоже несёт
# одну попытку. Назвать любой из них самым тяжёлым значило бы дать Разбору
# готовую фразу «тяжелее всего дался», которой числа не подтверждают; сами
# попытки при этом никуда не деваются, они в списке квестов.
HARD_ATTEMPTS = 2


def facts(state, today=None):
    """Факты прохождения. Чистая функция от сохранения и даты.

    `today` — календарная дата UTC строкой «ГГГГ-ММ-ДД»; не передали, берём
    по часам. Влияет она ровно на одно число, days_in_path у падавана,
    который ещё не закрыл Акт 5.

    Что в ответе (ключи латиницей, значения — только числа и списки):

    | ключ | что значит |
    |---|---|
    | `rank`, `rank_title` | слаг ранга и его русское имя из ranks.RANK_TITLES |
    | `acts_completed` | номера закрытых актов по возрастанию |
    | `track` | трек падавана или None, если не выбран |
    | `deploy_path` | путь деплоя (ось Акта 4) или None |
    | `product_url` | ссылка на продукт из паспорта или None |
    | `days_in_path` | дней от входа в Акт 1 до финала или до сегодня; None, если даты нет |
    | `quests` | все записанные квесты: act, quest, attempts, closed |
    | `quests_closed` | сколько квестов закрыто ВСЕГО, по обе стороны развилок |
    | `attempts_total` | сумма попыток по всем записанным квестам |
    | `hardest_quest` | запись самого тяжёлого квеста или None |
    | `first_try` | passed/attempted — счётчики «с первой попытки» |
    | `streak` | current/best — серия сохранений |
    | `terms_unlocked` | сколько терминов словаря открыто |
    | `xp` | очки опыта |
    | `dark_side` | см. _dark_side: счётчик, журнал по типам и полнота журнала |

    Пустое сохранение отдаёт ту же форму: ранг youngling, пустые списки,
    нули и None. Ни одного ключа не пропадает — печатающему не придётся
    гадать, чего в ответе нет.
    """
    state = state if isinstance(state, dict) else {}
    rank = ranks.rank_for(state)
    quests = _quests(state)
    return {
        "rank": rank,
        "rank_title": ranks.RANK_TITLES.get(rank, rank),
        "acts_completed": ranks.completed_acts(state),
        "track": acts_mod.track_of(state),
        "deploy_path": acts_mod.deploy_of(state),
        "product_url": _product_url(state),
        "days_in_path": days_in_path(state, today),
        "quests": quests,
        "quests_closed": sum(1 for quest in quests if quest["closed"]),
        "attempts_total": sum(quest["attempts"] for quest in quests),
        "hardest_quest": _hardest(quests),
        "first_try": _counters(state, "first_try", ("passed", "attempted")),
        # last_commit_date из серии не берётся: Разбор говорит о её длине,
        # а не о том, когда падаван сохранялся в последний раз.
        "streak": _counters(state, "streak", ("current", "best")),
        "terms_unlocked": _count(state.get("lexicon_unlocked")),
        "xp": _int(state.get("xp")),
        "dark_side": _dark_side(state),
    }


def days_in_path(state, today=None):
    """Дней от входа в Акт 1 до закрытия Акта 5 включительно.

    Акт 5 ещё не закрыт — путь идёт, и конец считается по сегодняшнему дню:
    Свиток выдаётся на любом ранге, и «дней в пути» у дошедшего до середины
    такой же честный факт, как у Мастера. А вот у закрытого Акта 5 без даты
    закрытия (беты прошлых версий) ответ — None, а не счёт до сегодня:
    закончившему в июле нельзя приписывать недели, которых у него не было.

    Дни календарные, а не полные сутки между отметками: вошёл поздно вечером
    и закрыл ранним утром — это два дня жизни падавана, а не один. Разница
    видна только на краях, но именно на краях число и читается как ошибка.

    Отметки входа нет или она не разобралась — тоже None: тот, кто печатает,
    молча пропустит строку, а не назовёт выдуманное число.
    """
    acts_map = state.get("acts")
    if not isinstance(acts_map, dict):
        return None
    start = _parsed_date(_field(acts_map, "1", "started_at"), STAMP_FORMAT)
    if start is None:
        return None
    end = _parsed_date(_field(acts_map, "5", "completed_at"), STAMP_FORMAT)
    if end is None:
        if _field(acts_map, "5", "status") == ranks.STATUS_DONE:
            return None
        end = _parsed_date(today or st.today_utc(), DATE_FORMAT)
    if end is None:
        return None
    return max(1, (end - start).days + 1)


def _dark_side(state):
    """Тёмная сторона: счётчик, журнал по типам и признак неполного журнала.

    Наружу идут ДВА числа на каждый тип — очки и разные дни, — потому что
    одно прочитывается неверно. Запись в журнале — это очко, а не пойманное
    действие: отправка `.env` стоит двух очков и оставляет две записи одной
    датой, так что «дважды» по числу записей — это один вечер, а не два.

    Счётчик и журнал тоже отдаются оба и не сводятся к одному. У игравшего
    до появления журнала (ADR-0011 в репозитории сайта) очки есть, а записей
    нет, и восстановить их задним числом нечем: команду не хранили никогда.
    Выдать разницу за ноль — значит сказать падавану, что он чист там, где
    он не чист; поэтому есть unlogged и log_incomplete, а решает, как это
    произнести, тот, кто печатает.

    Незнакомый тип не отсеивается: фильтра здесь нет вовсе (его нет и в
    state.dark_side_entries), а порядок строк задаётся очками и алфавитом,
    а не перечнем DARK_SIDE_KINDS. Запись от плагина новее переживает откат
    версии — потерять очко хуже, чем назвать его незнакомым словом.
    """
    entries = st.dark_side_entries(state)
    points = _int(state.get("dark_side"))
    per_kind = {}
    days = set()
    for entry in entries:
        kind, date = entry["type"], entry["date"]
        seen = per_kind.setdefault(kind, {"points": 0, "days": set()})
        seen["points"] += 1
        seen["days"].add(date)
        days.add(date)
    by_kind = [
        {"kind": kind, "points": seen["points"], "days": len(seen["days"])}
        for kind, seen in per_kind.items()
    ]
    # Сначала по очкам вниз, при равенстве по имени: порядок обязан быть
    # одним и тем же на одном и том же сохранении — Разбор попадает в файл
    # и в git падавана, и переставленные строки читались бы как правка.
    by_kind.sort(key=lambda row: (-row["points"], row["kind"]))
    return {
        "points": points,
        "logged": len(entries),
        "unlogged": max(0, points - len(entries)),
        "log_incomplete": points > len(entries),
        "days": len(days),
        "by_kind": by_kind,
    }


def _quests(state):
    """Записанные квесты по актам: акты по номеру, внутри — порядок реестра.

    Выбор падавана на развилке не спрашивается намеренно: сменивший трек
    оставляет в сохранении квесты обоих треков, и попытки на них он всё-таки
    потратил. Реестр здесь задаёт только порядок перечисления, а не состав —
    поэтому и quest_ids не годится, он отвечает на другой вопрос.

    Квест или целый акт, которых в реестре нет (сохранение от плагина новее,
    откат версии), не выбрасываются, а встают в хвост по алфавиту: молча
    потерять попытки хуже, чем перечислить их не на своём месте.
    """
    acts_map = state.get("acts")
    if not isinstance(acts_map, dict):
        return []
    records = []
    for act in _act_numbers(acts_map):
        recorded = _field(acts_map, str(act), "quests")
        if not isinstance(recorded, dict):
            continue
        try:
            order = acts_mod.all_quest_ids(act)
        except acts_mod.UnknownActError:
            order = ()
        tail = tuple(sorted(set(recorded) - set(order)))
        for quest_id in order + tail:
            entry = recorded.get(quest_id)
            if isinstance(entry, dict):
                records.append({
                    "act": act,
                    "quest": quest_id,
                    "attempts": _int(entry.get("attempts")),
                    "closed": entry.get("status") == ranks.STATUS_DONE,
                })
    return records


def _hardest(quests):
    """Квест, на который ушло больше всего попыток; ничья — за более ранним.

    Ничья решается в пользу раннего намеренно: там падаван застрял впервые,
    и это про него честнее, чем последний из равных. Все квесты с первой
    попытки — None, см. HARD_ATTEMPTS.
    """
    hardest = None
    for record in quests:
        if record["attempts"] >= HARD_ATTEMPTS and (
            hardest is None or record["attempts"] > hardest["attempts"]
        ):
            hardest = record
    return dict(hardest) if hardest else None


def _act_numbers(acts_map):
    """Номера актов, записанных в сохранении, по возрастанию.

    Из сохранения, а не из реестра: акт, которого движок не знает, — это
    откат версии, и его квесты тоже история падавана. Ключ, который не
    число (правка руками), пропускается молча — тем же правилом, что и в
    ranks.completed_acts.
    """
    numbers = []
    for key in acts_map:
        try:
            numbers.append(int(key))
        except (TypeError, ValueError):
            continue
    return sorted(numbers)


def _field(acts_map, key, name):
    """Поле записи акта; запись не словарь (правка руками) — None."""
    entry = acts_map.get(key)
    return entry.get(name) if isinstance(entry, dict) else None


def _product_url(state):
    project = state.get("project")
    if not isinstance(project, dict):
        return None
    url = project.get("url")
    return url if isinstance(url, str) and url else None


def _counters(state, key, names):
    """Пара счётчиков из вложенного словаря сохранения.

    Мусор в поле — те же нули, что у новичка: у Разбора нет права упасть
    из-за правки руками.
    """
    source = state.get(key)
    if not isinstance(source, dict):
        source = {}
    return dict((name, _int(source.get(name))) for name in names)


def _parsed_date(value, fmt):
    """Календарная дата из строки заданного вида; не разобралась — None."""
    try:
        return datetime.strptime(value, fmt).date()
    except (TypeError, ValueError):
        return None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _count(value):
    return len(value) if isinstance(value, (list, tuple, set)) else 0

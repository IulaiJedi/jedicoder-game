"""Прогрессия: ранги, артефакты, право войти в акт.

Два правила, которые здесь закодированы и легко нарушить случайно:

1. Ранг считается ТОЛЬКО по закрытым актам, идущим непрерывно от первого.
   XP на ранг не влияет — иначе падаван, насобиравший терминов, перескочит
   акт, которого не проходил.
2. Артефакт выдаётся на ВХОДЕ в акт (он инструмент прохождения), ранг —
   на выходе (он заслуга).

Модуль без I/O: функции принимают и возвращают dict состояния.
"""
from datetime import datetime, timezone

RANKS = ("youngling", "seeker", "padawan", "knight", "sentinel", "master")

RANK_TITLES = {
    "youngling": "Юнлинг",
    "seeker": "Искатель",
    "padawan": "Падаван",
    "knight": "Рыцарь",
    "sentinel": "Страж",
    "master": "Мастер",
}

# Акты, временно выключенные: войти нельзя, карта показывает «готовится».
#
# Именно «выключен», а не «удалён»: реестр акта, его контент, квесты и их
# проверки остаются целыми и тестируются как прежде. Вернуть акт — убрать
# номер отсюда, и всё оживёт тем же составом.
#
# Два решения сложились в этот список.
#
# 2026-09-10: Акт 5 «Выход в свет» — деплой, домен, SSL, публикация — уходит
# из бесплатной игры в клуб.
#
# 2026-10-08 (спека #75): игра перестраивается под полного новичка — сначала
# человек учится работать с Claude Code, потом собирает своё. Новый Акт 1
# «Знакомство» встал на место прежнего «Поиска боли» (тот лежит на полке,
# shelf/act1-poisk-boli/), а Акты 2–4 ждут своих спек под прежними номерами:
# их порядок и состав изменятся, и пускать в них после нового первого акта
# значило бы вести человека старой дорогой.
#
# 2026-10-13 (спека #99): номер 2 занял Акт 2 «Память и силы» — он играется.
# Прежний «Чертёж» лежит на полке (shelf/act2-chertezh/) вместе с приёмом
# `plan`: тот вернётся приёмом будущего Акта 4. Игра пока кончается Актом 2.
#
# 2026-10-13 (спека #108): номер 3 занял Акт 3 «Умения» — скиллы, набор,
# свой скилл, хук, мод. Прежняя «Первая кровь» лежит на полке
# (shelf/act3-pervaya-krov/); её приём `investigate` остался в игре приёмом
# нового акта. Игра пока кончается Актом 3.
#
# 2026-10-14 (спека #117): номер 4 занял Акт 4 «Свой продукт» — сайт или
# Telegram-бот на своём компьютере простым путём второго вечера. Прежний «Щит»
# лежит на полке (shelf/act4-shchit/) вместе с приёмом `cso`. Приём нового
# акта — `goal` («Цель»): прежде он был без замка, теперь его выдают на входе.
#
# 2026-10-16 (спека #123): номер 5 занял Акт 5 «Три места кода» — GitHub,
# закрытое хранилище, одна версия на компьютере и на GitHub, чужой сервис,
# сервер словами. Прежний «Выход в свет» с выкладкой в интернет лежит на полке
# (shelf/act5-vyhod-v-svet/) вместе с приёмом `deploy`; приём нового акта —
# `cso` («Проверка ключей»), он вернулся с полки «Щита». Выключенных актов
# больше нет: игра кончается Актом 5 и рангом Мастер.
#
# Отсюда же считаются последний играбельный акт и последний достижимый ранг:
# два места, где раньше стояло «пятый» и «Мастер» просто потому, что они шли
# в реестре последними. Список пуст, но механика цела: выключить акт снова —
# вписать сюда его номер.
MUTED_ACTS = ()

ACTS = {
    1: {
        "slug": "act1-znakomstvo",
        "title": "Знакомство",
        "artifact": "brainstorm",
        "rank": "seeker",
    },
    2: {
        "slug": "act2-pamyat-i-sily",
        "title": "Память и силы",
        "artifact": "handoff",
        "rank": "padawan",
    },
    3: {
        "slug": "act3-umeniya",
        "title": "Умения",
        "artifact": "investigate",
        "rank": "knight",
    },
    4: {
        "slug": "act4-svoy-produkt",
        "title": "Свой продукт",
        "artifact": "goal",
        "rank": "sentinel",
    },
    5: {
        "slug": "act5-tri-mesta",
        "title": "Три места кода",
        "artifact": "cso",
        "rank": "master",
    },
}

# Артефакты без замка: открыты с первого дня, поэтому в ACTS их нет и
# добавить их туда нельзя — ACTS читают и вход в акт, и ранги, и катсцены.
# Сегодня таких нет: `goal` жил здесь до 2026-10-14 и стал приёмом Акта 4
# (спека #117). Место оставлено — механика без замка в движке цела.
#
# Список имён артефактов при этом обязан быть один. Читателям, которым
# нужен полный состав (линтер инструкций Свитка, сборка самого Свитка),
# полагается брать ALL_ARTIFACTS, а не перечислять имена у себя: два
# перечня разъедутся молча — новый артефакт появится в одном и не появится
# в другом, и никто не заметит.
UNLOCKED_ARTIFACTS = ()

ALL_ARTIFACTS = tuple(
    ACTS[number]["artifact"] for number in sorted(ACTS)
) + UNLOCKED_ARTIFACTS

STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"


class ProgressionError(RuntimeError):
    """Действие нарушает порядок прохождения."""


def _act_entry(state, act):
    return state.get("acts", {}).get(str(act))


def _require_known(act):
    if act not in ACTS:
        raise ValueError("нет акта {}".format(act))


def completed_acts(state):
    done = []
    for number, entry in (state.get("acts") or {}).items():
        # Ключ, который не число, пропускается молча: правка руками не
        # должна ронять ни close_act (он зовёт rank_for), ни Разбор — а
        # актом такая запись всё равно не является.
        try:
            act = int(number)
        except (TypeError, ValueError):
            continue
        if (entry or {}).get("status") == STATUS_DONE:
            done.append(act)
    return sorted(done)


def rank_for(state):
    done = set(completed_acts(state))
    rank = RANKS[0]
    for number in sorted(ACTS):
        if number in done:
            rank = ACTS[number]["rank"]
        else:
            break
    return rank


def can_enter_act(state, act):
    _require_known(act)
    if act == min(ACTS):
        return True, ""
    previous = act - 1
    entry = _act_entry(state, previous)
    if entry and entry.get("status") == STATUS_DONE:
        return True, ""
    return False, (
        "Акт {} опирается на приёмы Акта {}. Сначала закрой Акт {} — "
        "иначе дальше придётся возвращаться.".format(act, previous, previous)
    )


def artifacts_for(state):
    given = []
    for number in sorted(ACTS):
        entry = _act_entry(state, number)
        if entry and entry.get("status") in (STATUS_IN_PROGRESS, STATUS_DONE):
            given.append(ACTS[number]["artifact"])
    return given


def artifact_unlocked(state, artifact):
    return artifact in artifacts_for(state)


def _stamp_started_at(entry):
    # Дата входа ставится один раз, как и completed_at: по паре считается
    # «дней в пути» на карточке Мастера.
    if not entry.get("started_at"):
        entry["started_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )


def enter_act(state, act):
    # Импорт внутри функции, а не в шапке модуля, — след прежнего цикла: до
    # #78 state.py импортировал ranks.py на верхнем уровне (rank_for был
    # нужен миграции), и обратный импорт там же падал на порядке
    # `from jedicoder import ranks, state as st`. Миграция ушла вместе с
    # прежней игрой, цикла больше нет; импорт оставлен на месте, чтобы
    # состояние не стало зависимостью модуля чистых функций на загрузке.
    from . import state as st

    _require_known(act)
    allowed, reason = can_enter_act(state, act)
    if not allowed:
        raise ProgressionError(reason)
    acts = state.setdefault("acts", {})
    entry = acts.get(str(act))
    if entry is None:
        acts[str(act)] = {"status": STATUS_IN_PROGRESS, "quests": {}}
        entry = acts[str(act)]
        _stamp_started_at(entry)
        st.enqueue_event(state, "act_started", act=act)
    elif entry.get("status") != STATUS_DONE:
        entry["status"] = STATUS_IN_PROGRESS
        entry.setdefault("quests", {})
        _stamp_started_at(entry)
    # Акт уже закрыт (DONE) — вход задним числом не переписывает started_at:
    # иначе падаван из до-Act5-беты, перезаходящий в закрытый акт, получит
    # свежий штамп и лживо короткие «дни в пути» на карточке Мастера.
    state["current_act"] = act
    state["artifacts"] = artifacts_for(state)
    return state


def close_act(state, act):
    # См. enter_act — импорт state здесь же и по той же причине: цикл на
    # верхнем уровне модуля, безопасно только внутри функции.
    from . import state as st

    _require_known(act)
    entry = _act_entry(state, act)
    if entry is None:
        raise ProgressionError("Акт {} не начат".format(act))
    entry["status"] = STATUS_DONE
    entry.setdefault("quests", {})
    # Дата закрытия ставится один раз: повторный вызов не должен переписывать
    # историю падавана — по ней считается длительность прохождения.
    if not entry.get("completed_at"):
        entry["completed_at"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    # Сравнение до/после, а не факт закрытия акта: _maybe_close_act (через
    # close_act) вызывается и там, где ранг не меняется (открытый долг №1 —
    # «Новый ранг» при закрытии без повышения), событие rank_up должно быть
    # честным сигналом смены ранга, а не эхом любого close_act.
    before = state.get("rank")
    state["rank"] = rank_for(state)
    if state["rank"] != before:
        st.enqueue_event(state, "rank_up", payload={
            "rank": state["rank"], "xp": int(state.get("xp", 0)),
        })
    state["artifacts"] = artifacts_for(state)
    return state


def add_xp(state, amount):
    state["xp"] = int(state.get("xp", 0)) + int(amount)
    return state


def playable_acts():
    """Акты, в которые падаван может войти сегодня, по порядку."""
    return [number for number in sorted(ACTS) if number not in MUTED_ACTS]


def is_muted(act):
    return act in MUTED_ACTS


def muted_after(act):
    """Выключенные акты, стоящие в реестре после данного, по порядку.

    Непустой ответ для FINAL_ACT значит, что игра не кончилась, а
    приостановлена: дорога дальше есть, она готовится. Финал — карточка с
    адресом страницы, событие боту — бывает только у конца реестра (решение
    оператора 2026-10-08: один вечер Акта 1 финалом не объявляется).
    """
    return [number for number in sorted(ACTS)
            if number > act and number in MUTED_ACTS]


#: Последний играбельный акт: им игра заканчивается, его закрытие даёт финал.
FINAL_ACT = playable_acts()[-1]

#: Ранг, которым игра заканчивается сегодня. Не RANKS[-1]: когда последний
#: акт реестра выключен, его ранг недостижим, и ворота финала, сверяясь с
#: ним, не открылись бы никогда. С 2026-10-16 выключенных актов нет, и это
#: Мастер — тот же ранг, но посчитанный, а не набранный.
FINAL_RANK = ACTS[FINAL_ACT]["rank"]

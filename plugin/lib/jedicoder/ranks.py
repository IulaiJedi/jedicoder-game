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

# Акты, временно выключенные. Решение автора 2026-09-10: Акт 5 «Выход в свет»
# — деплой, домен, SSL, публикация — уходит из бесплатной игры в клуб, и игра
# пока заканчивается Актом 4.
#
# Именно «выключен», а не «удалён»: реестр акта, его контент, семь квестов и
# их проверки остаются целыми и тестируются как прежде. Вернуть акт — убрать
# номер отсюда, и всё оживёт тем же составом.
#
# Отсюда же считаются последний играбельный акт и последний достижимый ранг:
# два места, где раньше стояло «пятый» и «Мастер» просто потому, что они шли
# в реестре последними.
MUTED_ACTS = (5,)

ACTS = {
    1: {
        "slug": "act1-poisk-boli",
        "title": "Поиск боли",
        "artifact": "brainstorm",
        "rank": "seeker",
    },
    2: {
        "slug": "act2-chertezh",
        "title": "Чертёж",
        "artifact": "plan",
        "rank": "padawan",
    },
    3: {
        "slug": "act3-pervaya-krov",
        "title": "Первая кровь",
        "artifact": "investigate",
        "rank": "knight",
    },
    4: {
        "slug": "act4-shchit",
        "title": "Щит",
        "artifact": "cso",
        "rank": "sentinel",
    },
    5: {
        "slug": "act5-vyhod-v-svet",
        "title": "Выход в свет",
        "artifact": "deploy",
        "rank": "master",
    },
}

# Артефакт без замка. `goal` не принадлежит ни одному акту: он открыт с
# первого дня, поэтому в ACTS его нет и добавить его туда нельзя — ACTS
# читают и вход в акт, и ранги, и катсцены.
#
# Список имён артефактов при этом обязан быть один. Читателям, которым
# нужен полный состав (линтер инструкций Свитка, сборка самого Свитка),
# полагается брать ALL_ARTIFACTS, а не перечислять имена у себя: два
# перечня разъедутся молча — новый артефакт появится в одном и не появится
# в другом, и никто не заметит.
UNLOCKED_ARTIFACTS = ("goal",)

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
        "Акт {} опирается на артефакты Акта {}. Сначала закрой Акт {} — "
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
    # Импорт внутри функции, а не в шапке модуля: state.py импортирует
    # ranks.py на верхнем уровне (rank_for нужен миграции), и обратный
    # импорт там же завёл бы настоящий цикл — падает ровно на порядке
    # `from jedicoder import ranks, state as st`, которым открывается
    # tests/test_ranks.py. Внутри функции цикла нет: к моменту вызова
    # enter_act оба модуля уже полностью загружены.
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


#: Последний играбельный акт: им игра заканчивается, его закрытие даёт финал.
FINAL_ACT = playable_acts()[-1]

#: Ранг, которым игра заканчивается сегодня. Не RANKS[-1]: последний ранг
#: реестра принадлежит выключенному акту, и ворота финала, сверяясь с ним,
#: не открылись бы никогда.
FINAL_RANK = ACTS[FINAL_ACT]["rank"]

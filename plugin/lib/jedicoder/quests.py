"""Запуск проверок квестов и учёт попыток.

Исход квеста определяет exit-код check.sh, а не модель. JSON в stdout
нужен только чтобы объяснить падавану, что именно не сошлось.

Поле attempts кормит три механики сразу — хук «ИИ ходит по кругу», ось
«с первой попытки» и payload события — поэтому инкремент живёт здесь и
только здесь.
"""
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import state as st
from .ranks import STATUS_DONE, STATUS_IN_PROGRESS, add_xp

KIND_SCRIPT = "script"
KIND_ACK = "ack"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CANNOT_CHECK = 2

LOOP_THRESHOLD = 3

# Спек решения по XP (2026-07-27): плоские 20 за первое закрытие квеста,
# у квестов нет поля xp — балансировать нечего, пока XP ни на что не влияет.
QUEST_XP = 20


class QuestError(RuntimeError):
    """check.sh нарушил контракт: не JSON в stdout или exit-код не сходится."""


@dataclass(frozen=True)
class CheckResult:
    quest: str
    kind: str
    exit_code: int
    ok: bool
    checks: tuple
    stderr: str
    countable: bool


def script_path(quests_root, act_slug, quest_id):
    # resolve() обязателен: сам скрипт ищется относительно процесса CLI, а
    # запускается с cwd=проект падавана. При относительном quests_root
    # проверка файла проходила бы, а bash отдавал 127.
    return Path(quests_root).resolve() / act_slug / quest_id / "check.sh"


def cannot_check(result):
    """Скрипт не смог вынести решение: exit-код вне {0, 1}.

    Кроме честного `exit 2` сюда попадают инфраструктурные сбои (127 — нет
    bash или скрипта, 126 — нет прав, >128 — убит сигналом). Всё это не вина
    падавана, поэтому попытка не засчитывается.
    """
    return result.kind == KIND_SCRIPT and result.exit_code not in (
        EXIT_PASS, EXIT_FAIL
    )


def run_check(quests_root, act_slug, quest_id, project_dir,
              env_extra=None, timeout=60):
    script = script_path(quests_root, act_slug, quest_id)
    if not script.is_file():
        return CheckResult(
            quest=quest_id, kind=KIND_ACK, exit_code=EXIT_PASS, ok=False,
            checks=(), stderr="", countable=False,
        )

    env = dict(os.environ)
    env.update(env_extra or {})
    process = subprocess.run(
        ["bash", str(script)],
        cwd=str(project_dir),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    code = process.returncode

    if code not in (EXIT_PASS, EXIT_FAIL):
        # Любой код вне {0, 1} — «не смог проверить». stdout не разбираем: у
        # сорванного скрипта его может не быть вовсе, а требовать JSON от
        # bash'а, который не нашёл файл, бессмысленно.
        return CheckResult(
            quest=quest_id, kind=KIND_SCRIPT, exit_code=code, ok=False,
            checks=(), stderr=process.stderr.strip(), countable=False,
        )

    try:
        payload = json.loads(process.stdout)
    except ValueError:
        raise QuestError(
            "{}: stdout не JSON: {!r}".format(script, process.stdout[:200])
        )
    if not isinstance(payload, dict):
        raise QuestError("{}: stdout не объект JSON".format(script))

    reported_ok = bool(payload.get("ok"))
    if reported_ok != (code == EXIT_PASS):
        raise QuestError(
            "{}: exit-код ({}) и поле ok ({}) расходятся".format(
                script, code, reported_ok
            )
        )

    return CheckResult(
        quest=quest_id, kind=KIND_SCRIPT, exit_code=code, ok=reported_ok,
        checks=tuple(payload.get("checks") or ()),
        stderr=process.stderr.strip(), countable=True,
    )


def failed_checks(result):
    return [check for check in result.checks if not check.get("ok")]


def _quest_entry(state, act, quest_id, create=False):
    acts = state.setdefault("acts", {}) if create else state.get("acts", {})
    entry = acts.get(str(act))
    if entry is None:
        if not create:
            return None
        entry = {"status": STATUS_IN_PROGRESS, "quests": {}}
        acts[str(act)] = entry
    quests_map = entry.setdefault("quests", {}) if create else entry.get("quests", {})
    quest = quests_map.get(quest_id)
    if quest is None and create:
        quest = {"status": STATUS_IN_PROGRESS, "attempts": 0}
        quests_map[quest_id] = quest
    return quest


def attempts(state, act, quest_id):
    quest = _quest_entry(state, act, quest_id)
    return int((quest or {}).get("attempts", 0))


def record_attempt(state, act, quest_id, result):
    quest = _quest_entry(state, act, quest_id, create=True)
    if quest["status"] == STATUS_DONE:
        return state
    if result.countable:
        quest["attempts"] = int(quest.get("attempts", 0)) + 1
    if result.ok:
        quest["status"] = STATUS_DONE
        add_xp(state, QUEST_XP)
        counters = state.setdefault("first_try", {"passed": 0, "attempted": 0})
        counters["attempted"] = int(counters.get("attempted", 0)) + 1
        if quest["attempts"] == 1:
            counters["passed"] = int(counters.get("passed", 0)) + 1
        st.enqueue_event(state, "quest_completed", act=act, quest=quest_id, payload={
            "attempts": quest["attempts"],
            "first_try": quest["attempts"] == 1,
            "xp": int(state.get("xp", 0)),
            "first_try_passed": counters["passed"],
            "first_try_attempted": counters["attempted"],
        })
    elif result.countable:
        st.enqueue_event(state, "quest_failed", act=act, quest=quest_id, payload={
            "attempts": quest["attempts"],
        })
    return state


def acknowledge(state, act, quest_id):
    """Закрыть квест, у которого нет check.sh (обучающий или самоотчётный).

    first_try не трогаем: ack-квест всегда «с первой попытки», и учёт его
    исказил бы ось соревнования.
    """
    quest = _quest_entry(state, act, quest_id, create=True)
    if quest["status"] != STATUS_DONE:
        quest["status"] = STATUS_DONE
        quest["attempts"] = max(1, int(quest.get("attempts", 0)))
        quest["acknowledged"] = True
        add_xp(state, QUEST_XP)
        counters = state.get("first_try") or {"passed": 0, "attempted": 0}
        st.enqueue_event(state, "quest_completed", act=act, quest=quest_id, payload={
            "attempts": quest["attempts"],
            "first_try": True,
            "acknowledged": True,
            "xp": int(state.get("xp", 0)),
            "first_try_passed": int(counters.get("passed", 0)),
            "first_try_attempted": int(counters.get("attempted", 0)),
        })
    return state


def loop_warning(state, act, quest_id, threshold=LOOP_THRESHOLD):
    quest = _quest_entry(state, act, quest_id)
    if not quest or quest.get("status") == STATUS_DONE:
        return False
    return int(quest.get("attempts", 0)) >= threshold

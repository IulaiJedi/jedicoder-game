#!/usr/bin/env python3
"""Реплей Stop-хука словаря-лута по транскрипту живого прогона.

Запуск:
    python3 scripts/replay_lexicon.py <транскрипт.jsonl> \\
        --act-switch 2026-08-01T21:06:49.281Z=2

Инструмент разработки, не рантайм. Отбор терминов берётся у настоящего хука
(`lexicon_loot.find_terms`) — своей копии логики здесь нет намеренно: копия
доказывала бы работу самой себя, а не игры. Состояние живёт в памяти, файл
падавана не читается и не пишется вовсе.

Зачем нужен: за весь Акт 1 прогона 2026-08-01 словарь выдал ноль карточек.
Прежде чем чинить, надо было воспроизвести молчание на том самом тексте —
и получить те же три карточки в те же секунды, что видел живой падаван.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "lib"))
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))

import lexicon_loot  # noqa: E402

from jedicoder import content  # noqa: E402

DEFAULT_CONTENT_ROOT = ROOT / "plugin" / "content" / "ru"

# Служебные записи между ответами модели. Их пропускаем, НЕ прерывая сбор:
# Claude Code вклинивает их между кусками одного и того же ответа, и обрыв
# на них дал бы реплею меньше текста, чем видел живой хук.
NOISE = frozenset([
    "attachment",
    "file-history-snapshot",
    "file-history-delta",
    "ai-title",
    "mode",
    "permission-mode",
    "last-prompt",
    "system",
])

DEFAULT_ACT = 1


def _parse_stamp(raw):
    """ISO 8601 → datetime с зоной. None, если не разобрать.

    'Z' на конце `datetime.fromisoformat` не понимает вплоть до Python 3.11,
    а минимум проекта — 3.8, поэтому подменяем вручную. Наивному моменту
    приписываем UTC: сравнение наивного с зонным бросает TypeError, и реплей
    упал бы трейсбеком там, где обязан объяснить.
    """
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp


def parse_switches(raw_values):
    """[(момент, акт)] из --act-switch. Мусор — отказ, а не «всегда».

    Пустая метка (`--act-switch =2`) сравнилась бы как «раньше всего» и
    перевела бы на второй акт ВСЕ точки. Точек Акта 1 не осталось бы вовсе,
    и «ноль карточек за Акт 1» вышел бы сам собой — при полностью исправном
    словаре. Это ложный зелёный, поэтому здесь ValueError, а выше — код 2.
    """
    switches = []
    for raw in raw_values or []:
        stamp_text, sign, act_text = str(raw).rpartition("=")
        if not sign:
            raise ValueError(
                "метка {!r} не содержит '=': ждали <ISO8601>=<номер акта>".format(raw)
            )
        stamp = _parse_stamp(stamp_text)
        if stamp is None:
            raise ValueError(
                "в метке {!r} момент {!r} не разобрался как ISO 8601 "
                "(пример: 2026-08-01T21:06:49.281Z)".format(raw, stamp_text)
            )
        try:
            act = int(act_text.strip())
        except ValueError:
            raise ValueError(
                "в метке {!r} номер акта {!r} — не целое число".format(raw, act_text)
            )
        switches.append((stamp, act))
    switches.sort(key=lambda pair: pair[0])
    return switches


def act_at(stamp, switches):
    """Номер акта на момент точки: максимум среди меток не позже неё."""
    act = DEFAULT_ACT
    for moment, number in switches:
        if moment <= stamp:
            act = max(act, number)
    return act


def load_entries(path):
    """Записи транскрипта по строкам JSONL."""
    entries = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                raise ValueError(
                    "строка {} транскрипта не разобралась как JSON".format(number)
                )
    return entries


def assistant_text(entry):
    """Только text-блоки ответа модели: вывод инструментов хук не читает."""
    blocks = (entry.get("message") or {}).get("content") or []
    return "\n".join(
        block.get("text", "") for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    )


def text_before(entries, index):
    """Хвост подряд идущих assistant-записей перед точкой, в исходном порядке.

    Ровно то, что хук получает в last_assistant_message: одно сообщение
    бывает разбито на несколько записей, первая настоящая не-assistant
    останавливает сбор.
    """
    chunks = []
    position = index - 1
    while position >= 0:
        kind = entries[position].get("type")
        if kind in NOISE:
            position -= 1
            continue
        if kind != "assistant":
            break
        text = assistant_text(entries[position])
        if text:
            chunks.append(text)
        position -= 1
    return "\n".join(reversed(chunks))


def replay(entries, terms, switches):
    """Прогон по всем точкам Stop. Возвращает список строк отчёта и итоги.

    Состояние накопительное и живёт только здесь: выданный термин уходит в
    lexicon_unlocked, чтобы второй раз не выпал, — как у настоящего хука.
    """
    stops = [i for i, entry in enumerate(entries) if entry.get("hookInfos")]
    unlocked = []
    rows = []
    for index in stops:
        entry = entries[index]
        stamp_raw = entry.get("timestamp") or ""
        stamp = _parse_stamp(stamp_raw)
        act = act_at(stamp, switches) if stamp is not None else DEFAULT_ACT
        text = text_before(entries, index)
        state = {"current_act": act, "lexicon_unlocked": list(unlocked)}
        found = lexicon_loot.find_terms(text, terms, state)[:lexicon_loot.MAX_CARDS]
        for term in found:
            unlocked.append(term.term)
        rows.append({
            "stamp": stamp_raw,
            "act": act,
            "length": len(text),
            "terms": [term.term for term in found],
        })
    return rows, unlocked


def report(rows, unlocked):
    """Печать. Карточка засчитывается акту ТОЙ ТОЧКИ, в которой выпала.

    Не полю `act` термина: иначе числа «до» и «после» окажутся из разных
    измерений, и сравнивать их будет нельзя.
    """
    print("Точек Stop: {}".format(len(rows)))
    print("")
    print("{:<26} {:<5} {:>6}  {}".format("момент", "акт", "длина", "карточки"))
    for row in rows:
        found = ", ".join(row["terms"]) if row["terms"] else "—"
        print("{:<26} {:<5} {:>6}  {}".format(
            row["stamp"], row["act"], row["length"], found
        ))

    by_act = {}
    cards_by_act = {}
    for row in rows:
        by_act[row["act"]] = by_act.get(row["act"], 0) + 1
        cards_by_act[row["act"]] = cards_by_act.get(row["act"], 0) + len(row["terms"])
    print("")
    print("Итог")
    for act in sorted(by_act):
        print("  точек в Акте {}: {} (карточек в них: {})".format(
            act, by_act[act], cards_by_act.get(act, 0)
        ))
    print("  карточек в точках Акта 1: {}".format(cards_by_act.get(1, 0)))
    print("  карточек всего: {}".format(sum(cards_by_act.values())))
    print("  разблокировано ({}): {}".format(
        len(unlocked), ", ".join(sorted(unlocked)) if unlocked else "—"
    ))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Реплей словаря-лута по транскрипту прогона.",
    )
    parser.add_argument("transcript", help="путь к .jsonl транскрипта")
    parser.add_argument(
        "--content-root", default=str(DEFAULT_CONTENT_ROOT),
        help="корень контент-ядра (по умолчанию plugin/content/ru)",
    )
    parser.add_argument(
        "--act-switch", action="append", default=[], metavar="ISO8601=АКТ",
        help="момент входа в акт, можно повторять",
    )
    args = parser.parse_args(argv)

    try:
        switches = parse_switches(args.act_switch)
    except ValueError as problem:
        print("Не смог проверить: {}".format(problem))
        print(
            "Прибор без настройки не измеряет, а врёт: без верной метки все "
            "точки посчитались бы вторым актом, и «ноль карточек за Акт 1» "
            "получился бы из пустоты."
        )
        return 2

    path = Path(args.transcript)
    try:
        entries = load_entries(path)
    except (OSError, ValueError) as problem:
        print("Не смог проверить: транскрипт {} не читается ({}).".format(
            path, problem
        ))
        return 2

    terms = content.load_terms(Path(args.content_root))
    rows, unlocked = replay(entries, terms, switches)
    report(rows, unlocked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

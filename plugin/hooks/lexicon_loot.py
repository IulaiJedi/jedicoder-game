#!/usr/bin/env python3
"""Stop-хук словаря-лута: слово услышано в бою — слово в Голокроне.

Читает последний ответ ассистента, находит неоткрытые термины доступных
актов по алиасам с границей слова, печатает одну карточку с «+N XP»
через systemMessage и начисляет term.xp. Ещё два найденных слова ждут в
`lexicon_queue` сохранения и печатаются по одному следующими ходами:
слово без карточки падаван не заметит, а XP без объяснения — цифра ни о
чём. Слова сверх двух не копятся и откроются при следующем упоминании.
Засчитывается термин в тот ход, когда напечатан.

Правило session_start.py действует и здесь: любая ошибка — exit 0 молча,
сломать ход падавана из-за лута недопустимо.
"""
import json
import os
import re
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(
    os.environ.get("CLAUDE_PLUGIN_ROOT")
    or Path(__file__).resolve().parents[1]
)
sys.path.insert(0, str(_PLUGIN_ROOT / "lib"))

from jedicoder import content, ranks
from jedicoder import state as st

MAX_CARDS = 1
# Сколько слов ждёт в очереди. Длинная очередь раздаёт карточки о словах,
# прозвучавших много ходов назад, — падаван уже не помнит, где их слышал
# (прогон новичком 2026-09-13: восемь слов в очереди). Слово сверх предела
# не копится и откроется при следующем упоминании.
MAX_QUEUE = 2
# Так печатается вторая строка карточки — пример из `example`. Линтер берёт
# префикс отсюда (правило card), второй копии строки нет.
EXAMPLE_PREFIX = "Пример: "


def _alias_pattern(alias):
    # Граница слова руками, а не \b: \b вокруг «.env» встал бы ПОСЛЕ точки
    # (она не \w), и «file.env» ловился бы. Лукэраунды смотрят на символ
    # снаружи совпадения целиком: перед «.env» буква — не матч.
    return re.compile(
        r"(?<!\w)" + re.escape(alias) + r"(?!\w)",
        re.IGNORECASE,
    )


def _mentioned(text, term):
    return any(_alias_pattern(alias).search(text) for alias in term.aliases)


def find_terms(text, terms, state):
    """Неоткрытые термины доступных актов, упомянутые в тексте.

    Порядок: act по возрастанию (фундамент раньше), xp по убыванию
    (ценное раньше), term по алфавиту (детерминизм). Лимита нет —
    его накладывает вызывающий (MAX_CARDS).
    """
    current_act = state.get("current_act")
    if not isinstance(current_act, int):
        return []
    unlocked = set(state.get("lexicon_unlocked") or [])
    found = [
        t for t in terms
        if t.act <= current_act and t.term not in unlocked
        and _mentioned(text, t)
    ]
    return sorted(found, key=lambda t: (t.act, -t.xp, t.term))


def pick_cards(text, terms, state):
    """Что печатать этим ходом и что оставить ждать: (термины, очередь имён).

    Очередь идёт раньше новых слов — она ждёт дольше. Термин, открытый пока
    ждал (или исчезнувший из словаря), из очереди выпадает молча. В очереди
    не больше MAX_QUEUE имён: остальные отбрасываются, в том числе хвост
    длинной очереди из сохранения прошлой версии.
    """
    if not isinstance(state.get("current_act"), int):
        return [], []
    by_name = {t.term: t for t in terms}
    unlocked = set(state.get("lexicon_unlocked") or [])
    queued = [
        by_name[name] for name in (state.get("lexicon_queue") or [])
        if name in by_name and name not in unlocked
    ]
    fresh = [t for t in find_terms(text, terms, state) if t not in queued]
    candidates = queued + fresh
    waiting = candidates[MAX_CARDS:MAX_CARDS + MAX_QUEUE]
    return candidates[:MAX_CARDS], [t.term for t in waiting]


def _section(body, header):
    """Текст секции «**Заголовок:** …» до пустой строки, одной строкой."""
    match = re.search(
        r"\*\*" + re.escape(header) + r":?\*\*\s*(.+?)(?:\n\n|\Z)",
        body,
        re.S,
    )
    if not match:
        return ""
    return " ".join(match.group(1).split())


def _definition(body):
    """Первый абзац тела — «**Термин** — определение» без разметки."""
    first = body.strip().split("\n\n")[0]
    return first.replace("**", "").strip()


def render_card(term):
    """Карточка для терминала: заголовок и две строки — что это и пример.

    «Зачем нужно» и «проверь себя» остаются в файле термина для Полки
    Голокрона и Книги (language.md, «Размеры»). Поле `example` у термина
    поставки обязательно (#72); ветка без него — для сохранений и тестов,
    собирающих Term руками: печатаются прежние разделы, и линтер по длине
    такой карточки скажет об этом.
    """
    # «XP» латиницей человек не прочёл (второй прогон 2026-10-08) — словом.
    lines = ["✦ Новое слово: {} (очки: +{})".format(term.title, term.xp)]
    definition = _definition(term.body)
    if term.example:
        # Переносы файла (80 колонок) в терминале не нужны — одна строка.
        definition = " ".join(definition.split())
        # Название уже в заголовке: «Боль — место, где…» → «место, где…».
        # Иначе длинное название съедает бюджет фразы в 15 слов.
        prefix = term.title + " — "
        if definition.startswith(prefix):
            definition = definition[len(prefix):]
        # Строка начинается с заглавной, как любая строка в терминале.
        lines.append(definition[:1].upper() + definition[1:])
        lines.append(EXAMPLE_PREFIX + " ".join(term.example.split()))
        return "\n".join(lines)
    if definition:
        lines.append(definition)
    why = _section(term.body, "Зачем нужно")
    if why:
        lines.append("Зачем нужно: {}".format(why))
    check = _section(term.body, "Проверь, что понял")
    if check:
        lines.append("Проверь себя: {}".format(check))
    return "\n".join(lines)


def _last_assistant_text(payload):
    """Текст последнего ответа ассистента.

    Основной путь — поле last_assistant_message из payload: в нём нет
    вывода инструментов (§9.3). Фолбэк для старых Claude Code — хвостовые
    assistant-записи транскрипта, только text-блоки.
    """
    text = payload.get("last_assistant_message")
    if isinstance(text, str) and text:
        return text
    return _text_from_transcript(payload.get("transcript_path"))


def _text_from_transcript(transcript_path):
    if not transcript_path:
        return ""
    lines = Path(transcript_path).read_text(encoding="utf-8").splitlines()
    chunks = []
    # С конца: собираем непрерывный хвост assistant-записей (одно сообщение
    # может быть разбито на несколько строк), первая не-assistant запись
    # останавливает сбор.
    for line in reversed(lines):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("type") != "assistant":
            break
        blocks = (entry.get("message") or {}).get("content") or []
        text = "\n".join(
            b.get("text", "") for b in blocks
            if isinstance(b, dict) and b.get("type") == "text"
        )
        if text:
            chunks.append(text)
    return "\n".join(reversed(chunks))


def main():
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        # Пустой ответ не повод молчать: в очереди может ждать слово.
        text = _last_assistant_text(payload) or ""
        state_path = st.state_path()
        # Разведка не под блокировкой: нужно только понять, есть ли вообще
        # что засчитывать. Настоящий read-modify-write — ниже, под замком,
        # на свежеперечитанном состоянии (паттерн bash_guard.py).
        recon = st.load(state_path)
        terms = content.load_terms(_PLUGIN_ROOT / "content" / "ru")
        winners, queue = pick_cards(text, terms, recon)
        if not winners and queue == list(recon.get("lexicon_queue") or []):
            return 0  # ни карточки, ни устаревших имён в очереди
        with st.update_state(state_path) as state:
            winners, queue = pick_cards(text, terms, state)
            for term in winners:
                ranks.add_xp(state, term.xp)
                state.setdefault("lexicon_unlocked", []).append(term.term)
                st.enqueue_event(state, "term_unlocked", payload={
                    "term": term.term, "xp": int(state.get("xp", 0)),
                })
            state["lexicon_queue"] = queue
        if not winners:
            return 0
        cards = "\n\n".join(render_card(term) for term in winners)
        print(json.dumps({"systemMessage": cards}, ensure_ascii=False))
    except Exception:
        # Широко и намеренно (правило session_start.py): лут не имеет права
        # сломать ход. BaseException проходит насквозь.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

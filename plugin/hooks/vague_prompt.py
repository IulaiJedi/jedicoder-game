#!/usr/bin/env python3
"""UserPromptSubmit-хук: «сделай мне приложение» — это не задача.

Матчер узкий намеренно. Ложное срабатывание на нормальном запросе
раздражает сильнее, чем польза от катсцены, поэтому ловим только явный
случай: короткая просьба «сделай/напиши мне <вещь>» без единой детали.
Никогда не блокирует — только показывает правило и зовёт /jedicoder:brainstorm.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _shared  # noqa: E402
from jedicoder import state as st  # noqa: E402

DARK_VAGUE = 1

# Длиннее — уже не «одна фраза настроения»: там наверняка есть детали.
MAX_LENGTH = 120

# Продуктовый масштаб — то, что просят построить целиком.
_PRODUCT = (
    r"(приложени\w*|прилож\w*|сайт\w*|бот\w*|игр\w*|сервис\w*|платформ\w*"
    r"|магазин\w*|лендинг\w*|маркетплейс\w*|соцсет\w*|мессенджер\w*"
    r"|стартап\w*|landing\s+page|landing|app|website|shop)"
)

# Заказ продукта: глагол, дательное «мне», продукт следом (допускается
# одно определение — «новое приложение» — и составные слова через дефис).
_ASK_PRODUCT = re.compile(
    r"^\s*(сделай|создай|напиши|запили|построй)\w*\s+мне\s+"
    r"([\w-]+\s+){0,1}[\w-]*" + _PRODUCT,
    re.IGNORECASE,
)

# Слова-работы: речь о задаче ПРО продукт, а не о заказе продукта.
# «Сделай мне ревью приложения» — обычная работа, катсцена тут лишняя.
_WORK = re.compile(
    r"(ревью|рефактор\w*|тест\w*|логотип\w*|дизайн\w*|отчёт\w*|отчет\w*"
    r"|бэкап\w*|бекап\w*|деплой\w*|миграци\w*|апдейт\w*|фикс\w*|правк\w*"
    r"|баг\w*|аудит\w*)",
    re.IGNORECASE,
)

# Что стоит после продукта. У заказа — ничего или цель («для медитации»,
# «по медитации»); у правки существующего — определение или сравнительная
# степень («быстрее», «молчаливым», «новый логотип»). Это и отличает
# «сделай мне сайт» от «сделай мне сайт быстрее».
_PURPOSE_TAIL = re.compile(
    r"^\s*($|[^\w\s]+\s*$"
    r"|(для|по|про|чтобы|который|которое|которая|на|с)\b)",
    re.IGNORECASE,
)

# Признаки того, что разговор уже про дело: цифра, путь, файл, цитата,
# двоеточие с уточнением.
_CONCRETE = re.compile(
    r"[0-9]|[/\\]|\.[a-z]{2,4}\b|«[^»]+»|\"[^\"]+\"|:",
    re.IGNORECASE,
)


def is_vague(text):
    if not isinstance(text, str):
        return False
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_LENGTH:
        return False
    match = _ASK_PRODUCT.match(stripped)
    if not match:
        return False
    if _WORK.search(stripped):
        return False
    if not _PURPOSE_TAIL.match(stripped[match.end():]):
        return False
    return not _CONCRETE.search(stripped)


def react(payload):
    # Поле разное в версиях Claude Code — читаем оба, это дешевле, чем
    # молча не сработать.
    text = payload.get("prompt") or payload.get("user_prompt")
    if not is_vague(text):
        return None
    with _shared.update_state() as state:
        _shared.add_dark_side(state, DARK_VAGUE, st.DARK_VAGUE_PROMPT)
        invite = _shared.magistr_invite(state)
    message = (
        "Это заказ по настроению, а не задача: ИИ достроит недосказанное "
        "из среднего по интернету. Назови боль, того, для кого решаешь, и "
        "что должно заработать сегодня. Или позови /jedicoder:brainstorm — "
        "он поможет нарезать."
    )
    extra = _shared.rule_text(_shared.plugin_root(), "vague-prompt")
    if extra:
        message += "\n\n" + extra
    if invite:
        message += "\n\n" + invite
    return {"systemMessage": message}


def main():
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        # Раньше разбора запроса и сам по себе: режим пишется на каждом
        # запросе, а не только на расплывчатом.
        _shared.record_permission_mode(payload)
        out = react(payload)
        if out:
            print(json.dumps(out, ensure_ascii=False))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

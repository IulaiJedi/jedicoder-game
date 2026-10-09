"""Сборка поведенческого контракта под конкретного падавана.

Базовый текст лежит в plugin/content/ru/behavior.md и одинаков для всех.
Ручки из паспорта (результата квиза) добавляют к нему директивы: насколько
подробно объяснять, в каком регистре говорить, когда спрашивать «да».
"""
from pathlib import Path

from . import state as st
from .frontmatter import parse


class ContractError(ValueError):
    """Паспорт содержит неизвестное значение ручки."""


DEFAULTS = {
    # Читатель игры — человек, впервые открывший Claude Code (спека #75).
    # Прежнее умолчание «normal» печатало ему «падаван что-то уже пробовал»
    # при нуле закрытых квестов (прогон новичком 2026-10-08).
    "explain_depth": "max",
    "language_register": "adult",
    "confirm_before_action": "risky_only",
    # Трек по умолчанию НЕ «craftsman»: до ответа человека его нет, а Акт 1
    # «Знакомство» этого ответа не просит вовсе. Прогон падаваном
    # 2026-09-10: контракт печатал
    # «Трек Ремесленник: не заводи разговор о рынке» ещё до вопроса о треке —
    # то есть модель получала прямое указание вести будущего Основателя
    # ровно наоборот, а падаван и не знал, что за него уже решили.
    "track": "unknown",
    "product_type": "unknown",
    "os": "linux",
}

DIRECTIVES = {
    "explain_depth": {
        "max": (
            "Падаван с нулевым опытом: Claude Code он открыл впервые. "
            "Поясняй каждое новое слово при первом употреблении. Команду, "
            "которую он набирает сам, объясни до того, как он её наберёт."
        ),
        "normal": (
            "Падаван что-то уже пробовал. Поясняй термины при первом "
            "употреблении, команды — только неочевидные."
        ),
    },
    "language_register": {
        "teen": (
            "Говори на «ты», короткими фразами, без деловой лексики. Не "
            "приводи примеры про бизнес, налоги и юрлица."
        ),
        "adult": "Говори на «ты», спокойно и по делу, без сюсюканья.",
    },
    "confirm_before_action": {
        "always": (
            "Спрашивай «да» перед каждым действием, которое меняет файлы, "
            "ставит пакеты или трогает сервер."
        ),
        "risky_only": (
            "Спрашивай «да» перед установкой пакетов, правкой более трёх "
            "файлов и любыми действиями на сервере."
        ),
    },
    "track": {
        "craftsman": (
            "Трек Ремесленник: продукт делается для себя. Не заводи "
            "разговор о рынке, ЦА и монетизации, пока падаван сам не спросит."
        ),
        "founder": (
            "Трек Основатель: продукт делается на рынок. Держи в фокусе "
            "боль, ЦА и канал доставки."
        ),
        # Не «спроси и запиши»: скилл Акта 1 прямо запрещает этот вопрос, и
        # контракт спорил со скиллом (прогон новичком 2026-10-08). Вопрос
        # задаёт акт, которому нужен ответ, а не общий контракт.
        "unknown": (
            "Для кого продукт — для себя или для людей — не спрашивай и не "
            "решай за падавана: спросит акт, которому нужен ответ."
        ),
    },
}

DIRECTIVE_ORDER = (
    "explain_depth",
    "language_register",
    "confirm_before_action",
    "track",
)

SETTINGS_HEADER = "## Настройки под этого падавана"


def load_behavior(content_root):
    path = Path(content_root) / "behavior.md"
    _, body = parse(path.read_text(encoding="utf-8"))
    return body


def resolve(passport):
    resolved = dict(DEFAULTS)
    for key, value in (passport or {}).items():
        if key in DEFAULTS:
            resolved[key] = value
    return resolved


#: Что контракт говорит модели о режиме разрешений. Режим называет сам
#: Claude Code данными хука (state.permission_mode); игра его не угадывает.
MODE_FREE = (
    "Режим Claude Code: без вопросов. Так сообщил сам Claude Code — "
    "падавану это можно сказать прямо."
)
MODE_OTHER = (
    "Режим Claude Code: другой, не «без вопросов». Claude Code сообщил "
    "режим `{}`: перед частью действий он спросит у падавана разрешения."
)
MODE_UNKNOWN = (
    "Режим Claude Code игре неизвестен. Не утверждай, в каком режиме "
    "работает падаван, и искать его на экране не проси."
)


def mode_directive(permission_mode):
    """Строка контракта о режиме — по тому, что вернул state.permission_mode."""
    if permission_mode is None:
        return MODE_UNKNOWN
    if permission_mode == st.PERMISSION_MODE_FREE:
        return MODE_FREE
    return MODE_OTHER.format(permission_mode)


def render(behavior_body, passport, mode=MODE_UNKNOWN):
    """`mode` — готовая строка о режиме (mode_directive): контракт состояния
    не читает, его читает вызывающий."""
    resolved = resolve(passport)
    lines = [behavior_body.strip(), "", SETTINGS_HEADER, ""]
    for knob in DIRECTIVE_ORDER:
        value = resolved[knob]
        directive = DIRECTIVES[knob].get(value)
        if directive is None:
            raise ContractError(
                "неизвестное значение ручки {}: {!r}".format(knob, value)
            )
        lines.append("- {}".format(directive))
    lines.append(
        "- Операционная система падавана: {}. Все команды давай под неё.".format(
            resolved["os"]
        )
    )
    lines.append("- Тип продукта: {}.".format(resolved["product_type"]))
    lines.append("- {}".format(mode))
    return "\n".join(lines) + "\n"

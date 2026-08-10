"""Сборка поведенческого контракта под конкретного падавана.

Базовый текст лежит в plugin/content/ru/behavior.md и одинаков для всех.
Ручки из паспорта (результата квиза) добавляют к нему директивы: насколько
подробно объяснять, в каком регистре говорить, когда спрашивать «да».
"""
from pathlib import Path

from .frontmatter import parse


class ContractError(ValueError):
    """Паспорт содержит неизвестное значение ручки."""


DEFAULTS = {
    "explain_depth": "normal",
    "language_register": "adult",
    "confirm_before_action": "risky_only",
    "track": "craftsman",
    "product_type": "unknown",
    "os": "linux",
}

DIRECTIVES = {
    "explain_depth": {
        "max": (
            "Падаван с нулевым опытом. Поясняй каждый термин при первом "
            "употреблении и каждую команду перед запуском."
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


def render(behavior_body, passport):
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
    return "\n".join(lines) + "\n"

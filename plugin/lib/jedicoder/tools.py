"""Инструменты игры: перечень (чистые данные, без I/O).

Инструмент игры — команда игры, которую модель зовёт напрямую, без
терминала (спека #89, тикет #93). Объявляет и обслуживает инструменты модуль
Лица, но слов и перечня он не держит (ADR-0019): имя, описание, схему входа
и порядок значений отдаёт команда `tools`, а выполняет вызов команда
`tool <имя> [значения]` — обе в `cli.py`.

Три правила перечня.

Только путь Акта 1 — от контракта, с которого начинает скилл, до памятки.
Команд, которые уводят сохранение, говорят с ботом или
принадлежат выключенным актам, здесь нет — и через инструмент их не позвать:
`tool` выполняет только имена из этого файла.

Ни номера акта, ни кода квеста на входе. Вызов инструмента с аргументами
видит человек, а кодов квестов на экране нет. Квест называется словами,
как на экране: `check (MCP)(quest: "Папка")`. Шаг пути игра знает сама
(`cli._next_position`) и сверяет с ним название: не тот квест — команда
не запускается.

Описание читает модель и видит человек в списке инструментов: оно пишется
по правилам языка (`content/ru/language.md`), фраза до 15 слов.
"""
from collections import namedtuple

#: На что действует инструмент: `NEEDS_QUEST` — на текущий открытый квест,
#: `NEEDS_ACT` — на ближайший незакрытый акт, `NEEDS_NOTHING` — ни на что.
NEEDS_NOTHING = "nothing"
NEEDS_ACT = "act"
NEEDS_QUEST = "quest"

#: Значения входа: путь к папке проекта и название квеста.
INPUT_PATH = "path"
INPUT_QUEST = "quest"

#: Название квеста — обязательное значение инструментов, действующих на квест.
QUEST_INPUT = (
    (INPUT_QUEST, "Название квеста, как на экране. Например: «Папка».", True),
)

#: name — имя инструмента, его видит человек: `jedicoder - <имя> (MCP)`;
#: command — подкоманда игры, которую он зовёт; needs — на что действует;
#: description — что он делает; inputs — значения входа по порядку:
#: тройки (имя, описание, обязательно ли).
Tool = namedtuple("Tool", "name command needs description inputs")

TOOLS = (
    Tool(
        "status", "status", NEEDS_NOTHING,
        "Игра Jedicoder: первый экран. Показывает ранг, карту актов и что "
        "делать дальше.",
        (),
    ),
    Tool(
        "enter", "enter", NEEDS_ACT,
        "Игра Jedicoder: войти в акт. Номер не нужен: игра берёт ближайший "
        "незакрытый акт.",
        (),
    ),
    Tool(
        "folder", "project", NEEDS_NOTHING,
        "Игра Jedicoder: записать папку проекта, которую назвал падаван. "
        "Без пути — показать, что игра знает о проекте.",
        ((INPUT_PATH,
          "Путь к папке проекта. Точка значит папку, в которой открыт "
          "Claude Code.", False),),
    ),
    Tool(
        "check", "check", NEEDS_QUEST,
        "Игра Jedicoder: прогнать проверку квеста. Квест назови, как на "
        "экране. Исход решает проверка.",
        QUEST_INPUT,
    ),
    Tool(
        "seen", "seen", NEEDS_QUEST,
        "Игра Jedicoder: записать рассказ падавана о квесте. Он посмотрел на "
        "результат и сказал, что увидел.",
        QUEST_INPUT,
    ),
    Tool(
        "ack", "ack", NEEDS_QUEST,
        "Игра Jedicoder: подтвердить квест, у которого нет проверки. Только "
        "после рассказа падавана.",
        QUEST_INPUT,
    ),
    Tool(
        "scroll", "scroll", NEEDS_NOTHING,
        "Игра Jedicoder: выдать памятку. Игра кладёт её в папку проекта.",
        (),
    ),
    Tool(
        "contract", "contract", NEEDS_NOTHING,
        "Игра Jedicoder: загрузить контракт игры. Только когда раздела с "
        "контрактом нет в системном промпте.",
        (),
    ),
)

#: Имена инструментов по порядку пути.
NAMES = tuple(tool.name for tool in TOOLS)
BY_NAME = {tool.name: tool for tool in TOOLS}
#: Имя инструмента → подкоманда игры.
COMMANDS = {tool.name: tool.command for tool in TOOLS}


def listing():
    """Перечень, каким его получает модуль Лица: список словарей.

    Ключи — договор с модулем (`plugin/types/index.d.ts`, тип `GameTool`):
    `name`, `description`, `inputSchema` — что модуль объявляет движку как
    есть; `input` — имена значений входа по порядку: в этом порядке модуль
    кладёт их в вызов `tool <имя>` отдельными аргументами.
    """
    listed = []
    for tool in TOOLS:
        schema = {
            "type": "object",
            "properties": {
                key: {"type": "string", "description": text}
                for key, text, _ in tool.inputs
            },
            "additionalProperties": False,
        }
        required = [key for key, _, must in tool.inputs if must]
        if required:
            schema["required"] = required
        listed.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": schema,
            "input": [key for key, _, _ in tool.inputs],
        })
    return listed

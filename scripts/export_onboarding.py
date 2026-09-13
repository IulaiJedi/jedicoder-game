#!/usr/bin/env python3
"""Генератор модуля Акта 0 из контент-ядра плагина.

Запуск: python3 scripts/export_onboarding.py [plugin/content/ru] > .../act0.generated.ts

Потребителей у вывода двое, и файл они получают один и тот же байт в байт:
бот (`jedicoder_academy_bot/src/act0.generated.ts`) и сайт
(`src/data/act0.ts`) — обе двери Акта 0 по решению D-06 фазы 01.4. Разные у
них только адреса, поэтому скрипт по-прежнему печатает в stdout, а куда
положить, решает вызывающий.

Зачем он есть. Текст Акта 0 читает человек, у которого плагина ещё нет: он
приходит в бота раньше, чем ставит игру. Значит текст обязан доехать до бота —
и это ровно та развилка, где 2026-08-06 контент разошёлся между двумя
репозиториями (долг №14). Решение то же, что у `export_acts.py`: единственный
источник правды остаётся здесь, в `plugin/content/ru/onboarding/`, а
`act0.generated.ts` — производная, которую руками не правит никто и никогда.

Печатает в stdout и ничего не пишет на диск: перенаправление — дело
вызывающего, и файл в чужом репозитории не появится по ошибке. При любой
проблеме контента печатает её в stderr, выходит с кодом 1 и не печатает в
stdout ни байта — генератор не имеет права выпустить модуль, который врёт.
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "plugin" / "lib"))
# Линтер лежит рядом и переиспользуется целиком — см. _problems ниже.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jedicoder import content  # noqa: E402

import lint_content  # noqa: E402

DEFAULT_ROOT = _ROOT / "plugin" / "content" / "ru"

FORMAT_TS = "ts"
FORMAT_MD = "md"
FORMATS = (FORMAT_TS, FORMAT_MD)

HEADER = """\
// Сгенерировано scripts/export_onboarding.py из
// plugin/content/ru/onboarding/ репозитория jedicoder-game. Руками не
// править: правится генератор, файл перегенерируется. Единственный источник
// правды — контент-ядро плагина, здесь его производная.
//
// Защиты от расхождения в CI нет (долг №14 репозитория плагина). Пока её
// нет, расхождение ловится diff-ом генератора с этим файлом в приёмке
// каждого плана, который трогает Акт 0.
"""

TYPES = """\
/** Кнопка узла: куда ведёт и что на ней написано. */
export interface Act0Option {
    node: string
    title: string
}

export interface Act0Step {
    node: string
    title: string
    order: number
    /** install | check | trouble | first-session | link */
    section: string
    /** Команда, которую человек выполняет в этом узле. Пусто — команды нет. */
    probe: string | null
    options: Act0Option[]
    /** Тело узла как есть; абзацы разделены двойным переводом строки. */
    text: string
}
"""


def _problems(items):
    """Сверить дерево той же функцией, что и линтер.

    Своя копия проверок была бы дефектом: два независимых проверяльщика
    одного и того же расходятся молча, и тогда генератор выпустит модуль с
    тупиком при полностью зелёном линтере.
    """
    if not items:
        return ["в контенте нет ни одного узла Акта 0"]
    return lint_content._onboarding_problems(items)


def _lit(value):
    """Строковый литерал TypeScript.

    Через json.dumps, а не своим экранированием: это разом решает кавычки,
    обратные слэши и переводы строк внутри многострочного тела узла. Пустые
    строки внутри тела обязаны пережить экспорт — бот отправляет тело одним
    сообщением, и склеенные абзацы человек увидит стеной.
    """
    return json.dumps(value, ensure_ascii=False)


def render(items):
    ordered = sorted(items, key=lambda entry: entry.order)
    out = [HEADER]
    out.append(TYPES)
    out.append("export const act0Steps: Act0Step[] = [")
    for item in ordered:
        out.append("    {")
        out.append("        node: {},".format(_lit(item.node)))
        out.append("        title: {},".format(_lit(item.title)))
        out.append("        order: {},".format(item.order))
        out.append("        section: {},".format(_lit(item.section)))
        out.append(
            "        probe: {},".format(_lit(item.probe) if item.probe else "null")
        )
        if item.options:
            out.append("        options: [")
            for node, title in zip(item.options, item.option_titles):
                out.append(
                    "            {{ node: {}, title: {} }},".format(
                        _lit(node), _lit(title)
                    )
                )
            out.append("        ],")
        else:
            out.append("        options: [],")
        # visible_text, а не item.body: служебный комментарий правила 3
        # падавану не доезжает нигде — ни в игре, ни в боте. Своё вырезание
        # здесь разошлось бы с тем, что мерил линтер.
        out.append("        text: {},".format(_lit(lint_content.visible_text(item.body))))
        out.append("    },")
    out.append("]")
    out.append("")
    out.append("/** Корень дерева — узел с наименьшим order. */")
    out.append("export const ACT0_ROOT = {}".format(_lit(ordered[0].node)))
    out.append("")
    return "\n".join(out)


MD_HEADER = """\
<!-- Сгенерировано `python3 scripts/export_onboarding.py --format md` из
plugin/content/ru/onboarding/. Руками не править: правится генератор, файл
перегенерируется. Единственный источник правды — контент-ядро плагина,
здесь его производная. Свежесть держится тестом
tests/test_onboarding.py. -->

# Акт 0 — от скачанного приложения до первой команды

Пять шагов, одинаковых для Windows, macOS и Linux. Тот же текст лежит ещё в
двух местах — в Telegram-боте и на странице сайта; поставить можно по любому.

Шаги идут подряд: закончил один — переходи к следующему.
"""

MD_FLOW_TITLE = "## По шагам"


def _md_node(item):
    """Один узел в markdown.

    Якорь ставится HTML-тегом, а не заголовком: адрес, собранный markdown из
    русского заголовка, зависит от того, чем файл читают, — а переход обязан
    работать одинаково и на GitHub, и в редакторе падавана.
    """
    out = ['<a id="node-{}"></a>'.format(item.node), ""]
    out.append("### {}".format(item.title))
    out.append("")
    out.append(lint_content.visible_text(item.body))
    if item.probe:
        out.append("")
        out.append("```")
        out.append(item.probe)
        out.append("```")
    if item.options:
        out.append("")
        out.append("Дальше:")
        out.append("")
        for node, title in zip(item.options, item.option_titles):
            out.append("- [{}](#node-{})".format(title, node))
    out.append("")
    return out


def render_md(items):
    """То же дерево в markdown — третья дверь по решению D-06.

    Порядок — это order контент-ядра, и он же порядок кнопок: путь один,
    без развилок (ADR-0015), поэтому глав в файле одна.
    """
    ordered = sorted(items, key=lambda entry: entry.order)
    out = [MD_HEADER, MD_FLOW_TITLE, ""]
    for item in ordered:
        out.extend(_md_node(item))
    return "\n".join(out)


RENDERERS = {FORMAT_TS: render, FORMAT_MD: render_md}


def _parse(argv):
    """Разбор аргументов: `--format md` плюс необязательный корень контента.

    Своими руками, а не argparse: цена — десять строк, зато сообщение об
    ошибке остаётся русским, как и всё остальное, что видит человек.
    Возвращает (root, format) либо (None, сообщение об ошибке).
    """
    fmt = FORMAT_TS
    positional = []
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg.startswith("--format="):
            fmt = arg.split("=", 1)[1]
        elif arg == "--format":
            if not rest:
                return None, "у --format нет значения; ожидалось одно из: {}".format(
                    ", ".join(FORMATS)
                )
            fmt = rest.pop(0)
        elif arg.startswith("-"):
            return None, "неизвестный ключ {}".format(arg)
        else:
            positional.append(arg)
    if fmt not in FORMATS:
        return None, "неизвестный формат {}; ожидалось одно из: {}".format(
            fmt, ", ".join(FORMATS)
        )
    if len(positional) > 1:
        return None, "лишний аргумент: корень контента один"
    root = Path(positional[0]) if positional else DEFAULT_ROOT
    return (root, fmt), None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parsed, error = _parse(argv)
    if error:
        sys.stderr.write("{}\n".format(error))
        return 1
    root, fmt = parsed
    try:
        items = content.load_onboarding(root)
    except (content.ContentError, OSError) as exc:
        sys.stderr.write("Контент Акта 0 не читается: {}\n".format(exc))
        return 1
    problems = _problems(items)
    if problems:
        sys.stderr.write("Дерево Акта 0 битое, модуль не выпущен:\n")
        for problem in problems:
            sys.stderr.write("  - {}\n".format(problem))
        return 1
    # Печать одним куском и только здесь: до этой строки в stdout не уходит
    # ничего, поэтому оборванная сверка не оставляет полуфайла.
    sys.stdout.write(RENDERERS[fmt](items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

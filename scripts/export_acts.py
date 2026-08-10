#!/usr/bin/env python3
"""Генератор src/data/acts.ts для сайта из контент-ядра плагина.

Запуск: python3 scripts/export_acts.py [plugin/content/ru] > .../src/data/acts.ts

Зачем он есть. Странице книги нужны название акта, текст катсцены и список
квестов с русскими подписями. Отдавать это эндпоинтом сегодня нельзя: у бота
контента актов нет вовсе, а /kniga без ключа — будущая страница продаж, и с
контентом на сервере она пустая. Значит контент едет статикой на сайт. Цена
такого решения — дублирование текста между репозиториями и риск молчаливого
расхождения; она снимается ровно тем, что руками текст туда не попадает
никогда: единственный источник правды остаётся здесь, а acts.ts — производная.

Печатает в stdout и ничего не пишет на диск: перенаправление — дело
вызывающего, и файл в чужом репозитории не появится по ошибке. При любом
расхождении с реестрами движка печатает проблемы в stderr, выходит с кодом 1
и не печатает в stdout ни байта — генератор не имеет права выпустить
acts.ts, который врёт.
"""
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "plugin" / "lib"))
# Линтер лежит рядом и переиспользуется целиком — см. _problems ниже.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from jedicoder import acts  # noqa: E402
from jedicoder import content  # noqa: E402
from jedicoder import ranks  # noqa: E402

import lint_content  # noqa: E402

DEFAULT_ROOT = _ROOT / "plugin" / "content" / "ru"

IMAGE_TEMPLATE = "/images/golokron/{}.webp"

HEADER = """\
// Сгенерировано scripts/export_acts.py из plugin/content/ru/acts/ репозитория
// jedicoder-game. Руками не править: правится генератор, файл
// перегенерируется. Единственный источник правды — контент-ядро плагина,
// здесь его производная.
//
// В Фазе 3 контент поедет с сервера, и эта статика заменится эндпоинтом без
// переписывания страницы.
"""

TYPES = """\
export interface ActQuest {{
    id: string
    title: string
    branch: Branch
}}

export interface ActChapter {{
    act: number
    slug: string
    title: string
    rank: string
    rankTitle: string
    artifact: string
    axis: "track" | "deploy"
    /** Тело катсцены как есть; абзацы разделены двойным переводом строки. */
    cutscene: string
    quests: ActQuest[]
    image: string
}}
"""


def _branch_union():
    """Тип Branch собирается из тех же констант, что и метки квестов.

    Перечислить значения строкой было бы короче ровно до первой новой ветки:
    разойтись список и реестр могут молча, а тип на сайте — единственное, что
    ловит опечатку в метке.
    """
    values = [acts.BRANCH_BOTH] + list(acts.TRACKS) + list(acts.DEPLOYS)
    return " | ".join(json.dumps(value, ensure_ascii=False) for value in values)


def _problems(items):
    """Сверить контент с реестрами движка — той же функцией, что и линтер.

    Своя копия проверок была бы дефектом: два независимых проверяльщика одного
    и того же расходятся молча, и тогда генератор выпустит acts.ts, который
    врёт, при полностью зелёном линтере.
    """
    return lint_content._act_problems(items)


def _quests(item):
    """Пары «квест — подпись» в порядке реестра движка.

    Ветка берётся из acts.QUESTS_BY_ACT, а не из фронтматтера: метка ветки —
    свойство движка, и фронтматтер её не несёт. Совпадение списков к этому
    моменту уже проверено сверкой.
    """
    registry = acts.QUESTS_BY_ACT[item.act]
    titles = list(item.quest_titles)
    rows = []
    for index, entry in enumerate(registry):
        quest_id, _kind, branch = entry
        rows.append((quest_id, titles[index], branch))
    return rows


def _axis(number):
    if acts.ACT_AXIS.get(number) == acts.AXIS_DEPLOY:
        return "deploy"
    return "track"


def _lit(value):
    """Строковый литерал TypeScript.

    Через json.dumps, а не своим экранированием: это разом решает кавычки,
    обратные слэши и переводы строк внутри многострочного тела катсцены.
    Пустые строки внутри тела обязаны пережить экспорт — страница режет
    катсцену на абзацы по двойному переводу строки.
    """
    return json.dumps(value, ensure_ascii=False)


def render(items):
    out = [HEADER]
    out.append("export type Branch = {}\n".format(_branch_union()))
    out.append(TYPES.format())
    out.append("export const acts: ActChapter[] = [")
    for item in sorted(items, key=lambda entry: entry.act):
        out.append("    {")
        out.append("        act: {},".format(item.act))
        out.append("        slug: {},".format(_lit(item.slug)))
        out.append("        title: {},".format(_lit(item.title)))
        out.append("        rank: {},".format(_lit(item.rank)))
        out.append("        rankTitle: {},".format(_lit(ranks.RANK_TITLES[item.rank])))
        out.append("        artifact: {},".format(_lit(item.artifact)))
        out.append("        axis: {},".format(_lit(_axis(item.act))))
        out.append("        cutscene: {},".format(_lit(item.body)))
        out.append("        quests: [")
        for quest_id, title, branch in _quests(item):
            out.append(
                "            {{ id: {}, title: {}, branch: {} }},".format(
                    _lit(quest_id), _lit(title), _lit(branch)
                )
            )
        out.append("        ],")
        out.append(
            "        image: {},".format(_lit(IMAGE_TEMPLATE.format(item.slug)))
        )
        out.append("    },")
    out.append("]")
    out.append("")
    out.append("export const rankTitles: Record<string, string> = {")
    for rank in ranks.RANKS:
        out.append("    {}: {},".format(_lit(rank), _lit(ranks.RANK_TITLES[rank])))
    out.append("}")
    out.append("")
    return "\n".join(out)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(argv[0]) if argv else DEFAULT_ROOT
    try:
        items = content.load_acts(root)
    except (content.ContentError, OSError) as exc:
        sys.stderr.write("Контент актов не читается: {}\n".format(exc))
        return 1
    problems = _problems(items)
    if problems:
        sys.stderr.write("Контент расходится с движком, acts.ts не выпущен:\n")
        for problem in problems:
            sys.stderr.write("  - {}\n".format(problem))
        return 1
    # Печать одним куском и только здесь: до этой строки в stdout не уходит
    # ничего, поэтому оборванная сверка не оставляет полуфайла.
    sys.stdout.write(render(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

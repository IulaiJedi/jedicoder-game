"""Одно слово для папки: «папка проекта» (#82, решение оператора 2026-10-08).

Новичок встречал три имени одной вещи: «папка продукта» в Голокроне, «папка
затеи» в игре и «Папка проекта» в словаре — и вправе был решить, что это три
разные папки. Осталось одно, то, что стоит на карточке словаря.

Страж читает всё, что едет в установленный плагин, и markdown-производную
Акта 0: тексты для человека там лежат вперемешку с кодом (строки `check.sh`,
печать `cli.py`, речь скиллов), и отделять одно от другого по файлам значило
бы оставить щель. Комментарии под запрет попадают заодно — слово в них
подсказало бы следующему автору прежнюю формулировку.

Слово «затея» само по себе остаётся: «первая версия своей затеи», «заведи
для затеи отдельную папку». Запрещено только сочетание, которое звучит как
имя папки.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
INSTALL_MD = ROOT / "docs" / "act0-install.md"
TEXT_SUFFIXES = (".md", ".py", ".sh", ".json", ".txt")

# «папка затеи», «папку своей затеи», «Папка продукта» — во всех падежах.
# Пробел любой, включая перенос строки: markdown скилла переносится по
# ширине, и «в папке\n  затеи» человек услышит так же.
FORBIDDEN = re.compile(
    r"папк\w*\s+(?:(?:сво|тво)\w+\s+)?(?:затеи|продукта)", re.IGNORECASE
)
# Шов между строковыми литералами: «"в папке "\n    "затеи"» и то же с плюсом.
LITERAL_SEAM = re.compile(r"""["'`]\s*\+?\s*\n\s*["'`]""")
# Перенос строки вместе с тем, чем начинается следующая: отступ, цитата
# markdown, комментарий Python, bash или TypeScript.
LINE_BREAK = re.compile(r"\s*\n[ \t]*(?:#|//|/\*+|\*|>)?[ \t]*")


def scanned_files():
    files = [
        path for path in sorted(PLUGIN.rglob("*"))
        if path.is_file() and path.suffix in TEXT_SUFFIXES
        and "__pycache__" not in path.parts
    ]
    files.append(INSTALL_MD)
    return files


def flatten(text):
    """Склеить переносы: шов литералов, знак комментария, цитата и отступ —
    не часть фразы. Неразрывный пробел — тоже пробел."""
    text = text.replace("\u00a0", " ").replace("&nbsp;", " ")
    return LINE_BREAK.sub(" ", LITERAL_SEAM.sub("", text))


def hits(text):
    return [match.group(0) for match in FORBIDDEN.finditer(flatten(text))]


@pytest.mark.parametrize("phrase", [
    "папка затеи", "папки затеи", "папку затеи", "папке затеи", "папкой затеи",
    "папка продукта", "папки продукта", "папку продукта", "папке продукта",
    "Папка продукта", "папку своей затеи", "в папке твоего продукта",
    "в папке\n  затеи", "> в папке\n> затеи", "# в папке\n# затеи",
    '"в папке "\n    "затеи"', "'в папке ' +\n    'продукта'",
    "в папке\u00a0продукта", "в папке&nbsp;продукта",
])
def test_guard_sees_every_form(phrase):
    assert hits("Открой {} и работай.".format(phrase))


@pytest.mark.parametrize("phrase", [
    "папка проекта", "первая версия своей затеи", "заведи для затеи отдельную папку",
    "одна папка на одну затею", "папка одного продукта",
])
def test_guard_leaves_the_rest_alone(phrase):
    assert not hits("Вот: {}.".format(phrase))


def test_scan_covers_the_texts_a_person_reads():
    """Страж без файлов зелёный всегда — пусть назовёт, что он прочёл."""
    names = {path.relative_to(ROOT).as_posix() for path in scanned_files()}
    for expected in (
        "plugin/skills/act1-znakomstvo/SKILL.md",
        "plugin/quests/act1-znakomstvo/01-folder/check.sh",
        "plugin/lib/jedicoder/cli.py",
        "plugin/commands/start.md",
        "plugin/content/ru/onboarding/30-prepare.md",
        "plugin/content/ru/lexicon/project-folder.md",
        "plugin/hooks/hooks.json",
        "docs/act0-install.md",
    ):
        assert expected in names, expected


def test_folder_has_one_name_everywhere():
    found = []
    for path in scanned_files():
        for hit in hits(path.read_text(encoding="utf-8")):
            found.append("{}: «{}»".format(path.relative_to(ROOT), hit))
    assert found == [], "папка названа не «папка проекта»:\n" + "\n".join(found)

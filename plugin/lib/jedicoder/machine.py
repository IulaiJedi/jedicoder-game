#!/usr/bin/env python3
"""Машина игрока: свой скилл и хук на запрос в настройках Claude Code.

Только чтение. Квесты Акта 3 «Умения» судят то, что Claude сделал по словам
человека: файл скилла в папке проекта и хук в файле настроек. Где что лежит —
замеры в `docs/research/2026-10-13-act3-skills-hooks-mods.md`, раздел
«Замеры #110»:

    свой скилл   <папка проекта>/.claude/skills/<имя>/SKILL.md — блок `---`
                 с полем `description` и тело под ним; личный —
                 ~/.claude/skills/<имя>/SKILL.md
    хук          `hooks.UserPromptSubmit` в <папка проекта>/.claude/settings.json,
                 .claude/settings.local.json или ~/.claude/settings.json

Читателей два, и вопрос у них один — поэтому разбор живёт здесь, а не в
`quests/_lib/machine.sh`: проверка квеста зовёт этот файл командой
(`python3 machine.py …`), хук следов — функцией. Второй разбор тех же
настроек разошёлся бы молча.

Правило трёх исходов то же, что у `machine.sh`: нет файла — «нет», честный
провал с подсказкой; файл есть, а прочитать его нельзя или в нём не JSON —
`Unreadable`: проверка ответит «не смог проверить», хук промолчит.

Домашнюю папку вызывающий передаёт сам: проверка — из `HOME`, и тесты
подменяют её песочной.
"""
import json
import os
import sys

#: Событие Claude Code «человек отправил запрос».
PROMPT_EVENT = "UserPromptSubmit"

#: Файлы настроек относительно папки проекта: общий и свой для машины.
PROJECT_SETTINGS = (
    os.path.join(".claude", "settings.json"),
    os.path.join(".claude", "settings.local.json"),
)
#: Файл настроек относительно домашней папки.
USER_SETTINGS = os.path.join(".claude", "settings.json")

#: Чем хук бывает задан: команда, запрос к модели, адрес.
_HOOK_BODY = ("command", "prompt", "url")

#: Исходы поиска своего скилла — их печатает команда `own-skill`.
SKILL_NONE = "none"                # своего скилла нет
SKILL_NO_DESCRIPTION = "no-description"   # файл есть, описания нет
SKILL_NO_BODY = "no-body"          # описание есть, под ним пусто
SKILL_OK = "ok"
#: От худшего к лучшему: из нескольких своих скиллов судится самый готовый.
_SKILL_ORDER = (SKILL_NONE, SKILL_NO_DESCRIPTION, SKILL_NO_BODY, SKILL_OK)

#: Код возврата команды, когда прочитать не удалось.
EXIT_UNREADABLE = 3


#: Код возврата команды, которую позвали не так: не путать с «не смог
#: проверить» у проверок (2).
EXIT_USAGE = 4


class Unreadable(Exception):
    """Файл или папка есть, а прочитать нельзя — судить нечем."""


def _kind(path):
    """Что лежит по пути: "dir", "file", "other" либо None — ничего нет.

    Папка на пути закрыта — `Unreadable`: «ничего нет» было бы неправдой, и
    попытка ушла бы человеку в счёт. `os.path.isdir` и `exists` в таком
    случае молча отвечают «нет».
    """
    try:
        if os.path.isdir(path):
            return "dir"
        if os.path.isfile(path):
            return "file"
        os.lstat(path)
    except FileNotFoundError:
        return None
    except NotADirectoryError:
        return None
    except OSError as error:
        raise Unreadable(path) from error
    return "other"


def settings_files(project, home):
    """Файлы настроек, в которых Claude Code ищет хуки этого проекта."""
    files = [os.path.join(project, name) for name in PROJECT_SETTINGS]
    if home:
        files.append(os.path.join(home, USER_SETTINGS))
    return files


def _prompt_hooks_in(path):
    """Сколько хуков на запрос записано в одном файле настроек."""
    if _kind(path) is None:
        return 0
    try:
        with open(path, encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, ValueError) as error:
        raise Unreadable(path) from error
    if not isinstance(data, dict):
        raise Unreadable(path)
    hooks = data.get("hooks")
    groups = hooks.get(PROMPT_EVENT) if isinstance(hooks, dict) else None
    if not isinstance(groups, list):
        return 0
    found = 0
    for group in groups:
        inner = group.get("hooks") if isinstance(group, dict) else None
        for item in inner if isinstance(inner, list) else ():
            if not isinstance(item, dict):
                continue
            if any(isinstance(item.get(key), str) and item[key].strip()
                   for key in _HOOK_BODY):
                found += 1
    return found


def has_prompt_hook(project, home):
    """Записан ли хук на запрос в настройках проекта или пользователя.

    Хуки игры в этих файлах не живут: они в `hooks.json` плагина. Другие
    события (`Stop`, `PreToolUse`) сюда не попадают — на них висят хуки
    набора SDD и хуки, которые человек мог поставить до игры.
    """
    return any(_prompt_hooks_in(path) for path in settings_files(project, home))


def _front_matter(text):
    """(поля блока `---`, тело под ним) либо (None, текст), когда блока нет.

    Разбор нарочно простой и прощающий: файл пишет Claude, и поля в нём
    бывают любыми. Нужно одно — есть ли у ключа `description` значение: на
    той же строке или строками с отступом под ним (`description: >`).
    """
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            break
    else:
        return None, text
    fields = {}
    key = None
    for line in lines[1:end]:
        if line[:1] in (" ", "\t"):
            if key is not None and line.strip():
                fields[key] = (fields[key] + " " + line.strip()).strip()
            continue
        name, colon, value = line.partition(":")
        if not colon or not name.strip():
            key = None
            continue
        key = name.strip()
        value = value.strip()
        # `>` и `|` открывают значение на следующих строках, сами они не текст.
        fields[key] = "" if value.rstrip("+-") in (">", "|") else value.strip("\"'")
    return fields, "\n".join(lines[end + 1:])


def judge_skill(text):
    """Исход для одного файла скилла."""
    fields, body = _front_matter(text)
    if fields is None or not fields.get("description", "").strip():
        return SKILL_NO_DESCRIPTION
    # Заголовок — ещё не правило: нужна хоть одна строка текста.
    wrote = [line for line in body.splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    return SKILL_OK if wrote else SKILL_NO_BODY


def _skill_files(root, known, not_before=None):
    """Файлы своих скиллов в `<корень>/.claude/skills/`: имя папки не из
    известных, а при `not_before` — файл изменён не раньше этого момента."""
    skills = os.path.join(root, ".claude", "skills")
    if _kind(skills) != "dir":
        return []
    try:
        names = sorted(os.listdir(skills))
    except OSError as error:
        raise Unreadable(skills) from error
    found = []
    for name in names:
        if name.lower() in known:
            continue
        path = os.path.join(skills, name, "SKILL.md")
        if _kind(path) != "file":
            continue
        try:
            if not_before is not None and os.path.getmtime(path) < not_before:
                continue
        except OSError as error:
            raise Unreadable(path) from error
        found.append(path)
    return found


def own_skill(project, home, known, started=None):
    """Лучший исход среди своих скиллов человека.

    Свой — значит не из готовых, которые игра называет примерами (`known`):
    их имена держит `quests/_lib/machine.sh`. Скилл в папке проекта принимается любой.
    Личный (`~/.claude/skills/`) — только изменённый не раньше входа в акт
    (`started`, секунды эпохи): иначе квест закрывал бы скилл, поставленный
    до игры. Момента нет — личные не смотрятся вовсе.
    """
    known = {name.lower() for name in known}
    files = _skill_files(project, known)
    if home and started is not None:
        files += _skill_files(home, known, not_before=started)
    best = SKILL_NONE
    for path in files:
        try:
            with open(path, encoding="utf-8", errors="replace") as source:
                verdict = judge_skill(source.read())
        except OSError as error:
            raise Unreadable(path) from error
        if _SKILL_ORDER.index(verdict) > _SKILL_ORDER.index(best):
            best = verdict
    return best


def main(argv=None):
    """Команды для проверок квестов.

    `prompt-hook <папка проекта> <домашняя папка>` — код 0: хук на запрос
    записан; 1: нет; 3: настройки не читаются.

    `own-skill <папка проекта> <домашняя папка> <вход в акт> [известные…]` —
    печатает исход (`none`, `no-description`, `no-body`, `ok`), код 0; код
    3: папка или файл не читаются. Вход в акт — секунды эпохи или пусто.

    Позвали не так — код 4.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(argv) == 3 and argv[0] == "prompt-hook":
            return 0 if has_prompt_hook(argv[1], argv[2]) else 1
        if len(argv) >= 4 and argv[0] == "own-skill":
            started = int(argv[3]) if argv[3].isdigit() else None
            print(own_skill(argv[1], argv[2], argv[4:], started))
            return 0
    except Unreadable:
        return EXIT_UNREADABLE
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())

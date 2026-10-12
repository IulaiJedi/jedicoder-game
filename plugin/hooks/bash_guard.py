#!/usr/bin/env python3
"""PreToolUse-хук Тёмной стороны: что игра не даёт сделать молча.

Три сюжета: `.env` уезжает в индекс (блок, +2 ТС), `rm -rf` мимо проекта
(блок, +1 ТС), вход на сервер под root (предупреждение, +1 ТС однократно).

Закон хуков: не смогли уверенно опознать — пропускаем. Ложный блок
дороже пропуска: он останавливает работу человека, который ничего плохого
не делал.

Что считается опознанным. Bash целиком хук не разбирает и не пытается:
он узнаёт короткий список форм, а всё остальное пропускает молча.

- Команда — `git`, `rm`, `ssh` или `cd` первым словом; перед ней могут
  стоять присваивания, обёртки из `_WRAPPER_VALUE_OPTS` и служебные слова
  из `_SHELL_KEYWORDS`. Всё, что запускает команду иначе (`bash -c`,
  `eval`, `xargs`, `find -exec`, функция, алиас), — не опознано.
- Путь — написан буквально или собран из `~` и переменных, которые видны
  самому хуку. Осталась подстановка, значения которой хук не знает
  (`$D`, `$(…)`, обратные кавычки), — путь не опознан, см. `_literal`.
- Папка, от которой считаются относительные пути, — cwd из payload'а и
  буквальные `cd` по ходу команды. Ушли неизвестно куда — относительные
  пути и `git add` до конца команды не судятся, см. `located_commands`.

Абсолютный путь и катастрофы (корень, домашняя папка) судятся всегда.
"""
import io
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _shared  # noqa: E402
from jedicoder import state as st  # noqa: E402

# Символы-операторы, разделяющие простые команды. Токен, целиком из них
# состоящий, — разделитель: так покрываются и `&&`, и `;`, и `|`, и
# скобки подоболочки, и перевод строки.
_PUNCTUATION = set("();<>|&\n")

ENV_NAME = ".env"

DARK_ENV = 2
DARK_RM = 1
DARK_ROOT = 1


def _prepare(command):
    """Подготовить строку к разбору.

    `$'…'` превращается в обычные кавычки: для опознания пути
    escape-последовательности внутри не важны, а иначе `rm -rf $'/etc'`
    читается как относительный путь и проходит мимо блока.

    Висячий обратный слэш в конце строки bash игнорирует, а lexer на нём
    падает — и тогда не проверяется ВСЯ команда, включая опасную. Один
    символ не должен отключать защиту.
    """
    prepared = command.replace("$'", "'")
    stripped = prepared.rstrip()
    if stripped.endswith("\\") and not stripped.endswith("\\\\"):
        return stripped[:-1]
    return prepared


def _strip_heredocs(tokens):
    """Выбросить тела heredoc: это данные, а не команды.

    Без этого `cat > script.sh <<'EOF'` с `rm -rf /tmp/x` в теле блокирует
    падавана за написание текстового файла — тот же принцип, по которому
    не считается командой текст в кавычках. Хвост после терминатора
    проверяется как обычно.

    `<<-EOF` лексер режет на `<<` и слово `-EOF`: дефис в операторы не
    входит. Поэтому слово с дефисом впереди закрывается и самим собой
    (`<< -EOF`, редкость), и словом без дефиса (`<<-EOF`, обычная форма
    с отступом): различить эти две записи по токенам нельзя, а не
    признать вторую — значит не найти терминатор никогда и выбросить
    вместе с телом весь хвост команды. Дефис отдельным словом
    (`<<- EOF`) — тот же оператор, разделитель идёт следом.
    """
    result = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "<<" and index + 1 < len(tokens):
            if tokens[index + 1] == "-" and index + 2 < len(tokens):
                index += 1
            delimiters = {tokens[index + 1]}
            if len(tokens[index + 1]) > 1 and tokens[index + 1][0] == "-":
                delimiters.add(tokens[index + 1][1:])
            index += 2
            while index < len(tokens):
                if (tokens[index] == "\n" and index + 1 < len(tokens)
                        and tokens[index + 1] in delimiters):
                    index += 2
                    break
                index += 1
            continue
        result.append(token)
        index += 1
    return result


class _Source(io.StringIO):
    """Текст команды для лексера: комментарий не съедает перевод строки.

    Комментарий лексер выбрасывает через `readline()`, то есть вместе с
    «\\n» на конце. Перевод строки здесь — разделитель команд, и без
    него `echo hi # заметка` склеивается со следующей строкой в одну
    команду: `rm -rf /` строкой ниже становится аргументами `echo`.
    """

    def readline(self, *args):
        line = super().readline(*args)
        if line.endswith("\n"):
            self.seek(self.tell() - 1)
        return line


def _tokens(command):
    """Токены команды без тел heredoc или None, если строка не разбирается.

    Перевод строки — такой же разделитель, как «;», поэтому он передан
    лексеру в punctuation_chars и убран из whitespace. Резать строку по
    «\\n» до лексера нельзя: легальный многострочный аргумент в кавычках
    («git commit -m "две\\nстроки"») разорвался бы посередине, лексер
    упал бы на незакрытой кавычке, и проверяться перестала бы вся
    команда, включая опасный хвост.

    Продолжения строк («\\» на конце) склеиваются заранее: для bash это
    одна строка, и разделителем такой перевод не является.
    """
    try:
        lexer = shlex.shlex(
            _Source(_prepare(command).replace("\\\n", " ")),
            posix=True,
            punctuation_chars=";&|()<>\n",
        )
        lexer.whitespace_split = True
        lexer.whitespace = " \t\r"
        tokens = list(lexer)
    except ValueError:
        return None
    return _strip_heredocs(tokens)


# Чего хук про путь знать не может: значение переменной, которой нет в
# его окружении, и результат подстановки команды.
_UNKNOWN_VALUE = "$`"

_GLOB = "*?["

_PWD = re.compile(r"\$(?:PWD\b|\{PWD\})")
_OLDPWD = re.compile(r"\$(?:OLDPWD\b|\{OLDPWD\})")


def _literal(text, cwd):
    """Путь как он написан, с раскрытыми `~` и переменными, либо None.

    Переменные берутся из окружения хука: `$HOME` там тот же, что у
    команды. Переменная, заданная в самой команде (`D=/tmp/x; rm -rf $D`),
    хуку не видна и остаётся в тексте как есть — раньше такой текст
    читался именем папки `$D` рядом с cwd, и приговор зависел от случая.
    Теперь это честное «не знаю»: None, и вызывающий пропускает.

    `$PWD` из окружения брать нельзя: там папка процесса хука, а не
    команды. Вместо него подставляется `cwd` — папка, в которой команда
    пойдёт; `$OLDPWD` хуку взять неоткуда вовсе.
    """
    if _OLDPWD.search(text):
        return None
    if _PWD.search(text):
        if cwd is None:
            return None
        text = _PWD.sub(lambda match: str(cwd), text)
    expanded = os.path.expanduser(os.path.expandvars(text))
    if expanded.startswith("~"):
        return None
    if any(ch in expanded for ch in _UNKNOWN_VALUE):
        return None
    return expanded


def _cd_target(args, here):
    """Куда приведёт `cd` с такими аргументами, либо None — «не знаю»."""
    args = [arg for arg in args if arg not in ("-L", "-P", "-e", "-@", "--")]
    if not args:
        target = "~"
    elif len(args) != 1 or args[0] == "-":
        return None
    else:
        target = args[0]
    literal = _literal(target, here)
    if literal is None or any(ch in literal for ch in _GLOB):
        return None
    path = Path(literal)
    if not path.is_absolute():
        if here is None:
            return None
        path = Path(here) / path
    return Path(os.path.realpath(str(path)))


# Команды, которые меняют папку. `pushd папка` — тот же cd; `popd` и
# `pushd` без папки ходят по стеку, которого хук не видит.
_MOVES = ("cd", "pushd", "popd")


def _is_redirection(token):
    """`>`, `>>`, `2>&1`, `&>`, `<`, `<<<` — перенаправление, а не граница
    команды."""
    return (
        ("<" in token or ">" in token)
        and all(ch in "<>&|" for ch in token)
    )


def _move(normal, here):
    """Папка после cd/pushd/popd, либо None — «не знаю»."""
    head, args = normal[0], normal[1:]
    if head == "popd":
        return None
    if head == "pushd" and (not args or args[0][:1] in ("+", "-")):
        return None
    return _cd_target(args, here)

# Операторы, при которых cd мог и не сработать в этой оболочке: ветка
# `||`, конвейер и фон (оба уводят cd в подоболочку).
_CD_NOT_CERTAIN = ("||", "|", "|&", "&")


def _cd_is_certain(tokens, before, after):
    """`cd` точно выполнится раньше следующей команды и в этой оболочке?

    Нет — под служебным словом (`then cd x`), в ветке `||`, в конвейере
    или в фоне, и после `&&`, если цепочка на нём обрывается:
    `test -d x && cd x; rm -rf dist` доходит до rm и без cd. Цепочка
    `a && cd x && rm …` — не условие, а порядок: дошли до rm, значит cd
    был.
    """
    if tokens[0] in _SHELL_KEYWORDS:
        return False
    if before in _CD_NOT_CERTAIN or after in _CD_NOT_CERTAIN:
        return False
    return before != "&&" or after == "&&"


def located_commands(command, cwd):
    """Простые команды строки вместе с папкой, в которой каждая пойдёт.

    Возвращает список пар `(токены, папка)`. Папка — cwd из payload'а,
    пока команда сама не ушла через `cd`: `cd api && git add .` смотрит
    `api`, а `cd ~/проект && rm -rf dist` из сессии этажом выше — это
    уборка в проекте, а не мимо него. Без этого первое давало ложный
    блок, второе — тоже.

    Папка `None` значит «не знаю»: `cd "$D"`, `cd -`, `popd`, cd под
    условием (`_cd_is_certain`). Скобки подоболочки, включая `$(…)`,
    папку возвращают: `(cd x && make); rm -rf dist` стирает `dist` там
    же, где начали.

    Определение функции и `case` сами папку не меняют, но после них
    разбор хрупок: тело функции могло и не выполниться, а `case`
    расставляет непарные «)». Поэтому первый же cd после них — и папка
    неизвестна до конца команды. Нет cd — судим как обычно: одна
    функция в строке не должна выключать защиту целиком.

    Перенаправления (`2>/dev/null`, `> log`) из команды вынимаются:
    лексер режет их на цифру, оператор и путь, и без этого `cd sub
    2>/dev/null` читался бы как cd с двумя аргументами.

    Не разбирается (незакрытая кавычка, мусор) — пустой список: судить
    не о чем, значит пропускаем.
    """
    tokens = _tokens(command)
    if tokens is None:
        return []
    located = []
    current = []
    stack = []
    here = cwd
    fragile = False
    lost = False
    before = None
    redirected = False
    for token in tokens:
        if not (token and all(ch in _PUNCTUATION for ch in token)):
            if redirected:
                # Слово после оператора — куда перенаправили, не аргумент.
                redirected = False
            else:
                current.append(token)
            continue
        if _is_redirection(token):
            if current and current[-1].isdigit():
                current.pop()
            redirected = True
            continue
        redirected = False
        if current:
            located.append((current, None if lost else here))
            normal = normalize(current)
            head = normal[0] if normal else ""
            if head in _MOVES:
                if fragile:
                    lost = True
                elif _cd_is_certain(current, before, token):
                    here = _move(normal, here)
                else:
                    here = None
            elif head == "case":
                fragile = True
                if stack:
                    # Внутри подоболочки «)» ветки case снял бы со стека
                    # чужую папку — тут уже не разобраться.
                    lost = True
            current = []
        before = token
        if token == "()":
            fragile = True
            continue
        for ch in token:
            if ch == "(":
                stack.append(here)
            elif ch == ")":
                if stack:
                    here = stack.pop()
                else:
                    fragile = True
    if current:
        located.append((current, None if lost else here))
    return located


def simple_commands(command):
    """Разбить строку на простые команды списками токенов.

    То же, что `located_commands`, без папок — для тех, кому важно
    только, какие команды в строке есть (`commit_pulse`).
    """
    return [tokens for tokens, _ in located_commands(command, None)]


def _git_status_names(cwd, pathspec=None):
    """Пути из `git status --porcelain`, которые `git add` заберёт с
    содержимым. Только чтение, проект не трогаем.

    `pathspec`, если задан, ограничивает вывод им (`-- .`) — иначе
    `git status` всегда репозиторно-широкий и не зависит от `cwd`,
    независимо от того, откуда его позвали.

    Удаления сюда не входят: `D ` (уже убран из индекса) и ` D` (стёрт с
    диска) при `git add` отправляют в индекс исчезновение файла, а не
    файл. Иначе хук блокировал бы само лечение — `.env` в `.gitignore`,
    `git rm --cached .env`, `git add .`.
    """
    # `--untracked-files=all`: по умолчанию новая папка сворачивается в
    # одну строку `?? api/`, и `.env` внутри неё не виден — а `git add .`
    # заберёт его вместе со всей папкой.
    command = ["git", "status", "--porcelain", "--untracked-files=all"]
    if pathspec is not None:
        command += ["--", pathspec]
    try:
        done = subprocess.run(
            command,
            cwd=str(cwd), capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    names = []
    for line in done.stdout.splitlines():
        # Формат: XY<пробел>путь; при переименовании «старый -> новый».
        if line[:2] == "D " or line[1:2] == "D":
            continue
        path = line[3:].strip() if len(line) > 3 else ""
        if " -> " in path:
            path = path.split(" -> ")[-1]
        if path:
            names.append(path.strip('"'))
    return names


def _is_env_path(path):
    """Ровно .env, а не .env.example и не file.env."""
    return Path(path).name == ENV_NAME


# Обёртки, за которыми прячется настоящая команда, и их опции, которые
# забирают следующий токен как значение. Таблица, а не угадывание: без
# неё значение опции («sudo -u root») принимается за имя команды, и
# настоящая команда становится невидимой.
_WRAPPER_VALUE_OPTS = {
    "sudo": ("-u", "-g", "-p", "-C", "-D", "-R", "-T", "-h",
             "--user", "--group", "--prompt", "--chdir",
             "--close-from", "--command-timeout", "--host"),
    "doas": ("-u", "-C"),
    "env": ("-u", "--unset", "-C", "--chdir", "-S", "--split-string"),
    "nice": ("-n", "--adjustment"),
    "nohup": (),
    "command": (),
    "time": ("-f", "--format", "-o", "--output"),
}


# Служебные слова bash, после которых идёт обычная команда: без них
# `if [ -d ../x ]; then rm -rf ../x; fi` читается командой `then`, и
# rm внутри условия или цикла невидим.
_SHELL_KEYWORDS = (
    "if", "then", "elif", "else", "do", "while", "until", "{", "!",
)


def normalize(tokens):
    """Отбросить обёртки и присваивания, привести argv[0] к имени файла.

    `sudo rm -rf /`, `env FOO=1 rm -rf /` и `/bin/rm -rf /` — это всё
    `rm -rf /`. Опции обёрток, забирающие значение (`sudo -u root`,
    `nice -n 10`), пропускаются по таблице `_WRAPPER_VALUE_OPTS` вместе
    со своим значением — иначе значение принимается за имя команды.
    Служебные слова (`then rm -rf …`) снимаются так же.
    """
    rest = list(tokens)
    while rest:
        head = rest[0]
        if head in _SHELL_KEYWORDS:
            rest = rest[1:]
            continue
        if "=" in head and not head.startswith("-"):
            rest = rest[1:]
            continue
        name = PurePosixPath(head).name
        if name in _WRAPPER_VALUE_OPTS:
            value_opts = _WRAPPER_VALUE_OPTS[name]
            rest = rest[1:]
            while rest and (rest[0].startswith("-") or "=" in rest[0]):
                takes_value = rest[0] in value_opts
                rest = rest[1:]
                if takes_value and rest:
                    rest = rest[1:]
            continue
        break
    if not rest:
        return []
    return [PurePosixPath(rest[0]).name] + rest[1:]


# Глобальные опции git, забирающие следующий токен как значение.
_GIT_VALUE_OPTS = ("-C", "-c", "--git-dir", "--work-tree", "--namespace")


def _git_subcommand(tokens):
    """Подкоманда git с пропуском глобальных опций (`git -C dir add .`)."""
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in _GIT_VALUE_OPTS:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token, tokens[index + 1:]
    return "", []


_MASS_ADD_REPO_WIDE = ("-A", "--all", ":/")

# "*" сюда никогда не входил бы полезно: это раскрывает bash ДО git, а
# bash-глобы дотфайлы не трогают — `git add *` физически не может
# захватить `.env` независимо от того, что лежит в рабочем дереве.


def _is_folder(target, cwd):
    literal = _literal(target, cwd)
    return literal is not None and (Path(cwd) / literal).is_dir()


def _add_args(tokens):
    """Аргументы `git add` / `git stage` или None, если команда не о том."""
    tokens = normalize(tokens)
    if not tokens or tokens[0] != "git":
        return None
    sub, args = _git_subcommand(tokens)
    if sub not in ("add", "stage"):
        return None
    return args


def names_env(tokens):
    """`.env` назван в `git add` по имени?

    Единственная форма, для которой не нужно знать папку команды: имя
    говорит само за себя. Поэтому после `cd` неизвестно куда судится
    только она — по папке сессии, как судилась всегда.
    """
    args = _add_args(tokens)
    if args is None:
        return False
    return any(_is_env_path(a) for a in args if not a.startswith("-"))


def stages_env(tokens, cwd):
    """Команда отправит `.env` в индекс?

    Две формы: файл назван явно и массовое добавление (`git add .`,
    `git add api`), при котором `.env` реально лежит незаигноренным в
    рабочем дереве — это и есть настоящий случай «не собирался, оно
    само». `cwd` — папка, в которой пойдёт команда (см.
    `located_commands`); неизвестна — не судим. Свой `-C` у команды не
    подхватывается намеренно: это отдельный случай и гадать не надо.

    Папка по имени — то же массовое добавление, что и точка: git берёт
    её целиком, и смотреть надо её поддерево.

    `git add .` смотрит только своё поддерево (`git status -- .`
    от `cwd`): `cd frontend && git add .` не должен блокироваться из-за
    незаигноренного `.env` в корне репозитория, если сам `frontend/` чист
    — `.` в git добавляет ровно то, что находится под ним, не больше.
    `-A`/`--all`/`:/` остаются репозиторно-широкими: это explicit просьба
    добавить весь репозиторий, а не текущее поддерево.
    """
    if cwd is None:
        return False
    args = _add_args(tokens)
    if args is None:
        return False
    if names_env(tokens):
        return True
    targets = [a for a in args if not a.startswith("-")]
    folders = [t for t in targets if _is_folder(t, cwd)]
    if folders:
        return any(
            _is_env_path(name)
            for folder in folders
            for name in _git_status_names(cwd, folder)
        )
    if not any(a in _MASS_ADD_REPO_WIDE for a in args):
        return False
    return any(_is_env_path(name) for name in _git_status_names(cwd))


def _rm_flags(tokens):
    """Множество коротких флагов rm: -rf, -fr, -rfv, -r -f, --recursive."""
    flags = set()
    for token in tokens[1:]:
        if token == "--":
            break
        if token.startswith("--"):
            if token == "--recursive":
                flags.add("r")
            elif token == "--force":
                flags.add("f")
        elif token.startswith("-") and len(token) > 1:
            flags.update(token[1:])
    # `-R` — то же самое, что `-r`: `rm -Rf` пишут не реже, чем `rm -rf`.
    if "R" in flags:
        flags.add("r")
    return flags


def _rm_targets(tokens):
    return [t for t in tokens[1:] if not t.startswith("-") and t != "--"]


def _resolve(target, cwd):
    """Путь цели, приведённый через realpath, либо None — «не знаю».

    None — когда в пути осталась подстановка с неизвестным значением
    (`_literal`) или путь относительный, а папка, от которой его считать,
    неизвестна (`located_commands`).

    realpath, а не normpath: `project.path` в состоянии кладётся через
    `.resolve()` (cli.py раскрывает симлинки), и если цель здесь
    оставить нераскрытой, обе стороны сравнения окажутся в разном виде
    — падаван, зашедший в проект по симлинку, читался бы как «вне
    проекта» на собственной же папке. realpath не требует существования
    пути (в отличие от строгого resolve() на некоторых версиях Python)
    и раскрывает симлинки в той части пути, что существует.

    realpath берётся у РОДИТЕЛЯ, а сам последний сегмент не
    раскрывается: `build → /вне/кэш` внутри проекта — это всё ещё файл
    проекта, и `rm -rf build` без слэша снимает только ссылку.

    Со слэшем на конце всё наоборот: `rm -rf build/` идёт по ссылке и
    стирает содержимое того, на что она указывает. Тогда цель
    раскрывается целиком — судить надо о том, что будет стёрто.
    """
    expanded = _literal(target, cwd)
    if expanded is None:
        return None
    path = Path(expanded)
    if not path.is_absolute():
        if cwd is None:
            return None
        path = Path(cwd) / path
    if expanded.endswith("/"):
        return Path(os.path.realpath(str(path)))
    parent = Path(os.path.realpath(str(path.parent)))
    return parent / path.name


def _is_catastrophic(path):
    """Корень или домашний каталог — блок независимо от знания проекта.

    `rm -rf /*` и `rm -rf ~/*` — то же самое другими словами: стирается
    не сама папка, а всё, что в ней.
    """
    home = Path(os.path.realpath(os.path.expanduser("~")))
    if path.name == "*":
        path = path.parent
    return path == Path(path.anchor) or path == home


def inside_project(cwd, project_dir):
    """Команда выполняется внутри папки, которую падаван назвал проектом?

    Зачем это есть. Плагин ставится глобально, и хук видит **каждую**
    bash-команду на машине — в том числе в репозиториях, к игре отношения
    не имеющих. Без этой границы посторонний, поставивший игру ради Акта 1,
    получал бы отказ на `git add .` у себя на работе: за `.env`, которого
    игра ему не показывала и о котором ничему не учила. Это ровно тот
    ложный блок, который по закону хуков дороже пропуска.

    Проекта не знаем — значит «снаружи». Тот же выбор, что у
    `wipes_outside_project`, и по той же причине: гадать не надо. Разница
    между ними намеренная — `rm -rf` мимо проекта всё равно ловит
    катастрофы (корень, домашний каталог), потому что там цена промаха
    несопоставима, а незамеченный `git add .` в чужом репозитории не
    стоит ничего.
    """
    if not project_dir or cwd is None:
        return False
    root = Path(project_dir)
    if not root.is_dir():
        return False
    root = Path(os.path.realpath(str(root)))
    here = Path(os.path.realpath(str(Path(cwd))))
    return here == root or root in here.parents


def wipes_outside_project(tokens, cwd, project_dir):
    """`rm -rf` целится мимо папки проекта?

    Блок уверенный: катастрофы (корень, домашний каталог) — всегда;
    остальное — только когда папка проекта известна. Не знаем проект —
    пропускаем: ложный блок останавливает работу, а от `rm -rf /` мы
    защитили в любом случае. «Известна» значит и существует на диске:
    устаревший (удалённый, переименованный) `project.path` в состоянии —
    это тоже «не знаем», а не «весь остальной диск теперь чужой».
    """
    tokens = normalize(tokens)
    if not tokens or tokens[0] != "rm":
        return False
    flags = _rm_flags(tokens)
    if "r" not in flags or "f" not in flags:
        return False
    targets = _rm_targets(tokens)
    if not targets:
        return False
    root = None
    if project_dir is not None and Path(project_dir).is_dir():
        root = Path(os.path.realpath(str(Path(project_dir))))
    for target in targets:
        path = _resolve(target, cwd)
        if path is None:
            continue
        if _is_catastrophic(path):
            return True
        if root is None:
            continue
        if root != path and root not in path.parents:
            return True
    return False


def logs_in_as_root(tokens):
    tokens = normalize(tokens)
    if not tokens or tokens[0] != "ssh":
        return False
    return any(
        token.startswith("root@") for token in tokens[1:]
        if not token.startswith("-")
    )


def _deny(reason, said, extra):
    """Отказ PreToolUse: причина — Claude, слова — человеку.

    Адресатов два, и языка два. Claude получает точную причину, по которой
    чинить: имя файла, имя списка. Человек первого вечера этих слов ещё не
    знает — ему говорится, что случилось и что ничего не пропало.
    """
    message = said if not extra else said + "\n\n" + extra
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": message,
    }


#: Причина отказа на `rm -rf` мимо папки проекта. Её же получает катастрофа
#: в чужой сессии — одна, без штрафа и без правила Кодекса.
RM_REASON = (
    "Это rm -rf мимо папки проекта. Удалённое так не "
    "возвращается — посмотри путь ещё раз."
)

# Вне игры папки проекта нет, и слов игры быть не должно: человек не играет.
# Блок здесь один — корень диска и домашняя папка.
RM_CATASTROPHE_REASON = (
    "Это rm -rf корня диска или домашней папки. Удалённое так не "
    "возвращается — посмотри путь ещё раз."
)


def _decide_outside_the_game(command, cwd):
    """Чужая сессия: человек работает, а не играет (#97).

    Плагин стоит на всей машине, и хук видит каждую команду Bash. Вне
    игровой сессии он не судит ничего — ни `.env`, ни удаление мимо папки
    проекта, ни вход под root — и сохранение не читает и не пишет. Блок
    остаётся один: катастрофа, `rm -rf` корня или домашней папки. Он не
    штраф, а защита, поэтому в ответе только причина отказа: ни слова
    «штраф», ни правила Кодекса.
    """
    for tokens, where in located_commands(command, cwd):
        # Папка проекта не называется: без неё `wipes_outside_project`
        # отвечает «да» только на катастрофу.
        if wipes_outside_project(tokens, where, None):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": RM_CATASTROPHE_REASON,
                },
            }
    return None


def decide(payload):
    """Решение по одной команде Bash или None, если сказать нечего.

    Сначала команда проходится целиком — по всем простым командам внутри
    неё — и только потом принимается решение. Так `ssh root@host ; rm -rf
    ../x` не теряет блок за rm: одиночный `return` на первом совпадении
    отдавал бы только предупреждение про root и пропускал бы саму
    катастрофу мимо блока.
    """
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    cwd = payload.get("cwd") or os.getcwd()
    if not _shared.is_game_session(payload):
        return _decide_outside_the_game(command, cwd)
    # Первое чтение — не под блокировкой: это разведка (нужен project_dir
    # и было ли уже предупреждение), а не запись. Настоящая
    # read-modify-write ниже перечитывает состояние заново под замком —
    # именно там, где будет мутация.
    state = _shared.load_state()
    project_dir = (state.get("project") or {}).get("path")

    # Судим `.env` только внутри проекта падавана: см. inside_project.
    # Место у каждой простой команды своё — `cd` посреди строки его
    # меняет, см. located_commands.
    session_inside = inside_project(cwd, project_dir)

    env_hit = False
    rm_hit = False
    root_hit = False
    for tokens, where in located_commands(command, cwd):
        if not env_hit:
            if where is None:
                env_hit = session_inside and names_env(tokens)
            else:
                env_hit = (inside_project(where, project_dir)
                           and stages_env(tokens, where))
        if not rm_hit and wipes_outside_project(tokens, where, project_dir):
            rm_hit = True
        if not root_hit and logs_in_as_root(tokens):
            root_hit = True

    # Предупреждение про root начисляется один раз за всё прохождение
    # (не наказание — повод привести в квест), а не при каждом входе.
    was_warned = bool(state.get("root_login_warned"))
    root_new = root_hit and not was_warned

    invite = ""
    if env_hit or rm_hit or root_new:
        with _shared.update_state() as fresh:
            if env_hit:
                _shared.add_dark_side(fresh, DARK_ENV, st.DARK_ENV_STAGED)
            if rm_hit:
                _shared.add_dark_side(fresh, DARK_RM, st.DARK_RM_OUTSIDE_PROJECT)
            if root_new:
                if fresh.get("root_login_warned"):
                    # Между разведкой и этим окном другой процесс уже
                    # предупредил падавана — не начисляем ТС дважды за
                    # одно и то же предупреждение.
                    root_new = False
                else:
                    fresh["root_login_warned"] = True
                    _shared.add_dark_side(fresh, DARK_ROOT, st.DARK_ROOT_LOGIN)
            if env_hit or rm_hit or root_new:
                invite = _shared.magistr_invite(fresh)

    if env_hit or rm_hit:
        env_reason = (
            "Это отправит .env в индекс git. Ключи, попавшие в историю, "
            "остаются там навсегда — сначала добавь .env в .gitignore."
        )
        rm_reason = RM_REASON
        env_said = (
            _shared.penalty_line(DARK_ENV, st.DARK_ENV_STAGED)
            + " Игра остановила команду: файл на месте, в сохранение он не"
            " попал."
        )
        rm_said = (
            _shared.penalty_line(DARK_RM, st.DARK_RM_OUTSIDE_PROJECT)
            + " Игра остановила команду: ничего не удалено."
        )
        if env_hit:
            reason, said = env_reason, env_said
            extra = _shared.rule_text(_shared.plugin_root(), "env-never-in-git")
        else:
            reason, said = rm_reason, rm_said
            extra = _shared.rule_text(
                _shared.plugin_root(), "rm-rf-outside-project"
            )
        out = _deny(reason, said, extra)
        if env_hit and rm_hit:
            # Оба сработали в одной команде: причина отказа — про .env
            # (она опаснее), но rm -rf мимо проекта тоже произошёл и тоже
            # был начислен — падаван должен увидеть оба, а не только
            # первый по счёту.
            out["systemMessage"] += "\n\n" + rm_said
        if invite:
            out["systemMessage"] += "\n\n" + invite
        return out

    if root_new:
        # Не блокируем: у падавана может ещё не быть другого
        # пользователя — он его и заводит в Акте 4.
        message = (
            _shared.penalty_line(DARK_ROOT, st.DARK_ROOT_LOGIN)
            + " Команда прошла: об этом игра только предупреждает."
        )
        extra = _shared.rule_text(
            _shared.plugin_root(), "no-root-in-production"
        )
        if extra:
            message += "\n\n" + extra
        if invite:
            message += "\n\n" + invite
        return {"systemMessage": message}

    return None


def main():
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        # Режим разрешений — попутно: хук срабатывает перед каждой командой,
        # в том числе перед командами самой игры. На решение о команде не
        # влияет и бросить не может (_shared.record_permission_mode).
        _shared.record_permission_mode(payload)
        out = decide(payload)
        if out:
            print(json.dumps(out, ensure_ascii=False))
    except Exception:
        # Закон хуков: не смогли решить — не мешаем. BaseException
        # проходит насквозь.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

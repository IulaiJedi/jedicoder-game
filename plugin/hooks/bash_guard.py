#!/usr/bin/env python3
"""PreToolUse-хук Тёмной стороны: что игра не даёт сделать молча.

Три сюжета: `.env` уезжает в индекс (блок, +2 ТС), `rm -rf` мимо проекта
(блок, +1 ТС), вход на сервер под root (предупреждение, +1 ТС однократно).

Закон хуков: не смогли уверенно опознать — пропускаем. Ложный блок
дороже пропуска: он останавливает работу человека, который ничего плохого
не делал.
"""
import json
import os
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
    """
    result = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in ("<<", "<<-") and index + 1 < len(tokens):
            delimiter = tokens[index + 1]
            index += 2
            while index < len(tokens):
                if (tokens[index] == "\n" and index + 1 < len(tokens)
                        and tokens[index + 1] == delimiter):
                    index += 2
                    break
                index += 1
            continue
        result.append(token)
        index += 1
    return result


def simple_commands(command):
    """Разбить строку на простые команды списками токенов.

    Перевод строки — такой же разделитель, как «;», поэтому он передан
    лексеру в punctuation_chars и убран из whitespace. Резать строку по
    «\\n» до лексера нельзя: легальный многострочный аргумент в кавычках
    («git commit -m "две\\nстроки"») разорвался бы посередине, лексер
    упал бы на незакрытой кавычке, и проверяться перестала бы вся
    команда, включая опасный хвост.

    Продолжения строк («\\» на конце) склеиваются заранее: для bash это
    одна строка, и разделителем такой перевод не является.

    Не разбирается (незакрытая кавычка, мусор) — пустой список: судить
    не о чем, значит пропускаем.
    """
    try:
        lexer = shlex.shlex(
            _prepare(command).replace("\\\n", " "),
            posix=True,
            punctuation_chars=";&|()<>\n",
        )
        lexer.whitespace_split = True
        lexer.whitespace = " \t\r"
        tokens = list(lexer)
    except ValueError:
        return []
    tokens = _strip_heredocs(tokens)
    commands = []
    current = []
    for token in tokens:
        if token and all(ch in _PUNCTUATION for ch in token):
            if current:
                commands.append(current)
            current = []
        else:
            current.append(token)
    if current:
        commands.append(current)
    return commands


def _git_status_names(cwd, pathspec=None):
    """Пути из `git status --porcelain`. Только чтение, проект не трогаем.

    `pathspec`, если задан, ограничивает вывод им (`-- .`) — иначе
    `git status` всегда репозиторно-широкий и не зависит от `cwd`,
    независимо от того, откуда его позвали.
    """
    command = ["git", "status", "--porcelain"]
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


def normalize(tokens):
    """Отбросить обёртки и присваивания, привести argv[0] к имени файла.

    `sudo rm -rf /`, `env FOO=1 rm -rf /` и `/bin/rm -rf /` — это всё
    `rm -rf /`. Опции обёрток, забирающие значение (`sudo -u root`,
    `nice -n 10`), пропускаются по таблице `_WRAPPER_VALUE_OPTS` вместе
    со своим значением — иначе значение принимается за имя команды.
    """
    rest = list(tokens)
    while rest:
        head = rest[0]
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


def stages_env(tokens, cwd):
    """Команда отправит `.env` в индекс?

    Две формы: файл назван явно и массовое добавление (`git add .`),
    при котором `.env` реально лежит незаигноренным в рабочем дереве —
    это и есть настоящий случай «не собирался, оно само». `cwd` — это
    всегда рабочая директория из payload'а, даже если сама команда
    несёт свой `-C`: значение `-C` не подхватывается намеренно, это
    отдельный случай и гадать не надо.

    `git add .` смотрит только своё поддерево (`git status -- .`
    от `cwd`): `cd frontend && git add .` не должен блокироваться из-за
    незаигноренного `.env` в корне репозитория, если сам `frontend/` чист
    — `.` в git добавляет ровно то, что находится под ним, не больше.
    `-A`/`--all`/`:/` остаются репозиторно-широкими: это explicit просьба
    добавить весь репозиторий, а не текущее поддерево.
    """
    tokens = normalize(tokens)
    if not tokens or tokens[0] != "git":
        return False
    sub, args = _git_subcommand(tokens)
    if sub not in ("add", "stage"):
        return False
    targets = [a for a in args if not a.startswith("-")]
    if any(_is_env_path(t) for t in targets):
        return True
    if "." in args:
        return any(
            _is_env_path(name) for name in _git_status_names(cwd, ".")
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
    return flags


def _rm_targets(tokens):
    return [t for t in tokens[1:] if not t.startswith("-") and t != "--"]


def _resolve(target, cwd):
    """Путь цели, приведённый через realpath.

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
    """
    expanded = os.path.expanduser(os.path.expandvars(target))
    path = Path(expanded)
    if not path.is_absolute():
        path = Path(cwd) / path
    parent = Path(os.path.realpath(str(path.parent)))
    return parent / path.name


def _is_catastrophic(path):
    """Корень или домашний каталог — блок независимо от знания проекта."""
    home = Path(os.path.realpath(os.path.expanduser("~")))
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
    if not project_dir:
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


def _deny(reason, extra):
    """Отказ PreToolUse: причина уходит и в решение, и падавану."""
    message = reason if not extra else reason + "\n\n" + extra
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        },
        "systemMessage": message,
    }


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
    # Первое чтение — не под блокировкой: это разведка (нужен project_dir
    # и было ли уже предупреждение), а не запись. Настоящая
    # read-modify-write ниже перечитывает состояние заново под замком —
    # именно там, где будет мутация.
    state = _shared.load_state()
    project_dir = (state.get("project") or {}).get("path")

    # Судим `.env` только внутри проекта падавана: см. inside_project.
    # Проверка вынесена из цикла — она про место, а не про команду.
    here = inside_project(cwd, project_dir)

    env_hit = False
    rm_hit = False
    root_hit = False
    for tokens in simple_commands(command):
        if not env_hit and here and stages_env(tokens, cwd):
            env_hit = True
        if not rm_hit and wipes_outside_project(tokens, cwd, project_dir):
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
        rm_reason = (
            "Это rm -rf мимо папки проекта. Удалённое так не "
            "возвращается — посмотри путь ещё раз."
        )
        if env_hit:
            reason = env_reason
            extra = _shared.rule_text(_shared.plugin_root(), "env-never-in-git")
        else:
            reason = rm_reason
            extra = _shared.rule_text(
                _shared.plugin_root(), "rm-rf-outside-project"
            )
        out = _deny(reason, extra)
        if env_hit and rm_hit:
            # Оба сработали в одной команде: причина отказа — про .env
            # (она опаснее), но rm -rf мимо проекта тоже произошёл и тоже
            # был начислен — падаван должен увидеть оба, а не только
            # первый по счёту.
            out["systemMessage"] += "\n\n" + rm_reason
        if invite:
            out["systemMessage"] += "\n\n" + invite
        return out

    if root_new:
        # Не блокируем: у падавана может ещё не быть другого
        # пользователя — он его и заводит в Акте 4.
        message = (
            "Ты заходишь на сервер под root. Это работает, но однажды "
            "стоит всего сервера — заведи обычного пользователя "
            "(квест 03v-user Акта 4)."
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

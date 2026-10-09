#!/usr/bin/env python3
"""SessionStart: корень плагина — в ~/.jedicoder/plugin_root, папка проекта
и Ключ Голокрона из окружения запуска — в сохранение.

Корень. Скиллы и команды — это markdown, им нужен путь до cli.py, а он
заранее неизвестен. В хуках $CLAUDE_PLUGIN_ROOT гарантированно есть, в
markdown — не гарантированно. Поэтому корень фиксируется здесь один раз
за сессию, а скиллы читают его из файла.

Папка проекта (#81). Приложение Голокрон запускает Claude Code в режиме
без вопросов, а сторож (`bash_guard.py`) стережёт `.env` только внутри
папки, записанной в сохранении. Человек выбрал её ещё в Подготовке
приложения, но само приложение в сохранение не пишет — оно передаёт путь
переменной окружения запуска, а записывает игра, здесь: раньше первой
команды человека, пока он ещё не мог ни о чём попросить.

Ключ Голокрона (#84). Человек ввёл его в приложении один раз, при запуске.
Тем же путём, что папка, ключ приезжает сюда и записывается как связь с
ботом — если человек не связал игру с ботом сам командой `link`. Бот
находит по ключу того, кому его выдал, и видит путь человека: второй код
новичку приложения не нужен. Сеть здесь не трогается — событие ложится в
очередь, отправит его первая же команда игры. Игра в терминале без
приложения переменной не получает и идёт как шла.

Хук молчит и всегда завершается успешно: сломать старт сессии падавана
из-за нашей учётной записи недопустимо.
"""
import os
import re
import sys
from pathlib import Path

DEFAULT_MARKER = Path.home() / ".jedicoder" / "plugin_root"

# Маркер осмысленен только если по этому пути действительно лежит CLI: скиллы
# запускают именно его. Иначе после обновления, переноса или переустановки
# плагина падаван получит «python3: can't open file ...» вместо игры.
CLI_RELATIVE = Path("lib") / "jedicoder" / "cli.py"

# Папка проекта, как её видит игра (на Windows — путь внутри Linux). Ставит
# приложение: golokron/src/main/workbench/launch.ts, PROJECT_DIR_VAR.
PROJECT_DIR_VAR = "JEDICODER_GOLOKRON_PROJECT"

# Ключ Голокрона, принятый приложением. Ставит оно же: launch.ts, KEY_VAR.
GOLOKRON_KEY_VAR = "JEDICODER_GOLOKRON_KEY"

# Форма ключа: `GK-` и три группы по четыре знака из алфавита без 0, 1, O и
# I (golokronKey.ts в репозитории сайта). Только форма — контрольный знак
# считают приложение, которое ключ приняло, и бот, который его выдал;
# третья копия проверки здесь разошлась бы с ними молча.
GOLOKRON_KEY_RE = re.compile(r"GK(-[2-9A-HJ-NP-Z]{4}){3}")


def write_plugin_root():
    sys.stdin.read()  # payload не нужен, но stdin надо вычитать
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return
    if not (Path(root) / CLI_RELATIVE).is_file():
        return
    marker = Path(os.environ.get("JEDICODER_PLUGIN_ROOT_FILE") or DEFAULT_MARKER)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(root + "\n", encoding="utf-8")


class _NothingToWrite(Exception):
    """Выход из окна записи без сохранения: менять нечего."""


def launch_folder():
    """Папка из окружения запуска, пригодная под проект, либо None.

    Значение пришло из чужого процесса, поэтому годится только бесспорное:
    абсолютный путь к существующей папке. Корень, домашний каталог и всё,
    внутри чего он лежит (`/home`, `/mnt/c`), проектом не бывают — «внутри
    проекта» означало бы «везде», и сторож судил бы каждую команду человека
    на машине.

    realpath — как `resolve()` у `project path` в cli.py: сторож сравнивает
    раскрытые пути, и папка, записанная через ссылку, читалась бы как
    «вне проекта» на самой себе.
    """
    raw = os.environ.get(PROJECT_DIR_VAR)
    if not raw or not os.path.isabs(raw):
        return None
    folder = os.path.realpath(raw)
    if not os.path.isdir(folder):
        return None
    home = os.path.realpath(os.path.expanduser("~"))
    if os.path.commonpath([folder, home]) == folder:
        return None
    return folder


def _recorded(state):
    """Папка, записанная в сохранении и живая на диске, либо None.

    Мусор в поле читается как отсутствие — и путь, по которому папки
    больше нет, тоже: приложение в этом случае спрашивает папку заново и
    передаёт новую, а со старой сторожу стеречь нечего.
    """
    project = state.get("project")
    path = project.get("path") if isinstance(project, dict) else None
    if not isinstance(path, str) or not path:
        return None
    return path if os.path.isdir(path) else None


def launch_key():
    """Ключ Голокрона из окружения запуска, либо None.

    Значение пришло из чужого процесса, поэтому годится только бесспорное:
    строка точно по форме ключа, как её передаёт приложение. Прежний код от
    бота сюда не подходит и не должен — его человек вводит сам командой
    `link`.
    """
    raw = os.environ.get(GOLOKRON_KEY_VAR)
    if not raw or not GOLOKRON_KEY_RE.fullmatch(raw):
        return None
    return raw


def _linked(state):
    """Есть ли уже связь с ботом. Мусор в поле читается как отсутствие."""
    key = state.get("link_key")
    return isinstance(key, str) and bool(key)


def _link_announce(state):
    """Полезная нагрузка события привязки — тем же составом, что у команды
    `link` (`sync.passport_snapshot`), либо None, если собрать её не вышло."""
    try:
        from jedicoder import sync

        # Очередь не список (сохранение правили руками) — событие в неё не
        # лечь не сможет, и запись сорвалась бы целиком, вместе с папкой.
        if not isinstance(state.get("pending_sync", []), list):
            return None
        return sync.passport_snapshot(state)
    except Exception:
        return None


def record_launch():
    folder = launch_folder()
    key = launch_key()
    if folder is None and key is None:
        return
    # Движок подключается только здесь: сессии без переменных (терминал
    # без приложения) он не нужен, и её старт не должен зависеть от того,
    # импортируется ли он.
    import _shared

    # Чтение одно и сразу под замком. Разведка без замка здесь опасна:
    # испорченное сохранение `load` на первом чтении уносит в сторону и
    # отдаёт копию, а второе чтение уже не нашло бы файла и записало бы
    # поверх прогресса пустое состояние.
    try:
        with _shared.update_state() as state:
            # Записанное человеком старше нашего: папка — `project path`,
            # связь с ботом — `link`. Исключение — способ выйти из окна, не
            # пересохраняя файл того, кто уже играет.
            write_folder = folder is not None and not _recorded(state)
            # Событие привязки собирается до любой правки: не собралось
            # (мусор в сохранении) — ключ не пишется вовсе, а папка пишется.
            # Сторож `.env` важнее связи с ботом и ждать её не должен.
            announce = None
            if key is not None and not _linked(state):
                announce = _link_announce(state)
            if not write_folder and announce is None:
                raise _NothingToWrite()
            if write_folder:
                project = state.get("project")
                if not isinstance(project, dict):
                    project = state["project"] = {}
                project["path"] = folder
            if announce is not None:
                state["link_key"] = key
                # Бот применяет события пути только после события привязки.
                _shared.st.enqueue_event(state, "linked", payload=announce)
    except _NothingToWrite:
        pass


def main():
    # Два шага — два отдельных ограждения: сорвавшаяся запись корня не
    # отменяет запись в сохранение, и наоборот. Внутри второго шага папка и
    # ключ пишутся одним окном, и там ключ уступает папке (record_launch).
    #
    # Ловим широко и намеренно: это учётная запись, а не критичная
    # операция, и никакая её ошибка (stdin не в UTF-8, недоступный диск,
    # сохранение от более новой версии игры) не должна долететь до
    # падавана в виде traceback'а. BaseException не трогаем — Ctrl+C и
    # SystemExit обязаны проходить насквозь.
    for step in (write_plugin_root, record_launch):
        try:
            step()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

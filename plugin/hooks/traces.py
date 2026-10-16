#!/usr/bin/env python3
"""Хук следов: записать действие, которого нет в папке проекта.

След (ADR-0020 в репозитории сайта) — запись в сохранении о том, что
действие было. Хук — свидетель: он не знает, какой квест открыт, ничего не
засчитывает и ничего не говорит. Судит проверка квеста, след ей отдаёт
команда игры (`cli._env_for`).

Что и по какому событию пишется — замеры Claude Code 2.1.296, отчёт
`docs/research/2026-10-13-act2-claude-code-facts.md`:

- `plan_approved` — PostToolUse с инструментом `ExitPlanMode`. Инструмент
  выполняется, только когда человек одобрил план (первая или вторая строка
  экрана одобрения). При поправке третьей строкой, Esc и выходе из режима
  плана по Shift+Tab это событие не приходит вовсе — отказ следа не даёт.
  Вне режима плана инструмент отказывает сам, и хукам не приходит ничего:
  без экрана одобрения и человека на нём события не получить.
- `cleared` — `/clear`. Событий два, и слушаются оба: SessionEnd с причиной
  `clear` приходит с прежним идентификатором сессии — по нему узнаётся
  игра, начатая командой в чужой папке; SessionStart с источником `clear`
  приходит с новым идентификатором и страхует в приложении и в папке
  проекта, если конец разговора не успел. След помнит, была ли к этому
  моменту записана память проекта: квесту «Чистый лист» нужен `/clear`
  после неё.

- `file_shown` — UserPromptSubmit: в тексте запроса есть `@путь`, и такой
  файл лежит в папке проекта. Файл через `@` Claude Code читает сам, без
  инструмента, поэтому другого события о нём нет. Что считается `@путём` —
  у `mentioned_paths`.
- `image_shown` — признаков два. Картинку, вставленную в поле ввода (так её
  отдаёт и приложение), Claude Code прикладывает сам и оставляет в тексте
  запроса `[Image #N]`: UserPromptSubmit. Картинку, названную путём внутри
  фразы, Claude читает инструментом: PreToolUse с `Read` и именем файла на
  `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`. Лежать она может где угодно:
  снимки экрана живут вне папки проекта.

- `hook_word` — UserPromptSubmit: в запросе есть отдельное слово «чистка», и
  в настройках проекта или пользователя уже записан хук на запрос (замер
  2026-10-13, `docs/research/2026-10-13-act3-skills-hooks-mods.md`, «Замеры
  #110»). Вывода чужого хука этому хуку не видно: видно только, что слово
  сказано, когда хук был. След помнит момент слова — проверка квеста «Хук»
  сверяет с ним время записи передачи (`HANDOFF.md` в папке проекта). Момент
  сдвигается, только пока на прежнее слово передача не записана: «я же сказал
  чистка» после сработавшего хука квест не отбирает.

След плана, файла, картинки и слова хука несёт пометку `in_act`, если сделан,
пока идёт его акт (`acts.TRACE_ACTS`): проверке уходит только такой. Одобренный до входа в акт план — тоже
след, но квест он не закрывает; пометка появится, когда действие повторят.

План Акта 4 «Свой продукт» судится не пометкой, а моментом: пока его квест
«План» открыт, след плана помнит последнее одобрение (`acts.FRESH_TRACE_QUESTS`),
и проверка сверяет его с моментом входа в акт. План второго вечера квест
четвёртого не закрывает.

Текст запроса в сохранение не пишется никогда: след — имя, день и пометки.

Хук зовётся на каждом запросе и каждом чтении файла в любой сессии Claude
Code. Сначала — признаки в самих данных, без диска; затем игровая ли сессия
(чтение сохранения без замка); только в игровой — есть ли названный файл на
диске; замок — только когда запись что-то меняет.

Только в игровой сессии (#97) и только под замком. Закон хуков: любая
ошибка — тишина и код 0, хук ничего не блокирует и ничего не печатает.
Тому, кто ещё не играет, сохранение не заводится.
"""
import copy
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _shared  # noqa: E402
from jedicoder import acts  # noqa: E402
from jedicoder import machine  # noqa: E402
from jedicoder import quests  # noqa: E402
from jedicoder import state as st  # noqa: E402

#: Инструмент, которым Claude Code выходит из режима плана. Выполняется
#: только после одобрения человеком.
PLAN_TOOL = "ExitPlanMode"

#: Слово, которым Claude Code называет `/clear`: причина у конца сессии,
#: источник у старта.
CLEAR = "clear"


#: Инструмент, которым Claude читает файл — и картинку, названную путём.
READ_TOOL = "Read"

#: Чем кончается имя картинки. Регистр любой: снимки Windows — `.PNG`.
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif")

#: Так Claude Code пишет в запросе вставленную картинку (замер 2026-10-13).
_PASTED_IMAGE = re.compile(r"\[Image #[0-9]+\]")

#: `@"путь с пробелами"` — в начале запроса или после пробела.
_QUOTED_MENTION = re.compile(r'(?:^|(?<=\s))@"([^"]+)"')

#: Хвост слова, который Claude Code в путь не берёт: всё после последней
#: латинской буквы, цифры или подчёркивания.
_MENTION_TAIL = re.compile(r"[^A-Za-z0-9_]+$")

#: Слово квеста «Хук» — отдельным словом, в любом регистре: «очистка» и
#: «чистками» — другие слова. Так же его ловит хук, который Claude пишет по
#: просьбе человека (замер 2026-10-13).
_HOOK_WORD = re.compile(r"(?<!\w)чистка(?!\w)", re.IGNORECASE)

#: Файл передачи в папке проекта: его пишет Claude по слову.
HANDOFF_NAME = "HANDOFF.md"

#: Больше путей из одного запроса не смотрим: вставленный лог с сотней `@`
#: не должен превращаться в сотню обращений к диску на каждом запросе.
MAX_MENTIONS = 20

#: Следы, которых ждёт квест «свежего следа»: им хук пишет момент действия.
_FRESH = frozenset(acts.FRESH_TRACE_QUESTS.values())

#: Следы, которым нужна пометка акта.
_IN_ACT = tuple(
    kind for kind in st.TRACE_KINDS
    if st.TRACE_MARK.get(kind) == st.TRACE_IN_ACT
)


def mentioned_paths(text):
    """Пути, которые запрос называет через `@`, — как их читает Claude Code.

    Узнаваемых форм две, обе сняты с разбора самого Claude Code 2.1.296:

    - `@"путь с пробелами"` — в начале запроса или после пробела;
    - слово, которое начинается с `@`: путь — всё до конца слова, без хвоста
      из знаков (`@notes.txt,` и `@notes.txt?` — это `notes.txt`) и без
      указания строк (`@notes.txt#L1-5`).

    `@` посреди слова — почта, а не файл. Имя, которое кончается не латинской
    буквой и не цифрой (`@заметки`), Claude Code без кавычек не берёт — не
    берём и мы. Не уверены — пути нет.
    """
    if not isinstance(text, str) or "@" not in text:
        return []
    found = [match.group(1) for match in _QUOTED_MENTION.finditer(text)]
    for word in text.split():
        if not word.startswith("@") or word.startswith('@"'):
            continue
        name = _MENTION_TAIL.sub("", word[1:]).split("#", 1)[0]
        if name:
            found.append(name)
    return found[:MAX_MENTIONS]


def _on_disk(name, cwd):
    """Путь из данных хука — раскрытым, либо None, когда его не от чего считать.

    Относительный считается от папки сессии; папки в данных нет — не гадаем.
    """
    path = Path(name)
    if not path.is_absolute():
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            return None
        path = Path(cwd) / path
    return path.resolve()


def shows_project_file(payload, state):
    """Назван ли в запросе через `@` файл, лежащий в папке проекта.

    Папка — не файл; ссылка, ведущая из папки проекта наружу, — не файл
    проекта: сверяются раскрытые пути. Любая ошибка диска — «не назван».
    """
    root = _project_root(state)
    if root is None:
        return False
    try:
        root = Path(root).resolve()
        for name in mentioned_paths(payload.get("prompt")):
            path = _on_disk(name, payload.get("cwd"))
            if path is not None and root in path.parents and path.is_file():
                return True
    except (OSError, RuntimeError, ValueError):
        return False
    return False


def _image_read(payload):
    """Имя картинки, которую Claude читает инструментом, либо None."""
    if payload.get("tool_name") != READ_TOOL:
        return None
    tool_input = payload.get("tool_input")
    name = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(name, str) or not name.lower().endswith(IMAGE_SUFFIXES):
        return None
    return name


def reads_existing_image(payload):
    """Есть ли на диске картинка, которую читает Claude.

    Событие приходит до чтения, и путь в нём мог придумать сам Claude:
    картинки нет — показывать было нечего.
    """
    name = _image_read(payload)
    if name is None:
        return False
    try:
        path = _on_disk(name, payload.get("cwd"))
        return path is not None and path.is_file()
    except (OSError, RuntimeError, ValueError):
        return False


def seen_kinds(payload):
    """Имена следов, о которых говорит событие, — по одним его данным.

    Не уверены — следа нет: незнакомое событие, другой инструмент, поле не
    того типа. Сравнение строк со списком и словарём даёт False, а не
    исключение, поэтому мусор в полях сюда доходит безопасно.

    Диск здесь не читается: хук зовут в любой сессии. `file_shown` — пока
    только «в запросе есть `@путь`», `image_shown` у чтения — «имя кончается
    как у картинки»; есть ли такой файл, сверяет `confirmed` — после того,
    как сессия оказалась игровой.
    """
    event = payload.get("hook_event_name")
    if event == "PostToolUse":
        if payload.get("tool_name") != PLAN_TOOL:
            return ()
        # Режим в данных — уже после решения человека. Всё ещё режим плана —
        # план не одобрен, что бы ни значило это событие в будущей версии.
        if payload.get("permission_mode") == "plan":
            return ()
        return (st.TRACE_PLAN_APPROVED,)
    if event == "SessionEnd" and payload.get("reason") == CLEAR:
        return (st.TRACE_CLEARED,)
    if event == "SessionStart" and payload.get("source") == CLEAR:
        return (st.TRACE_CLEARED,)
    if event == "UserPromptSubmit":
        text = payload.get("prompt")
        if not isinstance(text, str):
            return ()
        kinds = []
        if mentioned_paths(text):
            kinds.append(st.TRACE_FILE_SHOWN)
        if _PASTED_IMAGE.search(text):
            kinds.append(st.TRACE_IMAGE_SHOWN)
        if _HOOK_WORD.search(text):
            kinds.append(st.TRACE_HOOK_WORD)
        return tuple(kinds)
    if event == "PreToolUse" and _image_read(payload) is not None:
        return (st.TRACE_IMAGE_SHOWN,)
    return ()


def _project_root(state):
    """Записанная папка проекта строкой либо None. Мусор — как отсутствие."""
    project = state.get("project") if isinstance(state, dict) else None
    root = project.get("path") if isinstance(project, dict) else None
    if not isinstance(root, str) or not root or not Path(root).is_absolute():
        return None
    return root


def prompt_hook_recorded(state):
    """Записан ли в настройках проекта или пользователя хук на запрос.

    Не уверены — «не записан»: папки проекта нет, настройки не читаются.
    """
    root = _project_root(state)
    if root is None:
        return False
    try:
        return machine.has_prompt_hook(root, os.environ.get("HOME") or "")
    except (machine.Unreadable, OSError, ValueError):
        return False


def _handoff_since(state, moment):
    """Записана ли передача не раньше момента. Ошибка диска — «нет»."""
    root = _project_root(state)
    if root is None:
        return False
    try:
        return os.path.getmtime(os.path.join(root, HANDOFF_NAME)) >= moment
    except OSError:
        return False


def moment_for(state, kind, marks, now=None):
    """Момент, который надо записать следу, либо None — не трогать.

    У слова хука момент сдвигается на «сейчас», пока на прежнее слово нет
    ответа: передача после него не записана — или прежнее слово сказано до
    акта и проверке не годилось. Квест «Хук» закрыт — момент больше никому
    не нужен и не трогается: слово остаётся рабочим словом человека, и
    сохранение из-за него не переписывается.

    У следа, которого ждёт квест «свежего следа» (`acts.FRESH_TRACE_QUESTS`,
    сегодня — план Акта 4), момент — последнее действие, пока такой квест
    открыт: проверка сверяет его с моментом входа в акт. Квест закрыт или
    акт не идёт — момент не трогается.
    """
    if kind in _FRESH:
        if acts.fresh_trace_open(state, kind):
            return int(time.time() if now is None else now)
        return None
    if kind != st.TRACE_HOOK_WORD:
        return None
    entry = st.trace(state, kind) or {}
    before = st.trace_moment(state, kind)
    if before is not None and acts.is_closed(state, *acts.HOOK_QUEST):
        return None
    newly_marked = any(entry.get(name) is not True for name in (marks or {}))
    if before is not None and not newly_marked and _handoff_since(state, before):
        return None
    return int(time.time() if now is None else now)


def confirmed(kinds, payload, state):
    """Те из названных следов, за которыми на диске есть файл."""
    kept = []
    for kind in kinds:
        if kind == st.TRACE_FILE_SHOWN:
            if not shows_project_file(payload, state):
                continue
        elif kind == st.TRACE_HOOK_WORD:
            if not prompt_hook_recorded(state):
                continue
        elif (kind == st.TRACE_IMAGE_SHOWN
                and payload.get("hook_event_name") == "PreToolUse"):
            if not reads_existing_image(payload):
                continue
        kept.append(kind)
    return tuple(kept)


def _write(state, kinds):
    """Записать следы с пометками. True — сохранение изменилось."""
    changed = []
    for kind in kinds:
        marks = marks_for(state, kind)
        moment = moment_for(state, kind, marks)
        changed.append(st.record_trace(state, kind, marks, at=moment))
        if (kind == st.TRACE_HOOK_WORD and moment is not None
                and quests.refused(state, *acts.HOOK_QUEST)):
            # Слово сказано заново: прежний провал проверки к нему не
            # относится, и строка «Что дальше» снова зовёт проверку.
            quests.forget_refused(state, *acts.HOOK_QUEST)
            changed.append(True)
    return any(changed)


def marks_for(state, kind):
    """Пометки следа, которые знает только сохранение в момент записи."""
    if kind == st.TRACE_CLEARED and acts.is_closed(state, *acts.MEMORY_QUEST):
        return {st.TRACE_AFTER_MEMORY: True}
    if kind in _IN_ACT and acts.trace_in_act(state, kind):
        return {st.TRACE_IN_ACT: True}
    return None


def record(payload):
    kinds = seen_kinds(payload)
    if not kinds:
        return
    if not _shared.is_game_session(payload):
        # Чужая сессия: человек работает, а не играет. Сохранение не тронуто.
        return
    path = _shared.state_path()
    if not Path(path).exists():
        # Сохранения нет — игру ещё не начинали (приложение открыто, а
        # первой команды не было). Заводить её не хуку, и замок не берётся:
        # он оставил бы на диске папку игры и свой файл.
        return
    # До замка: `@` на файл, которого нет, повтор уже записанного действия —
    # обычный запрос, и ждать из-за него замка незачем.
    saved = st.peek(path)
    kinds = confirmed(kinds, payload, saved)
    if not kinds:
        return
    try:
        if isinstance(saved, dict) and not _write(copy.deepcopy(saved), kinds):
            return
    except Exception:
        # Сохранение с мусором примерку не пережило — пусть его чинит и
        # судит чтение под замком.
        pass
    try:
        with _shared.update_state(path) as state:
            # Под замком, после чтения — как у записи режима: испорченный
            # файл `load` к этому моменту уже унёс в сторону.
            if not Path(path).exists():
                raise _shared._Unchanged()
            if not _write(state, kinds):
                raise _shared._Unchanged()
    except _shared._Unchanged:
        return


def main():
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            return 0
        try:
            record(payload)
        finally:
            # Режим — попутно, как у сторожа: одобрение плана меняет режим
            # сессии, а следующую проверку модель зовёт инструментом игры,
            # мимо хуков запроса и команды (живой прогон 2026-10-13: в
            # сохранении оставался `plan`). У конца и старта сессии режима
            # в данных нет, и запись стёрла бы известный — там не зовётся.
            if (payload.get("hook_event_name") == "PostToolUse"
                    and payload.get("tool_name") == PLAN_TOOL):
                _shared.record_permission_mode(payload)
    except Exception:
        # Закон хуков: не смогли записать — молчим. BaseException проходит
        # насквозь.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

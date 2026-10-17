#!/usr/bin/env bash
# Дымовая проверка лица игры.
#
# Запуск:  bash scripts/face_smoke.sh [папка плагина]
#          (без аргумента — plugin/ рядом с этим скриптом)
#
# Зачем. Полосу «Что дальше», всплывающие сообщения и инструменты игры рисует
# модуль plugin/hooks/face.tsx, а исполняет его сам Claude Code. API модулей —
# ранний доступ: обновление Claude Code может сломать лицо молча, игра при
# этом пойдёт как раньше, и ни один тест не покраснеет. Поэтому перед каждым
# выпуском и после каждого обновления Claude Code лицо смотрят живьём.
#
# Что делает. Поднимает игровую сессию в своём сервере tmux, под песочной
# домашней папкой и с песочным сохранением, ждёт первый экран и смотрит:
#   а) полоса «Что дальше:» стоит над полем ввода;
#   б) первый экран показан инструментом игры, а не командой в терминале;
#   в) в журнале Claude Code нет отказов и падений модуля игры.
# Один прогон — один ход модели.
#
# Ответ — слово и код возврата:
#   0  ЛИЦО НА МЕСТЕ
#   1  ЛИЦА НЕТ: <что именно>
#   2  НЕ СМОГ ПРОВЕРИТЬ: <почему>
#
# Чего не делает никогда. Не запускает Claude Code под настоящей домашней
# папкой: хук старта сессии пишет туда указатель на плагин, и боевая игра
# получила бы путь рабочей копии. Не трогает сохранение игры. Не читает и не
# печатает учётные данные — в песочнице лежит только ссылка на файл. Гасит
# только свой сервер tmux. Песочницу не стирает: из неё убираются два файла с
# данными учётной записи и копии настроек в .claude/backups/, остальное
# остаётся для разбора.
#
# Следы. Claude Code кладёт в папку плагина tsconfig.json и
# .claude-plugin/types/. В рабочей копии это безвредно (их держит .gitignore).
# Собранную выгрузку проверяют на её КОПИИ: папку, в которой шла проверка,
# не публикуют.
set -u

WAIT_SECONDS="${FACE_SMOKE_TIMEOUT:-240}"
STEP_SECONDS=3

say() { printf '%s\n' "$*"; }

cannot() {
    say "НЕ СМОГ ПРОВЕРИТЬ: $*"
    exit 2
}

# --- Что нужно для проверки ---------------------------------------------

for tool in tmux claude python3 mktemp; do
    command -v "$tool" >/dev/null 2>&1 || cannot "нет программы $tool"
done

REAL_HOME="${HOME:-}"
[ -n "$REAL_HOME" ] || cannot "не задана домашняя папка"
CREDENTIALS="$REAL_HOME/.claude/.credentials.json"
ACCOUNT="$REAL_HOME/.claude.json"
[ -e "$CREDENTIALS" ] || cannot "нет файла учётных данных Claude Code (.claude/.credentials.json) — войди в Claude Code; на macOS они лежат в связке ключей, и проверка там не идёт"
[ -e "$ACCOUNT" ] || cannot "нет файла настроек Claude Code (.claude.json) — запусти Claude Code один раз"

SELF="${BASH_SOURCE[0]}"
case "$SELF" in
    */*) SELF_DIR="${SELF%/*}" ;;
    *)   SELF_DIR="." ;;
esac
PLUGIN="${1:-$SELF_DIR/../plugin}"
[ -f "$PLUGIN/.claude-plugin/plugin.json" ] || cannot "в папке нет плагина: $PLUGIN"
PLUGIN="$(cd "$PLUGIN" && pwd)"

# --- Песочница ------------------------------------------------------------

SANDBOX="$(mktemp -d)" || cannot "не создалась временная папка"
SANDBOX_HOME="$SANDBOX/home"
PROJECT="$SANDBOX/proj"
SCREEN="$SANDBOX/screen.txt"
DEBUG_LOG="$SANDBOX/debug.log"
mkdir -p "$SANDBOX_HOME/.claude" "$PROJECT" || cannot "не создалась песочница"
[ "$SANDBOX_HOME" != "$REAL_HOME" ] || cannot "песочница совпала с домашней папкой"

SOCKET="jcface-smoke-$$"
SESSION="g"

in_tmux() {
    env -u TMUX HOME="$SANDBOX_HOME" tmux -L "$SOCKET" -f /dev/null "$@"
}

LEFT_BEFORE="no"
[ -e "$PLUGIN/tsconfig.json" ] && LEFT_BEFORE="yes"

# Уборка стоит раньше, чем в песочнице появляются данные учётной записи:
# прерванный прогон их тоже не оставит. Claude Code сам кладёт копии файла
# настроек в .claude/backups/ — это те же данные учётной записи, и они
# уходят вместе с папкой (#122). Папка стирается по одному файлу: в ней нет
# ничего, кроме копий, а rmdir не тронет её, если там окажется чужое.
BACKUPS="$SANDBOX_HOME/.claude/backups"
cleanup() {
    in_tmux kill-server >/dev/null 2>&1
    rm -f "$SANDBOX_HOME/.claude.json" "$SANDBOX_HOME/.claude/.credentials.json"
    rm -f "$BACKUPS"/.claude.json.backup.*
    rmdir "$BACKUPS" >/dev/null 2>&1
}
trap cleanup EXIT
trap 'say "НЕ СМОГ ПРОВЕРИТЬ: прогон прерван"; exit 2' INT TERM

ln -s "$CREDENTIALS" "$SANDBOX_HOME/.claude/.credentials.json" \
    || cannot "не создалась ссылка на учётные данные"
# Настройки едут целиком, кроме двух списков: без настроек Claude Code начал
# бы с выбора темы и входа. Список проектов не нужен, а серверы инструментов
# хозяина машины в сессии без вопросов запускаться не должны. Содержимое не
# печатается.
( umask 077 && python3 - "$ACCOUNT" "$SANDBOX_HOME/.claude.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    data = json.load(source)
data.pop("projects", None)
data.pop("mcpServers", None)
with open(sys.argv[2], "w", encoding="utf-8") as target:
    json.dump(data, target)
PY
) || cannot "не прочитан файл настроек Claude Code"

VERSION="$(env -u CLAUDE_CODE_PLUGIN_DIRS -u CLAUDE_CONFIG_DIR HOME="$SANDBOX_HOME" claude --version 2>/dev/null)"
say "Claude Code: ${VERSION:-версия не названа}"
say "плагин: $PLUGIN"
say "песочница: $SANDBOX"

# --- Сессия ---------------------------------------------------------------

GAME="$(printf 'env -u CLAUDE_CODE_PLUGIN_DIRS -u CLAUDE_CONFIG_DIR -u JEDICODER_PLUGIN_ROOT_FILE -u JEDICODER_GOLOKRON -u JEDICODER_GOLOKRON_KEY -u JEDICODER_GOLOKRON_PROJECT HOME=%q JEDICODER_STATE_PATH=%q claude --plugin-dir %q --dangerously-skip-permissions --debug-file %q /jedicoder:start' \
    "$SANDBOX_HOME" "$SANDBOX/state.json" "$PLUGIN" "$DEBUG_LOG")"

in_tmux new-session -d -s "$SESSION" -x 110 -y 42 -c "$PROJECT" "$GAME" \
    || cannot "не поднялся сервер tmux"

shot() {
    in_tmux capture-pane -p -t "$SESSION" >"$SCREEN" 2>/dev/null
}

on_screen() {
    grep -c -e "$1" "$SCREEN" >/dev/null 2>&1
}

# Вопросы чистой машины — о доверии папке и о режиме без вопросов. Курсор в
# обоих стоит на «No»; согласие — строкой ниже.
answer_dialog() {
    if on_screen '^ *❯ *Yes'; then
        in_tmux send-keys -t "$SESSION" Enter
    elif on_screen '^ *Yes'; then
        in_tmux send-keys -t "$SESSION" Down
        in_tmux send-keys -t "$SESSION" Enter
    else
        return 1
    fi
}

# Поле ввода — строка «❯» последней из таких на экране, ниже строки ответа.
answered() {
    awk '/^● / { reply = NR } /^❯/ { field = NR }
         END { exit !(reply && field && reply < field) }' "$SCREEN"
}

# Строки журнала Claude Code об отказе принять модуль игры и о его падениях.
module_trouble() {
    [ -f "$DEBUG_LOG" ] || return 0
    grep -E 'refused|threw' "$DEBUG_LOG" | grep 'jedicoder'
}

waited=0
dialogs=0
still=0
previous=""
shown="no"
while [ "$waited" -lt "$WAIT_SECONDS" ]; do
    sleep "$STEP_SECONDS"
    waited=$((waited + STEP_SECONDS))
    shot || cannot "сессия закрылась раньше первого экрана (журнал: $DEBUG_LOG)"

    if on_screen 'Enter to confirm'; then
        dialogs=$((dialogs + 1))
        [ "$dialogs" -le 6 ] || cannot "вопросы на старте не кончаются (экран: $SCREEN)"
        answer_dialog || cannot "незнакомый вопрос на старте (экран: $SCREEN)"
        previous=""
        continue
    fi

    on_screen 'API Error' && cannot "Claude Code не достучался до модели (экран: $SCREEN)"

    # Модель ответила на первую команду: на экране есть её строка («●») и
    # поле ввода. Чем она показала первый экран — решается ниже, в суде.
    if on_screen '^❯ /jedicoder:start' && on_screen '^● ' && answered; then
        current="$(cat "$SCREEN")"
        if [ "$current" = "$previous" ]; then
            still=$((still + 1))
        else
            still=0
        fi
        previous="$current"
        # Экран стоит три замера подряд — ход модели кончился.
        if [ "$still" -ge 3 ]; then
            shown="yes"
            break
        fi
    fi
done

in_tmux kill-server >/dev/null 2>&1

if [ "$shown" != "yes" ]; then
    say "--- последний экран ---"
    grep -v '^ *$' "$SCREEN" 2>/dev/null | tail -n 15
    trouble="$(module_trouble | grep -c '')"
    if [ "$trouble" -gt 0 ]; then
        say "--- журнал Claude Code ---"
        module_trouble | head -n 5 | cut -c 1-240
        say "экран: $SCREEN"
        say "журнал: $DEBUG_LOG"
        say "ЛИЦА НЕТ: первый экран не появился, в журнале Claude Code отказов и падений модуля игры: $trouble"
        exit 1
    fi
    cannot "первый экран игры не появился за $WAIT_SECONDS с (экран: $SCREEN)"
fi

# --- Суд -------------------------------------------------------------------

missing=""
add() {
    if [ -z "$missing" ]; then missing="$1"; else missing="$missing; $1"; fi
}

# а) Полоса стоит с начала строки и не дальше восьми строк над полем ввода;
#    те же слова в ответе модели стоят с отступом и выше.
if awk '/^Что дальше:/ { strip = NR } /^❯/ { field = NR }
        END { exit !(strip && field && strip < field && field - strip <= 8) }' "$SCREEN"; then
    say "полоса: $(grep -e '^Что дальше:' "$SCREEN" | tail -n 1 | sed 's/   .*$//')"
else
    add "полосы «Что дальше:» над полем ввода нет"
fi

# б) Чем показан первый экран: строка вызова инструмента стоит с «●».
if on_screen '^● jedicoder - status (MCP)'; then
    say "первый экран: инструмент игры — jedicoder - status (MCP)"
else
    add "инструмент игры не позван — за первым экраном модель пошла в терминал"
fi

# в) Журнал Claude Code: отказ принять модуль и его падения.
if [ -f "$DEBUG_LOG" ]; then
    trouble="$(module_trouble | grep -c '')"
    if [ "$trouble" -gt 0 ]; then
        say "--- журнал Claude Code ---"
        module_trouble | head -n 5 | cut -c 1-240
        add "в журнале Claude Code отказов и падений модуля игры: $trouble"
    else
        say "журнал: отказов и падений модуля игры нет"
    fi
else
    cannot "Claude Code не написал журнал: $DEBUG_LOG"
fi

if [ "$LEFT_BEFORE" = "no" ] && [ -e "$PLUGIN/tsconfig.json" ]; then
    say "заметка: Claude Code положил в папку плагина tsconfig.json и .claude-plugin/types/ — эту папку не публиковать"
fi
say "экран: $SCREEN"
say "журнал: $DEBUG_LOG"

if [ -n "$missing" ]; then
    say "ЛИЦА НЕТ: $missing"
    exit 1
fi
say "ЛИЦО НА МЕСТЕ"
exit 0

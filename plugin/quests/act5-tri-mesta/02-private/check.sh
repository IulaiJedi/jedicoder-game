#!/usr/bin/env bash
# Акт 5, квест 02: код на GitHub, в закрытом хранилище.
#
# Три строки по шагам — следующая печатается, только когда сошлась
# предыдущая:
#
# 1. `origin` проекта смотрит на хранилище github.com. Владелец и имя берутся
#    из адреса в любой из форм, какие кладут Claude и `gh`:
#    `https://github.com/<владелец>/<имя>(.git)`, тот же адрес с именем или
#    ключом перед `@`, `git@github.com:<владелец>/<имя>(.git)`,
#    `ssh://git@github.com/<владелец>/<имя>(.git)`, ssh через порт 443
#    (`ssh://git@ssh.github.com:443/…`). Локальная папка с `github.com` в пути
#    (долг №16) — не адрес GitHub. Псевдонимы хоста из `~/.ssh/config` не
#    разбираются: адрес с ними для проверки — не GitHub.
# 2. Отправка была: git знает ветку `origin/<текущая ветка>` — она появляется
#    только после удачной отправки (или скачивания).
# 3. Хранилище закрытое. GitHub без входа отвечает на закрытое хранилище тем
#    же, что на несуществующее: 404 (замер 2026-10-16, docs/research). 200 —
#    хранилище открыто всем. Отправка в него уже была (строка 2), значит, оно
#    есть, и 404 говорит «чужим не видно». Код сверяется с телом ответа: 404 —
#    `"message": "Not Found"`, 200 — `"private": false`. Не совпало — отвечал
#    не GitHub (страница входа гостевого Wi-Fi), и это «не смог проверить».
#
# Сеть: `curl -q` — без `~/.curlrc`, где мог лечь ключ входа, — и без
# `--noproxy`: API GitHub внешний адрес, и прокси человека ему нужен (в
# отличие от `localhost` Акта 4). Таймауты обязательны. Нет `curl`, нет сети, GitHub ответил иначе (лимит запросов
# без входа — 60 в час, 403/429; сбой — 5xx) — «не смог проверить», попытка не
# в счёт. Переадресацию (переименованное хранилище) `curl` проходит сам.
#
# Подделка отправки (`git update-ref`) возможна и не преследуется: обман
# игры — обман себя. Адрес и ключ из него не печатаются нигде: в строках —
# только владелец и имя.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — скажи Claude, в какой папке лежит твой проект"
command -v git >/dev/null 2>&1 || jc_bail "не найден git — поставь его и вернись"

# Свой репозиторий в самой папке проекта: папка внутри чужого репозитория
# иначе судилась бы по чужому адресу.
repo_exists() { [ -e .git ] && git rev-parse --git-dir >/dev/null 2>&1; }

OWNER=""
NAME=""

# Разбор адреса `origin` в OWNER и NAME. Ничего не печатает.
parse_origin() {
  local url rest
  repo_exists || return 1
  url=$(git remote get-url origin 2>/dev/null) || return 1
  case "$url" in
    # https://, ssh://, git:// — всё после схемы.
    *://*) rest=${url#*://} ;;
    # Короткая форма ssh: [пользователь@]хост:владелец/имя.
    *:*) rest="${url%%:*}/${url#*:}" ;;
    # Путь к папке на диске — не GitHub, даже если в пути есть github.com.
    *) return 1 ;;
  esac
  # Имя и ключ перед `@` в адресе — срезаются.
  case "${rest%%/*}" in *@*) rest=${rest#*@} ;; esac
  local host=${rest%%/*}
  host=${host%%:*}
  # Регистр хоста — через tr: `${host,,}` нет в bash 3.2 на macOS.
  host=$(printf '%s' "$host" | tr 'A-Z' 'a-z')
  case "$host" in github.com|www.github.com|ssh.github.com) ;; *) return 1 ;; esac
  local path=${rest#*/}
  path=${path%/}
  path=${path%.git}
  local owner=${path%%/*}
  local name=${path#*/}
  [ "$owner" != "$path" ] || return 1
  [[ "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ ]] || return 1
  [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || return 1
  OWNER=$owner
  NAME=$name
}

on_github() { [ -n "$OWNER" ] && [ -n "$NAME" ]; }

# Ветка `origin/<текущая ветка>`; без текущей ветки (отделённый HEAD) —
# любая ветка `origin/*`.
pushed() {
  local branch
  branch=$(git symbolic-ref --short -q HEAD 2>/dev/null)
  if [ -n "$branch" ]; then
    git rev-parse --verify -q "refs/remotes/origin/$branch" >/dev/null 2>&1
    return
  fi
  [ -n "$(git for-each-ref --count=1 refs/remotes/origin 2>/dev/null)" ]
}

# Ответ GitHub без входа: код HTTP — в CODE, тело — в BODY. Без `curl` или
# сети — бейл. Зовётся не в подоболочке: бейл обязан завершить проверку.
CODE=""
BODY=""
ask_github() {
  local response status
  command -v curl >/dev/null 2>&1 \
    || jc_bail "не найден curl — без него игра не спросит GitHub, закрыто ли хранилище"
  response=$(curl -q -sS -L --max-redirs 3 --connect-timeout 10 --max-time 20 \
    -w '\n%{http_code}' \
    -H 'Accept: application/vnd.github+json' -H 'User-Agent: jedicoder-game' \
    "https://api.github.com/repos/${OWNER}/${NAME}" 2>/dev/null)
  status=$?
  CODE=${response##*$'\n'}
  BODY=${response%$'\n'*}
  if [ "$status" -ne 0 ] || [ -z "$CODE" ] || [ "$CODE" = "000" ]; then
    jc_bail "не достучался до GitHub — проверь интернет и VPN и попробуй снова"
  fi
}

# Тело ответа содержит образец (ERE). Читатель дочитывает до конца: pipefail.
body_says() { printf '%s' "$BODY" | grep -c -E "$1" >/dev/null; }

NOT_GITHUB="ответил не GitHub — например, страница входа в сеть Wi-Fi. Открой любой сайт в браузере и попробуй снова"

parse_origin

jc_init "act5/02-private"
jc_check on_github "Проект связан с хранилищем на GitHub" \
  "Скажи Claude: «Помоги создать на GitHub закрытое хранилище для проекта и отправь туда код»." \
  on_github
if on_github; then
  jc_check pushed "Код отправлен в хранилище ${OWNER}/${NAME}" \
    "Скажи Claude: «Отправь код на GitHub»." \
    pushed
  if pushed; then
    ask_github
    case "$CODE" in
      404)
        body_says '"message"[[:space:]]*:[[:space:]]*"Not Found"' || jc_bail "$NOT_GITHUB"
        VISIBLE=no ;;
      200)
        body_says '"private"[[:space:]]*:[[:space:]]*false' || jc_bail "$NOT_GITHUB"
        VISIBLE=yes ;;
      403|429) jc_bail "GitHub попросил подождать: без входа он отвечает не чаще 60 раз в час — попробуй позже" ;;
      *) jc_bail "GitHub ответил непонятно (код ${CODE}) — попробуй позже" ;;
    esac
    jc_check private "Хранилище закрытое: чужие его не видят" \
      "Хранилище открытое — его видят все. Скажи Claude: «Сделай хранилище на GitHub закрытым». Или сам на сайте: Settings → Danger Zone → Change visibility." \
      test "$VISIBLE" = no
  fi
fi
jc_finish

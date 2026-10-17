#!/usr/bin/env bash
# Акт 5, квест 04: чужой сервис по документации, ключ — только в `.env`.
#
# Человек дал Claude ссылку на документацию сервиса, ключ (если он нужен)
# выпустил сам и отдал Claude — тот положил его в `.env`. До проверки идёт
# рассказ: что продукт теперь умеет (acts.WORDS_FIRST, это решает движок).
# Подключился ли сервис, проверка не видит: чужой сервис она не зовёт. Она
# судит то, что от подключения остаётся в папке проекта, — ключ не ушёл ни
# в сохранения, ни на GitHub. Строки по шагам — следующая печатается, только
# когда сошлась предыдущая:
#
# 1. Файл `.env` не попадает в сохранения: закрыт `.gitignore` и не лежит в
#    сохранённых. Строка звучит, только когда в `.env` что-то записано или он
#    уже сохранён: сервис без ключа — законный выбор (спека #123), тогда
#    судится одно — ключей нет нигде.
# 2. Ключей нет в файлах проекта — в тех, что сохраняются или будут
#    сохранены следующим коммитом (`git grep --untracked`: отслеживаемые и
#    новые, кроме закрытых `.gitignore`). Здесь ключ — любая строка формы
#    известного ключа (JC_SECRET_RE в `_lib/secrets.sh`, общий для игры) и
#    значение ключа из `.env`. Подсказка называет файлы — имя файла не
#    секрет; сам ключ — никогда.
# 3. Ключей нет в сохранениях — во всех ветках, метках и копиях веток с
#    GitHub (`git log -p --branches --tags --remotes`): после «Приватного
#    репозитория» всё это лежит и на GitHub. Здесь ключ — только нынешнее
#    значение из `.env`, как в «Работает» Акта 4: старый ключ, отозванный в
#    кабинете сервиса, уже не работает, и переписывать сохранения незачем
#    (решение координатора по ревью #125). Утёк живой — его отзывают и
#    выпускают новый.
#
# Значение из `.env` — ключ, когда оно известной формы (JC_SECRET_RE) или
# когда имя переменной говорит о ключе (KEY, TOKEN, SECRET, PASS, PWD, HASH,
# CREDENTIAL), а в значении не меньше восьми знаков, есть цифра, нет пробела
# и это не адрес (`://`). Значения прочих переменных — адрес API, город,
# порт — не ищутся: Claude часто кладёт их и в `.env.example`, и в код, и это
# не утечка. `TOKEN_URL=https://…/token` — адрес, а не ключ. Без цифры —
# заглушка вида `your_key_here`.
#
# Ничего из `.env` не печатается и не уходит в аргументы команд: значения
# идут поиску через `-f` из потока, а не строкой команды.
#
# Сайт (тип продукта из JEDICODER_PRODUCT_TYPE) — страница без своей
# программы: ключ в ней видит каждый, кто её открыл, и «пусть код берёт ключ
# из .env» ему не выполнить. Сайту подсказка другая: сервис без ключа.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/secrets.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — скажи Claude, в какой папке лежит твой проект"
command -v git >/dev/null 2>&1 || jc_bail "не найден git — поставь его и вернись"

if [ -e .env ] && [ ! -r .env ]; then
  jc_bail "не могу прочитать файл .env — проверь права на файл"
fi

repo_exists() { [ -e .git ] && git rev-parse --git-dir >/dev/null 2>&1; }

# Имя переменной говорит о ключе. Регистр — через tr: `${name^^}` нет в
# bash 3.2 на macOS. Имена переменных — латиница, складывать их безопасно.
secret_name() {
  local upper
  upper=$(printf '%s' "$1" | tr 'a-z' 'A-Z')
  case "$upper" in
    *KEY*|*TOKEN*|*SECRET*|*PASS*|*PWD*|*HASH*|*CREDENTIAL*) return 0 ;;
  esac
  return 1
}

# Значение похоже на ключ, а не на заглушку и не на адрес.
key_like() {
  [ "${#1}" -ge 8 ] || return 1
  case "$1" in *[[:space:]]*|*://*) return 1 ;; esac
  case "$1" in *[0-9]*) return 0 ;; esac
  return 1
}

# Значения ключей из `.env` — в массив KEYS. Ничего не печатает.
# `export ` в начале, кавычки вокруг и комментарий после пробела у значения
# без кавычек — как их понимают библиотеки `.env`.
KEYS=()
ENV_HAS_LINES=no
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line=${line%$'\r'}
    trimmed=${line#"${line%%[![:space:]]*}"}
    case "$trimmed" in ''|'#'*) continue ;; esac
    ENV_HAS_LINES=yes
    trimmed=${trimmed#export }
    case "$trimmed" in *=*) ;; *) continue ;; esac
    name=${trimmed%%=*}
    name=${name%"${name##*[![:space:]]}"}
    value=${trimmed#*=}
    value=${value#"${value%%[![:space:]]*}"}
    case "$value" in
      \"*\"*) value=${value#\"}; value=${value%%\"*} ;;
      \'*\'*) value=${value#\'}; value=${value%%\'*} ;;
      *) value=${value%% \#*}; value=${value%%$'\t'\#*}
         value=${value%"${value##*[![:space:]]}"} ;;
    esac
    [ -n "$value" ] || continue
    if printf '%s\n' "$value" | grep -c -E "$JC_SECRET_RE" >/dev/null; then
      KEYS+=("$value")
    elif secret_name "$name" && key_like "$value"; then
      KEYS+=("$value")
    fi
  done < .env
fi
unset line trimmed name value

# Внутри `bash -c`: pipefail туда не наследуется, и `grep -q` не рвёт конвейер.
env_tracked() { bash -c 'git ls-files 2>/dev/null | grep -qE "(^|/)\.env$"'; }
env_ignored() { git check-ignore -q --no-index .env 2>/dev/null; }
env_not_saved() { env_ignored && ! env_tracked; }

# Строка о `.env` звучит, когда в нём что-то есть или он уже сохранён.
env_matters() { [ "$ENV_HAS_LINES" = yes ] || env_tracked; }

SAVED_HINT="Попроси Claude: «Закрой .env от сохранений — допиши его в .gitignore»."
if repo_exists && env_tracked; then
  if env_ignored; then
    SAVED_HINT="Файл .env уже в сохранениях. Попроси Claude: «Убери .env из сохранений, сам файл оставь»."
  else
    SAVED_HINT="Файл .env уже в сохранениях. Попроси Claude: «Убери .env из сохранений и допиши его в .gitignore»."
  fi
fi

# Файлы, где лежат ключи, — среди тех, что сохраняются или будут сохранены.
# Ответ — имена файлов, по одному в строке, в LEAKED. Код `git grep`: 0 —
# нашлось, 1 — нет, другое — git не смог искать.
LEAKED=""
search_files() {
  local found status
  found=$(git -c core.quotePath=false grep -l -I --untracked -E -e "$JC_SECRET_RE" -- . 2>/dev/null)
  status=$?
  [ "$status" -le 1 ] || jc_bail "git не смог просмотреть файлы проекта"
  LEAKED=$found
  [ "${#KEYS[@]}" -gt 0 ] || return 0
  # Код — самого `git grep`, а не конвейера: под pipefail тот назвал бы
  # код писателя, если бы git закончил раньше, чем дочитал образцы.
  found=$(printf '%s\n' "${KEYS[@]}" \
    | git -c core.quotePath=false grep -l -I --untracked -F -f - -- . 2>/dev/null; \
    exit "${PIPESTATUS[1]}")
  status=$?
  [ "$status" -le 1 ] || jc_bail "git не смог просмотреть файлы проекта"
  LEAKED=$(printf '%s\n%s\n' "$LEAKED" "$found" | awk 'NF && !seen[$0]++')
}
no_keys_in_files() { [ -z "$LEAKED" ]; }

# Не больше трёх имён через запятую; остальные — числом.
leaked_names() {
  printf '%s\n' "$LEAKED" | awk '
    NF { n++; if (n <= 3) names = names (n > 1 ? ", " : "") $0 }
    END { if (n > 3) names = names " и ещё " (n - 3); print names }'
}

# Нынешние ключи из `.env` во всей истории — один проход. Читатель
# дочитывает до конца (`grep -c`): под pipefail `grep -q` рвал бы конвейер.
# Значения — через `-f` из потока процесса, не строкой команды.
no_keys_in_saves() {
  [ "${#KEYS[@]}" -gt 0 ] || return 0
  ! git log -p --branches --tags --remotes --no-color 2>/dev/null \
    | grep -c -F -f <(printf '%s\n' "${KEYS[@]}") >/dev/null
}

jc_init "act5/04-service"
if ! repo_exists; then
  jc_check repo_exists "В папке проекта заведён git — он хранит сохранения" \
    "Попроси Claude завести git в папке проекта и закрыть в нём .env от сохранений." \
    repo_exists
  jc_finish
fi
if env_matters; then
  jc_check env_not_saved "Файл .env не попадает в сохранения и на GitHub" \
    "$SAVED_HINT" \
    env_not_saved
  env_not_saved || jc_finish
fi
search_files
FILES_HINT=""
if ! no_keys_in_files; then
  WHERE=$(leaked_names)
  if [ "${JEDICODER_PRODUCT_TYPE:-}" = site ]; then
    FILES_HINT="Ключ лежит здесь: ${WHERE}. Страницу видит каждый, кто её открыл. Скажи Claude: «Подключи сервис без ключа». Не знаешь, как быть, — позови Магистра: /jedicoder:magistr."
  else
    FILES_HINT="Ключ лежит здесь: ${WHERE}. Попроси Claude: «Убери ключ из кода — пусть код берёт его из .env»."
  fi
fi
jc_check no_keys_in_files "Ключей нет в коде и в других файлах" \
  "$FILES_HINT" \
  no_keys_in_files
if no_keys_in_files; then
  jc_check no_keys_in_saves "Ключей нет в сохранениях" \
    "Ключ из .env попал в сохранения — а с ними и на GitHub. Выпусти в кабинете сервиса новый ключ, старый удали. Новый положи в .env — переписывать сохранения не нужно." \
    no_keys_in_saves
fi
jc_finish

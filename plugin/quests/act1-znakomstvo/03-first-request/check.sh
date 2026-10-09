#!/usr/bin/env bash
# Акт 1, квест 03: в папке появилась первая версия, а не только заметки.
#
# До этой проверки движок ждёт слов человека (acts.WORDS_FIRST): он открыл
# то, что получилось, и рассказал, что увидел. Скрипт судит только файлы.
#
# Признак честный и грубый: хотя бы один непустой файл, который не заметка
# (`.md`, `.txt`), не картинка и не служебный (скрытые файлы и папки, LICENSE,
# README, `desktop.ini` и `Thumbs.db` — их Windows кладёт в папку сама).
# Работает ли код, скрипт не судит — это человек видит глазами и говорит сам.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — сначала закрой квест «Папка»"
command -v find >/dev/null 2>&1 \
  || jc_bail "не найдена команда find — без неё папку не осмотреть"
if [ ! -r . ] || [ ! -x . ]; then
  jc_bail "не могу прочитать папку проекта — проверь права на неё"
fi

# Скрытое (`.git`, `.claude`, `.env`) и папки чужого кода отсекаются целиком:
# это не то, что сделал падаван, а в `node_modules` файлов тысячи. Регистр
# расширений — классами: `-iname` в POSIX нет. Счёт через `wc -l`, а не
# ранний выход: читатель конвейера под pipefail обязан дочитать до конца.
has_code() {
  local count
  count=$(find . \
      \( -name '.?*' -o -name node_modules -o -name venv -o -name __pycache__ \) -prune \
      -o -type f -size +0c \
      ! -name '*.[Mm][Dd]' ! -name '*.[Mm][Aa][Rr][Kk][Dd][Oo][Ww][Nn]' \
      ! -name '*.[Tt][Xx][Tt]' ! -name '*.[Pp][Dd][Ff]' \
      ! -name '*.[Pp][Nn][Gg]' ! -name '*.[Jj][Pp][Gg]' ! -name '*.[Jj][Pp][Ee][Gg]' \
      ! -name '*.[Gg][Ii][Ff]' ! -name '*.[Ww][Ee][Bb][Pp]' ! -name '*.[Ii][Cc][Oo]' \
      ! -name '[Dd]esktop.ini' ! -name '[Tt]humbs.db' \
      ! -name 'LICENSE*' ! -name 'LICENCE*' ! -name 'README*' \
      -print 2>/dev/null | wc -l)
  [ "$count" -ge 1 ]
}

jc_init "act1/03-first-request"
jc_check has_code "В папке есть первая версия: файл страницы или программы" \
  "Пока в папке только заметки. Попроси Claude сделать первую версию." \
  has_code
jc_finish

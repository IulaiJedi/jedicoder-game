#!/usr/bin/env bash
# Акт 3, квест 01: проект поднят локально и отвечает на именованном порту.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

# Порт называет падаван (project port <N>). Перебор запрещён: на машине
# может слушать что угодно, ложное срабатывание закрыло бы непройденный
# квест.
[ -n "${JEDICODER_PORT:-}" ] || \
  jc_bail "Не назван порт проекта. Скажи игре: project port <номер>"

command -v curl >/dev/null 2>&1 || \
  jc_bail "Для этой проверки нужен curl — поставь его и повтори"

jc_init "act3/01-launch"
jc_check server_responds \
  "Проект отвечает на http://localhost:${JEDICODER_PORT}" \
  "Подними проект локально и повтори проверку" \
  curl -sf --max-time 10 -o /dev/null "http://localhost:${JEDICODER_PORT}"
jc_finish

#!/usr/bin/env bash
# Акт 3, квест 05: DECISIONS.md — журнал, который вёлся, а не создан разом.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

DATE_RE='^##[[:space:]]+20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]'

enough_entries() {
  awk -v re="$DATE_RE" '$0 ~ re {n++} END {exit (n >= 2) ? 0 : 1}' DECISIONS.md
}

distinct_days() {
  awk -v re="$DATE_RE" '$0 ~ re {d[$2] = 1}
       END {n = 0; for (k in d) n++; exit (n >= 2) ? 0 : 1}' DECISIONS.md
}

jc_init "act3/05-decisions"
jc_check decisions_exists "DECISIONS.md есть и непустой" \
  "Заведи DECISIONS.md — журнал решений: что выбрали, почему, что отвергли" \
  test -s DECISIONS.md
jc_check decisions_entries "В журнале не меньше двух записей «## ГГГГ-ММ-ДД …»" \
  "Каждая запись — заголовок «## 2026-07-27 — что решили» и абзац почему" \
  enough_entries
jc_check decisions_dates "Записи сделаны минимум в два разных дня" \
  "Журнал ведут по ходу работы — вернись к нему завтра с новым решением" \
  distinct_days
jc_finish

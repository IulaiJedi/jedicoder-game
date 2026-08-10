#!/usr/bin/env bash
# Акт 1, квест 02: правило одного вечера — идея урезана до вертикального слайса.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/md.sh"

FILE=research/SLICE.md

jc_init "act1/02-one-evening"

jc_check slice_exists "research/SLICE.md есть и непустой" \
  "Создай research/SLICE.md и опиши срез, который шипится за один вечер" \
  test -s "$FILE"
jc_check slice_in "Раздел «## Войдёт» заполнен" \
  "Добавь раздел ## Войдёт — что именно попадёт в первую версию" \
  jc_section_words "$FILE" '[Вв]ойдёт' 8
jc_check slice_cut "Раздел «## Отрезано» заполнен" \
  "Добавь раздел ## Отрезано. Фильтр, который ничего не отрезал, не сработал" \
  jc_section_words "$FILE" '[Оо]трезано' 8
jc_check slice_estimate "В разделе «## Оценка» назван срок" \
  "Добавь раздел ## Оценка и назови срок — часы или «один вечер»" \
  jc_section_matches "$FILE" '[Оо]ценка' '[0-9]|вечер'
jc_finish

#!/usr/bin/env bash
# Акт 1, квест 01: идея сформулирована по формуле «боль → для кого → почему сейчас».
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/md.sh"

FILE=research/IDEA.md

jc_init "act1/01-idea"

jc_check idea_exists "research/IDEA.md есть и непустой" \
  "Создай research/IDEA.md — в следующем квесте резать будет нечего" \
  test -s "$FILE"
jc_check idea_pain "Раздел «## Боль» заполнен" \
  "Добавь раздел ## Боль и опиши, что именно бесит — своими словами, не одним словом" \
  jc_section_words "$FILE" '[Бб]оль' 8
jc_check idea_who "Раздел «## Для кого» заполнен" \
  "Добавь раздел ## Для кого — у кого эта боль есть кроме тебя" \
  jc_section_words "$FILE" '[Дд]ля кого' 8
jc_check idea_why_now "Раздел «## Почему сейчас» заполнен" \
  "Добавь раздел ## Почему сейчас — что изменилось, из-за чего это стало возможно" \
  jc_section_words "$FILE" '[Пп]очему сейчас' 8
jc_finish

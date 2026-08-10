#!/usr/bin/env bash
# Акт 1, квест 06f (трек Основатель): юнитка — три числа.
# Стоимость токенов и инфраструктуры обязательна: ИИ-приложение, где каждый
# запрос стоит денег, при сотне пользователей съедает API-счётом всю выручку.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/md.sh"

FILE=research/UNIT.md

jc_init "act1/06f-unit"

jc_check unit_exists "research/UNIT.md есть и непустой" \
  "Создай research/UNIT.md и посчитай три числа: CAC, LTV, стоимость токенов" \
  test -s "$FILE"
jc_check unit_cac "В разделе «## CAC» есть число" \
  "Добавь раздел ## CAC — сколько стоит привести одного пользователя" \
  jc_section_matches "$FILE" 'CAC' '[0-9]'
jc_check unit_ltv "В разделе «## LTV» есть число" \
  "Добавь раздел ## LTV — сколько он приносит за всё время" \
  jc_section_matches "$FILE" 'LTV' '[0-9]'
jc_check unit_tokens "В разделе «## Стоимость токенов» есть число" \
  "Добавь раздел ## Стоимость токенов — сколько стоит один пользователь в месяц по API и инфраструктуре" \
  jc_section_matches "$FILE" '[Сс]тоимость токенов' '[0-9]'
jc_finish

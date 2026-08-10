#!/usr/bin/env bash
# Акт 1, квест 03f (трек Основатель): TAM / SAM / SOM.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/md.sh"

FILE=research/MARKET.md

jc_init "act1/03f-market"

jc_check market_exists "research/MARKET.md есть и непустой" \
  "Создай research/MARKET.md и оцени TAM, SAM и SOM" \
  test -s "$FILE"
jc_check market_numbers "В оценке не меньше трёх чисел" \
  "Назови три величины числами: весь рынок, доступная часть, реальная доля" \
  jc_min_matches 3 '[0-9]+' "$FILE"
jc_check market_substance "Оценка объяснена, а не только посчитана" \
  "Напиши, откуда взяты числа — оценка без объяснения не проверяется и не спорится" \
  jc_file_words "$FILE" 30
jc_finish

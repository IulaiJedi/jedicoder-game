#!/usr/bin/env bash
# Акт 1, квест 03c (трек Ремесленник): для кого именно и как часто.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/md.sh"

FILE=research/WHO.md

# Регистр первой буквы задан классом: grep -i не складывает кириллицу
# предсказуемо во всех локалях.
FREQ='[Кк]ажд(ый|ое|ую) (день|утро|вечер|неделю)|[Ее]жеднев|[Ее]женедель'
FREQ="$FREQ"'|[Рр]аз в (день|неделю)|[Нн]есколько раз в|[Пп]остоянно|[Рр]егулярно'

jc_init "act1/03c-who"

jc_check who_exists "research/WHO.md есть и непустой" \
  "Создай research/WHO.md и напиши, для кого это: ты, семья или работа" \
  test -s "$FILE"
jc_check who_frequency "Назван измеримый критерий использования" \
  "Напиши, как часто ты этим пользуешься — например «каждый день» или «раз в неделю»" \
  grep -qE "$FREQ" "$FILE"
jc_finish

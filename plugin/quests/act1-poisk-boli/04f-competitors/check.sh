#!/usr/bin/env bash
# Акт 1, квест 04f (трек Основатель): конкуренты и их продукты.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/md.sh"

FILE=research/COMPETITORS.md

jc_init "act1/04f-competitors"

jc_check competitors_exists "research/COMPETITORS.md есть и непустой" \
  "Создай research/COMPETITORS.md и выпиши тех, кто уже решает эту боль" \
  test -s "$FILE"
jc_check competitors_urls "Не меньше трёх разных ссылок" \
  "Дай ссылку на каждого конкурента. Три раза одна ссылка — это один конкурент" \
  jc_min_urls 3 "$FILE"
jc_finish

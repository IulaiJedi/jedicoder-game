#!/usr/bin/env bash
# Акт 1, квест 05f (трек Основатель): портрет идеального клиента.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/md.sh"

FILE=research/ICP.md

jc_init "act1/05f-icp"

jc_check icp_exists "research/ICP.md есть и непустой" \
  "Создай research/ICP.md и опиши одного конкретного человека, а не сегмент" \
  test -s "$FILE"
jc_check icp_depth "Портрет описан подробно, не одной строкой" \
  "Опиши подробнее: кто он, что у него болит, где его искать, готов ли платить" \
  jc_file_words "$FILE" 60
jc_finish

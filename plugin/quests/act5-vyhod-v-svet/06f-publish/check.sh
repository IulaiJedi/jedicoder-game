#!/usr/bin/env bash
# Акт 5, квест 06 (Основатель): публикация в канале из Акта 1 — самоотчёт
# со ссылкой, как и задумано мастер-спекой. Ссылку валидирует ручка
# project post; здесь фиксируется факт «ссылка названа» — она нужна боту
# потока (демо-день). Обман ссылкой — обман себя.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_POST_URL:-}" ] || \
  jc_bail "Не названа ссылка на публикацию. Опубликуй продукт в своём канале из Акта 1 и скажи игре: project post <ссылка>"

jc_init "act5/06f-publish"
jc_check post_named "Ссылка на публикацию записана: ${JEDICODER_POST_URL}" \
  "Назови ссылку: project post <ссылка>" \
  test -n "$JEDICODER_POST_URL"
jc_finish

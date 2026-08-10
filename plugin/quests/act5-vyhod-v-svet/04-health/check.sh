#!/usr/bin/env bash
# Акт 5, квест 04: у продукта есть эндпоинт здоровья.
#
# Путь фиксированный — /health: квест учит его завести, а не настроить
# игру под то, что уже есть. JEDICODER_URL приходит без хвостового /
# (нормализует _env_for).
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_URL:-}" ] || \
  jc_bail "Не назван URL продукта. Скажи игре: project url <https://адрес>"
command -v curl >/dev/null 2>&1 || \
  jc_bail "Для этой проверки нужен curl — поставь его и повтори"

jc_init "act5/04-health"
jc_check health_alive "Эндпоинт ${JEDICODER_URL}/health отвечает" \
  "Заведи в приложении маршрут /health, который отвечает 200, и задеплой" \
  curl -sf --max-time 15 -o /dev/null "${JEDICODER_URL}/health"
jc_finish

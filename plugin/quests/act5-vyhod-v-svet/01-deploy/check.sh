#!/usr/bin/env bash
# Акт 5, квест 01: продукт задеплоен и отвечает; на vps — переживёт reboot.
#
# Перезапуск после reboot проверяется только на vps: managed-платформа
# поднимает сервис сама. Это рантайм-ветка по пути деплоя, не ось реестра —
# оси у акта не бывает две (ось Акта 5 — трек, квест 06).
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_URL:-}" ] || \
  jc_bail "Не назван URL продукта. Скажи игре: project url <https://адрес>"
command -v curl >/dev/null 2>&1 || \
  jc_bail "Для этой проверки нужен curl — поставь его и повтори"
if [ "${JEDICODER_DEPLOY_PATH:-}" = "vps" ]; then
  [ -n "${JEDICODER_SSH_ALIAS:-}" ] || \
    jc_bail "Не назван ssh-алиас сервера. Скажи игре: project ssh <алиас>"
  [ -n "${JEDICODER_SERVICE:-}" ] || \
    jc_bail "Не назван systemd-юнит сервиса. Скажи игре: project service <юнит>"
  command -v ssh >/dev/null 2>&1 || \
    jc_bail "Для vps-проверки нужен ssh — поставь openssh-client и повтори"
fi

jc_init "act5/01-deploy"
jc_check alive "Продукт отвечает: ${JEDICODER_URL}" \
  "Задеплой по своему пути (артефакт /deploy) и повтори" \
  curl -sf --max-time 15 -o /dev/null "$JEDICODER_URL"
if [ "${JEDICODER_DEPLOY_PATH:-}" = "vps" ]; then
  jc_check reboot_proof "Сервис в автозапуске — переживёт reboot" \
    "На сервере: sudo systemctl enable ${JEDICODER_SERVICE:-<юнит>}" \
    ssh -o BatchMode=yes -o ConnectTimeout=10 "$JEDICODER_SSH_ALIAS" \
      "systemctl is-enabled --quiet $JEDICODER_SERVICE"
fi
jc_finish

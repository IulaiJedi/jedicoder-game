#!/usr/bin/env bash
# Акт 4, квест 03 (vps): вход на сервер по ключу, работа не под root.
#
# BatchMode запрещает интерактивные пароли: пройти проверку может только
# ключ. Провал соединения — провал квеста, а не «не смог проверить»:
# настроить ключ и алиас — ровно то, чему квест учит. Хост берётся по
# алиасу из ~/.ssh/config, который падаван завёл сам.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_SSH_ALIAS:-}" ] || \
  jc_bail "Не назван ssh-алиас сервера. Скажи игре: project ssh <алиас>"
command -v ssh >/dev/null 2>&1 || \
  jc_bail "Для этой проверки нужен ssh — поставь openssh-client и повтори"

remote_user=$(ssh -o BatchMode=yes -o ConnectTimeout=10 \
  "$JEDICODER_SSH_ALIAS" whoami 2>/dev/null || true)

jc_init "act4/03v-user"
jc_check key_login "Вход по ключу через алиас работает" \
  "Заведи алиас в ~/.ssh/config (Host, HostName, User) и положи ключ: ssh-copy-id <алиас>" \
  test -n "$remote_user"
jc_check not_root "На сервере ты не root" \
  "Создай отдельного пользователя (adduser <имя>), дай ему ключ и ходи под ним" \
  bash -c '[ -n "$1" ] && [ "$1" != "root" ]' _ "$remote_user"
jc_finish

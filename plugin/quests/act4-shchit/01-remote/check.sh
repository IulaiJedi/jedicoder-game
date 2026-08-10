#!/usr/bin/env bash
# Акт 4, квест 01: проект на GitHub — origin указывает туда, пуш состоялся.
#
# Без gh намеренно: он потребовал бы установки и отдельной авторизации на
# машине новичка, а нужен только факт «репо на GitHub и запушено». Его
# чистый git даёт офлайн: remote-tracking ref появляется только после
# успешного push (или fetch). Подделка update-ref'ом возможна и не
# преследуется: обман игры — обман себя.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

command -v git >/dev/null 2>&1 || jc_bail "не найден git — поставь его и вернись"
git rev-parse --git-dir >/dev/null 2>&1 \
  || jc_bail "это не git-репозиторий — сначала пройди Акт 2"

jc_init "act4/01-remote"
jc_check origin_github "origin указывает на GitHub" \
  "Создай репозиторий на github.com и подключи: git remote add origin <url>" \
  bash -c 'git remote get-url origin 2>/dev/null | grep -cE "github\.com" >/dev/null'
jc_check pushed "Пуш состоялся — git знает удалённую ветку" \
  "Отправь код: git push -u origin main (или master — как называется твоя ветка)" \
  bash -c '[ -n "$(git for-each-ref refs/remotes)" ]'
jc_finish

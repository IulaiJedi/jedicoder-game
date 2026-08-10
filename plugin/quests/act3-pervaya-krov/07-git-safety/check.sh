#!/usr/bin/env bash
# Акт 3, квест 07: падаван умеет откатываться — есть revert-коммит.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

# git пишет «Revert …» в ЗАГОЛОВОК сам; ищем только по заголовкам —
# «Revert» в теле обычного коммита не должен закрывать квест (см. 03-break).
has_revert() {
  [ "$(git log --format=%s 2>/dev/null | grep -c '^Revert')" -ge 1 ]
}

jc_init "act3/07-git-safety"
jc_check revert_commit "В истории есть revert-коммит" \
  "Найди неудачный коммит через git log и откати его: git revert <хэш>" \
  has_revert
jc_finish

#!/usr/bin/env bash
# Акт 3, квест 02: первая фича сделана и история коммитов растёт.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

enough_commits() {
  [ "$(git rev-list --count HEAD 2>/dev/null || echo 0)" -ge 5 ]
}

jc_init "act3/02-feature"
jc_check enough_commits "В истории не меньше пяти коммитов" \
  "Сделай фичу и коммить шаги работы по ходу, а не одним куском в конце" \
  enough_commits
jc_finish

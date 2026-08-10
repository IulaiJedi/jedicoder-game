#!/usr/bin/env bash
# Акт 2, квест 04: репозиторий инициализирован и есть первая точка сохранения.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

command -v git >/dev/null 2>&1 || jc_bail "не найден git — поставь его и вернись"

jc_init "act2/04-git-init"
jc_check repo_exists "Репозиторий инициализирован" \
  "Запусти в папке проекта: git init" \
  git rev-parse --git-dir
jc_check has_commit "Есть хотя бы один коммит" \
  "Сохранись: git add -A && git commit -m 'первый коммит'" \
  bash -c '[ "$(git rev-list --count HEAD 2>/dev/null || echo 0)" -ge 1 ]'
jc_finish

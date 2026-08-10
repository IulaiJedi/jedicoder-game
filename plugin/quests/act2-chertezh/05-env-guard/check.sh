#!/usr/bin/env bash
# Акт 2, квест 05: секреты защищены — .env игнорируется, в индексе его нет,
# и в истории нет строк, похожих на ключи.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/secrets.sh"

command -v git >/dev/null 2>&1 || jc_bail "не найден git — поставь его и вернись"
git rev-parse --git-dir >/dev/null 2>&1 \
  || jc_bail "это не git-репозиторий — сначала закрой квест 04-git-init"

jc_init "act2/05-env-guard"
jc_check gitignore_exists ".gitignore есть и непустой" \
  "Создай .gitignore в корне проекта" \
  test -s .gitignore
jc_check env_ignored "Git действительно игнорирует .env" \
  "Добавь в .gitignore отдельную строку: .env" \
  git check-ignore -q .env
jc_check env_not_tracked ".env не лежит в индексе git" \
  "Убери его из индекса: git rm --cached .env, потом закоммить" \
  bash -c '! git ls-files | grep -qE "(^|/)\.env$"'
jc_check no_secrets_in_history "В истории нет строк, похожих на ключи" \
  "Ключ попал в историю. Сначала смени сам ключ, потом спроси /magistr про чистку истории" \
  bash -c "! git log -p --all 2>/dev/null | grep -qE '$JC_SECRET_RE'"
jc_finish

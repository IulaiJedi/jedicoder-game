#!/usr/bin/env bash
# Акт 4, квест 03 (managed): перед жизнью на GitHub секретов нет ни в
# индексе, ни в истории.
#
# Да, это повтор проверки 05-env-guard Акта 2 — в новый момент времени:
# с тех пор шла настоящая разработка, и утечь могло что угодно. Щит
# применяется к тому, что есть.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/secrets.sh"

command -v git >/dev/null 2>&1 || jc_bail "не найден git — поставь его и вернись"
git rev-parse --git-dir >/dev/null 2>&1 \
  || jc_bail "это не git-репозиторий — сначала пройди Акт 2"

jc_init "act4/03m-secrets"
jc_check env_not_tracked ".env не лежит в индексе git" \
  "Убери его из индекса: git rm --cached .env, потом закоммить" \
  bash -c '! git ls-files | grep -qE "(^|/)\.env$"'
jc_check no_secrets_in_history "В истории нет строк, похожих на ключи" \
  "Ключ в истории увидит каждый, у кого есть доступ к репо. Сначала отзови и перевыпусти сам ключ, потом чисти историю" \
  bash -c "! git log -p --all 2>/dev/null | grep -qE '$JC_SECRET_RE'"
jc_finish

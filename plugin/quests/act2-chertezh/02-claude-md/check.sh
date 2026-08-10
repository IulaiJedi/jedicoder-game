#!/usr/bin/env bash
# Акт 2, квест 02: у проекта есть CLAUDE.md — внешняя память для ИИ.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

jc_init "act2/02-claude-md"
jc_check claude_md_exists "CLAUDE.md есть и непустой" \
  "Создай в корне проекта CLAUDE.md — это то, что ИИ прочитает первым" \
  test -s CLAUDE.md
# Порог в байтах: wc -c считает байты, а не символы (см. 01-recipe).
jc_check claude_md_substantial "CLAUDE.md не заглушка (от 300 байт)" \
  "Опиши: что делает проект, из чего состоит, как его запустить" \
  bash -c '[ "$(wc -c < CLAUDE.md 2>/dev/null || echo 0)" -ge 300 ]'
jc_finish

#!/usr/bin/env bash
# Акт 3, босс: знание пережило смену чата — внешняя память дописана.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

# Пустой прежний sha означает «файла не было»: существующий файл — уже
# перенос знания. Хэш — git hash-object, тот же, что пишет CLI при
# закрытии акта.
claude_md_grew() {
  [ -f CLAUDE.md ] || return 1
  [ -z "${JEDICODER_PREV_CLAUDE_MD_SHA:-}" ] && return 0
  [ "$(git hash-object CLAUDE.md 2>/dev/null)" != "$JEDICODER_PREV_CLAUDE_MD_SHA" ]
}

jc_init "act3/10-boss"
jc_check claude_md_exists "CLAUDE.md есть и непустой" \
  "Заведи CLAUDE.md — внешнюю память проекта: что это, как запустить, что решили" \
  test -s CLAUDE.md
jc_check claude_md_grew "CLAUDE.md дописан со времён Акта 2" \
  "Перенеси в CLAUDE.md то, что ИИ должен знать о проекте, начни новый чат и продолжи там" \
  claude_md_grew
jc_finish

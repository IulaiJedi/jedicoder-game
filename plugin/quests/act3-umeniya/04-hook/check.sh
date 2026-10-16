#!/usr/bin/env bash
# Акт 3, квест 04: хук на слово «чистка».
#
# Человек просит Claude сделать хук: по слову «чистка» в запросе Claude сам
# записывает передачу в HANDOFF.md и напоминает набрать /clear. Сам хук
# /clear не выполняет: Claude Code этого хукам не даёт.
#
# Замер 2026-10-13 (docs/research/2026-10-13-act3-skills-hooks-mods.md,
# «Замеры #110», пункт (з)): Claude пишет скрипт и запись
# `hooks.UserPromptSubmit` в <папка проекта>/.claude/settings.json; хук
# срабатывает на следующем же запросе, модель пишет HANDOFF.md в папку
# проекта. Вывода чужого хука игра не видит — только запрос человека.
#
# Три строки, каждая следующая — только когда сошлась предыдущая: человеку
# одна подсказка на шаг, а не три разом.
#   хук записан        — настройки проекта или пользователя (_lib/machine.sh);
#   слово сказано      — след hook_word (ADR-0020): хук игры видел в игровой
#                        сессии запрос со словом «чистка», когда хук уже был
#                        записан. Приходит от команды игры переменной
#                        JEDICODER_TRACE_HOOK_WORD, ровно `yes`;
#   передача записана  — HANDOFF.md в папке проекта изменён не раньше момента
#                        этого запроса (JEDICODER_TRACE_HOOK_WORD_AT, секунды
#                        эпохи): признак, что хук отработал.
# Следа нет — провал с подсказкой повторить слово, а не «не смог проверить».
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/machine.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — скажи Claude, в какой папке лежит твой проект"
jc_machine_guard

# До строк отчёта: «не смог проверить» обрывает проверку целиком.
jc_prompt_hook_recorded
RECORDED=$?

SAID="${JEDICODER_TRACE_HOOK_WORD:-}"
AT="${JEDICODER_TRACE_HOOK_WORD_AT:-}"
case "$AT" in ''|*[!0-9]*) AT="" ;; esac

hook_recorded() { [ "$RECORDED" -eq 0 ]; }
word_said()     { [ "$SAID" = "yes" ]; }

# Время изменения файла — через python3: у `stat` на Linux и macOS разные
# ключи.
handoff_after_word() {
  word_said || return 1
  [ -n "$AT" ] || return 1
  [ -f HANDOFF.md ] || return 1
  python3 -c '
import os
import sys

try:
    changed = os.path.getmtime("HANDOFF.md")
except OSError:
    sys.exit(1)
sys.exit(0 if changed >= int(sys.argv[1]) else 1)
' "$AT"
}

jc_init "act3/04-hook"
jc_check hook_recorded "Хук записан в настройках Claude Code" \
  "Скажи Claude: «Сделай хук: когда я пишу слово „чистка“ — запиши передачу и напомни набрать /clear»." \
  hook_recorded
if hook_recorded; then
  jc_check word_said "Слово «чистка» сказано, когда хук уже был" \
    "Набери одно слово: «чистка». Claude должен сам записать передачу." \
    word_said
  if word_said; then
    jc_check handoff_after_word "После слова записана передача" \
      "Слово сказано, а передачи после него нет. Попроси Claude найти, почему хук не сработал, и набери «чистка» снова." \
      handoff_after_word
  fi
fi
jc_finish

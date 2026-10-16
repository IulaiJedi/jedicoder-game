#!/usr/bin/env bash
# Акт 3, квест 03: свой скилл.
#
# Человек диктует Claude одно своё правило работы, Claude делает из него
# скилл. Замер 2026-10-13 (docs/research/2026-10-13-act3-skills-hooks-mods.md,
# «Замеры #110», пункт (ж)): Claude кладёт файл
#   <папка проекта>/.claude/skills/<имя латиницей>/SKILL.md
# с блоком `---` (поля `name` и `description`) и правилом под ним.
#
# Свой — значит не из готовых, которые игра называет примерами в квесте «Где
# брать» (JC_KNOWN_SKILLS в _lib/machine.sh): игра их не ставит, но человек
# мог поставить их сам. Скилл в папке проекта принимается любой; личный, в
# домашней папке, — только изменённый не раньше входа в акт
# (JEDICODER_ACT_STARTED от команды игры): иначе квест закрывал бы скилл,
# поставленный до игры.
#
# Судится наличие описания и текста под ним, а не смысл правила.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/machine.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — скажи Claude, в какой папке лежит твой проект"
jc_machine_guard

# Момент входа нужен только личным скиллам. Его нет или он не число —
# судится одна папка проекта: это не повод отказывать в проверке.
STARTED="${JEDICODER_ACT_STARTED:-}"
case "$STARTED" in *[!0-9]*) STARTED="" ;; esac

# Исход считается один раз, до строк отчёта.
VERDICT=$(jc_own_skill "$STARTED") || exit 2

skill_exists()    { [ "$VERDICT" != "none" ]; }
skill_described() { [ "$VERDICT" = "no-body" ] || [ "$VERDICT" = "ok" ]; }
skill_written()   { [ "$VERDICT" = "ok" ]; }

jc_init "act3/03-own-skill"
jc_check own_skill_exists "В папке проекта лежит твой скилл" \
  "Назови Claude одно своё правило и скажи: «Сделай из этого правила скилл для этого проекта»." \
  skill_exists
# Скилла нет — человеку одна строка и одна подсказка: описание и правило
# ему пока не у чего дописывать.
if skill_exists; then
  jc_check own_skill_described "У скилла есть описание: когда его применять" \
    "Попроси Claude дописать в скилл описание: когда его применять." \
    skill_described
  jc_check own_skill_written "В скилле записано само правило" \
    "Попроси Claude записать в скилл само правило: что делать." \
    skill_written
fi
jc_finish

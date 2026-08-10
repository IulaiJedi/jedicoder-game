#!/usr/bin/env bash
# Акт 3, квест 08: свой скилл верификации — первый шаг loop-инжиниринга.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

# Порог в байтах, как у заглушек Акта 2: кириллица — два байта на символ.
has_skill_file() {
  local f
  for f in .claude/skills/*/SKILL.md; do
    [ -f "$f" ] && [ "$(wc -c < "$f")" -ge 200 ] && return 0
  done
  return 1
}

jc_init "act3/08-skill"
jc_check skill_exists "В проекте есть свой скилл: .claude/skills/*/SKILL.md" \
  "Запиши в SKILL.md проверку, которую делал руками, — чтобы ИИ гонял её сам" \
  has_skill_file
jc_finish

#!/usr/bin/env bash
# Акт 1, квест 02: идея на вечер — в IDEA.md названо, что делается сегодня,
# и хотя бы одно отложено. Пустое «Не сегодня» значит, что ничего не отрезано.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/md.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — сначала закрой квест «Папка»"

FILE=IDEA.md

if [ -e "$FILE" ] && [ ! -r "$FILE" ]; then
  jc_bail "не могу прочитать IDEA.md — проверь права на файл"
fi

jc_init "act1/02-idea"
jc_check idea_exists "Идея записана в заметку IDEA.md в папке проекта" \
  "Попроси Claude записать идею в заметку IDEA.md прямо в папке проекта." \
  test -s "$FILE"
jc_check idea_today "Записано, что делаешь сегодня и для кого" \
  "Скажи Claude, что делаешь сегодня и для кого. Он запишет в раздел «Делаю сегодня»." \
  jc_section_words "$FILE" '[Дд]елаю[[:space:]]+сегодня' 3
jc_check idea_not_today "Записано хотя бы одно, что отложено на потом" \
  "Назови Claude хотя бы одно, что отложил. Он запишет в раздел «Не сегодня»." \
  jc_section_words "$FILE" '[Нн]е[[:space:]]+сегодня' 1
jc_finish

#!/usr/bin/env bash
# Акт 2, квест 03: схема базы данных описана.
# Квест применим не ко всем проектам, поэтому нужен ответ на вопрос
# «есть ли в проекте БД». Ответ приходит из состояния через переменную.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

HAS_DB=${JEDICODER_HAS_DB:-unknown}

# Сравниваем с оба значения явно: любое третье — не ответ, а мусор, и
# трактовать его как «БД есть» нельзя.
if [ "$HAS_DB" != "yes" ] && [ "$HAS_DB" != "no" ]; then
  jc_bail "ответ про базу данных ещё не записан. Запиши его командой: project db yes|no"
fi

jc_init "act2/03-db-schema"

if [ "$HAS_DB" = "no" ]; then
  jc_check not_applicable "В проекте нет базы данных — квест не нужен" "" true
  jc_finish
fi

jc_check db_schema_exists "DB-SCHEMA.md есть и непустой" \
  "Создай DB-SCHEMA.md и опиши таблицы — иначе ИИ будет писать код под таблицы, которых нет" \
  test -s DB-SCHEMA.md
# Регистр — классами, не `grep -i` (см. 01-recipe и CLAUDE.md): складывание
# регистра кириллицы через -i держится на локали и ломается на BSD grep.
jc_check db_schema_has_table "Описана хотя бы одна таблица" \
  "Перечисли таблицы и их поля" \
  grep -qE '([Тт][Аа][Бб][Лл][Ии][Цц]|[Tt][Aa][Bb][Ll][Ee])' DB-SCHEMA.md
jc_finish

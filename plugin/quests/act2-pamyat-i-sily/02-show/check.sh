#!/usr/bin/env bash
# Акт 2, квест 02: человек показал Claude файл проекта через `@` и снимок
# экрана — вместо пересказа словами.
#
# Оба действия записывает хук игровой сессии (след, ADR-0020 в репозитории
# сайта); сюда они приходят переменными JEDICODER_TRACE_FILE_SHOWN=yes и
# JEDICODER_TRACE_IMAGE_SHOWN=yes. Сохранение проверка не читает.
#
# Строк две, и каждая судит своё: показан файл, а картинки не было — не
# сошлась одна строка, а не обе.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — скажи Claude, в какой папке лежит твой проект"

file_shown() { [ "${JEDICODER_TRACE_FILE_SHOWN:-}" = "yes" ]; }
image_shown() { [ "${JEDICODER_TRACE_IMAGE_SHOWN:-}" = "yes" ]; }

jc_init "act2/02-show"
jc_check file_shown "Ты показал Claude файл проекта через @" \
  "Игра не видела файла в запросе. Набери @ и выбери файл проекта из списка. Потом допиши вопрос." \
  file_shown
jc_check image_shown "Ты показал Claude снимок экрана" \
  "Игра не видела картинки. Сделай снимок экрана и покажи его Claude вместе с вопросом." \
  image_shown
jc_finish

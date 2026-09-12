#!/usr/bin/env bash
# Акт 3, квест 04: починено по-настоящему — есть коммит после слома,
# и проект снова отвечает.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_PORT:-}" ] || \
  jc_bail "Не назван порт проекта. Скажи игре: project port <номер>"

command -v curl >/dev/null 2>&1 || \
  jc_bail "Для этой проверки нужен curl — поставь его и повтори"

# Заголовок, не любая строка сообщения (см. 03-break): иначе более поздний
# коммит со «слом:» в ТЕЛЕ (не в заголовке) перехватил бы маркер и увёл
# "marker..HEAD" вперёд, спрятав настоящую починку. Кириллический матч
# делает grep, не awk: mawk (дефолт WSL Ubuntu) складывает регэксп байтово,
# и класс [Сс] у него молча не находит ничего — awk здесь только вытаскивает
# хэш из первой (самой новой, git log идёт от новых к старым) строки, это
# чистый ASCII и mawk-safe. `awk 'NR==1'` без exit дочитывает трубу до конца
# (pipefail-safe, тот же приём, что и wc в 03-break). `|| true` — grep
# отдаёт 1, когда маркера нет вовсе, и это не авария, а законный пустой marker.
marker=$(git log --format='%H %s' 2>/dev/null \
  | grep -E '^[0-9a-f]+ [Сс]лом:' \
  | awk 'NR == 1 {print $1}') || true
[ -n "$marker" ] || \
  jc_bail "Не найден коммит слома («слом:» в сообщении) — сначала квест 03-break"

has_fix_commit() {
  [ "$(git rev-list --count "${marker}..HEAD" 2>/dev/null || echo 0)" -ge 1 ]
}

# Корень или /health: рецепт велит боту завести страницу «жив», и её кладут
# на /health по привычке всего мира; проверка не вправе требовать корень
# (живой прогон 2026-09-11: попытка ушла на 404 корня при живом /health).
jc_alive() {
  curl -sf --max-time 10 -o /dev/null "$1" \
    || curl -sf --max-time 10 -o /dev/null "$1/health"
}

jc_init "act3/04-fix"
jc_check fix_committed "После слома есть коммит с починкой" \
  "Скорми ИИ ошибку целиком, почини и закоммить починку" \
  has_fix_commit
jc_check server_alive \
  "Проект снова отвечает на http://localhost:${JEDICODER_PORT} (корень или /health)" \
  "Проверь, что проект запускается после починки" \
  jc_alive "http://localhost:${JEDICODER_PORT}"
jc_finish

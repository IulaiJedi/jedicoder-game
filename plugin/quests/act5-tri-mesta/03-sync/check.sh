#!/usr/bin/env bash
# Акт 5, квест 03: одна версия на компьютере и на GitHub.
#
# Порядок всегда один: поправил на компьютере → сохранение → отправка на
# GitHub (шпаргалка оператора, раздел 5). Проверка судит то, что от этого
# остаётся в папке проекта, тремя строками по шагам — следующая печатается,
# только когда сошлась предыдущая:
#
# 1. После входа в акт есть новое сохранение: коммит текущей ветки с датой
#    автора не раньше входа в акт. Момент входа отдаёт команда игры
#    (JEDICODER_ACT_STARTED, секунды эпохи) — как у «Сборки» Акта 4.
# 2. Несохранённых правок нет: `git status --porcelain` пуст. Статус — с
#    `--no-optional-locks`: иначе git обновил бы свой индекс, а проверка
#    проект не меняет. `.env` в нём звучать не должен — он закрыт от
#    сохранений с первого вечера; звучит — у строки своя подсказка: закрыть
#    `.env`, а не сохранять его.
# 3. На GitHub та же версия: `HEAD` совпадает с веткой, за которой следит
#    текущая (`@{u}`, если она на `origin`), иначе с `origin/<текущая>`.
#    Ветку git обновляет сам при отправке; проверка сеть не трогает —
#    `fetch` запрещён: проверка не меняет проект человека. Значит, правка,
#    сделанная прямо на сайте GitHub и ещё не скачанная, не видна — и это
#    честно: на компьютере её тоже нет.
#
# Подсказка третьей строки — по тому, что именно разошлось: не отправлено,
# на GitHub новее, версии разошлись, открыто старое сохранение вместо
# последней версии (отделённый HEAD).
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — скажи Claude, в какой папке лежит твой проект"
command -v git >/dev/null 2>&1 || jc_bail "не найден git — поставь его и вернись"

STARTED="${JEDICODER_ACT_STARTED:-}"
case "$STARTED" in ''|*[!0-9]*) jc_bail "игра не знает, когда начался этот акт" ;; esac

# Свой репозиторий в самой папке проекта: папка внутри чужого репозитория
# иначе судилась бы по чужой истории.
repo_exists() { [ -e .git ] && git rev-parse --git-dir >/dev/null 2>&1; }

# Коммит текущей ветки с датой автора не раньше входа в акт. Читатель
# дочитывает до конца (awk): под pipefail ранний выход рвал бы конвейер.
saved_after_entry() {
  git log --format=%at HEAD 2>/dev/null \
    | awk -v started="$STARTED" '$1 >= started { n++ } END { exit n ? 0 : 1 }'
}

# Пустой ответ `git status` — ещё не «чисто»: упавшая команда тоже молчит.
STATUS=""
STATUS_OK=no
if repo_exists && STATUS=$(git --no-optional-locks status --porcelain 2>/dev/null); then
  STATUS_OK=yes
fi
nothing_unsaved() { [ "$STATUS_OK" = yes ] && [ -z "$STATUS" ]; }

# `.env` среди несохранённого: новый (`??`) — не закрыт от сохранений;
# с любой другой пометкой — уже лежит в сохранениях. Путь — в конце строки
# статуса. Читатель дочитывает до конца (awk): pipefail.
env_status() {
  printf '%s\n' "$STATUS" \
    | awk '!found && /^.. (.*\/)?\.env$/ { print substr($0, 1, 2); found = 1 }'
}
UNSAVED_HINT="В папке есть правки без сохранения. Скажи Claude: «Сделай коммит и отправь на GitHub»."
case "$(env_status)" in
  '') ;;
  '??') UNSAVED_HINT="Файл .env не закрыт от сохранений, а это файл для ключей. Попроси Claude: «Закрой .env от сохранений — допиши его в .gitignore»." ;;
  *) UNSAVED_HINT="Файл .env уже в сохранениях, а это файл для ключей. Попроси Claude: «Убери .env из сохранений и допиши его в .gitignore»." ;;
esac

BRANCH=$(git symbolic-ref --short -q HEAD 2>/dev/null)
LOCAL=$(git rev-parse -q --verify HEAD 2>/dev/null)
REMOTE=""
if [ -n "$BRANCH" ]; then
  # Ветка, за которой следит текущая, — если она на `origin`: так её завёл
  # `git push -u`. Иначе — одноимённая на `origin`.
  UPSTREAM=$(git rev-parse -q --symbolic-full-name '@{u}' 2>/dev/null)
  case "$UPSTREAM" in
    refs/remotes/origin/?*) REMOTE=$(git rev-parse -q --verify "$UPSTREAM" 2>/dev/null) ;;
    *) REMOTE=$(git rev-parse -q --verify "refs/remotes/origin/${BRANCH}" 2>/dev/null) ;;
  esac
fi

same_version() { [ -n "$LOCAL" ] && [ -n "$REMOTE" ] && [ "$LOCAL" = "$REMOTE" ]; }

SEND="Скажи Claude: «Отправь на GitHub»."
if [ -z "$BRANCH" ]; then
  SYNC_HINT="Сейчас открыто старое сохранение, а не последняя версия. Скажи Claude: «Вернись к последней версии»."
elif [ -z "$REMOTE" ]; then
  SYNC_HINT="Этой версии на GitHub ещё нет. ${SEND}"
elif git merge-base --is-ancestor "$REMOTE" "$LOCAL" 2>/dev/null; then
  SYNC_HINT="Последнее сохранение ещё не на GitHub. ${SEND}"
elif git merge-base --is-ancestor "$LOCAL" "$REMOTE" 2>/dev/null; then
  SYNC_HINT="На GitHub версия новее, чем на компьютере. Скажи Claude: «Скачай последнюю версию с GitHub»."
else
  SYNC_HINT="Версии на компьютере и на GitHub разошлись. Скажи Claude: «Сведи версии на компьютере и на GitHub в одну»."
fi

jc_init "act5/03-sync"
if ! repo_exists; then
  # Без своего репозитория сохранений нет — строку о них не к чему
  # приложить. Сказано одной строкой, как в «Работает» Акта 4.
  jc_check repo_exists "В папке проекта заведён git — он хранит сохранения" \
    "Попроси Claude завести git в папке проекта и сохранить проект." \
    repo_exists
  jc_finish
fi
jc_check saved_after_entry "После входа в акт есть новое сохранение" \
  "Попроси Claude поправить мелочь в продукте. Посмотри и скажи: «Сделай коммит и отправь на GitHub»." \
  saved_after_entry
if saved_after_entry; then
  jc_check nothing_unsaved "Несохранённых правок нет" \
    "$UNSAVED_HINT" \
    nothing_unsaved
  if nothing_unsaved; then
    jc_check same_version "На GitHub та же версия, что на компьютере" \
      "$SYNC_HINT" \
      same_version
  fi
fi
jc_finish

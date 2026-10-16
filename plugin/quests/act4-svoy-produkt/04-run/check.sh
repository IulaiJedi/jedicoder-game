#!/usr/bin/env bash
# Акт 4, квест 04: продукт работает на компьютере человека.
#
# Ветка — по типу продукта. Тип называет человек, записывает команда игры
# (`project type site|bot`), проверке его отдаёт она же переменной
# JEDICODER_PRODUCT_TYPE. Типа нет — «не смог проверить»: попытка не в счёт.
#
# Сайт. Claude запускает его на компьютере, человек открывает адрес в
# браузере. Проверка: адрес http://localhost:<порт> отвечает. Порт называет
# команда игры (`project port`, JEDICODER_PORT); перебор портов запрещён —
# на машине может слушать что угодно (так судила и «Первая кровь», полка
# shelf/act3-pervaya-krov/, квест 01-launch). Нет порта или нет curl — «не
# смог проверить». Прокси из окружения адрес на своём компьютере не касается
# (`--noproxy`): через него localhost отвечал бы чужой машиной или никак.
#
# Бот. До проверки — рассказ человека: он написал боту в Telegram и сказал,
# что тот ответил (acts.WORDS_FIRST_FOR, это решает движок). Сама проверка
# судит ключ: он лежит в `.env` в корне папки проекта, `.env` не попадает в
# сохранения, в файлах проекта нет ни одной строки формы ключа, а в
# сохранениях — этого ключа. Живой ли бот, проверка не видит: бот сам
# забирает сообщения, и открыть его нечем.
#
# Форма ключа — одна на всю игру: JC_TELEGRAM_TOKEN_RE в `_lib/secrets.sh`.
# В файлах ищется любая строка этой формы: старый ключ, вписанный в код,
# тоже утечка. В сохранениях — сам ключ из `.env`, буква в букву: старый,
# сменённый у @BotFather, уже не работает, и переписывать историю незачем.
# Ключ не печатается нигде.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/secrets.sh"

[ -n "${JEDICODER_PROJECT_PATH:-}" ] \
  || jc_bail "папка проекта не названа — скажи Claude, в какой папке лежит твой проект"

KIND="${JEDICODER_PRODUCT_TYPE:-}"

case "$KIND" in
  site)
    [ -n "${JEDICODER_PORT:-}" ] \
      || jc_bail "игра не знает, на каком порту работает сайт — попроси Claude назвать его игре"
    command -v curl >/dev/null 2>&1 \
      || jc_bail "для этой проверки нужен curl — попроси Claude его поставить"
    ADDRESS="http://localhost:${JEDICODER_PORT}"
    site_answers() {
      curl -sf --noproxy '*' --max-time 10 -o /dev/null "$ADDRESS/"
    }

    jc_init "act4/04-run"
    jc_check site_answers "Сайт открывается на твоём компьютере: ${ADDRESS}" \
      "Сайт по этому адресу не отвечает. Попроси Claude запустить его снова и открой адрес в браузере." \
      site_answers
    jc_finish
    ;;
  bot)
    ;;
  *)
    jc_bail "игра не знает, сайт у тебя или бот — скажи Claude, что ты строишь"
    ;;
esac

# Дальше — бот. Без git не узнать, что попало в сохранения.
command -v git >/dev/null 2>&1 || jc_bail "не найден git — поставь его и вернись"

if [ -e .env ] && [ ! -r .env ]; then
  jc_bail "не могу прочитать файл .env — проверь права на файл"
fi

# Папки библиотек и сохранений: их содержимое кладёт не человек.
SKIP_DIRS=(.git node_modules .venv venv __pycache__)

TOKEN=""
if [ -f .env ]; then
  TOKEN=$(grep -m1 -oE "$JC_TELEGRAM_TOKEN_RE" .env 2>/dev/null)
  TOKEN=${TOKEN%%$'\n'*}
fi

# `.env` где-то глубже корня — частая ошибка: подсказка тогда о месте файла,
# а не о ключе, которого человек уже брал.
env_elsewhere() {
  local prune=() dir
  for dir in "${SKIP_DIRS[@]}"; do
    prune+=(-name "$dir" -o)
  done
  find . -type d \( "${prune[@]}" -false \) -prune -o \
    -type f -name .env ! -path ./.env -print 2>/dev/null | grep -c . >/dev/null
}

KEY_HINT="Возьми ключ у @BotFather в Telegram и скажи Claude: «Вот ключ, положи его в .env»."
if [ ! -f .env ] && env_elsewhere; then
  KEY_HINT="Файл .env лежит не там. Ключ нужен в файле .env в корне папки проекта — рядом с IDEA.md."
elif [ -f .env ]; then
  KEY_HINT="В файле .env нет ключа бота. Возьми ключ у @BotFather и скажи Claude: «Вот ключ, положи его в .env»."
fi

repo_exists() { [ -e .git ] && git rev-parse --git-dir >/dev/null 2>&1; }

key_in_env() { [ -n "$TOKEN" ]; }

# Внутри `bash -c`: pipefail туда не наследуется, и `grep -q` не рвёт конвейер.
env_tracked() { bash -c 'git ls-files 2>/dev/null | grep -qE "(^|/)\.env$"'; }
env_ignored() { git check-ignore -q --no-index .env 2>/dev/null; }

# Подсказка — по тому, что именно не так: `.env` уже в сохранениях — убрать
# оттуда; не закрыт — дописать в `.gitignore`.
SAVED_HINT="Попроси Claude: «Закрой .env от сохранений — допиши его в .gitignore»."
if repo_exists && env_tracked; then
  if env_ignored; then
    SAVED_HINT="Файл .env уже в сохранениях. Попроси Claude: «Убери .env из сохранений, сам файл оставь»."
  else
    SAVED_HINT="Файл .env уже в сохранениях. Попроси Claude: «Убери .env из сохранений и допиши его в .gitignore»."
  fi
fi

env_not_saved() { env_ignored && ! env_tracked; }

# Любая строка формы ключа — в файлах папки проекта, кроме самих `.env`.
key_not_in_files() {
  local excludes=() dir
  for dir in "${SKIP_DIRS[@]}"; do
    excludes+=("--exclude-dir=$dir")
  done
  ! grep -rIqE --exclude=.env "${excludes[@]}" -- "$JC_TELEGRAM_TOKEN_RE" . 2>/dev/null
}

# Сам ключ из `.env` — в сохранениях. Читатель дочитывает до конца
# (`grep -c`): под pipefail `grep -q` рвал бы конвейер.
key_not_in_saves() {
  ! git log -p --all 2>/dev/null | grep -cF -- "$TOKEN" >/dev/null
}

jc_init "act4/04-run"
jc_check key_in_env "Ключ бота лежит в файле .env в корне папки проекта" \
  "$KEY_HINT" \
  key_in_env
if key_in_env; then
  if repo_exists; then
    jc_check env_not_saved "Файл .env не попадает в сохранения" \
      "$SAVED_HINT" \
      env_not_saved
  else
    # Без своего репозитория сохранений нет — строку о них не к чему
    # приложить. Сказано честно и одной строкой, как в «Сохранении» Акта 1.
    jc_check repo_exists "В папке проекта заведён git — он хранит сохранения" \
      "Попроси Claude завести git в папке проекта и закрыть в нём .env от сохранений." \
      repo_exists
  fi
  jc_check key_not_in_files "Ключа нет в коде и в других файлах" \
    "Ключ бота записан не только в .env. Попроси Claude убрать его оттуда — пусть код берёт ключ из .env." \
    key_not_in_files
  if repo_exists; then
    jc_check key_not_in_saves "Ключа нет в сохранениях" \
      "Ключ попал в сохранение. У @BotFather набери /revoke: старый ключ перестанет работать. Новый положи в .env — переписывать сохранения не нужно." \
      key_not_in_saves
  fi
fi
jc_finish

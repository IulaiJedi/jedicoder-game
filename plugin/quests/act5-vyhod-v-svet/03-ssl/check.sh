#!/usr/bin/env bash
# Акт 5, квест 03: HTTPS настоящий — curl без -k и сертификат живёт > 7 дней.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_URL:-}" ] || \
  jc_bail "Не назван URL продукта. Скажи игре: project url <https://адрес>"
command -v curl >/dev/null 2>&1 || \
  jc_bail "Для этой проверки нужен curl — поставь его и повтори"
command -v openssl >/dev/null 2>&1 || \
  jc_bail "Для проверки сертификата нужен openssl — поставь его и повтори"

host=${JEDICODER_URL#*://}
host=${host%%/*}
host=${host%%:*}

# timeout(1) есть не везде (на macOS его нет) — оборачиваем, только если
# есть; s_client с </dev/null и сам завершается после хендшейка.
cert_fresh() {
  # Пайп s_client | x509 не читается по правилу pipefail-конвейеров: x509
  # останавливается после первого PEM-блока и не дочитывает поток до конца.
  # Здесь это безопасно не потому, что читатель дочитывает, а потому, что
  # писатель (s_client) укладывается в буфер пайпа несколькими КБ — SIGPIPE
  # не успевает возникнуть до штатного завершения обеих сторон.
  local runner=""
  command -v timeout >/dev/null 2>&1 && runner="timeout 20"
  $runner openssl s_client -connect "$host:443" -servername "$host" \
      </dev/null 2>/dev/null \
    | openssl x509 -checkend 604800 -noout >/dev/null 2>&1
}

jc_init "act5/03-ssl"
jc_check https_scheme "URL начинается с https://" \
  "Выпусти сертификат (у платформы — кнопкой, на vps — certbot) и назови URL заново: project url https://…" \
  bash -c 'case "$1" in https://*) exit 0 ;; *) exit 1 ;; esac' _ "$JEDICODER_URL"
jc_check https_alive "Продукт отвечает по HTTPS без -k" \
  "Сертификат должен быть настоящим, самоподписанный не считается" \
  curl -sf --max-time 15 -o /dev/null "$JEDICODER_URL"
jc_check cert_fresh "Сертификату жить больше 7 дней" \
  "Продли сертификат — у certbot это systemd-таймер certbot.timer, проверь его" \
  cert_fresh
jc_finish

#!/usr/bin/env bash
# Акт 5, квест 02: у продукта настоящий домен, а не IP и не localhost.
#
# Оффлайн-проверка строки: живость DNS уже доказана живым curl (квест 01),
# здесь отсекается «у меня и так работает по IP». Регексп требует точку и
# буквенную или punycode-TLD — IP (цифровая «TLD») и localhost (без точки)
# не проходят.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_URL:-}" ] || \
  jc_bail "Не назван URL продукта. Скажи игре: project url <https://адрес>"

host=${JEDICODER_URL#*://}
host=${host%%/*}
host=${host%%:*}

jc_init "act5/02-domain"
# TLD допускается либо буквенной (.ru, .com), либо punycode-формой (xn--…) —
# именно так выглядит IDN-домен (например .рф) после ASCII-преобразования.
# Unicode-хост здесь нарочно не принимается: openssl s_client -connect в
# 03-ssl не делает IDN-преобразования сам, и Unicode-хост сломался бы там же,
# только с менее понятной ошибкой.
jc_check real_domain "Хост ${host} — настоящий домен" \
  "Купи домен, заведи A-запись на сервер (или подключи домен в панели) и назови новый URL: project url <адрес>. Кириллический домен назови в punycode-форме (xn--…): её показывает панель регистратора, и именно её понимают curl и openssl." \
  bash -c 'printf "%s\n" "$1" | grep -cE "^([A-Za-z0-9-]+\.)+([A-Za-z]{2,}|[Xx][Nn]--[A-Za-z0-9-]{2,})$" >/dev/null' _ "$host"
jc_finish

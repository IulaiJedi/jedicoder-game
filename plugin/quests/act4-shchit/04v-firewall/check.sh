#!/usr/bin/env bash
# Акт 4, квест 04 (vps): стена стоит — ufw включён, fail2ban живёт.
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/emit.sh"

[ -n "${JEDICODER_SSH_ALIAS:-}" ] || \
  jc_bail "Не назван ssh-алиас сервера. Скажи игре: project ssh <алиас>"
command -v ssh >/dev/null 2>&1 || \
  jc_bail "Для этой проверки нужен ssh — поставь openssh-client и повтори"

jc_ssh() {
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$JEDICODER_SSH_ALIAS" "$1"
}

# Сначала sudo -n: дал разборчивый ответ — верим ему в обе стороны.
# «Status: inactive» — авторитетное «выключен», фолбэк после него вреден.
# Фолбэк — только когда sudo недоступен (нет NOPASSWD). Юнит ufw здесь
# не годится: на Ubuntu он oneshot с RemainAfterExit и «active (exited)»
# даже при ENABLED=no. Вместо юнита читаем /etc/ufw/ufw.conf (0644):
# ENABLED=yes появляется только после ufw enable.
ufw_status() {
  local out
  out=$(jc_ssh 'LC_ALL=C sudo -n ufw status' 2>/dev/null) || out=""
  if [ -n "$out" ]; then
    printf '%s\n' "$out" | grep -cE '^Status: active' >/dev/null
    return $?
  fi
  jc_ssh 'grep -c "^ENABLED=yes" /etc/ufw/ufw.conf' >/dev/null 2>&1
}

jc_init "act4/04v-firewall"
jc_check ufw_active "Файрвол ufw включён" \
  "На сервере: sudo ufw allow OpenSSH && sudo ufw enable — сначала allow, иначе отрежешь себе вход" \
  ufw_status
jc_check fail2ban_active "fail2ban работает" \
  "На сервере: sudo apt install fail2ban && sudo systemctl enable --now fail2ban" \
  jc_ssh 'systemctl is-active fail2ban'
jc_finish

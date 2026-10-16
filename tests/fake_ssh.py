"""Поддельный `ssh` для проверок, которые ходят на сервер: прежний Акт 4
«Щит» (полка) и Акт 5. Отдельным модулем: полка в выгрузку не едет, а Акт 5
едет и без неё.
"""
import os

import pytest

# Стаб ssh: команда на сервере — последний аргумент. Требует BatchMode=yes
# в аргументах: проверка, забывшая его, повисла бы у падавана на вводе
# пароля — стаб роняет её сразу.
FAKE_SSH = """#!/usr/bin/env bash
[ "${FAKE_DOWN:-0}" = "1" ] && exit 255
batch=0
for arg in "$@"; do [ "$arg" = "BatchMode=yes" ] && batch=1; done
if [ "$batch" != "1" ]; then echo "стаб: нет BatchMode" >&2; exit 96; fi
cmd=""
for arg in "$@"; do cmd="$arg"; done
case "$cmd" in
  *whoami*)
    printf '%s\\n' "${FAKE_WHOAMI:-deploy}"; exit 0 ;;
  *"sudo -n ufw status"*)
    if [ -n "${FAKE_SUDO_UFW:-}" ]; then
      printf '%s\\n' "$FAKE_SUDO_UFW"; exit 0
    fi
    echo "sudo: a password is required" >&2; exit 1 ;;
  *"ufw.conf"*)
    if [ "${FAKE_UFW_ENABLED:-no}" = "yes" ]; then
      printf '1\\n'; exit 0
    fi
    exit 1 ;;
  *"is-enabled"*)
    [ "${FAKE_SERVICE_ENABLED:-no}" = "yes" ] && exit 0 || exit 1 ;;
  *"is-active fail2ban"*)
    printf '%s\\n' "${FAKE_FAIL2BAN:-inactive}"
    [ "${FAKE_FAIL2BAN:-inactive}" = "active" ] && exit 0 || exit 3 ;;
esac
exit 0
"""


@pytest.fixture
def fake_ssh(tmp_path, monkeypatch):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    stub = bin_dir / "ssh"
    stub.write_text(FAKE_SSH, encoding="utf-8")
    stub.chmod(0o755)

    def configure(whoami="deploy", sudo_ufw="", ufw_enabled=False,
                  fail2ban="inactive", down=False, service_enabled=False):
        monkeypatch.setenv(
            "PATH", "{}{}{}".format(bin_dir, os.pathsep, os.environ["PATH"])
        )
        monkeypatch.setenv("FAKE_WHOAMI", whoami)
        monkeypatch.setenv("FAKE_SUDO_UFW", sudo_ufw)
        monkeypatch.setenv("FAKE_UFW_ENABLED", "yes" if ufw_enabled else "no")
        monkeypatch.setenv("FAKE_FAIL2BAN", fail2ban)
        monkeypatch.setenv("FAKE_DOWN", "1" if down else "0")
        monkeypatch.setenv("FAKE_SERVICE_ENABLED", "yes" if service_enabled else "no")

    return configure

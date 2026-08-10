"""Проверки квестов Акта 4. GitHub и сервер в тестах недостижимы, поэтому
git-факты сеются локально (remote-tracking ref — git update-ref, пуш не
нужен), а ssh подменяется стабом в PATH — проверки при этом ходят теми же
командами, что у падавана.
"""
import os

import pytest

from conftest import _git
from jedicoder import quests

ACT = "act4-shchit"

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

SSH_ENV = {"JEDICODER_SSH_ALIAS": "myvps"}


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


def check(quests_root, quest, project_dir, env=None):
    return quests.run_check(quests_root, ACT, quest, project_dir, env_extra=env)


def add_github_remote(proj, pushed=True, url="https://github.com/padawan/proj.git"):
    _git(proj, "remote", "add", "origin", url)
    if pushed:
        # Remote-tracking ref появляется после успешного push (или fetch);
        # в тестах его создаёт update-ref — сеть не нужна, дверь та же.
        _git(proj, "update-ref", "refs/remotes/origin/main", "HEAD")


def test_remote_bails_outside_git_repo(quests_root, project):
    result = check(quests_root, "01-remote", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False


def test_remote_fails_without_origin(quests_root, project):
    result = check(quests_root, "01-remote", project(git=True, commits=1))
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert "origin_github" in ids


def test_remote_fails_on_non_github_origin(quests_root, project):
    proj = project(git=True, commits=1)
    add_github_remote(proj, pushed=True, url="https://gitlab.com/p/p.git")
    result = check(quests_root, "01-remote", proj)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["origin_github"]


def test_remote_fails_before_first_push(quests_root, project):
    proj = project(git=True, commits=1)
    add_github_remote(proj, pushed=False)
    result = check(quests_root, "01-remote", proj)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["pushed"]


def test_remote_passes_after_push(quests_root, project):
    proj = project(git=True, commits=1)
    add_github_remote(proj)
    assert check(quests_root, "01-remote", proj).ok is True


def test_remote_accepts_ssh_form_url(quests_root, project):
    proj = project(git=True, commits=1)
    add_github_remote(proj, url="git@github.com:padawan/proj.git")
    assert check(quests_root, "01-remote", proj).ok is True


def test_secrets_bails_outside_git_repo(quests_root, project):
    result = check(quests_root, "03m-secrets", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_secrets_fails_when_env_tracked(quests_root, project):
    proj = project(git=True, commits=1, commit_env=True)
    result = check(quests_root, "03m-secrets", proj)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert "env_not_tracked" in ids


def test_secrets_fails_on_token_in_history(quests_root, project):
    proj = project(git=True, commits=1, leak_token=True)
    result = check(quests_root, "03m-secrets", proj)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["no_secrets_in_history"]


def test_secrets_passes_on_clean_repo(quests_root, project):
    proj = project(git=True, commits=2)
    assert check(quests_root, "03m-secrets", proj).ok is True


def test_user_bails_without_alias(quests_root, project, fake_ssh):
    fake_ssh()
    result = check(quests_root, "03v-user", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "project ssh" in result.stderr


def test_user_fails_when_server_unreachable(quests_root, project, fake_ssh):
    # Провал соединения — провал квеста, не bail: настроить ключ и алиас —
    # ровно то, чему квест учит.
    fake_ssh(down=True)
    result = check(quests_root, "03v-user", project(), env=SSH_ENV)
    assert result.ok is False
    assert result.countable is True


def test_user_fails_under_root(quests_root, project, fake_ssh):
    fake_ssh(whoami="root")
    result = check(quests_root, "03v-user", project(), env=SSH_ENV)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["not_root"]


def test_user_passes_for_named_user(quests_root, project, fake_ssh):
    fake_ssh(whoami="deploy")
    assert check(quests_root, "03v-user", project(), env=SSH_ENV).ok is True


def test_firewall_bails_without_alias(quests_root, project, fake_ssh):
    fake_ssh()
    result = check(quests_root, "04v-firewall", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_firewall_passes_via_sudo(quests_root, project, fake_ssh):
    fake_ssh(sudo_ufw="Status: active", fail2ban="active")
    assert check(quests_root, "04v-firewall", project(), env=SSH_ENV).ok is True


def test_firewall_passes_via_conf_when_sudo_wants_password(
    quests_root, project, fake_ssh
):
    # sudo без NOPASSWD в BatchMode недоступен — читаем /etc/ufw/ufw.conf
    # без привилегий.
    fake_ssh(sudo_ufw="", ufw_enabled=True, fail2ban="active")
    assert check(quests_root, "04v-firewall", project(), env=SSH_ENV).ok is True


def test_firewall_fails_when_ufw_inactive(quests_root, project, fake_ssh):
    # Регрессия ложноположительного результата: юнит ufw «active (exited)»
    # даже при выключенном файрволе — прежний фолбэк на systemctl это
    # засчитывал.
    fake_ssh(sudo_ufw="", ufw_enabled=False, fail2ban="active")
    result = check(quests_root, "04v-firewall", project(), env=SSH_ENV)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["ufw_active"]


def test_firewall_sudo_inactive_is_authoritative(quests_root, project, fake_ssh):
    # Авторитетное «inactive» от sudo не перекрывается фолбэком.
    fake_ssh(sudo_ufw="Status: inactive", ufw_enabled=True, fail2ban="active")
    result = check(quests_root, "04v-firewall", project(), env=SSH_ENV)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["ufw_active"]


def test_firewall_fails_without_fail2ban(quests_root, project, fake_ssh):
    fake_ssh(sudo_ufw="Status: active", fail2ban="inactive")
    result = check(quests_root, "04v-firewall", project(), env=SSH_ENV)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["fail2ban_active"]


def test_firewall_fails_when_server_down(quests_root, project, fake_ssh):
    fake_ssh(down=True)
    result = check(quests_root, "04v-firewall", project(), env=SSH_ENV)
    assert result.ok is False
    assert result.countable is True

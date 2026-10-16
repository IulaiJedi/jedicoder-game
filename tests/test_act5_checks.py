"""Проверки квестов Акта 5. Живой веб в тестах недостижим: curl и openssl
подменяются стабами в PATH (сценарии через FAKE_*), ssh-стаб Акта 4
переиспользуется — проверки ходят теми же командами, что у падавана.
"""
import os

import pytest

from fake_ssh import fake_ssh  # noqa: F401 — фикстура pytest
from jedicoder import quests

ACT = "act5-vyhod-v-svet"

WEB_ENV = {"JEDICODER_URL": "https://myapp.example"}

FAKE_CURL = """#!/usr/bin/env bash
url=""
for arg in "$@"; do url="$arg"; done
case "$url" in
  */health) [ "${FAKE_HEALTH:-down}" = "up" ] && exit 0 || exit 22 ;;
  *) [ "${FAKE_SITE:-down}" = "up" ] && exit 0 || exit 7 ;;
esac
"""

FAKE_OPENSSL = """#!/usr/bin/env bash
# s_client съедает stdin и рисует заглушку сертификата; x509 -checkend
# отвечает по FAKE_CERT_OK. Оба дочитывают ввод — pipefail-безопасно.
case "$1" in
  s_client)
    cat >/dev/null 2>&1 || true
    echo "-----BEGIN CERTIFICATE-----"; exit 0 ;;
  x509)
    cat >/dev/null 2>&1 || true
    [ "${FAKE_CERT_OK:-no}" = "yes" ] && exit 0 || exit 1 ;;
esac
exit 1
"""


@pytest.fixture
def fake_web(tmp_path, monkeypatch):
    bin_dir = tmp_path / "fakeweb"
    bin_dir.mkdir()
    for name, text in (("curl", FAKE_CURL), ("openssl", FAKE_OPENSSL)):
        stub = bin_dir / name
        stub.write_text(text, encoding="utf-8")
        stub.chmod(0o755)

    def configure(site="up", health="down", cert_ok=False):
        monkeypatch.setenv(
            "PATH", "{}{}{}".format(bin_dir, os.pathsep, os.environ["PATH"])
        )
        monkeypatch.setenv("FAKE_SITE", site)
        monkeypatch.setenv("FAKE_HEALTH", health)
        monkeypatch.setenv("FAKE_CERT_OK", "yes" if cert_ok else "no")

    return configure


def check(quests_root, quest, project_dir, env=None):
    return quests.run_check(quests_root, ACT, quest, project_dir, env_extra=env)


def test_deploy_bails_without_url(quests_root, project, fake_web):
    fake_web()
    result = check(quests_root, "01-deploy", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "project url" in result.stderr


def test_deploy_fails_when_site_down(quests_root, project, fake_web):
    fake_web(site="down")
    result = check(quests_root, "01-deploy", project(), env=WEB_ENV)
    assert result.ok is False
    assert result.countable is True


def test_deploy_passes_on_managed(quests_root, project, fake_web):
    # Без JEDICODER_DEPLOY_PATH=vps ветка reboot не запускается вовсе.
    fake_web(site="up")
    assert check(quests_root, "01-deploy", project(), env=WEB_ENV).ok is True


def test_deploy_vps_bails_without_service(quests_root, project, fake_web, fake_ssh):
    fake_web(site="up")
    fake_ssh()
    env = dict(WEB_ENV)
    env.update({"JEDICODER_DEPLOY_PATH": "vps", "JEDICODER_SSH_ALIAS": "myvps"})
    result = check(quests_root, "01-deploy", project(), env=env)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "project service" in result.stderr


def test_deploy_vps_fails_when_unit_not_enabled(quests_root, project, fake_web, fake_ssh):
    fake_ssh(service_enabled=False)
    fake_web(site="up")
    env = dict(WEB_ENV)
    env.update({
        "JEDICODER_DEPLOY_PATH": "vps", "JEDICODER_SSH_ALIAS": "myvps",
        "JEDICODER_SERVICE": "myapp",
    })
    result = check(quests_root, "01-deploy", project(), env=env)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["reboot_proof"]


def test_deploy_vps_passes_when_enabled(quests_root, project, fake_web, fake_ssh):
    fake_ssh(service_enabled=True)
    fake_web(site="up")
    env = dict(WEB_ENV)
    env.update({
        "JEDICODER_DEPLOY_PATH": "vps", "JEDICODER_SSH_ALIAS": "myvps",
        "JEDICODER_SERVICE": "myapp",
    })
    assert check(quests_root, "01-deploy", project(), env=env).ok is True


def test_domain_bails_without_url(quests_root, project):
    result = check(quests_root, "02-domain", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_domain_rejects_ip_localhost_and_no_tld(quests_root, project):
    # Юникодный «мойсайт.рф» отвергается намеренно: падавана ведут в
    # punycode-форму (см. test_domain_accepts_real_domains), которую
    # одинаково понимают curl, openssl и этот регексп.
    for bad in ("http://192.168.1.10:8000", "http://localhost:3000",
                "https://myapp", "https://мойсайт.рф"):
        env = {"JEDICODER_URL": bad}
        result = check(quests_root, "02-domain", project(), env=env)
        assert result.ok is False, bad
        ids = [c["id"] for c in quests.failed_checks(result)]
        assert ids == ["real_domain"], bad


def test_domain_accepts_real_domains(quests_root, project):
    for good in ("https://myapp.example", "https://sub.my-app.ru",
                 "http://myapp.dev:8443", "https://xn--80aswg.xn--p1ai"):
        env = {"JEDICODER_URL": good}
        assert check(quests_root, "02-domain", project(), env=env).ok is True, good


def test_ssl_bails_without_url(quests_root, project, fake_web):
    fake_web()
    result = check(quests_root, "03-ssl", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_ssl_fails_on_http_url(quests_root, project, fake_web):
    fake_web(site="up", cert_ok=True)
    env = {"JEDICODER_URL": "http://myapp.example"}
    result = check(quests_root, "03-ssl", project(), env=env)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert "https_scheme" in ids


def test_ssl_fails_on_stale_cert(quests_root, project, fake_web):
    fake_web(site="up", cert_ok=False)
    result = check(quests_root, "03-ssl", project(), env=WEB_ENV)
    assert result.ok is False
    ids = [c["id"] for c in quests.failed_checks(result)]
    assert ids == ["cert_fresh"]


def test_ssl_passes_with_fresh_cert(quests_root, project, fake_web):
    fake_web(site="up", cert_ok=True)
    assert check(quests_root, "03-ssl", project(), env=WEB_ENV).ok is True


def test_health_bails_without_url(quests_root, project, fake_web):
    fake_web()
    result = check(quests_root, "04-health", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_health_fails_without_endpoint(quests_root, project, fake_web):
    fake_web(site="up", health="down")
    result = check(quests_root, "04-health", project(), env=WEB_ENV)
    assert result.ok is False


def test_health_passes_with_endpoint(quests_root, project, fake_web):
    fake_web(site="up", health="up")
    assert check(quests_root, "04-health", project(), env=WEB_ENV).ok is True


def test_publish_bails_without_link(quests_root, project):
    result = check(quests_root, "06f-publish", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert "project post" in result.stderr


def test_publish_passes_with_link(quests_root, project):
    env = {"JEDICODER_POST_URL": "https://vc.ru/p/123"}
    assert check(quests_root, "06f-publish", project(), env=env).ok is True

"""Сквозной тест Акта 5: оба трека до ранга Мастер и карточки finale,
той же дверью, что падаван, — через cli.py. Веб и сервер — стабы в PATH.

Акт 5 выключен (ranks.MUTED_ACTS, решение автора 2026-09-10): войти в него
нельзя, значит и пройти его дверью падавана нельзя тоже. Файл не удалён и не
переписан: он оживёт сам в тот день, когда номер уйдёт из MUTED_ACTS.

Проверки самого акта при этом гоняются как прежде — они в
tests/test_act5_checks.py и от входа в акт не зависят.
"""
import pytest

from fake_ssh import fake_ssh  # noqa: F401 — фикстура pytest
from test_act5_checks import fake_web  # noqa: F401 — фикстура pytest
from jedicoder import cli, ranks, state as st


pytestmark = pytest.mark.skipif(
    ranks.is_muted(5),
    reason="Акт 5 выключен (ranks.MUTED_ACTS): войти в него нельзя, пройти — тем более",
)


def run_cli(args, paths, capsys):
    code = cli.main(args, **paths)
    return code, capsys.readouterr().out


@pytest.fixture
def paths(tmp_path, content_root, quests_root):
    return {
        "state_path": tmp_path / "state.json",
        "content_root": content_root,
        "quests_root": quests_root,
    }


def seeded_state(proj, track):
    data = st.default_state("local-test")
    data["passport"] = {"track": track}
    for act in (1, 2, 3, 4):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    data["project"] = {"path": str(proj), "has_db": False}
    return data


def close_common_quests(paths, capsys):
    assert run_cli(["project", "url", "https://myapp.example"], paths, capsys)[0] == 0
    assert run_cli(["enter", "5"], paths, capsys)[0] == 0
    for quest in ("01-deploy", "02-domain", "03-ssl", "04-health"):
        code, out = run_cli(["check", "5", quest], paths, capsys)
        assert code == 0, "{} не закрылся: {}".format(quest, out)
    assert run_cli(["ack", "5", "05-goal"], paths, capsys)[0] == 0


def test_founder_managed_walkthrough(paths, capsys, project, fake_web):
    proj = project(git=True, commits=2)
    st.save(seeded_state(proj, "founder"), paths["state_path"])
    fake_web(site="up", health="up", cert_ok=True)
    run_cli(["project", "deploy", "managed"], paths, capsys)

    close_common_quests(paths, capsys)
    assert run_cli(["project", "post", "https://vc.ru/p/123"], paths, capsys)[0] == 0
    code, out = run_cli(["check", "5", "06f-publish"], paths, capsys)
    assert code == 0
    assert "Мастер" in out

    data = st.load(paths["state_path"])
    assert data["rank"] == "master"
    assert data["xp"] == 120
    assert "deploy" in data["artifacts"]

    code, out = run_cli(["finale"], paths, capsys)
    assert code == 0
    assert "Карточка Мастера" in out
    assert "https://myapp.example" in out
    assert "Дней в пути: 1" in out
    assert "Коммитов: 2" in out


def test_craftsman_vps_walkthrough(paths, capsys, project, fake_ssh, fake_web):
    proj = project(git=True, commits=2)
    st.save(seeded_state(proj, "craftsman"), paths["state_path"])
    fake_ssh(service_enabled=True)
    fake_web(site="up", health="up", cert_ok=True)
    run_cli(["project", "deploy", "vps"], paths, capsys)
    run_cli(["project", "ssh", "myvps"], paths, capsys)
    run_cli(["project", "service", "myapp"], paths, capsys)

    close_common_quests(paths, capsys)
    code, out = run_cli(["ack", "5", "06c-use"], paths, capsys)
    assert code == 0
    assert "Мастер" in out

    data = st.load(paths["state_path"])
    assert data["rank"] == "master"
    assert data["xp"] == 120
    assert run_cli(["finale"], paths, capsys)[0] == 0


def test_finale_refused_until_master(paths, capsys, project):
    # Закрыты Акты 1–4 подряд — ранг Страж; финал ещё заперт.
    proj = project(git=True, commits=1)
    st.save(seeded_state(proj, "founder"), paths["state_path"])
    code, out = run_cli(["finale"], paths, capsys)
    assert code == 1
    assert "Страж" in out


def test_foreign_track_quest_is_refused(paths, capsys, project):
    # До запуска скрипта дело не доходит — отказывает реестр, стабы не нужны.
    proj = project(git=True, commits=1)
    st.save(seeded_state(proj, "craftsman"), paths["state_path"])
    run_cli(["project", "url", "https://myapp.example"], paths, capsys)
    run_cli(["enter", "5"], paths, capsys)
    code, out = run_cli(["check", "5", "06f-publish"], paths, capsys)
    assert code == 1
    assert "06c-use" in out, "отказ называет квесты текущего трека"


def test_check_without_url_is_not_counted(paths, capsys, project):
    # Скрипт бейлится на отсутствии URL раньше, чем позовёт curl.
    proj = project(git=True, commits=1)
    st.save(seeded_state(proj, "founder"), paths["state_path"])
    run_cli(["enter", "5"], paths, capsys)
    code, out = run_cli(["check", "5", "01-deploy"], paths, capsys)
    assert code == 1
    assert "Не смог проверить" in out
    assert "project url" in out
    data = st.load(paths["state_path"])
    quest = data["acts"]["5"]["quests"].get("01-deploy") or {}
    assert quest.get("attempts", 0) == 0, "bail не тратит попытку"

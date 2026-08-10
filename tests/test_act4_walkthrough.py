"""Сквозной тест Акта 4: обе ветки, той же дверью, что падаван, — через
cli.py. GitHub сеется локально (update-ref), сервер — стаб ssh в PATH.
"""
import pytest

from test_act4_checks import add_github_remote, fake_ssh  # noqa: F401 — фикстура pytest
from jedicoder import acts, cli, ranks, state as st

ACT = 4


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


def seeded_state(proj):
    data = st.default_state("local-test")
    for act in (1, 2, 3):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    data["project"] = {"path": str(proj), "has_db": False}
    return data


def test_managed_walkthrough(paths, capsys, project):
    proj = project(git=True, commits=2)
    add_github_remote(proj)
    st.save(seeded_state(proj), paths["state_path"])

    assert run_cli(["project", "deploy", "managed"], paths, capsys)[0] == 0
    code, out = run_cli(["enter", "4"], paths, capsys)
    assert code == 0
    assert "Щит" in out

    assert run_cli(["check", "4", "01-remote"], paths, capsys)[0] == 0
    assert run_cli(["ack", "4", "02-rotation"], paths, capsys)[0] == 0
    assert run_cli(["check", "4", "03m-secrets"], paths, capsys)[0] == 0
    code, out = run_cli(["ack", "4", "04m-guard"], paths, capsys)
    assert code == 0
    assert "закрыт" in out
    assert "Страж" in out

    data = st.load(paths["state_path"])
    assert data["rank"] == "sentinel"
    assert data["xp"] == 80
    assert "cso" in data["artifacts"]


def test_vps_walkthrough(paths, capsys, project, fake_ssh):
    proj = project(git=True, commits=2)
    add_github_remote(proj)
    st.save(seeded_state(proj), paths["state_path"])
    fake_ssh(whoami="deploy", sudo_ufw="Status: active", fail2ban="active")

    assert run_cli(["project", "deploy", "vps"], paths, capsys)[0] == 0
    assert run_cli(["project", "ssh", "myvps"], paths, capsys)[0] == 0
    assert run_cli(["enter", "4"], paths, capsys)[0] == 0

    assert run_cli(["check", "4", "01-remote"], paths, capsys)[0] == 0
    assert run_cli(["ack", "4", "02-rotation"], paths, capsys)[0] == 0
    assert run_cli(["check", "4", "03v-user"], paths, capsys)[0] == 0
    assert run_cli(["check", "4", "04v-firewall"], paths, capsys)[0] == 0
    code, out = run_cli(["ack", "4", "05v-hygiene"], paths, capsys)
    assert code == 0
    assert "Страж" in out

    data = st.load(paths["state_path"])
    assert data["rank"] == "sentinel"
    assert data["xp"] == 100


def test_vps_quest_without_alias_is_not_counted(paths, capsys, project, fake_ssh):
    proj = project(git=True, commits=1)
    st.save(seeded_state(proj), paths["state_path"])
    fake_ssh()
    run_cli(["project", "deploy", "vps"], paths, capsys)
    run_cli(["enter", "4"], paths, capsys)

    code, out = run_cli(["check", "4", "03v-user"], paths, capsys)
    assert code == 1
    assert "Не смог проверить" in out
    assert "project ssh" in out
    data = st.load(paths["state_path"])
    quest = data["acts"]["4"]["quests"].get("03v-user") or {}
    assert quest.get("attempts", 0) == 0, "bail не тратит попытку"


def test_check_refuses_ack_quest_and_back(paths, capsys, project):
    proj = project(git=True, commits=1)
    st.save(seeded_state(proj), paths["state_path"])
    run_cli(["project", "deploy", "managed"], paths, capsys)
    run_cli(["enter", "4"], paths, capsys)

    code, out = run_cli(["check", "4", "02-rotation"], paths, capsys)
    assert code == 1
    assert "ack 4 02-rotation" in out
    code, out = run_cli(["ack", "4", "01-remote"], paths, capsys)
    assert code == 1
    assert "check 4 01-remote" in out


def test_foreign_branch_quest_is_refused(paths, capsys, project):
    proj = project(git=True, commits=1)
    st.save(seeded_state(proj), paths["state_path"])
    run_cli(["project", "deploy", "managed"], paths, capsys)
    run_cli(["enter", "4"], paths, capsys)

    code, out = run_cli(["check", "4", "03v-user"], paths, capsys)
    assert code == 1
    assert "03m-secrets" in out, "отказ называет квесты текущей ветки"


def test_closed_act_survives_deploy_switch(paths, capsys, project, fake_ssh):
    proj = project(git=True, commits=2)
    add_github_remote(proj)
    st.save(seeded_state(proj), paths["state_path"])
    run_cli(["project", "deploy", "managed"], paths, capsys)
    run_cli(["enter", "4"], paths, capsys)
    run_cli(["check", "4", "01-remote"], paths, capsys)
    run_cli(["ack", "4", "02-rotation"], paths, capsys)
    run_cli(["check", "4", "03m-secrets"], paths, capsys)
    run_cli(["ack", "4", "04m-guard"], paths, capsys)
    assert st.load(paths["state_path"])["rank"] == "sentinel"

    # Смена пути после закрытия не роняет ни акт, ни ранг.
    run_cli(["project", "deploy", "vps"], paths, capsys)
    code, out = run_cli(["status"], paths, capsys)
    assert code == 0
    assert "Страж" in out
    assert st.load(paths["state_path"])["acts"]["4"]["status"] == "done"


def test_enter_act4_requires_act3_closed(paths, capsys, project):
    proj = project(git=True, commits=1)
    data = st.default_state("local-test")
    for act in (1, 2):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    data["project"] = {"path": str(proj), "deploy_path": "managed"}
    st.save(data, paths["state_path"])

    code, out = run_cli(["enter", "4"], paths, capsys)
    assert code == 1
    assert "Акт 3" in out

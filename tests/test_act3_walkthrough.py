"""Сквозной тест Акта 3. Наполняется по мере готовности квестов;
проход целиком — в финальной задаче плана.
"""
import pytest

from test_act3_checks import commit_all, live_server  # noqa: F401 — фикстура pytest
from conftest import _git

from jedicoder import acts, cli, content, ranks, state as st

ACT = 3
SLUG = "act3-pervaya-krov"

DECISIONS = (
    "# Решения\n\n"
    "## 2026-07-27 — SQLite вместо Postgres\n\nОдин файл, ноль настройки.\n\n"
    "## 2026-07-28 — поллинг, не вебхуки\n\nПроще на старте.\n"
)
SKILL = "# Проверка\n\n" + ("Открой страницу, обнови, посмотри консоль. " * 10)


def test_quest_order_declared():
    assert acts.quest_ids(ACT) == (
        "01-launch", "02-feature", "03-break", "04-fix", "05-decisions",
        "06-context7", "07-git-safety", "08-skill", "09-loop-protocol",
        "10-boss",
    )


def test_loop_protocol_is_ack_rest_are_scripts():
    for quest_id in acts.quest_ids(ACT):
        expected = acts.KIND_ACK if quest_id == "09-loop-protocol" else acts.KIND_SCRIPT
        assert acts.quest_kind(ACT, quest_id) == expected, quest_id


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
    for act in (1, 2):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    data["project"] = {"path": str(proj), "has_db": False}
    return data


def test_full_walkthrough_through_cli(
    tmp_path, paths, capsys, project, live_server
):
    proj = project(
        files={
            "CLAUDE.md": "# Проект\n\nБот присылает цитаты.\n",
            "DECISIONS.md": DECISIONS,
            ".claude/skills/verify/SKILL.md": SKILL,
            ".mcp.json": '{"mcpServers": {"context7": {}}}',
        },
        git=True,
        commits=3,
    )
    st.save(seeded_state(proj), paths["state_path"])

    code, out = run_cli(["enter", "3"], paths, capsys)
    assert code == 0
    assert "Первая кровь" in out

    # Критерий успеха фазы дословно: падаван с пустой link_key входит в акт
    # и получает катсцену и ссылку. Проверяется здесь потому, что это
    # единственный тест, доходящий до Акта 3 через ту же дверь, что человек.
    scene = next(
        item for item in content.load_acts(paths["content_root"]) if item.act == ACT
    )
    assert scene.body in out
    assert any(
        line.startswith("Разворот этой главы: ") for line in out.splitlines()
    ), out
    assert st.load(paths["state_path"])["link_key"] is None

    # вход дозаписал sha Акта 2 (миграция) — босс получит точку отсчёта
    data = st.load(paths["state_path"])
    assert len(data["acts"]["2"]["claude_md_sha"]) == 40

    code, _ = run_cli(["project", "port", str(live_server)], paths, capsys)
    assert code == 0

    # история для 03/04/07 и порога 02: слом → починка → костыль → revert.
    # revert делается на коммите с настоящим изменением: пустой коммит git
    # ревертить отказывается. Итого 3 + 4 = 7 коммитов ≥ 5.
    commit_all(proj, "слом: убрал кавычку нарочно")
    commit_all(proj, "починил: вернул кавычку")
    (proj / "hotfix.txt").write_text("временный костыль\n", encoding="utf-8")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "костыль")
    _git(proj, "revert", "--no-edit", "HEAD")

    # босс требует изменить CLAUDE.md после входа
    (proj / "CLAUDE.md").write_text(
        "# Проект\n\nБот присылает цитаты.\nЗапуск: python main.py.\n",
        encoding="utf-8",
    )

    for quest_id in (
        "01-launch", "02-feature", "03-break", "04-fix", "05-decisions",
        "06-context7", "07-git-safety", "08-skill",
    ):
        code, out = run_cli(["check", "3", quest_id], paths, capsys)
        assert code == 0, "{} не закрылся: {}".format(quest_id, out)

    code, out = run_cli(["ack", "3", "09-loop-protocol"], paths, capsys)
    assert code == 0

    code, out = run_cli(["check", "3", "10-boss"], paths, capsys)
    assert code == 0
    assert "закрыт" in out
    assert "Рыцарь" in out

    reloaded = st.load(paths["state_path"])
    assert reloaded["rank"] == "knight"
    assert reloaded["xp"] == 200
    assert "investigate" in reloaded["artifacts"]
    assert len(reloaded["acts"]["3"]["claude_md_sha"]) == 40

    code, out = run_cli(["status"], paths, capsys)
    assert code == 0
    assert "XP: 200" in out

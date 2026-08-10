"""Сквозной тест: Акт 2 проходится целиком на реальном проекте.

Это самый ценный тест плана. Он доказывает, что машинерия работает вместе:
вход в акт выдаёт артефакт, проверки закрывают квесты, закрытие акта
поднимает ранг.
"""
from test_act1_walkthrough import CRAFT_FILES, CRAFT_QUESTS

from jedicoder import acts, quests, ranks, state as st

ACT = 2
SLUG = "act2-chertezh"

ARCH = "# Архитектура\n\n## Стек\n\n" + ("Python, aiogram, SQLite. " * 40)
CLAUDE = "# Проект\n\n" + ("Бот присылает цитату по команде /цитата. " * 20)
DB = "# Схема\n\n## Таблица users\n\nid, tg_id, created_at\n"


def seeded_state():
    """Состояние с закрытым Актом 1: без него вход во второй акт запрещён."""
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    return data


def test_quest_order_declared():
    assert acts.quest_ids(ACT) == (
        "01-recipe", "02-claude-md", "03-db-schema",
        "04-git-init", "05-env-guard", "06-pipeline",
    )


def test_act1_has_declared_quests():
    """Состав Акта 1 зависит от трека, поэтому без трека список не отдаётся."""
    assert acts.quest_ids(1, acts.TRACK_CRAFTSMAN) == (
        "01-idea", "02-one-evening", "03c-who",
    )
    assert acts.quest_ids(1, acts.TRACK_FOUNDER) == (
        "01-idea", "02-one-evening", "03f-market", "04f-competitors",
        "05f-icp", "06f-unit", "07f-channel",
    )
    assert acts.quest_kind(1, "01-idea") == acts.KIND_SCRIPT


def test_next_quest_walks_in_order():
    data = seeded_state()
    ranks.enter_act(data, ACT)
    assert acts.next_quest(data, ACT) == "01-recipe"
    data["acts"]["2"]["quests"]["01-recipe"] = {"status": "done", "attempts": 1}
    assert acts.next_quest(data, ACT) == "02-claude-md"


def test_full_walkthrough(tmp_path, quests_root, project):
    proj = project(
        files={"ARCHITECTURE.md": ARCH, "CLAUDE.md": CLAUDE, "DB-SCHEMA.md": DB},
        gitignore=".env\n.venv\n",
        git=True,
        commits=1,
    )
    state_path = tmp_path / "state.json"
    data = seeded_state()
    data["project"] = {"path": str(proj), "has_db": True}
    ranks.enter_act(data, ACT)

    assert data["artifacts"] == ["brainstorm", "plan"]

    for quest_id in acts.quest_ids(ACT):
        result = quests.run_check(
            quests_root, SLUG, quest_id, proj,
            env_extra={"JEDICODER_HAS_DB": "yes"},
        )
        if result.kind == quests.KIND_ACK:
            quests.acknowledge(data, ACT, quest_id)
            continue
        assert result.ok is True, "квест {} не закрылся: {}".format(
            quest_id, quests.failed_checks(result)
        )
        quests.record_attempt(data, ACT, quest_id, result)

    assert acts.all_closed(data, ACT) is True
    assert acts.next_quest(data, ACT) is None

    ranks.close_act(data, ACT)
    st.save(data, state_path)

    reloaded = st.load(state_path)
    assert reloaded["rank"] == "padawan"
    assert reloaded["first_try"] == {"passed": 5, "attempted": 5}
    assert "plan" in reloaded["artifacts"]


def test_act_not_closed_while_quest_open(tmp_path, quests_root, project):
    proj = project(files={"CLAUDE.md": CLAUDE}, git=True, commits=1)
    data = seeded_state()
    ranks.enter_act(data, ACT)
    result = quests.run_check(quests_root, SLUG, "02-claude-md", proj)
    quests.record_attempt(data, ACT, "02-claude-md", result)
    assert acts.all_closed(data, ACT) is False
    assert acts.next_quest(data, ACT) == "01-recipe"


def test_full_walkthrough_via_cli(tmp_path, quests_root, project):
    """Пройти Акт 2 исключительно через CLI, как реальный падаван.

    Это отличается от test_full_walkthrough тем, что использует cli.main()
    вместо прямых вызовов ranks.* и quests.*. Это доказывает, что игра
    подлинно проходима через интерфейс, который видит пользователь.

    Засев Акта 1 записью состояния убран: предпосылка достижима теми же
    командами, что и всё остальное — Акт 1 проходится по-настоящему.
    """
    from jedicoder import cli

    proj = project(
        files=dict(
            CRAFT_FILES,
            **{"ARCHITECTURE.md": ARCH, "CLAUDE.md": CLAUDE, "DB-SCHEMA.md": DB}
        ),
        gitignore=".env\n.venv\n",
        git=True,
        commits=1,
    )
    state_path = tmp_path / "state.json"

    # Предпосылка — тоже через CLI: Акт 1 проходится по-настоящему.
    assert cli.main(["project", "path", str(proj)],
                    state_path=state_path) == 0
    assert cli.main(["track", "craftsman"], state_path=state_path) == 0
    assert cli.main(["enter", "1"], state_path=state_path) == 0
    for quest_id in CRAFT_QUESTS:
        assert cli.main(["check", "1", quest_id], state_path=state_path,
                        quests_root=quests_root) == 0
    assert cli.main(["project", "db", "yes"], state_path=state_path) == 0

    # Enter Act 2
    assert cli.main(["enter", "2"], state_path=state_path) == 0

    # Check all 5 script quests
    for quest_id in ("01-recipe", "02-claude-md", "03-db-schema", "04-git-init", "05-env-guard"):
        assert cli.main(
            ["check", "2", quest_id],
            state_path=state_path,
            quests_root=quests_root,
        ) == 0, "квест {} не закрылся через CLI".format(quest_id)

    # Acknowledge the ack quest
    assert cli.main(["ack", "2", "06-pipeline"], state_path=state_path) == 0

    # Verify final state
    reloaded = st.load(state_path)
    assert reloaded["rank"] == "padawan", "ранг должен быть padawan после закрытия акта"
    assert reloaded["acts"]["2"]["status"] == "done", "акт 2 должен быть done"
    # Восемь скриптовых квестов: три Ремесленника в Акте 1 плюс пять в Акте 2.
    # Шестой квест Акта 2 подтверждается через ack и в счёт не идёт.
    assert reloaded["first_try"] == {"passed": 8, "attempted": 8}
    assert ranks.can_enter_act(reloaded, 3)[0] is True, "должна быть возможность войти в акт 3"


def test_fresh_install_reaches_padawan_via_cli_only(tmp_path, quests_root, project):
    """Путь живого падавана целиком: от чистого состояния до ранга Падаван.

    БЕЗ ЗАСЕВА. Ни одного прямого вызова ranks.* или quests.* — только cli.main.
    Прежний «сквозной через CLI» тест засевал закрытый Акт 1 записью состояния,
    и это скрыло, что предпосылка недостижима через интерфейс падавана. Тест,
    который стартует из состояния, невоспроизводимого на реальной установке,
    ничего не доказывает.
    """
    from jedicoder import cli

    proj = project(
        files=dict(
            CRAFT_FILES,
            **{"ARCHITECTURE.md": ARCH, "CLAUDE.md": CLAUDE, "DB-SCHEMA.md": DB}
        ),
        gitignore=".env\n.venv\n",
        git=True,
        commits=1,
    )
    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)
    assert st.load(state_path)["rank"] == "youngling"
    assert st.load(state_path)["acts"] == {}

    def jc(*argv):
        return cli.main(list(argv), state_path=state_path, quests_root=quests_root)

    assert jc("project", "path", str(proj)) == 0
    assert jc("project", "db", "yes") == 0

    assert jc("track", "craftsman") == 0
    assert jc("enter", "1") == 0
    for quest_id in CRAFT_QUESTS:
        assert jc("check", "1", quest_id) == 0, (
            "квест Акта 1 {} не закрылся через CLI".format(quest_id)
        )

    assert jc("enter", "2") == 0
    for quest_id in ("01-recipe", "02-claude-md", "03-db-schema",
                     "04-git-init", "05-env-guard"):
        assert jc("check", "2", quest_id) == 0, (
            "квест {} не закрылся через CLI".format(quest_id)
        )
    assert jc("ack", "2", "06-pipeline") == 0

    reloaded = st.load(state_path)
    assert reloaded["rank"] == "padawan"
    assert reloaded["acts"]["1"]["status"] == "done"
    assert reloaded["acts"]["2"]["status"] == "done"
    # Акт 3 уже имеет квесты, поэтому вход разрешён.
    assert ranks.can_enter_act(reloaded, 3)[0] is True
    assert jc("enter", "3") == 0, "можно пускать в акт, для которого есть квесты"
    # Акт 3 объявлен и начат, но не закрыт — CLI обязан не пускать дальше по порядку актов.
    assert ranks.can_enter_act(reloaded, 4)[0] is False
    assert jc("enter", "4") == 1, "нельзя пускать в акт, если предыдущий не закрыт"
    assert jc("artifact", "cso") == 1, "и выдавать его артефакт тоже"
    after = st.load(state_path)
    assert "4" not in after["acts"], "отказанный вход не начинает акт"
    assert "cso" not in (after.get("artifacts") or [])

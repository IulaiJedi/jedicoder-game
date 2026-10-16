"""Вторая ось развилки: путь деплоя. Прежний Акт 4 «Щит» ветвился не по
треку, а по state.project.deploy_path; метка ветки стоит на квесте, ось — на
акте.

«Щит» с 2026-10-14 на полке (спека #117), и по этой оси не ветвится ни один
играемый акт. Механика цела: тесты ставят «Щит» на его прежний номер
фикстурой `shield_on_act4` — состав и ветки берутся с полки.
"""
import pytest

from jedicoder import acts

pytestmark = pytest.mark.usefixtures("shield_on_act4")

SAMPLE = (
    ("01-common", acts.KIND_SCRIPT, acts.BRANCH_BOTH),
    ("02m-panel", acts.KIND_SCRIPT, acts.DEPLOY_MANAGED),
    ("03v-server", acts.KIND_SCRIPT, acts.DEPLOY_VPS),
)


def test_deploys_come_from_content_schema():
    from jedicoder import content
    assert acts.DEPLOYS == content.DEPLOY_PATHS


def test_filter_keeps_common_and_own_deploy():
    assert acts.filter_by_deploy(SAMPLE, acts.DEPLOY_MANAGED) == (
        "01-common", "02m-panel",
    )
    assert acts.filter_by_deploy(SAMPLE, acts.DEPLOY_VPS) == (
        "01-common", "03v-server",
    )


def test_filter_without_deploy_raises_on_branching_act():
    with pytest.raises(acts.DeployRequiredError):
        acts.filter_by_deploy(SAMPLE, None)


def test_unknown_deploy_is_treated_as_absent():
    with pytest.raises(acts.DeployRequiredError):
        acts.filter_by_deploy(SAMPLE, "kubernetes")


def test_deploy_required_is_unknown_act_subclass():
    # Существующие обработчики UnknownActError не должны пропустить новую
    # ошибку мимо: до интеграции в CLI она обязана деградировать до
    # «квесты не завезены», а не до трейсбека.
    assert issubclass(acts.DeployRequiredError, acts.UnknownActError)


def test_deploy_of_reads_project_and_ignores_garbage():
    assert acts.deploy_of({"project": {"deploy_path": "vps"}}) == "vps"
    assert acts.deploy_of({"project": {"deploy_path": "heroku"}}) is None
    assert acts.deploy_of({"project": {}}) is None
    assert acts.deploy_of({}) is None
    assert acts.deploy_of(None) is None


def test_branch_of_act1_is_track_act4_is_deploy():
    state = {
        "passport": {"track": "craftsman"},
        "project": {"deploy_path": "vps"},
    }
    assert acts.branch_of(state, 1) == "craftsman"
    assert acts.branch_of(state, 2) == "craftsman"
    assert acts.branch_of(state, 4) == "vps"


def test_act4_quest_order_managed():
    assert acts.quest_ids(4, acts.DEPLOY_MANAGED) == (
        "01-remote", "02-rotation", "03m-secrets", "04m-guard",
    )


def test_act4_quest_order_vps():
    assert acts.quest_ids(4, acts.DEPLOY_VPS) == (
        "01-remote", "02-rotation", "03v-user", "04v-firewall", "05v-hygiene",
    )


def test_act4_without_deploy_raises():
    with pytest.raises(acts.DeployRequiredError):
        acts.quest_ids(4)


def test_act4_track_value_does_not_pass_for_deploy():
    # Трек не подменяет путь деплоя: оси разные, значения не пересекаются.
    with pytest.raises(acts.DeployRequiredError):
        acts.quest_ids(4, "craftsman")


def test_act4_kinds():
    acks = {"02-rotation", "04m-guard", "05v-hygiene"}
    for deploy in acts.DEPLOYS:
        for quest_id in acts.quest_ids(4, deploy):
            expected = (
                acts.KIND_ACK if quest_id in acks else acts.KIND_SCRIPT
            )
            assert acts.quest_kind(4, quest_id) == expected, quest_id


def test_act5_quest_order_craftsman():
    assert acts.quest_ids(5, acts.TRACK_CRAFTSMAN) == (
        "01-deploy", "02-domain", "03-ssl", "04-health", "05-goal",
        "06c-use",
    )


def test_act5_quest_order_founder():
    assert acts.quest_ids(5, acts.TRACK_FOUNDER) == (
        "01-deploy", "02-domain", "03-ssl", "04-health", "05-goal",
        "06f-publish",
    )


def test_act5_without_track_raises():
    with pytest.raises(acts.TrackRequiredError):
        acts.quest_ids(5)


def test_act5_kinds():
    acks = {"05-goal", "06c-use"}
    for track in acts.TRACKS:
        for quest_id in acts.quest_ids(5, track):
            expected = acts.KIND_ACK if quest_id in acks else acts.KIND_SCRIPT
            assert acts.quest_kind(5, quest_id) == expected, quest_id

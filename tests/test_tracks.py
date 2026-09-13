"""Ветвление реестра квестов по треку и команда выбора трека."""
import pytest

from jedicoder import acts, cli
from jedicoder import state as st

BOTH = acts.TRACK_BOTH
CRAFT = acts.TRACK_CRAFTSMAN
FOUND = acts.TRACK_FOUNDER

SAMPLE = (
    ("01-common", acts.KIND_SCRIPT, BOTH),
    ("02-common", acts.KIND_SCRIPT, BOTH),
    ("03c-craft", acts.KIND_SCRIPT, CRAFT),
    ("03f-found", acts.KIND_SCRIPT, FOUND),
    ("04f-found", acts.KIND_SCRIPT, FOUND),
)

FLAT = (
    ("01-a", acts.KIND_SCRIPT, BOTH),
    ("02-b", acts.KIND_SCRIPT, BOTH),
)


def test_filter_keeps_common_and_own_track():
    assert acts.filter_by_track(SAMPLE, CRAFT) == ("01-common", "02-common", "03c-craft")
    assert acts.filter_by_track(SAMPLE, FOUND) == (
        "01-common", "02-common", "03f-found", "04f-found",
    )


def test_filter_preserves_declaration_order():
    assert acts.filter_by_track(SAMPLE, FOUND)[0] == "01-common"


def test_filter_without_track_raises_on_branching_act():
    with pytest.raises(acts.TrackRequiredError):
        acts.filter_by_track(SAMPLE, None)


def test_filter_without_track_is_fine_on_flat_act():
    """Акты 2-5 не ветвятся, поэтому трек им не нужен."""
    assert acts.filter_by_track(FLAT, None) == ("01-a", "02-b")


def test_unknown_track_is_treated_as_absent():
    """Мусор в passport.track не должен молча давать половину акта."""
    with pytest.raises(acts.TrackRequiredError):
        acts.filter_by_track(SAMPLE, "jedi")


def test_act2_still_works_without_track():
    assert acts.quest_ids(2) == (
        "01-recipe", "02-claude-md", "03-db-schema",
        "04-git-init", "05-env-guard", "06-pipeline",
    )


def test_track_of_reads_passport():
    data = st.default_state("local-test")
    assert acts.track_of(data) is None
    data["passport"]["track"] = CRAFT
    assert acts.track_of(data) == CRAFT


# --- команда track ---

def test_track_command_shows_not_chosen(tmp_path, capsys):
    state_path = tmp_path / "state.json"
    assert cli.main(["track"], state_path=state_path) == 0
    assert "не выбран" in capsys.readouterr().out


def test_track_command_sets_craftsman(tmp_path):
    state_path = tmp_path / "state.json"
    assert cli.main(["track", "craftsman"], state_path=state_path) == 0
    assert st.load(state_path)["passport"]["track"] == CRAFT


def test_track_command_sets_founder(tmp_path):
    state_path = tmp_path / "state.json"
    assert cli.main(["track", "founder"], state_path=state_path) == 0
    assert st.load(state_path)["passport"]["track"] == FOUND


def test_track_command_rejects_garbage(tmp_path, capsys):
    state_path = tmp_path / "state.json"
    cli.main(["track", "craftsman"], state_path=state_path)
    assert cli.main(["track", "sith"], state_path=state_path) == 1
    out = capsys.readouterr().out
    assert "craftsman" in out and "founder" in out
    assert st.load(state_path)["passport"]["track"] == CRAFT, (
        "мусорное значение не должно затирать выбранный трек"
    )


def test_track_command_shows_current(tmp_path, capsys):
    state_path = tmp_path / "state.json"
    cli.main(["track", "founder"], state_path=state_path)
    capsys.readouterr()
    assert cli.main(["track"], state_path=state_path) == 0
    # Падаван видит слова, а не имя ручки: «для людей», не «founder».
    assert "для людей" in capsys.readouterr().out


def test_track_is_in_subcommands():
    assert "track" in cli.SUBCOMMANDS


def test_all_quest_ids_gives_both_sides_in_declaration_order():
    """Порядок перечисления записанного: выбор падавана на него не влияет.

    Разбору нужен именно он — у сменившего трек в сохранении лежат квесты
    обоих треков, и попытки на них он всё-таки потратил.
    """
    assert acts.all_quest_ids(1) == (
        "01-idea", "02-one-evening", "03c-who", "03f-market",
        "04f-competitors", "05f-icp", "06f-unit", "07f-channel",
    )
    assert acts.all_quest_ids(2) == acts.quest_ids(2)


def test_all_quest_ids_refuses_an_act_it_does_not_know():
    with pytest.raises(acts.UnknownActError):
        acts.all_quest_ids(9)


def test_choices_read_as_absent_when_the_whole_section_is_garbage():
    """«Мусор — как отсутствие» — и о значении, и о разделе целиком.

    Раздел правили руками: паспорт или проект оказались строкой. Обещание
    в docstring одно, а строка отвечала на .get трейсбеком.
    """
    assert acts.track_of({"passport": "мусор"}) is None
    assert acts.deploy_of({"project": "мусор"}) is None
    assert acts.branch_of({"project": "мусор"}, 4) is None

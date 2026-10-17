import pytest

from jedicoder import ranks, state as st


def make(*done_acts, **kwargs):
    data = st.default_state("abc123")
    for act in done_acts:
        data["acts"][str(act)] = {"status": "done", "quests": {}}
    in_progress = kwargs.get("in_progress")
    if in_progress:
        data["acts"][str(in_progress)] = {"status": "in_progress", "quests": {}}
    return data


def test_ranks_order():
    assert ranks.RANKS == (
        "youngling", "seeker", "padawan", "knight", "sentinel", "master",
    )
    assert set(ranks.RANK_TITLES) == set(ranks.RANKS)


def test_acts_table_complete():
    assert sorted(ranks.ACTS) == [1, 2, 3, 4, 5]
    assert [ranks.ACTS[n]["artifact"] for n in sorted(ranks.ACTS)] == [
        "brainstorm", "handoff", "investigate", "goal", "cso",
    ]
    assert [ranks.ACTS[n]["rank"] for n in sorted(ranks.ACTS)] == [
        "seeker", "padawan", "knight", "sentinel", "master",
    ]


def test_all_artifacts_are_one_list_and_goal_has_a_lock():
    """Полный список имён артефактов — один, и он здесь.

    До 2026-10-14 `goal` был без замка и жил в `UNLOCKED_ARTIFACTS`. Теперь
    его выдают на входе в Акт 4 «Свой продукт» (спека #117): он в `ACTS`, а
    приёмов без замка нет. Читателям (линтер состава инструкций, сборка
    памятки) нужен список целиком, и заводить его у себя им нельзя: два
    списка имён разойдутся молча.
    """
    assert ranks.ALL_ARTIFACTS == (
        "brainstorm", "handoff", "investigate", "goal", "cso",
    )
    assert ranks.UNLOCKED_ARTIFACTS == ()
    # Производный, а не переписанный: акт добавят — список вырастет сам.
    from_acts = tuple(ranks.ACTS[n]["artifact"] for n in sorted(ranks.ACTS))
    assert ranks.ALL_ARTIFACTS == from_acts + ranks.UNLOCKED_ARTIFACTS
    # Приём «Щита» вернулся приёмом Акта 5 (спека #123), а приём прежнего
    # «Выхода в свет» ушёл с ним на полку: имени нет ни в одном перечне.
    assert "deploy" not in ranks.ALL_ARTIFACTS


def test_rank_starts_at_youngling():
    assert ranks.rank_for(st.default_state("abc123")) == "youngling"


def test_rank_follows_contiguous_run():
    assert ranks.rank_for(make(1)) == "seeker"
    assert ranks.rank_for(make(1, 2)) == "padawan"
    assert ranks.rank_for(make(1, 2, 3, 4, 5)) == "master"


def test_rank_ignores_gap():
    # закрыты 1 и 3, второй пропущен — ранг только за первый
    assert ranks.rank_for(make(1, 3)) == "seeker"


def test_xp_does_not_affect_rank():
    data = make(1)
    ranks.add_xp(data, 10_000)
    assert data["xp"] == 10_000
    assert ranks.rank_for(data) == "seeker"


def test_can_enter_first_act_always():
    assert ranks.can_enter_act(st.default_state("abc123"), 1) == (True, "")


def test_cannot_skip_act():
    ok, reason = ranks.can_enter_act(make(1), 3)
    assert ok is False
    assert "Акт 2" in reason


def test_can_enter_next_after_close():
    assert ranks.can_enter_act(make(1), 2)[0] is True


def test_unknown_act_raises():
    with pytest.raises(ValueError, match="нет акта"):
        ranks.can_enter_act(st.default_state("abc123"), 9)


def test_artifact_given_on_entry_not_on_close():
    data = st.default_state("abc123")
    assert ranks.artifact_unlocked(data, "handoff") is False
    ranks.enter_act(data, 1)
    assert ranks.artifacts_for(data) == ["brainstorm"]
    assert ranks.artifact_unlocked(data, "handoff") is False
    ranks.close_act(data, 1)
    assert ranks.artifact_unlocked(data, "handoff") is False
    ranks.enter_act(data, 2)
    assert ranks.artifact_unlocked(data, "handoff") is True
    assert ranks.artifacts_for(data) == ["brainstorm", "handoff"]


def test_shelved_artifact_is_not_given_by_any_act():
    """Приём `plan` ушёл на полку с прежним Актом 2 (shelf/act2-chertezh/)."""
    data = st.default_state("abc123")
    for act in sorted(ranks.ACTS):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    assert "plan" not in ranks.ALL_ARTIFACTS
    assert ranks.artifact_unlocked(data, "plan") is False


def test_enter_act_sets_current_and_status():
    data = st.default_state("abc123")
    ranks.enter_act(data, 1)
    assert data["current_act"] == 1
    assert data["acts"]["1"]["status"] == "in_progress"
    assert data["acts"]["1"]["quests"] == {}


def test_enter_act_is_idempotent():
    data = st.default_state("abc123")
    ranks.enter_act(data, 1)
    data["acts"]["1"]["quests"]["01-idea"] = {"status": "done", "attempts": 1}
    ranks.enter_act(data, 1)
    assert data["acts"]["1"]["quests"]["01-idea"]["status"] == "done"
    assert data["artifacts"] == ["brainstorm"]


def test_enter_blocked_act_raises():
    with pytest.raises(ranks.ProgressionError, match="Акт 2"):
        ranks.enter_act(st.default_state("abc123"), 3)


def test_close_act_updates_rank_and_timestamp():
    data = st.default_state("abc123")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    assert data["acts"]["1"]["status"] == "done"
    assert data["acts"]["1"]["completed_at"]
    assert data["rank"] == "seeker"


def test_close_act_keeps_first_completed_at():
    """Повторное закрытие не переписывает дату: по ней считают длительность."""
    data = st.default_state("abc123")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    first = data["acts"]["1"]["completed_at"]
    data["acts"]["1"]["completed_at"] = "2020-01-01T00:00:00Z"
    ranks.close_act(data, 1)
    assert data["acts"]["1"]["completed_at"] == "2020-01-01T00:00:00Z"
    assert first  # первая отметка всё-таки ставилась


def test_close_act_not_entered_raises():
    with pytest.raises(ranks.ProgressionError, match="не начат"):
        ranks.close_act(st.default_state("abc123"), 1)


def test_enter_act_writes_started_at_once():
    from jedicoder import ranks, state as st
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    stamp = data["acts"]["1"]["started_at"]
    assert len(stamp) == 20 and stamp.endswith("Z")
    ranks.close_act(data, 1)
    ranks.enter_act(data, 2)
    sentinel = "2020-01-01T00:00:00Z"
    data["acts"]["2"]["started_at"] = sentinel
    ranks.enter_act(data, 2)  # повторный вход не переписывает дату
    assert data["acts"]["2"]["started_at"] == sentinel


def test_enter_act_does_not_backdate_closed_act():
    from jedicoder import ranks, state as st
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    del data["acts"]["1"]["started_at"]
    ranks.enter_act(data, 1)
    assert "started_at" not in data["acts"]["1"]


def test_completed_acts_skips_a_key_that_is_not_an_act_number():
    """Ключ, правленный руками, не роняет подсчёт закрытых актов.

    completed_acts зовут и close_act (через rank_for), и Разбор. Упасть на
    чужом ключе значило бы уронить игру посреди хода из-за строки, которая
    ни на что не влияет.
    """
    state = {"acts": {
        "2": {"status": ranks.STATUS_DONE},
        "заметка": {"status": ranks.STATUS_DONE},
        "1": {"status": ranks.STATUS_DONE},
    }}
    assert ranks.completed_acts(state) == [1, 2]
    assert ranks.rank_for(state) == "padawan"

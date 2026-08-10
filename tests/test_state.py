import json
import os
import threading

import pytest

from jedicoder import state as st


def test_default_state_shape():
    data = st.default_state("abc123")
    assert data["schema_version"] == st.SCHEMA_VERSION
    assert data["padawan_id"] == "abc123"
    assert data["rank"] == "youngling"
    assert data["xp"] == 0
    assert data["dark_side"] == 0
    assert data["acts"] == {}
    assert data["artifacts"] == []
    assert data["pending_sync"] == []
    assert data["streak"] == {"current": 0, "best": 0, "last_commit_date": None}
    assert data["first_try"] == {"passed": 0, "attempted": 0}


def test_load_missing_returns_default(tmp_path):
    assert st.load(tmp_path / "nope.json")["rank"] == "youngling"


def test_save_then_load_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    data = st.default_state("abc123")
    data["xp"] = 42
    data["project"] = {"path": "/тест/проект"}
    st.save(data, path)
    assert st.load(path)["xp"] == 42
    assert st.load(path)["project"]["path"] == "/тест/проект"
    assert "\\u" not in path.read_text(encoding="utf-8")


def test_save_creates_backup_of_previous(tmp_path):
    path = tmp_path / "state.json"
    first = st.default_state("abc123")
    first["xp"] = 1
    st.save(first, path)
    second = st.default_state("abc123")
    second["xp"] = 2
    st.save(second, path)
    assert st.load(path)["xp"] == 2
    backup = json.loads(st.backup_path(path).read_text(encoding="utf-8"))
    assert backup["xp"] == 1


def test_save_leaves_no_temp_files(tmp_path):
    path = tmp_path / "state.json"
    st.save(st.default_state("abc123"), path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".state-")]
    assert leftovers == []


def test_failed_replace_keeps_original_intact(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    good = st.default_state("abc123")
    good["xp"] = 7
    st.save(good, path)

    def boom(src, dst):
        raise OSError("диск кончился")

    monkeypatch.setattr(os, "replace", boom)
    broken = st.default_state("abc123")
    broken["xp"] = 999
    with pytest.raises(OSError):
        st.save(broken, path)

    assert st.load(path)["xp"] == 7
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".state-")]
    assert leftovers == []


def test_corrupted_state_recovered_from_backup(tmp_path):
    path = tmp_path / "state.json"
    good = st.default_state("abc123")
    good["xp"] = 5
    st.save(good, path)
    later = st.default_state("abc123")
    later["xp"] = 6
    st.save(later, path)

    path.write_text("{это не json", encoding="utf-8")
    recovered = st.load(path)
    assert recovered["xp"] == 5
    assert st.corrupt_path(path).exists()


def test_corrupted_without_backup_returns_default(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("мусор", encoding="utf-8")
    assert st.load(path)["rank"] == "youngling"
    assert st.corrupt_path(path).exists()


def test_migrate_fills_missing_keys():
    old = {"schema_version": 1, "xp": 10, "streak": {"current": 3}}
    migrated = st.migrate(old)
    assert migrated["xp"] == 10
    assert migrated["streak"] == {"current": 3, "best": 0, "last_commit_date": None}
    assert migrated["first_try"] == {"passed": 0, "attempted": 0}
    assert migrated["acts"] == {}


def test_migrate_rejects_future_version():
    with pytest.raises(st.StateError, match="обнови плагин"):
        st.migrate({"schema_version": st.SCHEMA_VERSION + 1})


def test_load_non_dict_json_recovers(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert st.load(path)["rank"] == "youngling"


def test_new_padawan_id_is_unique_and_short():
    first, second = st.new_padawan_id(), st.new_padawan_id()
    assert first != second
    assert first.startswith("local-")
    assert len(first) <= 16


def test_migration_reopens_acknowledged_act1_idea():
    """Ack-закрытие 01-idea значило другое: «идея есть», а не «IDEA.md написан»."""
    old = st.default_state("local-old")
    old["schema_version"] = 1
    old["acts"] = {
        "1": {
            "status": "done",
            "completed_at": "2026-07-25T12:00:00Z",
            "quests": {
                "01-idea": {"status": "done", "attempts": 1, "acknowledged": True},
            },
        }
    }
    migrated = st.migrate(old)
    quest = migrated["acts"]["1"]["quests"]["01-idea"]
    assert quest["status"] != "done"
    assert quest.get("acknowledged") is not True
    assert migrated["acts"]["1"]["status"] != "done", (
        "акт с переоткрытым квестом не может считаться закрытым"
    )
    assert migrated["schema_version"] == st.SCHEMA_VERSION


def test_migration_keeps_script_closed_act1_idea():
    """Квест, закрытый проверкой, не трогаем — работа сделана по-настоящему."""
    old = st.default_state("local-old")
    old["schema_version"] = 1
    old["acts"] = {
        "1": {
            "status": "done",
            "quests": {"01-idea": {"status": "done", "attempts": 2}},
        }
    }
    migrated = st.migrate(old)
    assert migrated["acts"]["1"]["quests"]["01-idea"]["status"] == "done"
    assert migrated["acts"]["1"]["status"] == "done"


def test_migration_leaves_act2_alone():
    old = st.default_state("local-old")
    old["schema_version"] = 1
    old["acts"] = {
        "2": {
            "status": "done",
            "quests": {"06-pipeline": {"status": "done", "attempts": 1,
                                       "acknowledged": True}},
        }
    }
    migrated = st.migrate(old)
    assert migrated["acts"]["2"]["quests"]["06-pipeline"]["status"] == "done"


def test_already_v2_state_is_untouched():
    data = st.default_state("local-new")
    data["acts"] = {
        "1": {"status": "done",
              "quests": {"01-idea": {"status": "done", "attempts": 1,
                                     "acknowledged": True}}},
    }
    migrated = st.migrate(data)
    assert migrated["acts"]["1"]["quests"]["01-idea"]["status"] == "done", (
        "в состоянии версии 2 ack на 01-idea уже не мог появиться — не трогаем"
    )


def test_migration_handles_missing_acts_key():
    """Совсем старое состояние без единого акта не должно падать на миграции."""
    old = {"schema_version": 1}
    migrated = st.migrate(old)
    assert migrated["schema_version"] == st.SCHEMA_VERSION
    assert migrated["acts"] == {}


def test_migration_leaves_act1_without_idea_quest_alone():
    """В Акте 1 нет квеста 01-idea (например, начат только 02-one-evening) —
    миграции нечего снимать, и она не должна падать на отсутствии ключа."""
    old = st.default_state("local-old")
    old["schema_version"] = 1
    old["acts"] = {
        "1": {
            "status": "in_progress",
            "quests": {"02-one-evening": {"status": "done", "attempts": 1}},
        }
    }
    migrated = st.migrate(old)
    assert migrated["acts"]["1"]["quests"] == {
        "02-one-evening": {"status": "done", "attempts": 1}
    }
    assert migrated["acts"]["1"]["status"] == "in_progress"


def test_migration_recomputes_stale_rank_after_reopening_act1():
    """rank — записанное поле. Если его не пересчитать, падаван увидит на
    первом же status ранг «Искатель», выданный за Акт 1, который эта же
    миграция только что вернула в in_progress — состояние соврёт само себе."""
    old = st.default_state("local-old")
    old["schema_version"] = 1
    old["rank"] = "seeker"
    old["acts"] = {
        "1": {
            "status": "done",
            "quests": {
                "01-idea": {"status": "done", "attempts": 1, "acknowledged": True},
            },
        }
    }
    migrated = st.migrate(old)
    assert migrated["rank"] == "youngling"


def test_migration_leaves_notice_when_it_takes_the_rank_away():
    """Молчание — и есть дефект. Падаван, закрывший в v1 Акт 1 словом, а Акт 2
    честно, после обновления теряет два ранга. Решение верное (Акт 1 не
    пройден по-настоящему, цепочка рвётся), но человеку надо это сказать."""
    old = st.default_state("local-old")
    old["schema_version"] = 1
    old["rank"] = "padawan"
    old["acts"] = {
        "1": {
            "status": "done",
            "quests": {
                "01-idea": {"status": "done", "attempts": 1, "acknowledged": True},
            },
        },
        "2": {"status": "done", "quests": {}},
    }
    migrated = st.migrate(old)
    assert migrated["rank"] == "youngling"
    assert st.NOTICE_ACT1_REAL in migrated["notices"]


def test_migration_without_loss_leaves_no_notice():
    """Квест закрыт проверкой — ничего не отбирается, объяснять нечего."""
    old = st.default_state("local-old")
    old["schema_version"] = 1
    old["acts"] = {
        "1": {"status": "done", "quests": {"01-idea": {"status": "done",
                                                       "attempts": 2}}},
    }
    assert st.migrate(old)["notices"] == []


def test_migration_does_not_duplicate_notice():
    """Миграция крутится на каждом load, пока файл не переписан версией 2."""
    old = st.default_state("local-old")
    old["schema_version"] = 1
    old["acts"] = {
        "1": {
            "status": "done",
            "quests": {
                "01-idea": {"status": "done", "attempts": 1, "acknowledged": True},
            },
        },
    }
    once = st.migrate(old)
    once["schema_version"] = 1
    twice = st.migrate(once)
    assert twice["notices"] == [st.NOTICE_ACT1_REAL]


def _v2_save_with_closed_act1():
    """Форма настоящего сохранения автора, а не выдуманная.

    Снята с ~/.jedicoder/state.json.BOEVOE-2026-08-06: Акт 1 закрыт тремя
    квестами с первой попытки, Акт 2 закрыт следом, ранг padawan, XP 280.
    Выдуманная фикстура доказывала бы работу миграции на выдуманных данных.

    Единственное поле, заменённое на выдуманное, — `link_key`: это учётные
    данные привязки к боту, а репозиторий публикуется. Форму миграции оно не
    задаёт, тест лишь требует, чтобы ключ пережил переезд, — и любая строка
    доказывает это ровно так же, как боевая.
    """
    data = st.default_state("local-boevoe")
    data["schema_version"] = 2
    data["rank"] = "padawan"
    data["xp"] = 280
    data["dark_side"] = 12
    data["link_key"] = "migkey01"
    data["acts"] = {
        "1": {
            "status": "done",
            "started_at": "2026-08-01T14:05:11Z",
            "completed_at": "2026-08-01T20:59:15Z",
            "claude_md_sha": "",
            "quests": {
                "01-idea": {"status": "done", "attempts": 1},
                "02-hutt-filter": {"status": "done", "attempts": 1},
                "03c-who": {"status": "done", "attempts": 1},
            },
        },
        "2": {
            "status": "done",
            "quests": {"01-recipe": {"status": "done", "attempts": 1}},
        },
    }
    return data


def test_migration_v2_to_v3_renames_closed_quest_key():
    """Ключ квеста переехал под новый идентификатор вместе со значением.

    Без этой миграции закрытый квест читается как неначатый: реестр движка
    после переименования спрашивает про 02-one-evening, а в состоянии лежит
    прежний ключ — и падаван видит Акт 1 закрытым при незакрытом квесте.
    """
    migrated = st.migrate(_v2_save_with_closed_act1())
    quests = migrated["acts"]["1"]["quests"]
    assert quests["02-one-evening"] == {"status": "done", "attempts": 1}
    assert "02-hutt-filter" not in quests


def test_migration_v2_to_v3_keeps_everything_visible():
    """Миграция не отбирает у падавана ничего видимого — потому и notices пуст.

    Если этот тест когда-нибудь упадёт, add_notice обязан появиться: молчаливая
    потеря видимого прогресса и есть дефект, ради которого заведены notices.
    """
    before = _v2_save_with_closed_act1()
    migrated = st.migrate(before)
    assert migrated["rank"] == "padawan"
    assert migrated["xp"] == 280
    assert migrated["dark_side"] == 12
    assert migrated["link_key"] == "migkey01"
    assert migrated["acts"]["1"]["status"] == "done"
    assert migrated["acts"]["1"]["completed_at"] == "2026-08-01T20:59:15Z"
    assert migrated["acts"]["2"] == before["acts"]["2"]
    assert migrated["notices"] == []


def test_migration_v2_to_v3_leaves_untouched_save_alone():
    """Сохранение без обоих ключей — миграции нечего переименовывать."""
    data = st.default_state("local-fresh")
    data["schema_version"] = 2
    data["acts"] = {"1": {"status": "in_progress",
                          "quests": {"01-idea": {"status": "done",
                                                 "attempts": 1}}}}
    migrated = st.migrate(data)
    assert migrated["acts"]["1"]["quests"] == {
        "01-idea": {"status": "done", "attempts": 1}
    }


def test_migration_v2_to_v3_is_idempotent():
    """Повторный прогон на уже мигрированном состоянии — тождество."""
    once = st.migrate(_v2_save_with_closed_act1())
    twice = st.migrate(json.loads(json.dumps(once)))
    assert twice == once
    assert twice["schema_version"] == 3


def test_migration_v2_to_v3_does_not_overwrite_existing_new_key():
    """Новый ключ уже есть — старый не переезжает поверх него.

    Иначе переименование затёрло бы работу, сделанную уже после обновления.
    """
    data = _v2_save_with_closed_act1()
    data["acts"]["1"]["quests"]["02-one-evening"] = {
        "status": "done", "attempts": 3,
    }
    migrated = st.migrate(data)
    assert migrated["acts"]["1"]["quests"]["02-one-evening"]["attempts"] == 3
    assert "02-hutt-filter" not in migrated["acts"]["1"]["quests"]


def test_migration_v2_to_v3_renames_quest_in_pending_sync():
    """Очередь — аутбокс, а не журнал: бот этих строк ещё не видел.

    Оставить в неотправленном событии мёртвый идентификатор значит
    гарантированно испортить книгу ровно тому падавану, который был офлайн.
    """
    data = _v2_save_with_closed_act1()
    st.enqueue_event(data, "act_started", act=1)
    st.enqueue_event(data, "quest_completed", act=1, quest="01-idea",
                     payload={"attempts": 1})
    st.enqueue_event(data, "quest_completed", act=1, quest="02-hutt-filter",
                     payload={"attempts": 1})
    st.enqueue_event(data, "dark_side", payload={"total": 12})
    untouched = json.loads(json.dumps(
        [data["pending_sync"][0], data["pending_sync"][1],
         data["pending_sync"][3]]
    ))
    migrated = st.migrate(data)
    queue = migrated["pending_sync"]
    assert queue[2]["quest"] == "02-one-evening"
    assert queue[2]["payload"] == {"attempts": 1}
    assert [queue[0], queue[1], queue[3]] == untouched


def test_migration_v1_state_passes_through_both_steps():
    """Сохранение версии 1 проходит обе миграции подряд, в порядке номеров."""
    data = _v2_save_with_closed_act1()
    data["schema_version"] = 1
    data["acts"]["1"]["quests"]["01-idea"] = {
        "status": "done", "attempts": 1, "acknowledged": True,
    }
    migrated = st.migrate(data)
    # v1→v2 сняла ack-закрытие 01-idea и переоткрыла акт
    assert migrated["acts"]["1"]["quests"]["01-idea"]["status"] != "done"
    assert migrated["acts"]["1"]["status"] != "done"
    # v2→v3 всё равно переименовала ключ соседнего квеста
    assert "02-one-evening" in migrated["acts"]["1"]["quests"]
    assert "02-hutt-filter" not in migrated["acts"]["1"]["quests"]
    assert migrated["schema_version"] == 3


def test_migration_rejects_v4_state_loudly():
    """Откат плагина обязан отказать громко и по-русски, а не показать
    противоречивый экран: закрытый Акт 1 с неначатым квестом 02."""
    with pytest.raises(st.StateError, match="обнови плагин"):
        st.migrate({"schema_version": 4})


def test_load_migrates_v1_state_on_disk(tmp_path):
    """migrate() тестируется напрямую выше, но настоящий падаван идёт через
    load() с диска — эта дверь должна вести туда же."""
    path = tmp_path / "state.json"
    raw = st.default_state("local-old")
    raw["schema_version"] = 1
    raw["acts"] = {
        "1": {
            "status": "done",
            "quests": {
                "01-idea": {"status": "done", "attempts": 1, "acknowledged": True},
            },
        }
    }
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    loaded = st.load(path)
    assert loaded["schema_version"] == st.SCHEMA_VERSION
    quest = loaded["acts"]["1"]["quests"]["01-idea"]
    assert quest["status"] != "done"
    assert quest.get("acknowledged") is not True
    assert loaded["acts"]["1"]["status"] != "done"


def test_update_state_survives_concurrent_writers(tmp_path):
    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)

    def bump():
        for _ in range(15):
            with st.update_state(state_path) as data:
                data["xp"] = int(data.get("xp", 0)) + 1

    threads = [threading.Thread(target=bump) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert st.load(state_path)["xp"] == 90


def test_update_state_skips_save_when_body_raises(tmp_path):
    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)
    try:
        with st.update_state(state_path) as data:
            data["xp"] = 999
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert st.load(state_path)["xp"] == 0


def test_enqueue_event_shape():
    data = st.default_state()
    event = st.enqueue_event(
        data, "quest_completed", act=3, quest="01-launch",
        payload={"attempts": 2},
    )
    assert data["pending_sync"] == [event]
    assert event["type"] == "quest_completed"
    assert event["act"] == 3
    assert event["quest"] == "01-launch"
    assert event["payload"] == {"attempts": 2}
    assert len(event["client_id"]) == 32
    assert event["at"].endswith("Z") and "T" in event["at"]


def test_enqueue_event_client_ids_unique():
    data = st.default_state()
    ids = {st.enqueue_event(data, "dark_side")["client_id"] for _ in range(100)}
    assert len(ids) == 100


def test_enqueue_event_caps_queue_dropping_oldest():
    data = st.default_state()
    for i in range(st.PENDING_SYNC_CAP + 50):
        st.enqueue_event(data, "dark_side", payload={"n": i})
    queue = data["pending_sync"]
    assert len(queue) == st.PENDING_SYNC_CAP
    assert queue[0]["payload"]["n"] == 50
    assert queue[-1]["payload"]["n"] == st.PENDING_SYNC_CAP + 49

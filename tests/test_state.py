import json
import os
import threading
from pathlib import Path

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
    old = {"schema_version": st.SCHEMA_VERSION, "xp": 10, "streak": {"current": 3}}
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


def test_record_dark_side_writes_kind_and_date():
    data = st.default_state()
    log = st.record_dark_side(data, "env_staged", today="2026-09-06")
    assert log == [{"type": "env_staged", "date": "2026-09-06"}]
    assert data["dark_side_log"] == log


def test_record_dark_side_writes_one_entry_per_point():
    # «Одна запись на очко» — единственная форма, при которой счётчик и
    # журнал сходятся по числу: отправка .env стоит двух очков.
    data = st.default_state()
    log = st.record_dark_side(data, "env_staged", count=2, today="2026-09-06")
    assert log == [
        {"type": "env_staged", "date": "2026-09-06"},
        {"type": "env_staged", "date": "2026-09-06"},
    ]


def test_record_dark_side_dates_by_the_clock_when_not_told():
    # Ожидаемое считается своим путём (datetime против time.strftime в
    # коде), иначе тест повторил бы реализацию и не мог бы с ней спорить.
    from datetime import datetime, timezone

    data = st.default_state()
    (entry,) = st.record_dark_side(data, "root_login")
    assert entry["date"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert len(entry["date"]) == 10, "календарная дата, без времени"


def test_old_state_without_the_dark_side_log_loads(tmp_path):
    # Сохранение, записанное до появления журнала: поле доезжает дефолтом,
    # как остальные плоские списки, и версия схемы для этого не нужна.
    path = tmp_path / "state.json"
    old = st.default_state("local-test")
    del old["dark_side_log"]
    old["dark_side"] = 3
    path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    loaded = st.load(path)
    assert loaded["dark_side_log"] == []
    assert loaded["dark_side"] == 3
    assert loaded["schema_version"] == st.SCHEMA_VERSION


def test_dark_side_kinds_are_exactly_what_the_hooks_distinguish():
    # Перечень один на всю игру: Разбор читает эти же имена, второго
    # списка заводить нельзя.
    assert st.DARK_SIDE_KINDS == (
        "env_staged", "rm_outside_project", "root_login", "vague_prompt",
    )


def test_dark_side_entries_reads_the_log():
    data = st.default_state()
    st.record_dark_side(data, "vague_prompt", today="2026-09-06")
    assert st.dark_side_entries(data) == [
        {"type": "vague_prompt", "date": "2026-09-06"},
    ]


def test_dark_side_entries_survives_a_hand_edited_save():
    # Состояние правят руками — читатель обязан отдать то, что понял, и
    # промолчать об остальном, а не упасть на глазах у падавана.
    good = {"type": "root_login", "date": "2026-09-06"}
    assert st.dark_side_entries({}) == []
    assert st.dark_side_entries({"dark_side_log": "мусор"}) == []
    assert st.dark_side_entries(
        {"dark_side_log": [good, "мусор", {"type": 1, "date": None}, {}]}
    ) == [good]


def test_record_dark_side_survives_a_garbage_log_field():
    # Правка руками не должна ронять хук: журнал начинается заново.
    data = {"dark_side_log": "мусор"}
    log = st.record_dark_side(data, "root_login", today="2026-09-06")
    assert log == [{"type": "root_login", "date": "2026-09-06"}]
    assert data["dark_side_log"] == log


# --- Путь сохранения: JEDICODER_STATE_PATH -------------------------------
#
# Долг №0: переменную читали только хуки, а движок ходил в прибитый
# ~/.jedicoder/state.json. Расщеплённое состояние (хуки в одном файле,
# движок в другом) — худший исход, поэтому обе стороны обязаны считать
# путь одним и тем же куском кода.


def test_state_path_falls_back_to_home_without_the_variable(monkeypatch):
    # «Переменной нет — поведение прежнее, до байта»: путь называется
    # целиком, а не сверяется с той же константой, из которой посчитан.
    monkeypatch.delenv("JEDICODER_STATE_PATH", raising=False)
    assert st.state_path() == Path.home() / ".jedicoder" / "state.json"
    assert st.state_path() == st.STATE_PATH


def test_state_path_honours_the_variable(monkeypatch, tmp_path):
    target = tmp_path / "песочница" / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(target))
    assert st.state_path() == target


def test_state_path_is_read_at_every_call_not_at_import(monkeypatch, tmp_path):
    # Хук живёт отдельным процессом, а тест выставляет переменную уже
    # после импорта модуля: путь, посчитанный один раз, обоим достался бы
    # устаревшим.
    first, second = tmp_path / "первый.json", tmp_path / "второй.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(first))
    assert st.state_path() == first
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(second))
    assert st.state_path() == second


def test_save_and_load_without_a_path_follow_the_variable(monkeypatch, tmp_path):
    target = tmp_path / "песочница" / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(target))
    data = st.default_state("local-test")
    data["xp"] = 7
    st.save(data)
    assert target.exists(), "запись без пути ушла не туда, куда указано"
    assert st.load()["xp"] == 7


def test_update_state_without_a_path_follows_the_variable(monkeypatch, tmp_path):
    target = tmp_path / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(target))
    with st.update_state() as data:
        data["xp"] = 11
    assert json.loads(target.read_text(encoding="utf-8"))["xp"] == 11


def test_empty_variable_is_as_good_as_no_variable(monkeypatch):
    # Пустая строка — не «пиши в корень» и не «пиши в текущую папку»:
    # переменную выставили и не заполнили, поведение прежнее.
    monkeypatch.setenv("JEDICODER_STATE_PATH", "")
    assert st.state_path() == st.STATE_PATH


def test_tilde_in_the_variable_is_expanded(monkeypatch, tmp_path):
    # В settings.json и в CI нет оболочки, которая раскрыла бы тильду за
    # нас. Дело не в удобстве: нераскрытая тильда — путь относительный, а у
    # движка и хука разные текущие папки, и одно значение развело бы их по
    # разным файлам.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("JEDICODER_STATE_PATH", "~/своя/state.json")
    assert st.state_path() == tmp_path / "своя" / "state.json"
    assert st.state_path().is_absolute(), "иначе путь зависел бы от cwd"


def test_tilde_of_an_unknown_user_does_not_raise(monkeypatch):
    # Закон хуков: раскрыть не во что — берём как есть и не падаем.
    monkeypatch.setenv("JEDICODER_STATE_PATH", "~нетТакого/state.json")
    assert st.state_path() == Path("~нетТакого/state.json")


def test_relative_variable_is_relative_to_the_current_folder(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("JEDICODER_STATE_PATH", "состояние/state.json")
    st.save(st.default_state("local-test"))
    assert (tmp_path / "состояние" / "state.json").exists()


def test_the_suite_itself_never_aims_at_the_live_save():
    """Канарейка изоляции суита (`isolated_state` в conftest.py).

    Без неё регресс в state_path() возвращает суит к записи в боевое
    сохранение того, кто гоняет тесты, — и заметить это будет некому:
    остальные тесты передают путь сами и промолчат.
    """
    assert st.state_path() != Path.home() / ".jedicoder" / "state.json"

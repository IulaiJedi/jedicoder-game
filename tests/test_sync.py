"""Очередь событий для бота потока: движок, сеть, CLI."""

import http.server
import json
import threading

import pytest

from jedicoder import quests, ranks, state as st, sync


def _result(ok, countable=True):
    return quests.CheckResult(
        quest="01-x", kind=quests.KIND_SCRIPT, exit_code=0 if ok else 1,
        ok=ok, checks=[], stderr="", countable=countable,
    )


def _events(data, event_type):
    return [e for e in data.get("pending_sync", []) if e["type"] == event_type]


def test_check_success_enqueues_quest_completed():
    data = st.default_state()
    quests.record_attempt(data, 1, "01-x", _result(ok=True))
    (event,) = _events(data, "quest_completed")
    assert event["act"] == 1 and event["quest"] == "01-x"
    assert event["payload"]["attempts"] == 1
    assert event["payload"]["first_try"] is True
    assert event["payload"]["xp"] == data["xp"]
    assert event["payload"]["first_try_passed"] == 1
    assert event["payload"]["first_try_attempted"] == 1


def test_check_failure_enqueues_quest_failed():
    data = st.default_state()
    quests.record_attempt(data, 1, "01-x", _result(ok=False))
    (event,) = _events(data, "quest_failed")
    assert event["payload"] == {"attempts": 1}
    assert _events(data, "quest_completed") == []


def test_cannot_check_enqueues_nothing():
    data = st.default_state()
    quests.record_attempt(data, 1, "01-x", _result(ok=False, countable=False))
    assert data["pending_sync"] == []


def test_repeat_of_done_quest_enqueues_nothing():
    data = st.default_state()
    quests.record_attempt(data, 1, "01-x", _result(ok=True))
    quests.record_attempt(data, 1, "01-x", _result(ok=True))
    assert len(_events(data, "quest_completed")) == 1


def test_ack_enqueues_quest_completed_with_flag():
    data = st.default_state()
    quests.acknowledge(data, 2, "06-pipeline")
    (event,) = _events(data, "quest_completed")
    assert event["payload"]["acknowledged"] is True
    quests.acknowledge(data, 2, "06-pipeline")
    assert len(_events(data, "quest_completed")) == 1


def test_enter_act_enqueues_act_started_once():
    data = st.default_state()
    ranks.enter_act(data, 1)
    ranks.enter_act(data, 1)
    events = _events(data, "act_started")
    assert len(events) == 1 and events[0]["act"] == 1


def test_close_act_enqueues_rank_up_only_on_change():
    data = st.default_state()
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    (event,) = _events(data, "rank_up")
    assert event["payload"]["rank"] == data["rank"] == "seeker"
    ranks.close_act(data, 1)  # повторное закрытие ранга не меняет
    assert len(_events(data, "rank_up")) == 1


class _StubBot(http.server.BaseHTTPRequestHandler):
    status = 200
    requests = []
    # Симулирует ответ бота на неизвестный/уже сгоревший link_key: тело
    # непустой пачки, но accepted+known == 0 — контракт различает этот
    # случай от честного приёма без парсинга ответа как раньше.
    unknown_key = False

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).requests.append(payload)
        if type(self).status == 200:
            if type(self).unknown_key:
                body = json.dumps({"accepted": 0, "known": 0}).encode("utf-8")
            else:
                body = json.dumps(
                    {"accepted": len(payload.get("events", [])), "known": 0}
                ).encode("utf-8")
        else:
            body = b"{}"
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_bot(monkeypatch):
    _StubBot.requests = []
    _StubBot.status = 200
    _StubBot.unknown_key = False
    server = http.server.HTTPServer(("127.0.0.1", 0), _StubBot)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv(
        "JEDICODER_SYNC_URL",
        "http://127.0.0.1:{}/api/events".format(server.server_port),
    )
    yield _StubBot
    server.shutdown()


def _linked_state(tmp_path, events=0):
    state_path = tmp_path / "state.json"
    data = st.default_state()
    data["link_key"] = "testkey1"
    for i in range(events):
        st.enqueue_event(data, "dark_side", payload={"n": i})
    st.save(data, state_path)
    return state_path


def test_flush_sends_chunks_and_drains(tmp_path, stub_bot):
    state_path = _linked_state(tmp_path, events=250)
    sent, dropped, remaining, status = sync.flush(state_path)
    assert (sent, dropped, remaining, status) == (250, 0, 0, "ok")
    assert [len(r["events"]) for r in stub_bot.requests] == [100, 100, 50]
    assert stub_bot.requests[0]["link_key"] == "testkey1"
    assert st.load(state_path)["pending_sync"] == []


def test_flush_keeps_queue_on_server_error(tmp_path, stub_bot):
    stub_bot.status = 500
    state_path = _linked_state(tmp_path, events=3)
    sent, dropped, remaining, status = sync.flush(state_path)
    assert (sent, status) == (0, "error")
    assert len(st.load(state_path)["pending_sync"]) == 3


def test_flush_keeps_queue_when_unreachable(tmp_path, monkeypatch):
    monkeypatch.setenv("JEDICODER_SYNC_URL", "http://127.0.0.1:1/api/events")
    state_path = _linked_state(tmp_path, events=3)
    sent, dropped, remaining, status = sync.flush(state_path)
    assert status == "error"
    assert len(st.load(state_path)["pending_sync"]) == 3


def test_flush_drops_chunk_on_400(tmp_path, stub_bot):
    stub_bot.status = 400
    state_path = _linked_state(tmp_path, events=3)
    sent, dropped, remaining, status = sync.flush(state_path)
    assert (sent, dropped, remaining, status) == (0, 3, 0, "ok")
    assert st.load(state_path)["pending_sync"] == []


def test_flush_without_key_sends_nothing(tmp_path, stub_bot):
    state_path = tmp_path / "state.json"
    data = st.default_state()
    st.enqueue_event(data, "dark_side")
    st.save(data, state_path)
    sync.flush(state_path)
    assert stub_bot.requests == []
    assert len(st.load(state_path)["pending_sync"]) == 1


def test_maybe_flush_never_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("JEDICODER_SYNC_URL", "http://127.0.0.1:1/x")
    state_path = _linked_state(tmp_path, events=1)
    sync.maybe_flush(state_path)  # не бросает
    assert len(st.load(state_path)["pending_sync"]) == 1


def test_flush_reports_unknown_key_and_keeps_queue(tmp_path, stub_bot):
    """Неизвестный link_key: бот отвечает 200 с нулями на непустую пачку —
    это не то же самое, что честный приём, и очередь не должна вычёркиваться
    навсегда на слово бота, которое на самом деле значит "я тебя не знаю".
    """
    stub_bot.unknown_key = True
    state_path = _linked_state(tmp_path, events=3)
    sent, dropped, remaining, status = sync.flush(state_path)
    assert (sent, dropped, remaining, status) == (0, 0, 3, "unknown_key")
    assert len(st.load(state_path)["pending_sync"]) == 3


@pytest.fixture
def paths(tmp_path, content_root, quests_root):
    return {
        "state_path": tmp_path / "state.json",
        "content_root": content_root,
        "quests_root": quests_root,
    }


def run(argv, paths, capsys):
    import jedicoder.cli as cli
    code = cli.main(argv, **paths)
    return code, capsys.readouterr().out


def test_link_stores_key_and_sends_linked(paths, capsys, stub_bot):
    code, out = run(["link", "testkey1"], paths, capsys)
    assert code == 0
    assert "привязан" in out
    assert st.load(paths["state_path"])["link_key"] == "testkey1"
    sent_types = [e["type"] for r in stub_bot.requests for e in r["events"]]
    assert "linked" in sent_types
    (linked,) = [e for r in stub_bot.requests for e in r["events"]
                 if e["type"] == "linked"]
    assert linked["payload"]["rank"] == "youngling"
    assert "padawan_id" in linked["payload"]


def test_link_offline_still_succeeds(paths, capsys, monkeypatch):
    monkeypatch.setenv("JEDICODER_SYNC_URL", "http://127.0.0.1:1/x")
    code, out = run(["link", "testkey1"], paths, capsys)
    assert code == 0
    assert "недоступен" in out
    assert st.load(paths["state_path"])["link_key"] == "testkey1"


def test_link_rejects_garbage(paths, capsys):
    code, out = run(["link", "плохой ключ"], paths, capsys)
    assert code == 1


def test_sync_without_key_refuses(paths, capsys):
    code, out = run(["sync"], paths, capsys)
    assert code == 1 and "не привязан" in out


def test_commands_flush_queue_automatically(paths, capsys, stub_bot):
    run(["link", "testkey1"], paths, capsys)
    stub_bot.requests = []
    run(["project", "db", "yes"], paths, capsys)
    run(["track", "craftsman"], paths, capsys)
    # смена трека шлёт свежий снапшот паспорта повторным linked
    sent_types = [e["type"] for r in stub_bot.requests for e in r["events"]]
    assert "linked" in sent_types
    assert st.load(paths["state_path"])["pending_sync"] == []


def test_offline_commands_stay_fast_and_green(paths, capsys, monkeypatch):
    monkeypatch.setenv("JEDICODER_SYNC_URL", "http://127.0.0.1:1/x")
    run(["link", "testkey1"], paths, capsys)
    code, _ = run(["project", "db", "yes"], paths, capsys)
    assert code == 0  # линкованный, но офлайн — игра не замечает


def test_unlinked_game_never_touches_network(paths, capsys, stub_bot):
    run(["project", "db", "yes"], paths, capsys)
    run(["track", "craftsman"], paths, capsys)
    assert stub_bot.requests == []


# --- Один ключ вместо двух кодов (#84) ----------------------------------
#
# Сквозной путь со стороны игры: приложение назвало Ключ Голокрона запуску →
# хук старта сессии записал его как связь с ботом → события игры уходят боту
# с этим ключом. Хук гоняется отдельным процессом, как его запускает Claude
# Code; дальше — та же дверь, что у человека, команды CLI.

GOLOKRON_KEY = "GK-3333-3333-333T"


def _session_from_the_app(paths, tmp_path, key=GOLOKRON_KEY):
    import os
    import subprocess

    from conftest import ROOT

    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    result = subprocess.run(
        ["python3", str(ROOT / "plugin" / "hooks" / "session_start.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
        capture_output=True, text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(home),
            "JEDICODER_STATE_PATH": str(paths["state_path"]),
            "JEDICODER_PLUGIN_ROOT_FILE": str(home / "plugin_root"),
            "CLAUDE_PLUGIN_ROOT": str(ROOT / "plugin"),
            "JEDICODER_GOLOKRON_KEY": key,
            # Хук в сеть не ходит; адрес подставного бота — на случай, если начнёт.
            "JEDICODER_SYNC_URL": os.environ.get("JEDICODER_SYNC_URL", "http://127.0.0.1:1/x"),
        },
    )
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""


def test_golokron_key_carries_the_game_events_to_the_bot(paths, capsys, stub_bot, tmp_path):
    _session_from_the_app(paths, tmp_path)
    assert stub_bot.requests == [], "старт сессии сеть не трогает"

    code, _ = run(["project", "db", "yes"], paths, capsys)
    assert code == 0
    run(["enter", "1"], paths, capsys)

    assert stub_bot.requests, "с ключом Голокрона события обязаны уйти боту"
    assert {request["link_key"] for request in stub_bot.requests} == {GOLOKRON_KEY}
    sent_types = [e["type"] for r in stub_bot.requests for e in r["events"]]
    assert "linked" in sent_types
    assert "act_started" in sent_types
    assert st.load(paths["state_path"])["pending_sync"] == []


def test_what_goes_to_the_bot_with_the_golokron_key(paths, capsys, stub_bot, tmp_path, project):
    """Экран ключа в приложении обещает: бот видит путь, команды и файлы
    проекта ему не уходят. Здесь это обещание меряется по настоящей пачке."""
    folder = project(files={"IDEA.md": "секретная идея\n"})
    _session_from_the_app(paths, tmp_path)
    run(["project", "path", str(folder)], paths, capsys)
    run(["enter", "1"], paths, capsys)
    run(["check", "1", "01-folder"], paths, capsys)

    assert stub_bot.requests
    for request in stub_bot.requests:
        assert set(request) == {"link_key", "events"}
        for event in request["events"]:
            assert set(event) == {"client_id", "type", "act", "quest", "at", "payload"}
    wire = json.dumps(stub_bot.requests, ensure_ascii=False)
    assert str(folder) not in wire
    assert folder.name not in wire
    assert "секретная идея" not in wire


def test_golokron_key_the_bot_does_not_know_leaves_the_game_alone(paths, capsys, stub_bot, tmp_path):
    # Ключ без владельца у бота (выдан вручную, из прежней продажи): бот
    # отвечает отказом, а игра идёт как шла — события ждут в очереди.
    stub_bot.unknown_key = True
    _session_from_the_app(paths, tmp_path)

    code, out = run(["project", "db", "yes"], paths, capsys)
    assert code == 0
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "Акт 1" in out
    assert len(st.load(paths["state_path"])["pending_sync"]) >= 2


def test_link_with_the_old_code_still_wins_over_the_golokron_key(paths, capsys, stub_bot, tmp_path):
    # Игра в терминале и прежний код: `link <код>` работает как работал и
    # ключу из запуска не уступает.
    run(["link", "testkey1"], paths, capsys)
    _session_from_the_app(paths, tmp_path)
    stub_bot.requests = []

    run(["enter", "1"], paths, capsys)

    assert st.load(paths["state_path"])["link_key"] == "testkey1"
    assert {request["link_key"] for request in stub_bot.requests} == {"testkey1"}


def test_project_url_enqueues_product_deployed(paths, capsys, monkeypatch):
    monkeypatch.setenv("JEDICODER_SYNC_URL", "http://127.0.0.1:1/x")
    run(["project", "url", "https://example.com"], paths, capsys)
    data = st.load(paths["state_path"])
    (event,) = [e for e in data["pending_sync"] if e["type"] == "product_deployed"]
    assert event["payload"] == {"url": "https://example.com"}


def test_queue_never_leaks_project_path(paths, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("JEDICODER_SYNC_URL", "http://127.0.0.1:1/x")
    project_dir = tmp_path / "секретный-проект"
    project_dir.mkdir()
    run(["project", "path", str(project_dir)], paths, capsys)
    run(["project", "url", "https://example.com"], paths, capsys)
    data = st.load(paths["state_path"])
    dump = json.dumps(data["pending_sync"], ensure_ascii=False)
    assert str(project_dir) not in dump
    assert "секретный" not in dump


def test_sync_unknown_key_exits_1_and_keeps_queue(paths, capsys, stub_bot):
    """Промах: раньше неизвестный ключ тихо дренировал очередь и sync
    рапортовал успех — события терялись навсегда. Явный sync обязан выйти
    с кодом 1, назвать причину (ключ) и не вычёркивать пачку.
    """
    run(["link", "testkey1"], paths, capsys)
    stub_bot.unknown_key = True
    # смена трека кладёт свежий 'linked' в очередь — есть что не потерять
    run(["track", "craftsman"], paths, capsys)
    before = list(st.load(paths["state_path"])["pending_sync"])
    assert before  # автослив после track тоже не должен был её осушить

    code, out = run(["sync"], paths, capsys)

    assert code == 1
    assert "ключ" in out
    after = st.load(paths["state_path"])["pending_sync"]
    assert after == before


def test_link_unknown_key_exits_1_but_records_key_and_keeps_queue(paths, capsys, stub_bot):
    stub_bot.unknown_key = True

    code, out = run(["link", "testkey1"], paths, capsys)

    assert code == 1
    assert "не узнал" in out
    data = st.load(paths["state_path"])
    assert data["link_key"] == "testkey1"
    assert any(e["type"] == "linked" for e in data["pending_sync"])

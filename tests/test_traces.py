"""Следы: режим плана и чистый лист (ADR-0020 в репозитории сайта, #101).

След — запись в сохранении о действии, которого нет в папке проекта. Пишет
хук игровой сессии, проверке его отдаёт команда игры, судит проверка.

Швы. Хук — процессом, той же дверью, что Claude Code, на данных формы из
живого замера (`docs/research/2026-10-13-act2-claude-code-facts.md`,
Claude Code 2.1.296). Сквозной проход — командами игры и теми же хуками:
след в сохранение тест не подсаживает нигде, кроме тестов самих функций
`state.py`. Следы квеста «Покажи» и пометка акта — `tests/test_show_traces.py`
(#102); вторая форма «Чистого листа» — там же, проходом до него командами.
"""
import json
from pathlib import Path

import pytest

from jedicoder import acts, cli, game_session, quests, ranks
from jedicoder import state as st
from test_act2_checks import MEMORY_OK
from test_act2_entry import entered, game  # noqa: F401 — фикстуры
from test_bash_guard import run_hook
from test_human_screens import machine_words

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "plugin" / "hooks"

HOOK = "traces.py"
#: Сессия, в которой игру уже позвали, и её преемница после `/clear`.
GAME = "301632d2-112c-4038-9a4e-7ee89db50867"
AFTER_CLEAR = "f07a92aa-0000-4000-8000-000000000001"
PLAN_TEXT = "# План: создать hello.txt\n\n## Изменения\n- Создать файл."


# --- данные хуков, как их присылает Claude Code ------------------------------

def plan_shown(session_id=GAME, cwd="/tmp/chuzhaya"):
    """Перед экраном одобрения: режим ещё `plan`."""
    return {
        "hook_event_name": "PreToolUse", "session_id": session_id,
        "permission_mode": "plan", "tool_name": "ExitPlanMode",
        "tool_input": {"plan": PLAN_TEXT}, "tool_use_id": "toolu_01",
        "cwd": str(cwd), "transcript_path": "/tmp/t.jsonl",
    }


def plan_approved(session_id=GAME, cwd="/tmp/chuzhaya",
                  mode="bypassPermissions"):
    """Enter на первой строке экрана одобрения: инструмент выполнился."""
    return {
        "hook_event_name": "PostToolUse", "session_id": session_id,
        "permission_mode": mode, "tool_name": "ExitPlanMode",
        "tool_input": {"plan": PLAN_TEXT},
        "tool_response": {"plan": PLAN_TEXT, "isAgent": False},
        "tool_use_id": "toolu_01", "duration_ms": 4000,
        "cwd": str(cwd), "transcript_path": "/tmp/t.jsonl",
    }


def clear_end(session_id=GAME, cwd="/tmp/chuzhaya"):
    """`/clear`: прежний разговор кончился — идентификатор ещё прежний."""
    return {
        "hook_event_name": "SessionEnd", "reason": "clear",
        "session_id": session_id, "cwd": str(cwd),
        "transcript_path": "/tmp/t.jsonl",
    }


def clear_start(session_id=AFTER_CLEAR, cwd="/tmp/chuzhaya"):
    """`/clear`: новый разговор — идентификатор новый, режима в данных нет."""
    return {
        "hook_event_name": "SessionStart", "source": "clear",
        "session_id": session_id, "cwd": str(cwd),
        "transcript_path": "/tmp/t2.jsonl",
    }


@pytest.fixture
def save(tmp_path):
    """Сохранение того, кто играет; сессия GAME в нём записана игровой."""
    path = tmp_path / "state.json"
    data = st.default_state("local-test")
    data[game_session.SESSIONS_KEY] = [GAME]
    st.save(data, path)
    return path


def fire(save, payload, **env):
    """Позвать хук и убедиться, что он молчит и ничего не блокирует."""
    done = run_hook(HOOK, payload, dict({"JEDICODER_STATE_PATH": str(save)}, **env))
    assert done.returncode == 0, done.stderr
    assert done.stdout == "" and done.stderr == ""
    return done


def untouched(save):
    return (save.stat().st_mtime_ns, save.read_bytes())


# --- запись и чтение в state.py ----------------------------------------------

def test_the_list_of_traces_is_one_and_complete():
    assert st.TRACE_KINDS == (
        "plan_approved", "file_shown", "image_shown", "cleared", "hook_word",
    )
    assert st.default_state()[st.TRACES_KEY] == {}


def test_trace_is_absent_until_recorded_and_stays_after():
    state = st.default_state()
    assert st.trace(state, st.TRACE_PLAN_APPROVED) is None
    assert st.record_trace(state, st.TRACE_PLAN_APPROVED, today="2026-10-13") is True
    assert st.trace(state, st.TRACE_PLAN_APPROVED) == {"date": "2026-10-13"}
    # Повтор действия ничего не меняет: день остаётся первым.
    assert st.record_trace(state, st.TRACE_PLAN_APPROVED, today="2026-10-14") is False
    assert st.trace(state, st.TRACE_PLAN_APPROVED) == {"date": "2026-10-13"}
    assert st.trace(state, st.TRACE_CLEARED) is None


def test_a_mark_appears_and_never_goes_away():
    state = st.default_state()
    st.record_trace(state, st.TRACE_CLEARED, today="2026-10-13")
    assert st.TRACE_AFTER_MEMORY not in st.trace(state, st.TRACE_CLEARED)
    marks = {st.TRACE_AFTER_MEMORY: True}
    assert st.record_trace(state, st.TRACE_CLEARED, marks) is True
    assert st.trace(state, st.TRACE_CLEARED)[st.TRACE_AFTER_MEMORY] is True
    assert st.record_trace(state, st.TRACE_CLEARED) is False
    assert st.record_trace(state, st.TRACE_CLEARED, {st.TRACE_AFTER_MEMORY: False}) is False
    assert st.trace(state, st.TRACE_CLEARED)[st.TRACE_AFTER_MEMORY] is True


def test_a_name_outside_the_list_is_a_bug_of_the_caller():
    with pytest.raises(ValueError):
        st.record_trace(st.default_state(), "plan_aproved")


@pytest.mark.parametrize("garbage", [None, [], "да", 7, {"plan_approved": "yes"},
                                     {"plan_approved": ["x"]}])
def test_garbage_in_the_save_reads_as_no_trace(garbage):
    state = {st.TRACES_KEY: garbage}
    assert st.trace(state, st.TRACE_PLAN_APPROVED) is None
    assert st.trace(None, st.TRACE_PLAN_APPROVED) is None
    # И запись поверх мусора не падает.
    assert st.record_trace(state, st.TRACE_PLAN_APPROVED, today="2026-10-13") is True
    assert st.trace(state, st.TRACE_PLAN_APPROVED) == {"date": "2026-10-13"}


def test_an_old_save_gets_the_empty_form_without_a_schema_bump(tmp_path):
    path = tmp_path / "state.json"
    data = st.default_state("p")
    del data[st.TRACES_KEY]
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = st.load(path)
    assert loaded[st.TRACES_KEY] == {} and loaded["schema_version"] == 4


def test_trace_names_are_not_spelled_out_outside_state_py():
    """Литерал имени следа на месте вызова запрещён — только константа."""
    offenders = []
    for folder in (ROOT / "plugin" / "lib" / "jedicoder", HOOKS):
        for path in sorted(folder.glob("*.py")):
            if path.name == "state.py":
                continue
            text = path.read_text(encoding="utf-8")
            for kind in st.TRACE_KINDS:
                for quote in ('"', "'"):
                    if quote + kind + quote in text:
                        offenders.append("{}: {}".format(path.name, kind))
    assert offenders == []


# --- хук: план одобрен --------------------------------------------------------

def test_approved_plan_leaves_the_trace(save):
    fire(save, plan_approved())
    data = st.load(save)
    assert st.trace(data, st.TRACE_PLAN_APPROVED) == {"date": st.today_utc()}
    assert st.trace(data, st.TRACE_CLEARED) is None


def test_approval_with_manual_edits_is_an_approval_too(save):
    """Вторая строка экрана: план одобрен, режим стал с вопросами."""
    fire(save, plan_approved(mode="default"))
    assert st.trace(st.load(save), st.TRACE_PLAN_APPROVED) is not None


def test_a_plan_only_shown_is_not_an_approved_plan(save):
    """Отказ от плана: поправка третьей строкой, Esc, выход по Shift+Tab.

    Замер: во всех трёх случаях инструмент не выполняется, и ни одно
    событие после экрана одобрения о плане не говорит. Хуки видят показ
    плана, новую правку файла плана в режиме плана, запрос человека в другом
    режиме и конец хода — следа не даёт ничто из этого. На эти события
    хук и не подписан (`hooks.json`, тест ниже); здесь стережётся, что он
    промолчит, даже если его на них позовут.
    """
    before = untouched(save)
    fire(save, plan_shown())
    fire(save, {
        "hook_event_name": "PreToolUse", "session_id": GAME,
        "permission_mode": "plan", "tool_name": "Write",
        "tool_input": {"file_path": "/home/u/.claude/plans/p.md", "content": "x"},
        "cwd": "/tmp/chuzhaya",
    })
    fire(save, {
        "hook_event_name": "UserPromptSubmit", "session_id": GAME,
        "permission_mode": "bypassPermissions", "prompt": "скажи одно слово: да",
        "cwd": "/tmp/chuzhaya",
    })
    fire(save, {
        "hook_event_name": "Stop", "session_id": GAME,
        "permission_mode": "bypassPermissions", "cwd": "/tmp/chuzhaya",
    })
    assert untouched(save) == before


def test_a_tool_that_reports_plan_mode_still_on_is_not_an_approval(save):
    fire(save, plan_approved(mode="plan"))
    data = st.load(save)
    assert data[st.TRACES_KEY] == {}
    assert st.permission_mode(data) == "plan"


def test_another_tool_leaves_no_trace(save):
    before = untouched(save)
    payload = plan_approved()
    payload["tool_name"] = "Write"
    fire(save, payload)
    assert untouched(save) == before


def test_a_repeated_approval_does_not_rewrite_the_save(save):
    fire(save, plan_approved())
    before = untouched(save)
    fire(save, plan_approved())
    assert untouched(save) == before


def test_approval_tells_the_game_the_mode_the_session_is_left_in(save):
    """После одобрения сессия в другом режиме, и игра обязана знать каком:
    по второй строке экрана человек попадает в режим с вопросами."""
    with st.update_state(save) as data:
        st.note_permission_mode(data, "plan")
    fire(save, plan_approved(mode="default"))
    assert st.permission_mode(st.load(save)) == "default"
    # У `/clear` режима в данных нет — известный не стирается.
    fire(save, clear_end())
    fire(save, clear_start(session_id=GAME))
    assert st.permission_mode(st.load(save)) == "default"


def test_a_foreign_session_does_not_tell_its_mode_through_this_hook(save):
    with st.update_state(save) as data:
        st.note_permission_mode(data, "bypassPermissions")
    before = untouched(save)
    fire(save, plan_approved(session_id="S-work", mode="default"))
    assert untouched(save) == before


# --- хук: чистый лист ---------------------------------------------------------

def _close_memory(save):
    """Закрыть «Память проекта» записью движка — для тестов самого хука."""
    with st.update_state(save) as data:
        quests.acknowledge(data, *acts.MEMORY_QUEST)


def test_clear_leaves_the_trace_by_the_end_of_the_old_conversation(save):
    """Игру позвали в чужой папке: игровой сессию знает только прежний
    идентификатор, и приходит он с концом разговора."""
    fire(save, clear_end())
    assert st.trace(st.load(save), st.TRACE_CLEARED) == {"date": st.today_utc()}


def test_the_new_conversation_of_a_foreign_folder_is_not_a_game_one(save):
    before = untouched(save)
    fire(save, clear_start())
    assert untouched(save) == before


def test_clear_leaves_the_trace_by_the_start_inside_the_project_folder(
        save, tmp_path):
    """Вторая опора: конец разговора не успел — старт нового в папке проекта."""
    proj = tmp_path / "proj"
    proj.mkdir()
    with st.update_state(save) as data:
        data["project"]["path"] = str(proj)
        data[game_session.SESSIONS_KEY] = []
    fire(save, clear_start(cwd=proj))
    assert st.trace(st.load(save), st.TRACE_CLEARED) is not None


def test_clear_inside_the_app_leaves_the_trace(save):
    with st.update_state(save) as data:
        data[game_session.SESSIONS_KEY] = []
    fire(save, clear_start(), JEDICODER_GOLOKRON="1")
    assert st.trace(st.load(save), st.TRACE_CLEARED) is not None


def test_clear_remembers_whether_the_memory_was_written_by_then(save):
    fire(save, clear_end())
    assert st.TRACE_AFTER_MEMORY not in st.trace(st.load(save), st.TRACE_CLEARED)
    _close_memory(save)
    # Квест закрылся позже — прежний `/clear` от этого «после» не стал.
    assert st.TRACE_AFTER_MEMORY not in st.trace(st.load(save), st.TRACE_CLEARED)
    fire(save, clear_end())
    assert st.trace(st.load(save), st.TRACE_CLEARED)[st.TRACE_AFTER_MEMORY] is True


@pytest.mark.parametrize("payload", [
    dict(clear_end(), reason="logout"),
    dict(clear_end(), reason="prompt_input_exit"),
    dict(clear_end(), reason="other"),
    dict(clear_start(session_id=GAME), source="startup"),
    dict(clear_start(session_id=GAME), source="resume"),
    dict(clear_start(session_id=GAME), source="compact"),
])
def test_other_ends_and_starts_are_not_a_clear(save, payload):
    before = untouched(save)
    fire(save, payload)
    assert untouched(save) == before


# --- только в игровой сессии, и закон хуков -----------------------------------

@pytest.mark.parametrize("payload", [
    plan_approved(session_id="S-work"), clear_end(session_id="S-work"),
    clear_start(session_id="S-work"),
])
def test_outside_a_game_session_there_is_no_trace_and_the_save_is_untouched(
        save, payload):
    before = untouched(save)
    fire(save, payload)
    assert untouched(save) == before
    assert st.trace(st.load(save), st.TRACE_PLAN_APPROVED) is None


def test_the_hook_does_not_start_a_game_for_someone_who_is_not_playing(tmp_path):
    """Приложение открыто, а игру ещё не начинали: сохранение хук не заводит."""
    path = tmp_path / "state.json"
    for payload in (plan_approved(), clear_end(), clear_start()):
        fire(path, payload, JEDICODER_GOLOKRON="1")
    # Ни сохранения, ни файла замка рядом: на диске не появилось ничего.
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("raw", [
    "", "не json", "[]", "null", '"строка"', "{}",
    '{"hook_event_name": 7}', '{"hook_event_name": "PostToolUse"}',
    '{"hook_event_name": "PostToolUse", "tool_name": ["ExitPlanMode"]}',
    '{"hook_event_name": "SessionEnd", "reason": {"a": 1}, "session_id": 5}',
    '{"hook_event_name": "SessionStart", "source": "clear", "cwd": 9}',
])
def test_garbage_on_the_input_is_silence(save, raw):
    import subprocess
    import sys

    before = untouched(save)
    done = subprocess.run(
        [sys.executable, str(HOOKS / HOOK)], input=raw, capture_output=True,
        text=True, timeout=30,
        env=dict(__import__("os").environ, JEDICODER_STATE_PATH=str(save)),
    )
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")
    assert untouched(save) == before


def test_a_broken_save_does_not_break_the_hook(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{не json", encoding="utf-8")
    for payload in (plan_approved(), clear_end()):
        fire(path, payload, JEDICODER_GOLOKRON="1")


def test_hooks_json_calls_the_trace_hook_on_its_three_events():
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]

    def matchers(event):
        return [
            entry.get("matcher") for entry in config.get(event, ())
            if any(HOOK in hook["command"] for hook in entry["hooks"])
        ]

    assert matchers("PostToolUse") == ["ExitPlanMode"]
    assert matchers("SessionEnd") == ["clear"]
    assert matchers("SessionStart") == ["clear"]
    # Хук старта сессии остался на своём месте и со своими событиями.
    assert any(
        "session_start.py" in hook["command"] and "startup" in entry["matcher"]
        for entry in config["SessionStart"] for hook in entry["hooks"]
    )


# --- команда игры отдаёт след проверке ----------------------------------------

def _trace_env(data):
    env = cli._env_for(data, 2)
    return {name: value for name, value in env.items()
            if name.startswith(quests.TRACE_ENV_PREFIX)}


def test_every_trace_has_the_mark_the_check_waits_for():
    assert set(st.TRACE_MARK) == set(st.TRACE_KINDS)
    assert st.TRACE_MARK[st.TRACE_CLEARED] == st.TRACE_AFTER_MEMORY
    for kind in (st.TRACE_PLAN_APPROVED, st.TRACE_FILE_SHOWN, st.TRACE_IMAGE_SHOWN):
        assert st.TRACE_MARK[kind] == st.TRACE_IN_ACT


def test_env_for_carries_every_marked_trace_and_nothing_else():
    data = st.default_state()
    assert _trace_env(data) == {}
    kinds = (st.TRACE_PLAN_APPROVED, st.TRACE_FILE_SHOWN, st.TRACE_IMAGE_SHOWN)
    for kind in kinds:
        st.record_trace(data, kind)
    # Сделано до входа в акт: след есть, проверке он не уходит.
    assert _trace_env(data) == {}
    for kind in kinds:
        st.record_trace(data, kind, {st.TRACE_IN_ACT: True})
    assert _trace_env(data) == {
        "JEDICODER_TRACE_PLAN_APPROVED": "yes",
        "JEDICODER_TRACE_FILE_SHOWN": "yes",
        "JEDICODER_TRACE_IMAGE_SHOWN": "yes",
    }


def test_env_for_gives_the_clear_only_when_it_came_after_the_memory():
    data = st.default_state()
    st.record_trace(data, st.TRACE_CLEARED)
    assert _trace_env(data) == {}
    st.record_trace(data, st.TRACE_CLEARED, {st.TRACE_AFTER_MEMORY: True})
    assert _trace_env(data) == {"JEDICODER_TRACE_CLEARED": "yes"}


def test_env_for_survives_garbage_in_the_traces():
    data = st.default_state()
    data[st.TRACES_KEY] = {
        "cleared": {"after_memory": "yes"}, "plan_approved": 1,
        "file_shown": {"in_act": "yes"}, "image_shown": {"in_act": 1},
    }
    assert _trace_env(data) == {}


def test_a_named_folder_inherited_from_the_shell_does_not_count(
        quests_root, project, monkeypatch):
    """Приставка `JEDICODER_PROJECT_NAMED=yes` перед командой квест «Папка»
    не закрывает: что папку назвал человек, знает только команда игры."""
    proj = project()
    env = {"JEDICODER_PROJECT_PATH": str(proj)}
    monkeypatch.setenv("JEDICODER_PROJECT_NAMED", "yes")
    result = quests.run_check(quests_root, "act1-znakomstvo", "01-folder", proj,
                              env_extra=env)
    assert result.exit_code == quests.EXIT_FAIL
    result = quests.run_check(
        quests_root, "act1-znakomstvo", "01-folder", proj,
        env_extra=dict(env, JEDICODER_PROJECT_NAMED="yes"),
    )
    assert result.ok is True


# --- сквозной проход: команды игры и хуки, сохранение не засевается -------------

def hook(game, payload):
    """Хук той же сессии, что игра: пишет в её сохранение."""
    return fire(game.state_path, payload)


def test_plan_quest_closes_after_the_hooks_saw_an_approved_plan(entered):
    game, proj = entered
    # План показан, человек попросил поправить, план показан снова.
    hook(game, plan_shown(cwd=proj))
    hook(game, plan_shown(cwd=proj))
    code, out = game("check", "2", "01-plan")
    assert code == 1
    assert out.splitlines() == [
        "Квест «План» пока не закрыт. Не сошлось:",
        "  [ ] Claude показал план, и ты его одобрил",
        "      Игра не видела одобренного плана. Набери /plan и своё дело. "
        "Прочитай план и нажми Enter на первой строке.",
    ]
    assert machine_words(out) == []

    hook(game, plan_approved(cwd=proj))
    code, out = game("check", "2", "01-plan")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «План» закрыт.",
        "  [x] Claude показал план, и ты его одобрил",
    ]
    data = st.load(game.state_path)
    assert data["acts"]["2"]["quests"]["01-plan"]["status"] == ranks.STATUS_DONE
    # Закрытие квеста след не стирает: он о прошлом, а не разрешение.
    assert st.trace(data, st.TRACE_PLAN_APPROVED) is not None


def test_a_failed_check_does_not_erase_the_trace(entered):
    """Проверка не сошлась по другой причине — след остаётся."""
    game, proj = entered
    hook(game, plan_approved(cwd=proj))
    hook(game, clear_end(cwd=proj))
    assert game("check", "2", "02-show")[0] == 1
    assert game("check", "2", "03-memory")[0] == 1
    data = st.load(game.state_path)
    assert st.trace(data, st.TRACE_PLAN_APPROVED) is not None
    assert st.trace(data, st.TRACE_CLEARED) is not None
    assert game("check", "2", "01-plan")[0] == 0


def test_clear_quest_closes_after_memory_then_clear_then_words(entered):
    game, proj = entered
    (proj / "CLAUDE.md").write_text(MEMORY_OK, encoding="utf-8")
    assert game("check", "2", "03-memory")[0] == 0

    hook(game, clear_end(cwd=proj))
    hook(game, clear_start(cwd=proj))
    # Слова по-прежнему раньше проверки.
    code, out = game("check", "2", "04-clear")
    assert code == 1 and "Квест «Чистый лист» пока не проверяю." in out
    code, out = game("seen", "2", "04-clear")
    assert code == 0, out
    assert out.strip() == (
        "Записано: в квесте «Чистый лист» ты начал новый разговор и "
        "рассказал, что ответил Claude."
    )
    code, out = game("check", "2", "04-clear")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Чистый лист» закрыт.",
        "  [x] Ты начал новый разговор после записи памяти проекта",
    ]


def test_clear_before_the_memory_does_not_close_the_quest(entered):
    game, proj = entered
    hook(game, clear_end(cwd=proj))
    hook(game, clear_start(cwd=proj))

    code, out = game("seen", "2", "04-clear")
    assert code == 1
    assert out.splitlines() == [
        "Рассказывать пока не о чем: новый разговор был раньше записи "
        "памяти проекта.",
        "Сначала закрой квест «Память проекта». Потом набери /clear и "
        "спроси Claude, на чём остановились.",
    ]
    assert machine_words(out) == []

    (proj / "CLAUDE.md").write_text(MEMORY_OK, encoding="utf-8")
    assert game("check", "2", "03-memory")[0] == 0
    # Память записана, а нового разговора после неё ещё не было.
    code, out = game("seen", "2", "04-clear")
    assert code == 1
    assert out.splitlines() == [
        "Рассказывать пока не о чем: новый разговор был раньше записи "
        "памяти проекта.",
        "Набери /clear ещё раз и спроси Claude, на чём остановились.",
    ]
    assert machine_words(out) == []
    assert not quests.seen(st.load(game.state_path), 2, "04-clear")
    code, out = game("check", "2", "04-clear")
    assert code == 1 and "пока не проверяю" in out
    assert not acts.is_closed(st.load(game.state_path), 2, "04-clear")

    hook(game, clear_end(cwd=proj))
    assert game("seen", "2", "04-clear")[0] == 0
    assert game("check", "2", "04-clear")[0] == 0


def test_traces_made_in_a_foreign_session_close_nothing(entered):
    game, _ = entered
    hook(game, plan_approved(session_id="S-work"))
    hook(game, clear_end(session_id="S-work"))
    assert game("check", "2", "01-plan")[0] == 1
    assert st.load(game.state_path)[st.TRACES_KEY] == {}


# --- вторая форма строки «Что дальше» ------------------------------------------

PLAN_STEP = "Что дальше: квест «План» — Акт 2 «Память и силы»."
PLAN_APPROVED = "План одобрен. Дальше — проверка квеста."
WORDS_TAKEN = "Рассказ записан. Дальше — проверка квеста."


def step(game):
    """Шаг, как его называют первый экран и снимок Лица, — обязаны совпасть."""
    code, out = game("status")
    assert code == 0, out
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Что дальше:"))
    shown = [line.strip() for line in lines[start:start + 2]]
    code, out = game("face", "--called")
    assert code == 0, out
    assert json.loads(out)["next"] == shown
    return shown


def test_plan_quest_asks_for_the_plan_until_it_is_approved(entered, content_root):
    game, proj = entered
    task = cli._quest_tasks(content_root)[(2, "01-plan")]
    assert step(game) == [PLAN_STEP, task]
    hook(game, plan_shown(cwd=proj))
    assert step(game) == [PLAN_STEP, task]


def test_approved_plan_waits_for_the_check_and_then_the_step_moves_on(entered):
    game, proj = entered
    hook(game, plan_approved(cwd=proj))
    assert step(game) == [PLAN_STEP, PLAN_APPROVED]
    assert machine_words(PLAN_APPROVED) == []
    assert game("check", "2", "01-plan")[0] == 0
    assert step(game)[0] == "Что дальше: квест «Покажи» — Акт 2 «Память и силы»."

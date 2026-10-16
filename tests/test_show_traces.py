"""Следы квеста «Покажи»: файл через `@` и картинка; пометка акта (#102).

Швы те же, что у `tests/test_traces.py`. Хук — процессом, на данных формы из
живого замера (`docs/research/2026-10-13-act2-claude-code-facts.md`, Claude
Code 2.1.296): запрос приходит текстом как есть, вставленная картинка — словом
`[Image #N]` в нём, картинка, названная путём, — вызовом `Read`. Сквозной
проход — командами игры и теми же хуками: след в сохранение тест не
подсаживает.
"""
import json
import os
import struct
import zlib
from pathlib import Path

import pytest

from jedicoder import acts, cli, game_session, ranks
from jedicoder import state as st
from test_act2_checks import MEMORY_OK
from test_act2_entry import close_act1, entered, game  # noqa: F401 — фикстуры
from test_human_screens import machine_words
from test_traces import (
    GAME, clear_end, fire, hook, plan_approved, step, untouched,
)

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "plugin" / "hooks"
HOOK = "traces.py"


# --- данные хуков, как их присылает Claude Code ------------------------------

def asked(prompt, cwd, session_id=GAME):
    """Запрос человека: текст как есть, с `@` и `[Image #N]`."""
    return {
        "hook_event_name": "UserPromptSubmit", "session_id": session_id,
        "permission_mode": "bypassPermissions", "prompt": prompt,
        "cwd": str(cwd), "transcript_path": "/tmp/t.jsonl",
    }


def read(path, cwd, session_id=GAME, tool="Read"):
    """Claude читает файл инструментом — так доезжает картинка, названная путём."""
    return {
        "hook_event_name": "PreToolUse", "session_id": session_id,
        "permission_mode": "bypassPermissions", "tool_name": tool,
        "tool_input": {"file_path": str(path)}, "tool_use_id": "toolu_02",
        "cwd": str(cwd), "transcript_path": "/tmp/t.jsonl",
    }


def png(path):
    """Настоящая картинка 1×1 — хуку важен файл, а не только имя."""
    def chunk(kind, body):
        raw = kind + body
        return (struct.pack(">I", len(body)) + raw
                + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )
    return path


@pytest.fixture
def played(tmp_path, project):
    """Сохранение играющего с названной папкой проекта. Отдаёт (файл, папка).

    Сессия GAME записана игровой: хук зовут и из папки проекта, и из чужой.
    """
    proj = project(files={
        "notes.txt": "молоко\n", "src/app.py": "print(1)\n",
        "мой список.txt": "хлеб\n", "заметки": "без расширения\n",
    })
    path = tmp_path / "state.json"
    data = st.default_state("local-test")
    data[game_session.SESSIONS_KEY] = [GAME]
    data["project"]["path"] = str(proj)
    st.save(data, path)
    return path, proj


def traces(save):
    return st.load(save)[st.TRACES_KEY]


# --- файл через @ -------------------------------------------------------------

@pytest.mark.parametrize("prompt", [
    "Что написано в @notes.txt?",
    "@notes.txt",
    "прочитай @notes.txt, пожалуйста",
    "посмотри строки @notes.txt#L1-5 и скажи",
    "что делает @src/app.py",
    "что делает @./src/app.py?",
    'открой @"мой список.txt" и прочитай',
    "вот так:\n@notes.txt\nчто скажешь?",
])
def test_a_project_file_named_with_at_leaves_the_trace(played, prompt):
    save, proj = played
    fire(save, asked(prompt, proj))
    assert traces(save) == {st.TRACE_FILE_SHOWN: {"date": st.today_utc()}}


def test_the_path_is_counted_from_the_folder_of_the_session(played):
    save, proj = played
    fire(save, asked("глянь @app.py и @../notes.txt", proj / "src"))
    assert st.TRACE_FILE_SHOWN in traces(save)


def test_an_absolute_path_into_the_project_counts_from_any_folder(
        played, tmp_path):
    save, proj = played
    elsewhere = tmp_path / "chuzhaya"
    elsewhere.mkdir()
    fire(save, asked("глянь @{}".format(proj / "notes.txt"), elsewhere))
    assert st.TRACE_FILE_SHOWN in traces(save)


@pytest.mark.parametrize("prompt", [
    "Что написано в @net-takogo.txt?",          # файла нет
    "что лежит в @src",                         # папка, а не файл
    "что лежит в @src/ ?",
    "напиши на адрес me@notes.txt",             # почта: `@` не в начале слова
    "почта ivan@example.com",
    "@",
    "@ notes.txt",
    "notes.txt без значка",
    'открой @"мой список.txt',                  # кавычка не закрыта
    "покажи @заметки",                          # Claude Code такое имя не берёт
    "@../outside.txt",                          # файл вне папки проекта
    "",
])
def test_what_is_not_a_shown_project_file_leaves_no_trace(played, prompt):
    save, proj = played
    (proj.parent / "outside.txt").write_text("чужое\n", encoding="utf-8")
    before = untouched(save)
    fire(save, asked(prompt, proj))
    assert untouched(save) == before


def test_a_file_outside_the_project_folder_leaves_no_trace(played, tmp_path):
    save, proj = played
    outside = tmp_path / "chuzhaya" / "notes.txt"
    outside.parent.mkdir()
    outside.write_text("чужое\n", encoding="utf-8")
    before = untouched(save)
    fire(save, asked("глянь @{}".format(outside), proj))
    # Сессия в чужой папке, имя то же, что у файла проекта.
    fire(save, asked("глянь @notes.txt", outside.parent))
    assert untouched(save) == before


def test_a_link_out_of_the_project_folder_is_not_a_project_file(
        played, tmp_path):
    save, proj = played
    outside = tmp_path / "secret.txt"
    outside.write_text("чужое\n", encoding="utf-8")
    try:
        os.symlink(str(outside), str(proj / "link.txt"))
    except (OSError, NotImplementedError):
        pytest.skip("ссылки на этой машине не создаются")
    before = untouched(save)
    fire(save, asked("глянь @link.txt", proj))
    assert untouched(save) == before


def test_without_a_named_project_folder_there_is_no_shown_file(played):
    save, proj = played
    with st.update_state(save) as data:
        data["project"]["path"] = None
    before = untouched(save)
    fire(save, asked("глянь @notes.txt", proj))
    assert untouched(save) == before


@pytest.mark.parametrize("cwd", [None, "", 7, "otnositelnaya"])
def test_a_relative_path_without_a_known_session_folder_is_not_guessed(
        played, cwd):
    save, proj = played
    payload = asked("глянь @notes.txt", proj)
    payload["cwd"] = cwd
    before = untouched(save)
    fire(save, payload)
    assert untouched(save) == before


def test_the_words_of_the_request_never_reach_the_save(played):
    save, proj = played
    fire(save, asked("секретное слово @notes.txt [Image #1]", proj))
    text = save.read_text(encoding="utf-8")
    assert "секретное" not in text and "notes.txt" not in text
    assert "Image" not in text


# --- картинка -----------------------------------------------------------------

@pytest.mark.parametrize("prompt", [
    "[Image #1] какого цвета? одним словом",
    "посмотри на [Image #12] и скажи, что не так",
    "[Image #1][Image #2]",
])
def test_a_pasted_picture_leaves_the_trace(played, prompt):
    save, proj = played
    fire(save, asked(prompt, proj))
    assert traces(save) == {st.TRACE_IMAGE_SHOWN: {"date": st.today_utc()}}


@pytest.mark.parametrize("prompt", [
    "что значит [Image] в тексте?",
    "[Image #]", "[image #1]", "[Image 1]", "[Image #один]", "Image #1",
])
def test_the_word_without_a_number_is_not_a_picture(played, prompt):
    save, proj = played
    before = untouched(save)
    fire(save, asked(prompt, proj))
    assert untouched(save) == before


@pytest.mark.parametrize("name", [
    "shot.png", "shot.jpg", "shot.jpeg", "shot.webp", "shot.gif", "SHOT.PNG",
    "Снимок экрана 2026-10-13.Jpeg",
])
def test_a_picture_read_by_its_path_leaves_the_trace(played, name):
    save, proj = played
    fire(save, read(png(proj / name), proj))
    assert traces(save) == {st.TRACE_IMAGE_SHOWN: {"date": st.today_utc()}}


def test_a_picture_outside_the_project_folder_counts(played, tmp_path):
    """Приложение кладёт снимок во временную папку — он тоже показан."""
    save, proj = played
    shot = png(tmp_path / "cache" / "golokron-snimki" / "snimok-1.png")
    fire(save, read(shot, proj))
    assert st.TRACE_IMAGE_SHOWN in traces(save)


def test_reading_something_else_is_not_a_shown_picture(played):
    save, proj = played
    png(proj / "shot.png")
    (proj / "png").write_text("не картинка\n", encoding="utf-8")
    (proj / "shot.png.txt").write_text("не картинка\n", encoding="utf-8")
    before = untouched(save)
    fire(save, read(proj / "notes.txt", proj))
    fire(save, read(proj / "png", proj))
    fire(save, read(proj / "shot.png.txt", proj))
    fire(save, read(proj / "net-takoy.png", proj))        # картинки нет
    fire(save, read(proj / "shot.png", proj, tool="Write"))
    fire(save, read(proj / "shot.png", proj, tool="Bash"))
    payload = read(proj / "shot.png", proj)
    payload["hook_event_name"] = "PostToolUse"
    fire(save, payload)
    for garbage in (None, 7, ["shot.png"], {"file_path": 7}, {}):
        payload = read(proj / "shot.png", proj)
        payload["tool_input"] = garbage
        fire(save, payload)
    assert untouched(save) == before


def test_one_request_may_show_both(played):
    save, proj = played
    fire(save, asked("[Image #1] сверь с @notes.txt", proj))
    assert set(traces(save)) == {st.TRACE_FILE_SHOWN, st.TRACE_IMAGE_SHOWN}


def test_a_repeat_does_not_rewrite_the_save(played):
    save, proj = played
    fire(save, asked("[Image #1] сверь с @notes.txt", proj))
    before = untouched(save)
    fire(save, asked("[Image #2] и ещё @src/app.py", proj))
    fire(save, read(png(proj / "shot.png"), proj))
    assert untouched(save) == before


# --- только в игровой сессии, и закон хуков -----------------------------------

def test_outside_a_game_session_nothing_is_shown_to_the_game(played, tmp_path):
    save, proj = played
    elsewhere = tmp_path / "rabota"
    elsewhere.mkdir()
    shot = png(elsewhere / "shot.png")
    before = untouched(save)
    fire(save, asked("[Image #1] и @{}".format(proj / "notes.txt"), elsewhere,
                     session_id="S-work"))
    fire(save, read(shot, elsewhere, session_id="S-work"))
    assert untouched(save) == before


def test_the_hook_does_not_start_a_game_by_a_request(tmp_path):
    path = tmp_path / "state.json"
    shot = png(tmp_path / "pics" / "shot.png")
    for payload in (asked("[Image #1] и @shot.png", shot.parent),
                    read(shot, shot.parent)):
        fire(path, payload, JEDICODER_GOLOKRON="1")
    assert sorted(item.name for item in tmp_path.iterdir()) == ["pics"]


@pytest.mark.parametrize("prompt", [None, 7, ["@notes.txt"], {"a": "[Image #1]"}])
def test_a_request_that_is_not_text_is_silence(played, prompt):
    save, proj = played
    before = untouched(save)
    fire(save, asked(prompt, proj))
    assert untouched(save) == before


def test_hooks_json_calls_the_trace_hook_on_the_request_and_on_read():
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]

    def entries(event):
        return [entry for entry in config[event]
                if any(HOOK in item["command"] for item in entry["hooks"])]

    assert [entry.get("matcher") for entry in entries("PreToolUse")] == ["Read"]
    assert len(entries("UserPromptSubmit")) == 1
    # Чужие входы запроса на месте: штраф за запрос без подробностей.
    assert any(
        "vague_prompt.py" in item["command"]
        for entry in config["UserPromptSubmit"] for item in entry["hooks"]
    )


# --- пометка акта --------------------------------------------------------------

@pytest.fixture
def before_act2(game, project):  # noqa: F811
    """Акт 1 пройден командами игры, во второй ещё не входили."""
    proj = project(files={"notes.txt": "молоко\n"})
    close_act1(game, proj)
    return game, proj


def show_both(game, proj):  # noqa: F811
    hook(game, asked("что в @notes.txt?", proj))
    hook(game, asked("[Image #1] что на снимке?", proj))


def _trace_env(game):  # noqa: F811
    env = cli._env_for(st.load(game.state_path), 2)
    return sorted(name for name in env if name.startswith("JEDICODER_TRACE_"))


def test_what_was_done_before_the_act_does_not_close_its_quests(before_act2):
    game, proj = before_act2
    hook(game, plan_approved(cwd=proj))
    show_both(game, proj)
    data = st.load(game.state_path)
    # Следы записаны — действие было, — но без пометки акта.
    for kind in (st.TRACE_PLAN_APPROVED, st.TRACE_FILE_SHOWN,
                 st.TRACE_IMAGE_SHOWN):
        assert st.trace(data, kind) == {"date": st.today_utc()}, kind
    assert _trace_env(game) == []

    assert game("enter", "2")[0] == 0
    assert _trace_env(game) == []
    code, out = game("check", "2", "01-plan")
    assert code == 1
    assert "Игра не видела одобренного плана." in out
    code, out = game("check", "2", "02-show")
    assert code == 1
    assert "Игра не видела файла в запросе." in out
    assert "Игра не видела картинки." in out


def test_the_same_action_repeated_inside_the_act_gets_the_mark(before_act2):
    game, proj = before_act2
    hook(game, plan_approved(cwd=proj))
    show_both(game, proj)
    assert game("enter", "2")[0] == 0

    hook(game, plan_approved(cwd=proj))
    show_both(game, proj)
    data = st.load(game.state_path)
    for kind in (st.TRACE_PLAN_APPROVED, st.TRACE_FILE_SHOWN,
                 st.TRACE_IMAGE_SHOWN):
        assert st.trace(data, kind)[st.TRACE_IN_ACT] is True, kind
    assert _trace_env(game) == [
        "JEDICODER_TRACE_FILE_SHOWN", "JEDICODER_TRACE_IMAGE_SHOWN",
        "JEDICODER_TRACE_PLAN_APPROVED",
    ]
    assert game("check", "2", "01-plan")[0] == 0
    assert game("check", "2", "02-show")[0] == 0


def test_a_picture_read_by_path_inside_the_act_gets_the_mark(entered):
    game, proj = entered
    hook(game, read(png(proj / "shot.png"), proj))
    entry = st.trace(st.load(game.state_path), st.TRACE_IMAGE_SHOWN)
    assert entry == {"date": st.today_utc(), st.TRACE_IN_ACT: True}


# --- сквозной проход: команды игры и хуки, сохранение не засевается -------------

SHOW_OPEN = "Квест «Покажи» пока не закрыт. Не сошлось:"
FILE_ROW = "Ты показал Claude файл проекта через @"
IMAGE_ROW = "Ты показал Claude снимок экрана"
FILE_HINT = (
    "      Игра не видела файла в запросе. Набери @ и выбери файл проекта из "
    "списка. Потом допиши вопрос."
)
IMAGE_HINT = (
    "      Игра не видела картинки. Сделай снимок экрана и покажи его Claude "
    "вместе с вопросом."
)


@pytest.fixture
def plan_done(entered):  # noqa: F811
    """Акт 2 открыт, квест «План» закрыт хуком и проверкой."""
    game, proj = entered
    (proj / "notes.txt").write_text("молоко\n", encoding="utf-8")
    hook(game, plan_approved(cwd=proj))
    assert game("check", "2", "01-plan")[0] == 0
    return game, proj


def test_show_quest_closes_after_the_hooks_saw_a_file_and_a_picture(plan_done):
    game, proj = plan_done
    code, out = game("check", "2", "02-show")
    assert code == 1
    assert out.splitlines() == [
        SHOW_OPEN, "  [ ] " + FILE_ROW, FILE_HINT,
        "  [ ] " + IMAGE_ROW, IMAGE_HINT,
    ]

    show_both(game, proj)
    code, out = game("check", "2", "02-show")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Покажи» закрыт.", "  [x] " + FILE_ROW, "  [x] " + IMAGE_ROW,
    ]
    assert machine_words(out) == []
    data = st.load(game.state_path)
    assert data["acts"]["2"]["quests"]["02-show"]["status"] == ranks.STATUS_DONE


def test_a_file_alone_leaves_the_picture_to_be_shown(plan_done):
    game, proj = plan_done
    hook(game, asked("что в @notes.txt?", proj))
    code, out = game("check", "2", "02-show")
    assert code == 1
    assert out.splitlines() == [
        SHOW_OPEN, "  [ ] " + IMAGE_ROW, IMAGE_HINT,
    ]
    assert FILE_ROW not in out
    assert machine_words(out) == []


def test_a_picture_alone_leaves_the_file_to_be_shown(plan_done, tmp_path):
    game, proj = plan_done
    # Снимок лежит вне папки проекта, и назван он путём внутри фразы.
    hook(game, read(png(tmp_path / "snimki" / "shot.png"), proj))
    code, out = game("check", "2", "02-show")
    assert code == 1
    assert out.splitlines() == [
        SHOW_OPEN, "  [ ] " + FILE_ROW, FILE_HINT,
    ]
    assert IMAGE_ROW not in out
    # Файл, которого нет, и файл вне папки проекта квест не закрывают.
    hook(game, asked("что в @net-takogo.txt и в @../snimki/shot.png?", proj))
    assert game("check", "2", "02-show")[0] == 1


# --- вторая форма строки «Что дальше» ------------------------------------------

SHOW_STEP = "Что дальше: квест «Покажи» — Акт 2 «Память и силы»."
SHOWN = "Файл и снимок экрана показаны. Дальше — проверка квеста."
CLEAR_STEP = "Что дальше: квест «Чистый лист» — Акт 2 «Память и силы»."
WORDS_TAKEN = "Рассказ записан. Дальше — проверка квеста."


def test_show_quest_asks_for_both_until_both_are_shown(plan_done, content_root):
    game, proj = plan_done
    task = cli._quest_tasks(content_root)[(2, "02-show")]
    assert step(game) == [SHOW_STEP, task]
    hook(game, asked("что в @notes.txt?", proj))
    assert step(game) == [SHOW_STEP, task]


def test_a_picture_alone_keeps_the_task_too(plan_done, content_root):
    game, proj = plan_done
    task = cli._quest_tasks(content_root)[(2, "02-show")]
    hook(game, asked("[Image #1] что тут?", proj))
    assert step(game) == [SHOW_STEP, task]


def test_both_shown_wait_for_the_check_and_then_the_step_moves_on(plan_done):
    game, proj = plan_done
    show_both(game, proj)
    assert step(game) == [SHOW_STEP, SHOWN]
    assert machine_words(SHOWN) == []
    assert game("check", "2", "02-show")[0] == 0
    assert step(game)[0] == (
        "Что дальше: квест «Память проекта» — Акт 2 «Память и силы»."
    )


def test_clear_quest_keeps_the_words_first_form(plan_done, content_root):
    """У «Чистого листа» вторых форм две: новый разговор начат (#114) и
    рассказ записан."""
    game, proj = plan_done
    show_both(game, proj)
    assert game("check", "2", "02-show")[0] == 0
    (proj / "CLAUDE.md").write_text(MEMORY_OK, encoding="utf-8")
    assert game("check", "2", "03-memory")[0] == 0
    task = cli._quest_tasks(content_root)[(2, "04-clear")]
    assert step(game) == [CLEAR_STEP, task]
    hook(game, clear_end(cwd=proj))
    # След есть, а рассказа ещё нет: передачу Полоса уже не просит.
    assert step(game) == [CLEAR_STEP, cli.STEP_NEW_TALK]
    assert game("seen", "2", "04-clear")[0] == 0
    assert step(game) == [CLEAR_STEP, WORDS_TAKEN]
    assert acts.next_quest(st.load(game.state_path), 2) == "04-clear"

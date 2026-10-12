"""UserPromptSubmit-хук: узкий матчер расплывчатых промптов.

Матчер намеренно узкий: ложное срабатывание на нормальном запросе
раздражает сильнее, чем польза от катсцены.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))

import vague_prompt  # noqa: E402

from jedicoder import game_session  # noqa: E402
from jedicoder import state as st  # noqa: E402

#: Сессия, в которой человек уже позвал команду игры: её идентификатор лежит
#: в сохранении, которое сеет `hook_state` (#97).
GAME = "S-game"


def asked(text, session_id=GAME, field="prompt", **more):
    """Данные хука запроса, как их шлёт Claude Code."""
    payload = {"hook_event_name": "UserPromptSubmit", field: text}
    if session_id is not None:
        payload["session_id"] = session_id
    payload.update(more)
    return payload


@pytest.mark.parametrize("text", [
    "сделай мне приложение для медитации",
    "Сделай мне сайт",
    "напиши мне бота",
])
def test_vague_prompts_are_caught(text):
    assert vague_prompt.is_vague(text) is True


@pytest.mark.parametrize("text", [
    "поправь отступ в src/app.py:42",
    "сделай мне кнопку «Оплатить» в footer, по клику — /checkout",
    "напиши мне тест на bump_streak: границы суток и разрыв",
    "почему падает test_env_guard_catches_token_in_history?",
    "сделай мне 3 варианта заголовка для лендинга",
    "давай продолжим",
    "",
    "сделай коммит",
    "создай ветку",
    "сделай ревью PR",
    "сделай ретрай на фейл",
    "создай новый компонент",
    "сделай рефактор auth-модуля",
    "напиши мне отчёт по вчерашним правкам",
    "сделай так же, но для мобилки",
    "сделай систему логирования",
    "сделай мне сайт быстрее",
    "сделай мне ревью приложения",
    "сделай мне бота молчаливым по умолчанию",
    "сделай мне приложению новый логотип",
    "сделай мне рефакторинг приложения",
    "сделай мне бота побыстрее",
])
def test_normal_prompts_are_not_caught(text):
    assert vague_prompt.is_vague(text) is False


def test_long_prompt_is_never_vague():
    assert vague_prompt.is_vague("сделай мне приложение " + "и ещё " * 40) is False


@pytest.fixture
def hook_state(tmp_path, monkeypatch):
    path = tmp_path / "state.json"

    def seed(**fields):
        data = st.default_state("local-test")
        data[game_session.SESSIONS_KEY] = [GAME]
        data.update(fields)
        st.save(data, path)
        monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
        return path

    return seed


def test_react_scores_and_suggests_brainstorm(hook_state):
    path = hook_state()
    out = vague_prompt.react(asked("сделай мне приложение для медитации"))
    assert "«помоги найти идею»" in out["systemMessage"]
    assert "Сила" not in out["systemMessage"], "образов нет (language.md)"
    assert "decision" not in out, "хук не блокирует промпт"
    assert st.load(path)["dark_side"] == 1


def test_react_reads_legacy_field(hook_state):
    hook_state()
    out = vague_prompt.react(asked("сделай мне сайт", field="user_prompt"))
    assert out is not None


def test_react_silent_on_normal_prompt(hook_state):
    path = hook_state()
    assert vague_prompt.react(asked("почини импорт в app.py")) is None
    assert st.load(path)["dark_side"] == 0


@pytest.mark.parametrize("text", [
    "сделай мне приложение 😊",
    "сделай мне приложение.",
    "Напиши мне игру",
    "сделай мне landing page",
    "напиши мне бота",
    "сделай мне новое приложение",
    "создай мне интернет-магазин",
    "сделай мне приложение по медитации",
    "напиши мне бота для заметок",
    "напиши мне бота!",
    "сделай мне сайт для бизнеса",
])
def test_product_scale_requests_are_caught(text):
    # Ловим просьбу построить целый продукт без единой детали — именно
    # её, а не любую короткую фразу «сделай X».
    assert vague_prompt.is_vague(text) is True


def test_purpose_tail_separates_order_from_fixup():
    # «для медитации» — цель нового продукта; «быстрее» — правка старого.
    assert vague_prompt.is_vague("сделай мне сайт для бизнеса") is True
    assert vague_prompt.is_vague("сделай мне сайт быстрее") is False


def test_work_words_mean_a_task_about_a_product():
    assert vague_prompt.is_vague("сделай мне ревью приложения") is False
    assert vague_prompt.is_vague("напиши мне тест для бота") is False
    assert vague_prompt.is_vague("сделай мне приложение") is True


def test_react_writes_its_kind_to_the_log(hook_state):
    path = hook_state()
    vague_prompt.react(asked("сделай мне приложение для медитации"))
    saved = st.load(path)
    (entry,) = st.dark_side_entries(saved)
    assert entry["type"] == "vague_prompt"
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", entry["date"]), entry
    assert len(st.dark_side_entries(saved)) == saved["dark_side"] == 1


def test_react_never_stores_the_prompt(hook_state):
    """ADR-0011: в промпте бывают имена заказчиков — журнал их не хранит."""
    path = hook_state()
    vague_prompt.react(asked("сделай мне сайт"))
    saved = st.load(path)
    assert "сайт" not in str(saved["dark_side_log"])
    for entry in saved["dark_side_log"]:
        assert sorted(entry) == ["date", "type"]


def test_broken_journal_leaves_the_prompt_alone(hook_state, monkeypatch,
                                                capsys):
    """Закон хуков: сломалась запись журнала — хук молчит, промпт идёт дальше."""
    import io
    import json
    import sys

    hook_state()

    def boom(*args, **kwargs):
        raise RuntimeError("журнал сломан")

    monkeypatch.setattr(st, "record_dark_side", boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        asked("сделай мне приложение для медитации")
    )))

    assert vague_prompt.main() == 0
    assert capsys.readouterr().out == ""


# --- Игровая сессия (#97) -----------------------------------------------------
#
# Плагин стоит на всей машине, и хук запроса зовётся в каждой сессии Claude
# Code. Штраф — только в игровой: её запустил Голокрон, она открыта в папке
# проекта или в ней позвана команда игры.

VAGUE = "сделай мне сайт"


def test_a_foreign_session_gets_no_penalty_and_the_save_is_untouched(
        hook_state, tmp_path):
    path = hook_state()
    before = (path.stat().st_mtime_ns, path.read_bytes())

    out = vague_prompt.react(asked(VAGUE, session_id="S-work", cwd=str(tmp_path)))

    assert out is None
    assert (path.stat().st_mtime_ns, path.read_bytes()) == before


def test_no_session_id_and_no_other_sign_is_a_foreign_session(hook_state):
    path = hook_state()
    assert vague_prompt.react(asked(VAGUE, session_id=None)) is None
    assert st.load(path)["dark_side"] == 0


def test_a_session_in_the_project_folder_is_penalised(hook_state, tmp_path):
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    path = hook_state(project={"path": str(project)}, game_sessions=[])

    out = vague_prompt.react(
        asked(VAGUE, session_id="S-new", cwd=str(project / "src"))
    )

    assert out["systemMessage"].startswith("Штраф: +1")
    assert st.load(path)["dark_side"] == 1


def test_a_session_launched_by_golokron_is_penalised(hook_state, monkeypatch):
    path = hook_state(game_sessions=[])
    monkeypatch.setenv(game_session.GOLOKRON_MARK, "1")

    assert vague_prompt.react(asked(VAGUE, session_id=None)) is not None
    assert st.load(path)["dark_side"] == 1


def test_first_evening_in_a_bare_terminal(tmp_path, monkeypatch):
    """Папка ещё не названа, Голокрона нет, сохранения нет: игровой сессию
    делает сам запрос `/jedicoder:start` — и с этой минуты хуки работают."""
    path = tmp_path / "jc" / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))

    assert vague_prompt.react(asked("/jedicoder:start", session_id="S")) is None
    assert game_session.sessions(st.load(path)) == ["S"]
    assert st.load(path)["padawan_id"] is None, (
        "паспорт ставит команда игры: по нему приложение держит «Первый запуск»"
    )
    assert st.load(path)["dark_side"] == 0, "команда игры — не запрос без подробностей"

    assert vague_prompt.react(asked(VAGUE, session_id="S-other")) is None
    assert st.load(path)["dark_side"] == 0

    out = vague_prompt.react(asked(VAGUE, session_id="S"))
    assert out["systemMessage"].startswith("Штраф: +1")
    assert st.load(path)["dark_side"] == 1


def test_a_game_command_keeps_everything_else_in_the_save(hook_state):
    path = hook_state(game_sessions=["S-old"], xp=40, dark_side=2)
    vague_prompt.react(asked("/jedicoder:magistr", session_id="S-new"))
    saved = st.load(path)
    assert game_session.sessions(saved) == ["S-old", "S-new"]
    assert (saved["xp"], saved["dark_side"]) == (40, 2)


def test_a_repeated_game_command_does_not_rewrite_the_save(hook_state):
    path = hook_state()
    vague_prompt.react(asked("/jedicoder:start"))
    before = path.stat().st_mtime_ns
    vague_prompt.react(asked("/jedicoder:start"))
    assert path.stat().st_mtime_ns == before


def test_game_commands_never_grow_the_list_past_the_cap(hook_state):
    path = hook_state(game_sessions=[])
    for number in range(game_session.SESSIONS_CAP + 3):
        vague_prompt.react(asked("/jedicoder:start", session_id="S{}".format(number)))
    kept = game_session.sessions(st.load(path))
    assert len(kept) == game_session.SESSIONS_CAP
    assert kept[0] == "S3"


def test_a_game_command_over_a_garbage_list_starts_a_clean_one(hook_state):
    path = hook_state(game_sessions={"мусор": 1})
    assert vague_prompt.react(asked(VAGUE)) is None, "мусор — пустой список"
    vague_prompt.react(asked("/jedicoder:start"))
    assert game_session.sessions(st.load(path)) == [GAME]


def test_a_game_command_without_a_session_id_starts_no_save(tmp_path, monkeypatch):
    path = tmp_path / "jc" / "state.json"
    path.parent.mkdir()
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
    assert vague_prompt.react(asked("/jedicoder:start", session_id=None)) is None
    assert list(path.parent.iterdir()) == []


def test_a_foreign_request_starts_no_save(tmp_path, monkeypatch):
    path = tmp_path / "jc" / "state.json"
    path.parent.mkdir()
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
    assert vague_prompt.react(asked(VAGUE, session_id="S", cwd=str(tmp_path))) is None
    assert list(path.parent.iterdir()) == []


def test_a_broken_session_record_leaves_the_request_alone(
        hook_state, monkeypatch):
    """Закон хуков: не смогли записать сессию — молчим, запрос идёт дальше."""
    hook_state(game_sessions=[])

    def boom(*args, **kwargs):
        raise RuntimeError("сломано")

    monkeypatch.setattr(game_session, "note", boom)
    assert vague_prompt.react(asked("/jedicoder:start", session_id="S")) is None
    assert vague_prompt.react(asked(VAGUE, session_id="S")) is None

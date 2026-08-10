"""UserPromptSubmit-хук: узкий матчер расплывчатых промптов.

Матчер намеренно узкий: ложное срабатывание на нормальном запросе
раздражает сильнее, чем польза от катсцены.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))

import vague_prompt  # noqa: E402

from jedicoder import state as st  # noqa: E402


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
        data.update(fields)
        st.save(data, path)
        monkeypatch.setenv("JEDICODER_STATE_PATH", str(path))
        return path

    return seed


def test_react_scores_and_suggests_brainstorm(hook_state):
    path = hook_state()
    out = vague_prompt.react({
        "hook_event_name": "UserPromptSubmit",
        "prompt": "сделай мне приложение для медитации",
    })
    assert "/brainstorm" in out["systemMessage"]
    assert "decision" not in out, "хук не блокирует промпт"
    assert st.load(path)["dark_side"] == 1


def test_react_reads_legacy_field(hook_state):
    hook_state()
    out = vague_prompt.react({"user_prompt": "сделай мне сайт"})
    assert out is not None


def test_react_silent_on_normal_prompt(hook_state):
    path = hook_state()
    assert vague_prompt.react({"prompt": "почини импорт в app.py"}) is None
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

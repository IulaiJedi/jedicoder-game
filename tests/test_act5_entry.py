"""Акт 5 «Три места кода» открыт: вход, приём «Проверка ключей», квесты
«GitHub» и «Приватный репозиторий» (спека jedicoder.store#123, тикет #124).

Той же дверью, что человек: сохранение не засевается. Акт 1 проходится
командами игры, Акты 2–4 — командами и хуками (`walk_act2`, `walk_act3`,
`walk_act4`), и только потом — `enter 5`.

Целиком акт проходит `walk_act5` (tests/test_act5_walkthrough.py, #125) —
там же конец игры. GitHub недостижим и не нужен: ответ API без входа
подменяет стаб `curl` (`tests/test_act5_checks.py`), отправку здесь сеет
`git update-ref`.
"""
from pathlib import Path

import pytest

from conftest import needs_shelf
from jedicoder import acts, cli, ranks
from jedicoder import state as st
from test_act2_entry import close_act1, game  # noqa: F401 — фикстура
from test_act2_walkthrough import walk_act2
from test_act3_walkthrough import walk_act3
from test_act4_walkthrough import BOT, walk_act4
from test_act5_checks import fake_github, link  # noqa: F401 — фикстура
from test_human_screens import machine_words

ACT = 5
QUESTS = ("01-github", "02-private", "03-sync", "04-service", "05-server")
TITLES = ("GitHub", "Приватный репозиторий", "Одна версия", "Чужой сервис",
          "Третье место")
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: проверки Акта 3 смотрят в неё."""
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


@pytest.fixture
def sentinel(game, project, home):  # noqa: F811
    """Человек прошёл четыре вечера — бот на своём компьютере. Отдаёт
    (игра, папка проекта, экран закрытия Акта 4)."""
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    closing = walk_act4(game, proj, home, BOT)
    return game, proj, closing


@pytest.fixture
def entered(sentinel):
    """Он вошёл в Акт 5. Отдаёт (игра, папка проекта)."""
    game, proj, _ = sentinel  # noqa: F811
    code, out = game("enter", "5")
    assert code == 0, out
    return game, proj


def step(game):  # noqa: F811
    _, out = game("status")
    return [line.strip() for line in out.rstrip().splitlines()[-2:]]


# --- реестр ------------------------------------------------------------------

def test_quest_order_declared():
    assert acts.quest_ids(ACT) == QUESTS
    assert [acts.quest_kind(ACT, quest_id) for quest_id in QUESTS] == [
        acts.KIND_ACK, acts.KIND_SCRIPT, acts.KIND_SCRIPT, acts.KIND_SCRIPT,
        acts.KIND_ACK,
    ]


def test_act5_does_not_branch():
    for track in (None, acts.TRACK_CRAFTSMAN, acts.TRACK_FOUNDER):
        assert acts.quest_ids(ACT, track) == QUESTS
    assert acts.ACT_AXIS == {}


def test_registry_names_the_act_its_artifact_and_rank():
    assert ranks.ACTS[ACT] == {
        "slug": "act5-tri-mesta", "title": "Три места кода",
        "artifact": "cso", "rank": "master",
    }
    # Выключенных актов нет: игра кончается Актом 5 и Мастером.
    assert ranks.MUTED_ACTS == ()
    assert ranks.playable_acts() == [1, 2, 3, 4, 5]
    assert ranks.FINAL_ACT == 5 and ranks.FINAL_RANK == "master"
    assert ranks.muted_after(ranks.FINAL_ACT) == []
    assert ranks.ALL_ARTIFACTS == ("brainstorm", "handoff", "investigate", "goal", "cso")
    assert cli.ARTIFACT_NAMES["cso"] == "Проверка ключей"
    assert "deploy" not in cli.ARTIFACT_WORDS


def test_only_the_service_waits_for_words():
    """«Чужой сервис»: сначала рассказ, что продукт теперь умеет, потом
    проверка ключей (#125). Своя запись слов ворот — не слова «первой версии»."""
    waiting = [quest_id for quest_id in QUESTS
               if acts.needs_words(ACT, quest_id, {})]
    assert waiting == ["04-service"]
    assert (ACT, "04-service") == acts.SERVICE_QUEST
    screen = cli.WORDS_FIRST_SCREENS[acts.SERVICE_QUEST]
    assert "первую версию" not in screen["ask"]
    assert screen.get("lines") is True


def test_content_describes_the_act_as_the_registry_does(content_root):
    from jedicoder import content

    scene = next(item for item in content.load_acts(content_root) if item.act == ACT)
    assert scene.slug == "act5-tri-mesta"
    assert scene.quests == QUESTS
    assert tuple(scene.quest_titles) == TITLES
    assert len(scene.quest_tasks) == len(QUESTS)
    assert scene.muted is False
    assert scene.artifact == "cso" and scene.rank == "master"
    for task in scene.quest_tasks:
        assert "," not in task and len(task.split()) <= 15, task
    paragraphs = [part for part in scene.body.split("\n\n") if part.strip()]
    assert len(paragraphs) == 2


@needs_shelf
def test_old_act5_left_the_plugin_and_no_skill_name_repeats():
    """Прежний акт — на полке, с приёмом и агентом; имена не повторяются."""
    plugin = ROOT / "plugin"
    for gone in (
        plugin / "skills" / "act5-vyhod-v-svet", plugin / "skills" / "deploy",
        plugin / "agents" / "sith-reviewer.md",
        plugin / "quests" / "act5-vyhod-v-svet",
        plugin / "content" / "ru" / "acts" / "act5-vyhod-v-svet.md",
        plugin / "content" / "ru" / "scroll" / "deploy.md",
    ):
        assert not gone.exists(), gone
    for kept in ("skills/act5-tri-mesta/SKILL.md", "skills/cso/SKILL.md",
                 "content/ru/scroll/cso.md", "content/ru/acts/act5-tri-mesta.md"):
        assert (plugin / kept).is_file(), kept
    shelf = ROOT / "shelf" / "act5-vyhod-v-svet"
    for kept in ("README.md", "skill/SKILL.md", "artifact/SKILL.md",
                 "agent/sith-reviewer.md", "content/scroll/deploy.md"):
        assert (shelf / kept).is_file(), kept
    # Приём `cso` ушёл с полки «Щита» обратно в игру.
    assert not (ROOT / "shelf" / "act4-shchit" / "artifact").exists()
    assert sorted(path.name for path in (plugin / "agents").iterdir()) == ["magistr.md"]

    skills = sorted(path.name for path in (plugin / "skills").iterdir() if path.is_dir())
    commands = sorted(path.stem for path in (plugin / "commands").glob("*.md"))
    names = skills + commands
    assert len(names) == len(set(names)), names


def test_cso_is_a_novice_artifact_with_a_lock_and_no_server_words():
    skill = (ROOT / "plugin" / "skills" / "cso" / "SKILL.md").read_text(encoding="utf-8")
    memo = (ROOT / "plugin" / "content" / "ru" / "scroll" / "cso.md").read_text(
        encoding="utf-8"
    )
    assert "cli.py\" artifact cso" in skill
    assert "на входе в Акт 5" in skill
    for text in (skill, memo):
        for word in ("сервер", "под root", "хостинг", "выкладк", "2FA", "Щит"):
            assert word not in text, word


# --- вход: Акты 1–4 целиком, потом `enter 5` -----------------------------------

def test_act5_is_closed_until_act4_is_done(game, project, home):  # noqa: F811
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    code, out = game("enter", "5")
    assert code == 1
    assert "Сначала закрой Акт 4" in out
    assert "5" not in st.load(game.state_path)["acts"]
    code, out = game("artifact", "cso")
    assert code == 1 and "на входе в Акт 5" in out


def test_closing_act4_no_longer_says_the_game_pauses(sentinel):
    _, _, closing = sentinel
    assert closing.splitlines() == [
        "Квест «Приёмка» закрыт: ты проверил продукт сам и сказал «да».",
        "",
        "Акт 4. Свой продукт — закрыт.",
        "Новый ранг: Страж.",
    ]


def test_after_act4_the_next_step_is_act5(sentinel):
    game, _, _ = sentinel  # noqa: F811
    _, out = game("status")
    lines = out.splitlines()
    assert "Ранг: Страж" in lines
    assert "  Акт 4. Свой продукт — пройден" in lines
    assert "  Акт 5. Три места кода — не начат, квестов закрыто: 0/5" in lines
    assert "ещё не написан" not in out
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: начать Акт 5 «Три места кода» — квестов в нём 5.",
        "  Скажи Claude: «начинаем».",
    ]
    assert machine_words(out) == []


def test_finale_is_still_locked_for_the_sentinel(sentinel):
    game, _, _ = sentinel  # noqa: F811
    code, out = game("finale")
    assert code == 1
    assert out.splitlines()[0] == (
        "Финал ждёт Мастера. Твой ранг сейчас — Страж, закрыто актов: 4 из 5."
    )
    assert "Ближайший незакрытый — Акт 5 «Три места кода»." in out
    assert "ещё не написан" not in out
    assert not st.load(game.state_path).get("finale_announced")


def test_enter_act5_prints_five_quests_in_words_and_gives_the_artifact(sentinel):
    """Приёмка тикета: с чистого сохранения Акты 1–4 целиком → `enter 5`."""
    game, _, _ = sentinel  # noqa: F811
    code, out = game("enter", "5")

    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "Акт 5. Три места кода — начат."
    assert lines[2] == (
        "В этом акте ты кладёшь копию своего кода на GitHub, в закрытое хранилище."
    )
    assert lines[4] == (
        "Сломается компьютер — проект не пропадёт: он ждёт тебя на GitHub."
    )
    start = lines.index("Квесты акта (5):") + 1
    assert lines[start:start + 5] == [
        "  1. GitHub. Заведи аккаунт на GitHub и попроси Claude подключить к "
        "нему твой компьютер.",
        "  2. Приватный репозиторий. Создай на GitHub закрытое хранилище "
        "проекта — Claude отправит туда код.",
        "  3. Одна версия. Попроси Claude поправить мелочь — потом скажи "
        "«сделай коммит и отправь на GitHub».",
        "  4. Чужой сервис. Дай Claude ссылку на документацию сервиса — он "
        "подключит его к твоему продукту.",
        "  5. Третье место. Послушай про сервер и домен и перескажи Claude их "
        "своими словами.",
    ]
    assert "Ранг за акт: Мастер. Это следующая ступень после Стража." in lines
    assert (
        "Приём этого акта — «Проверка ключей»: помогает проверить, не утекают "
        "ли ключи. Скажи Claude: «проверь, не утекают ли ключи»."
    ) in lines
    for quest_id in QUESTS:
        assert quest_id not in out
    assert "cso" not in out and "deploy" not in out
    assert machine_words(out) == []

    data = st.load(game.state_path)
    assert data["current_act"] == 5
    assert data["acts"]["5"]["status"] == ranks.STATUS_IN_PROGRESS
    assert data["acts"]["5"]["started_at"]
    assert data["artifacts"] == ["brainstorm", "handoff", "investigate", "goal", "cso"]
    assert data["rank"] == "sentinel"


def test_cso_lock_opens_on_entry(sentinel):
    game, _, _ = sentinel  # noqa: F811
    code, out = game("artifact", "cso")
    assert code == 1 and "на входе в Акт 5" in out
    assert game("enter", "5")[0] == 0
    code, out = game("artifact", "cso")
    assert code == 0 and out.strip() == "Приём cso открыт."


def test_first_screen_inside_act5_names_the_quest(entered):
    game, _ = entered  # noqa: F811
    _, out = game("status")
    lines = out.splitlines()
    assert "  Акт 5. Три места кода — идёт, квестов закрыто: 0/5" in lines
    assert step(game) == [
        "Что дальше: квест «GitHub» — Акт 5 «Три места кода».",
        "Заведи аккаунт на GitHub и попроси Claude подключить к нему твой компьютер.",
    ]
    head = lines.index(cli.ARTIFACTS_HEAD)
    assert lines[head + 5] == (
        "  «Проверка ключей»: проверить, не утекают ли ключи — «проверь, не "
        "утекают ли ключи»"
    )
    assert machine_words(out) == []


def test_project_screen_of_act5_asks_for_nothing_of_the_old_act(entered):
    """Базу, путь деплоя и адрес спрашивал прежний «Выход в свет»: пустых строк
    о них нет. Тип продукта и порт четвёртого вечера — названные — на месте."""
    game, _ = entered  # noqa: F811
    _, out = game("project")
    for silent in ("База данных", "Путь деплоя", "URL продукта"):
        assert silent not in out, silent
    assert "  Тип продукта: Telegram-бот" in out.splitlines()


def test_memo_carries_the_key_check_and_no_deploy(entered):
    game, proj = entered  # noqa: F811
    code, out = game("scroll")
    assert code == 0, out
    folder = proj / "docs" / "jedicoder"
    assert (folder / "cso.md").is_file()
    assert not (folder / "deploy.md").exists()
    assert not (folder / "roadmap.md").read_text(encoding="utf-8").startswith(
        "# Три шага"
    )
    frazy = (folder / "frazy.md").read_text(encoding="utf-8")
    assert "| Завёл аккаунт на GitHub | У меня есть GitHub, как его подключить? |" in frazy
    assert "Проверь, не утекают ли ключи" in frazy


# --- «GitHub» и «Приватный репозиторий» -------------------------------------------

def test_github_is_closed_by_the_story(entered):
    game, _ = entered  # noqa: F811
    code, out = game("ack", "5", "01-github")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «GitHub» закрыт: Claude назвал твой аккаунт на GitHub, и ты подтвердил.",
    ]
    assert machine_words(out) == []
    assert acts.next_quest(st.load(game.state_path), ACT) == "02-private"
    assert step(game) == [
        "Что дальше: квест «Приватный репозиторий» — Акт 5 «Три места кода».",
        "Создай на GitHub закрытое хранилище проекта — Claude отправит туда код.",
    ]


@pytest.fixture
def at_private(entered):
    game, proj = entered  # noqa: F811
    assert game("ack", "5", "01-github")[0] == 0
    return game, proj


def test_private_without_a_repository_says_what_to_ask(at_private, fake_github):  # noqa: F811
    game, _ = at_private  # noqa: F811
    code, out = game("check", "5", "02-private")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Приватный репозиторий» пока не закрыт. Не сошлось:",
        "  [ ] Проект связан с хранилищем на GitHub",
        "      Скажи Claude: «Помоги создать на GitHub закрытое хранилище для проекта и "
        "отправь туда код».",
    ]
    assert machine_words(out) == []
    assert fake_github.called_with() is None


def test_private_repository_closes_the_quest(at_private, fake_github):  # noqa: F811
    """Приёмка тикета: закрытое хранилище — GitHub без входа отвечает 404."""
    game, proj = at_private  # noqa: F811
    link(proj, "git@github.com:padawan/kruzhok.git")
    fake_github.answer(404)
    code, out = game("check", "5", "02-private")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Приватный репозиторий» закрыт.",
        "  [x] Проект связан с хранилищем на GitHub",
        "  [x] Код отправлен в хранилище padawan/kruzhok",
        "  [x] Хранилище закрытое: чужие его не видят",
    ]
    assert machine_words(out) == []
    data = st.load(game.state_path)
    assert acts.next_quest(data, ACT) == "03-sync"
    assert data["acts"]["5"]["quests"]["02-private"]["attempts"] == 1
    assert step(game) == [
        "Что дальше: квест «Одна версия» — Акт 5 «Три места кода».",
        "Попроси Claude поправить мелочь — потом скажи «сделай коммит и отправь "
        "на GitHub».",
    ]


def test_public_repository_fails_with_a_hint(at_private, fake_github):  # noqa: F811
    """Приёмка тикета: открытое — 200, провал с подсказкой сделать закрытым."""
    game, proj = at_private  # noqa: F811
    link(proj)
    fake_github.answer(200)
    code, out = game("check", "5", "02-private")
    assert code == 1
    lines = out.splitlines()
    assert lines[0] == "Квест «Приватный репозиторий» пока не закрыт. Не сошлось:"
    assert lines[1] == "  [ ] Хранилище закрытое: чужие его не видят"
    assert "Сделай хранилище на GitHub закрытым" in lines[2]
    assert machine_words(out) == []
    data = st.load(game.state_path)
    assert data["acts"]["5"]["quests"]["02-private"]["attempts"] == 1
    # Сделал закрытым — тот же квест закрывается со второй попытки.
    fake_github.answer(404)
    assert game("check", "5", "02-private")[0] == 0


def test_without_network_the_attempt_is_not_counted(at_private, fake_github):  # noqa: F811
    """Приёмка тикета: нет сети — «не смог проверить», попытка не в счёт."""
    game, proj = at_private  # noqa: F811
    link(proj)
    fake_github.answer("down")
    code, out = game("check", "5", "02-private")
    assert code == 1
    assert out.splitlines() == [
        "Не смог проверить: не достучался до GitHub — проверь интернет и VPN и "
        "попробуй снова",
        "Попытка не засчитана — это не твоя ошибка.",
    ]
    data = st.load(game.state_path)
    quest = data["acts"]["5"]["quests"].get("02-private") or {}
    assert quest.get("attempts", 0) == 0


def test_third_failure_calls_the_magistr_in_novice_words(at_private, fake_github):  # noqa: F811
    """Третья неудача в Акте 5 — как в Акте 4: остановись и позови Магистра.
    «Откатись на рабочий коммит» у «Приватного репозитория» ни при чём
    (ревью #124)."""
    game, proj = at_private  # noqa: F811
    link(proj)
    fake_github.answer(200)
    for attempt in range(3):
        code, out = game("check", "5", "02-private")
        assert code == 1
        assert ("Третья попытка" in out) is (attempt == 2)
    tail = out.split("Третья попытка.", 1)[1]
    assert "Позови Магистра" in tail and "/jedicoder:magistr" in tail
    for word in ("коммит", "протокол", "откат"):
        assert word not in tail, word


def test_server_is_closed_by_the_story_in_its_own_words(entered):
    game, _ = entered  # noqa: F811
    code, out = game("ack", "5", "05-server")
    assert code == 0, out
    assert out.splitlines()[0] == (
        "Квест «Третье место» закрыт: ты своими словами рассказал про третье место."
    )
    # Акт не закрыт: «GitHub» и три квеста до «Третьего места» открыты.
    assert st.load(game.state_path)["acts"]["5"]["status"] == ranks.STATUS_IN_PROGRESS


def test_the_tool_closes_github_by_its_name(entered):
    game, _ = entered  # noqa: F811
    code, out = game("tool", "ack", "GitHub")
    assert code == 0, out
    assert "Квест «GitHub» закрыт" in out
    assert acts.is_closed(st.load(game.state_path), ACT, "01-github")


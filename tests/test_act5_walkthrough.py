"""Сквозной проход Акта 5 «Три места кода» и конец игры — той же дверью, что
человек (спека jedicoder.store#123, тикет #125).

Чистое сохранение → Акт 1 командами игры → Акты 2–4 командами и хуками
(`walk_act2`, `walk_act3`, `walk_act4` сайтом или ботом) → `enter 5` →
«GitHub» рассказом → «Приватный репозиторий»: проект связан с хранилищем и
отправлен → «Одна версия»: мелочь поправлена, сохранена и отправлена →
«Чужой сервис»: рассказ, потом проверка ключей → «Третье место» рассказом →
ранг Мастер → финал → памятка.

GitHub здесь — голая копия на диске. Адрес `origin` проекта —
`git@github.com:…`, как его связывает Claude по замеру
(`docs/research/2026-10-16-act5-facts.md`); отправку git уводит в голую копию
правилом `pushInsteadOf` в настройках git песочной домашней папки. Папка
проекта о подмене не знает: `git remote get-url origin` видит адрес GitHub,
`git push` двигает ветку `origin/<ветка>` — как настоящая отправка. Закрыто
ли хранилище, отвечает стаб `curl` (`fake_github`): 404, как GitHub без входа.

Сохранение не засевается нигде: закрытые квесты пишут команды игры, следы
прежних актов — хук. Что делает Claude по словам человека — правку,
сохранение, отправку, ключ в `.env`, — кладёт тест так, как это делает Claude
по скиллу акта.

Это и есть конец игры в тестах: полоса, карта, `finale`, трофей, три места,
куда идти дальше, памятка после конца. Механику выключенного акта («игра
пока кончается») держит фикстура `last_act_muted` в других файлах.
"""
import json
import subprocess

import pytest

from conftest import _git
from jedicoder import acts, cli, debrief, ranks, scroll
from jedicoder import state as st
from test_act2_entry import close_act1, game  # noqa: F401 — фикстура
from test_act2_walkthrough import walk_act2
from test_act3_walkthrough import walk_act3
from test_act4_checks import past_the_last_save
from test_act4_checks import TOKEN as BOT_TOKEN
from test_act4_walkthrough import BOT, KINDS, SITE, servers, walk_act4  # noqa: F401
from test_act5_checks import fake_github  # noqa: F401 — фикстура
from test_act5_entry import QUESTS, TITLES
from test_human_screens import machine_words

#: Адрес хранилища, который прислал человек и по которому Claude связал
#: проект: ssh, а не https — без `gh` отправка по https спросила бы пароль.
ADDRESS = "git@github.com:padawan/kruzhok.git"

#: Ключ сервиса погоды — выдуманный, по форме настоящего: 32 знака.
WEATHER_KEY = "3f2a9c1d7e5b4a6f8c0d2e4f6a8b0c1d"


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    """Песочная домашняя папка: проверки Акта 3 смотрят в неё, git берёт из
    неё правило отправки в голую копию."""
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


def make_github(root, home):
    """GitHub на диске: голая копия и правило отправки в неё.

    Правило лежит в настройках git домашней папки, а не проекта: папка
    проекта остаётся такой, какой её оставил бы настоящий GitHub. Отдаёт
    путь голой копии.
    """
    bare = root / "github" / "padawan" / "kruzhok.git"
    bare.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True,
                   capture_output=True)
    with (home / ".gitconfig").open("a", encoding="utf-8") as config:
        config.write('[url "{}"]\n\tpushInsteadOf = {}\n'.format(bare, ADDRESS))
    return bare


@pytest.fixture
def github(tmp_path, home, fake_github):  # noqa: F811
    """GitHub для прохода: голая копия и ответ API «закрыто» (404)."""
    fake_github.answer(404)
    return make_github(tmp_path, home)


# --- что делает Claude по словам человека --------------------------------------

def branch(proj):
    return subprocess.run(
        ["git", "symbolic-ref", "--short", "HEAD"], cwd=str(proj),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def send(proj):
    """«Отправь на GitHub»: `git push` текущей ветки."""
    _git(proj, "push", "-q", "-u", "origin", branch(proj))


def save_and_send(proj, message):
    """«Сделай коммит и отправь на GitHub»."""
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", message)
    send(proj)


def do_link(proj):
    """Человек создал на сайте закрытое хранилище и прислал адрес; Claude
    проверил ключи, связал проект и по слову «отправляй» отправил."""
    _git(proj, "remote", "add", "origin", ADDRESS)
    send(proj)


#: Мелочь «Одной версии» — по типу продукта.
FIX = {
    SITE: ("index.html", "<h1>Кружок «Радуга»</h1>\n<p>Ждём с 1 сентября</p>\n"),
    BOT: ("bot.py", None),
}


def do_fix(proj, kind):
    """Мелочь поправлена — человек посмотрел и сказал «сделай коммит»."""
    name, text = FIX[kind]
    target = proj / name
    if text is None:
        text = target.read_text(encoding="utf-8") + "# приветствие теплее\n"
    target.write_text(text, encoding="utf-8")


WEATHER_JS = (
    "// Погода на сегодня: Open-Meteo, без ключа.\n"
    "fetch('https://api.open-meteo.com/v1/forecast?latitude=54.7&longitude=55.9"
    "&current=temperature_2m')\n"
)
WEATHER_PY = (
    "import os\n"
    "KEY = os.environ['WEATHER_API_KEY']\n"
    "URL = 'https://api.openweathermap.org/data/2.5/weather'\n"
)


def do_service(proj, kind):
    """«Вот ссылка на документацию. Изучи и скажи, что нужно для подключения».

    Сайт без своего сервера ключ не спрячет — ему сервис без ключа. Боту —
    сервис с ключом: человек выпустил его в кабинете, Claude положил его в
    `.env` (закрыт от сохранений с первого вечера), код берёт ключ оттуда.
    """
    if kind == SITE:
        (proj / "weather.js").write_text(WEATHER_JS, encoding="utf-8")
        return
    env = proj / ".env"
    env.write_text(
        env.read_text(encoding="utf-8") + "WEATHER_API_KEY={}\n".format(WEATHER_KEY),
        encoding="utf-8",
    )
    (proj / "weather.py").write_text(WEATHER_PY, encoding="utf-8")


def walk_act5(game, proj, home, kind=SITE, screens=None):  # noqa: F811
    """Пройти Акт 5 от входа до закрытия. Акты 1–4 закрыты, GitHub на диске
    поднят (`github` или `make_github`).

    `screens` — список, в который ложится каждый экран пути по порядку.
    Возвращает экран последней команды — закрытие акта и конец игры.
    """

    def step(*argv, **expect):
        code, out = game(*argv)
        assert code == expect.get("code", 0), (argv, out)
        if screens is not None:
            screens.append(out)
        return out

    step("enter", "5")
    # «GitHub»: Claude сделал ключ компьютера, человек добавил его на сайте,
    # GitHub назвал аккаунт, человек сказал «да, мой».
    step("ack", "5", "01-github")
    do_link(proj)
    step("check", "5", "02-private")
    do_fix(proj, kind)
    save_and_send(proj, "Мелочь: приветствие")
    step("check", "5", "03-sync")
    do_service(proj, kind)
    # Человек посмотрел, что продукт теперь умеет, и рассказал.
    step("seen", "5", "04-service")
    step("check", "5", "04-service")
    save_and_send(proj, "Погода от чужого сервиса")
    return step("ack", "5", "05-server")


def walk_the_whole_game(game, proj, home, kind=SITE, servers=None,  # noqa: F811
                        screens=None):
    """Вся игра командами и хуками: Акты 1–5."""
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    walk_act4(game, proj, home, kind, servers)
    return walk_act5(game, proj, home, kind, screens)


@pytest.fixture(params=KINDS)
def master(request, game, project, home, servers, github):  # noqa: F811
    """Игра пройдена до конца — сайтом и ботом. Отдаёт (игра, папка, экраны
    Акта 5, тип продукта)."""
    proj = project()
    screens = []
    walk_the_whole_game(game, proj, home, request.param, servers, screens)
    return game, proj, screens, request.param


@pytest.fixture
def sentinel(game, project, home, github):  # noqa: F811
    """Четыре вечера пройдены ботом, часы ушли за последнее сохранение.
    Отдаёт (игра, папка)."""
    proj = project()
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    walk_act4(game, proj, home, BOT)
    past_the_last_save(proj)
    return game, proj


@pytest.fixture
def at_sync(sentinel):
    """Он вошёл в Акт 5, подключил GitHub и отправил проект в закрытое
    хранилище. Новых сохранений после входа нет. Отдаёт (игра, папка)."""
    game, proj = sentinel  # noqa: F811
    assert game("enter", "5")[0] == 0
    assert game("ack", "5", "01-github")[0] == 0
    do_link(proj)
    assert game("check", "5", "02-private")[0] == 0
    return game, proj


@pytest.fixture
def at_service(at_sync):
    game, proj = at_sync  # noqa: F811
    do_fix(proj, BOT)
    save_and_send(proj, "Мелочь")
    assert game("check", "5", "03-sync")[0] == 0
    return game, proj


def git_log(proj):
    return subprocess.run(
        ["git", "log", "-p", "--all"], cwd=str(proj),
        capture_output=True, text=True, check=True,
    ).stdout


# --- проход ------------------------------------------------------------------

@pytest.mark.parametrize("kind", KINDS)
def test_novice_walks_the_whole_game_from_a_clean_save_to_master(
        game, project, home, servers, github, kind):  # noqa: F811
    """Приёмка тикета: от чистого сохранения до Мастера и финала, без засева."""
    proj = project()
    assert not game.state_path.exists()
    close_act1(game, proj)
    walk_act2(game, proj)
    walk_act3(game, proj, home)
    walk_act4(game, proj, home, kind, servers)
    assert st.load(game.state_path)["rank"] == "sentinel"

    walk_act5(game, proj, home, kind)

    data = st.load(game.state_path)
    assert data["rank"] == "master" == ranks.FINAL_RANK
    assert ranks.rank_for(data) == "master"
    assert data["acts"]["5"]["status"] == ranks.STATUS_DONE
    assert acts.all_closed(data, 5) is True
    assert sorted(data["acts"]["5"]["quests"]) == sorted(QUESTS)
    assert data["artifacts"] == ["brainstorm", "handoff", "investigate", "goal", "cso"]
    facts = debrief.facts(data)
    assert facts["acts_completed"] == [1, 2, 3, 4, 5]
    assert facts["first_try"]["passed"] == facts["first_try"]["attempted"]

    # На GitHub — та же версия, что на компьютере.
    local = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(proj),
                           capture_output=True, text=True, check=True).stdout
    remote = subprocess.run(
        ["git", "--git-dir", str(github), "rev-parse", branch(proj)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert local == remote
    # Ключи не попали ни в сохранение игры, ни в сохранения проекта, ни на
    # GitHub.
    log = git_log(proj)
    pushed = subprocess.run(
        ["git", "--git-dir", str(github), "log", "-p", "--all"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "Погода от чужого сервиса" in pushed
    for secret in (WEATHER_KEY, BOT_TOKEN):
        assert secret not in game.state_path.read_text(encoding="utf-8")
        assert secret not in log and secret not in pushed

    code, out = game("finale")
    assert code == 0, out
    assert out.splitlines()[0] == "=== Карточка Мастера ==="
    data = st.load(game.state_path)
    assert data["finale_announced"] is True
    assert len([e for e in data["pending_sync"] if e["type"] == "finale"]) == 1


# --- что человек читает на пути закрытия ---------------------------------------

def test_closing_act5_says_the_game_is_over(master):
    _, _, screens, _ = master
    assert screens[-1].splitlines() == [
        "Квест «Третье место» закрыт: ты своими словами рассказал про третье место.",
        "",
        "Акт 5. Три места кода — закрыт.",
        "Новый ранг: Мастер.",
        "",
        "Это конец игры: все акты пройдены.",
        "Попроси Claude показать финал и положить памятку в папку проекта.",
    ]
    assert "ещё не написан" not in screens[-1] and "пока кончается" not in screens[-1]


def test_no_screen_of_act5_speaks_to_the_model(master):
    game, _, screens, _ = master  # noqa: F811
    screens.append(game("status")[1])
    for screen in screens:
        assert machine_words(screen) == [], screen
        assert "Traceback" not in screen
        for quest_id in QUESTS:
            assert quest_id not in screen, screen
        for secret in (WEATHER_KEY, BOT_TOKEN):
            assert secret not in screen


def test_each_quest_of_act5_closes_in_its_own_words(master):
    _, _, screens, kind = master
    assert screens[2].splitlines() == [
        "Квест «Приватный репозиторий» закрыт.",
        "  [x] Проект связан с хранилищем на GitHub",
        "  [x] Код отправлен в хранилище padawan/kruzhok",
        "  [x] Хранилище закрытое: чужие его не видят",
    ]
    assert screens[3].splitlines() == [
        "Квест «Одна версия» закрыт.",
        "  [x] После входа в акт есть новое сохранение",
        "  [x] Несохранённых правок нет",
        "  [x] На GitHub та же версия, что на компьютере",
    ]
    assert screens[4].splitlines() == [
        "Записано: в квесте «Чужой сервис» ты рассказал, что продукт теперь умеет.",
    ]
    # Сайту — сервис без ключа: строки о `.env` нет. У бота `.env` с ключами.
    env_line = ["  [x] Файл .env не попадает в сохранения и на GitHub"] if kind == BOT else []
    assert screens[5].splitlines() == ["Квест «Чужой сервис» закрыт."] + env_line + [
        "  [x] Ключей нет в коде и в других файлах",
        "  [x] Ключей нет в сохранениях",
    ]


def test_first_screen_after_the_end_word_for_word(master):
    game, _, _, _ = master  # noqa: F811
    code, out = game("status")
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "Ранг: Мастер"
    start = lines.index("Карта:")
    assert lines[start:start + 6] == [
        "Карта:",
        "  Акт 1. Знакомство — пройден",
        "  Акт 2. Память и силы — пройден",
        "  Акт 3. Умения — пройден",
        "  Акт 4. Свой продукт — пройден",
        "  Акт 5. Три места кода — пройден",
    ]
    assert "ещё не написан" not in out
    assert lines[-2:] == [
        "Что дальше: игра пройдена, все акты закрыты.",
        "  Попроси Claude показать финал и положить памятку в папку проекта.",
    ]


def test_finale_draws_the_master_card_and_three_doors(master):
    """Приёмка тикета: карточка Мастера и три приглашения строками —
    консультация, обучение, клуб — и адрес страницы финала."""
    game, proj, _, _ = master  # noqa: F811
    code, out = game("finale")
    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "=== Карточка Мастера ==="
    assert lines[2] == cli.TROPHY_LINES[5]
    assert "Закрыто актов: 5 из 5." in lines
    for number in range(1, 6):
        assert "  Акт {}. {}".format(number, ranks.ACTS[number]["title"]) in lines
    doors = lines.index("Куда идти дальше:")
    # Слова — по смыслу те же, что на странице финала сайта (#126).
    assert lines[doors:doors + 8] == [
        "Куда идти дальше:",
        "  Консультация с автором игры — личный разбор продукта и выкладка в "
        "интернет: сервер и домен.",
        "    Записи по календарю нет — договоримся в переписке: "
        "https://t.me/iulaijedi",
        "  Обучение — мини-курсы, инструменты и живые события, чтобы дальше "
        "учиться самому:",
        "    https://jedicoder.store/academy",
        "  Клуб — закрытый чат, где есть у кого спросить и кому показать:",
        "    https://t.me/Jedicoderstore_bot?start=buy_club",
        "Кто вёл тебя всю игру — на странице финала: https://jedicoder.store/finale",
    ]
    # Ответ читает модель: чем выдать памятку, он называет ручкой.
    assert lines[-1] == "  scroll"
    for other in (1, 2, 3, 4):
        assert cli.TROPHY_LINES[other] not in out
    assert "ещё не" not in out


def test_the_finale_is_announced_to_the_bot_once(master):
    game, _, _, _ = master  # noqa: F811
    assert game("finale")[0] == 0
    assert game("finale")[0] == 0
    data = st.load(game.state_path)
    finals = [e for e in data["pending_sync"] if e["type"] == "finale"]
    assert len(finals) == 1
    assert finals[0]["payload"]["rank"] == "master"


def test_memo_at_the_end_carries_the_key_check_the_phrases_and_the_doors(master):
    game, proj, _, _ = master  # noqa: F811
    code, out = game("scroll")
    assert code == 0, out
    assert out.splitlines()[0] == "Памятка Мастера: {}/docs/jedicoder".format(proj.name)
    assert machine_words(out) == []
    folder = proj / "docs" / "jedicoder"
    names = sorted(path.name for path in folder.iterdir())
    for name in ("cso.md", "goal.md", "investigate.md", "handoff.md",
                 "brainstorm.md", "frazy.md", scroll.ROADMAP_NAME,
                 scroll.RANK_CARD_NAME):
        assert name in names, name
    assert "deploy.md" not in names
    razbor = (folder / "razbor.md").read_text(encoding="utf-8")
    assert "- Закрыто актов: 5 из 5" in razbor
    for quest_id in QUESTS:
        assert quest_id not in razbor
    for title in TITLES:
        assert "| 5 | {} |".format(title) in razbor, title
    # Фразы пятого вечера — рядом с фразами первых четырёх.
    frazy = (folder / "frazy.md").read_text(encoding="utf-8")
    for row in (
        "| Поправил, проверил, работает | Сделай коммит и отправь на GitHub |",
        "| Нужно подключить сервис | Вот ссылка на документацию. Изучи и скажи, "
        "что нужно для подключения |",
        "| Выпустил ключ в кабинете сервиса | Вот ключ, положи его в `.env`. В "
        "код и в сохранения его не пиши |",
        "| Перед отправкой кода и после нового ключа | Проверь, не утекают ли ключи |",
    ):
        assert row in frazy, row
    for word in ("квест", "Квест", "акт ", "Акт", "ранг", "Jedicoder", "jedicoder"):
        assert word not in frazy, word
    # Карточка в памятке — та же, что в финале: с трофеем и тремя местами.
    card = (folder / scroll.RANK_CARD_NAME).read_text(encoding="utf-8")
    assert cli.TROPHY_LINES[5] in card
    for door in cli.render_doors():
        assert door in card
    # Впереди ничего: страница так и говорит, без пустого раздела.
    path = (folder / scroll.ROADMAP_NAME).read_text(encoding="utf-8")
    assert scroll.PATH_ALL_DONE in path
    assert "- Акт 5 «Три места кода» — ранг Мастер." in path
    assert "ещё не пройден" not in path and "не написан" not in path
    everything = "\n".join(p.read_text(encoding="utf-8") for p in folder.iterdir())
    for secret in (WEATHER_KEY, BOT_TOKEN):
        assert secret not in everything


def test_the_strip_after_the_end_never_asks_for_what_is_done(master):
    """Полоса после конца не зовёт за тем, что у человека уже есть: прежняя
    звала за памяткой и после её выдачи."""
    game, _, _, _ = master  # noqa: F811
    end = "Что дальше: игра пройдена, все акты закрыты."
    first = strip_and_map(game)
    assert first[:2] == (end, cli.FINALE_INVITE)
    assert game("scroll")[0] == 0
    assert strip_and_map(game)[:2] == (end, cli.FINALE_ONLY_INVITE)
    assert game("finale")[0] == 0
    last = strip_and_map(game)
    assert last[:2] == (end, cli.END_DONE)
    # Остальное не меняется: карта, счёт квестов, ранг, фраза для поля ввода.
    assert last[2:] == first[2:]
    code, out = game(cli.TOOL_CALL, "enter")
    assert code == 1 and out.splitlines() == [cli.GAME_OVER, cli.END_DONE]


def test_a_memo_of_act4_is_not_the_memo_of_the_end(sentinel, home):
    """Памятку взяли Стражем, после Акта 4. После Мастера и финала полоса
    зовёт за новой: в прежней нет ни Мастера, ни трёх мест (ревью #125)."""
    game, proj = sentinel  # noqa: F811
    assert game("scroll")[0] == 0
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "Памятка Стража")
    closing = walk_act5(game, proj, home, BOT)
    assert "Новый ранг: Мастер." in closing
    assert game("finale")[0] == 0
    end = "Что дальше: игра пройдена, все акты закрыты."
    assert strip_and_map(game)[:2] == (end, cli.MEMO_INVITE)
    assert game("scroll")[0] == 0
    assert strip_and_map(game)[:2] == (end, cli.END_DONE)
    assert st.load(game.state_path)["scroll"]["rank"] == "master"


def test_after_the_finale_the_strip_asks_only_for_the_memo():
    data = {"finale_announced": True}
    assert cli._after_the_end(data) == cli.MEMO_INVITE
    files = {"README.md": {"sha256": "x"}}
    # Памятка прежнего ранга или без записанного ранга — не памятка конца.
    for rank in (None, "sentinel"):
        data["scroll"] = {"files": files, "rank": rank}
        assert cli._after_the_end(data) == cli.MEMO_INVITE
    data["scroll"] = {"files": files, "rank": "master"}
    assert cli._after_the_end(data) == cli.END_DONE
    for broken in ({"scroll": "строка"}, {"scroll": {"files": {}}},
                   {"finale_announced": "да"}):
        assert cli._after_the_end(broken) == cli.FINALE_INVITE


def test_after_the_end_the_tools_say_the_game_is_over(master):
    game, _, _, _ = master  # noqa: F811
    code, out = game(cli.TOOL_CALL, "enter")
    assert code == 1
    assert out.splitlines() == [cli.GAME_OVER, cli.FINALE_INVITE]
    for name in ("check", "seen", "ack"):
        code, out = game(cli.TOOL_CALL, name, "Третье место")
        assert code == 1, out
        lines = out.splitlines()
        assert lines[0] == cli.TOOL_QUEST_CLOSED.format("«Третье место»")
        assert lines[1] == cli.TOOL_NO_QUEST
        assert lines[2] == "Что дальше: игра пройдена, все акты закрыты."
        assert "05-server" not in out and "Traceback" not in out
        assert "ещё не написан" not in out


# --- Полоса, всплывающие и карта в каждом состоянии акта ------------------------

def strip_and_map(game):  # noqa: F811
    """Строка «Что дальше» первого экрана, она же в снимке Лица, строка карты
    об Акте 5 и то, по чему Лицо решает о всплывающих."""
    code, out = game("status")
    assert code == 0, out
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("Что дальше:"))
    step = [line.strip() for line in lines[start:start + 2]]
    code, raw = game("face", "--called")
    assert code == 0, raw
    face = json.loads(raw)
    assert face["is_game"] is True
    assert face["next"] == step
    assert face["toast_quest"] == "Квест закрыт"
    assert face["toast_rank"] == "Новый ранг: {}".format(face["rank"])
    act5 = next(line.strip() for line in lines if line.startswith("  Акт 5."))
    return step[0], step[1], act5, face["quests_closed"], face["rank"], face["say"]


def test_strip_toasts_and_map_are_true_in_every_state_of_the_act(sentinel, content_root):
    game, proj = sentinel  # noqa: F811
    tasks = cli._quest_tasks(content_root)
    quest = "Что дальше: квест «{}» — Акт 5 «Три места кода»."
    going = "Акт 5. Три места кода — идёт, квестов закрыто: {}/5"

    def see():
        return strip_and_map(game)

    assert see() == (
        "Что дальше: начать Акт 5 «Три места кода» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
        "Акт 5. Три места кода — не начат, квестов закрыто: 0/5",
        20, "Страж", cli.SAY_START,
    )
    assert game("enter", "5")[0] == 0
    assert see() == (quest.format("GitHub"), tasks[(5, "01-github")],
                     going.format(0), 20, "Страж", "")
    assert game("ack", "5", "01-github")[0] == 0

    assert see() == (quest.format("Приватный репозиторий"), tasks[(5, "02-private")],
                     going.format(1), 21, "Страж", "")
    do_link(proj)
    assert game("check", "5", "02-private")[0] == 0

    assert see() == (quest.format("Одна версия"), tasks[(5, "03-sync")],
                     going.format(2), 22, "Страж", "")
    do_fix(proj, BOT)
    save_and_send(proj, "Мелочь")
    assert game("check", "5", "03-sync")[0] == 0

    assert see() == (quest.format("Чужой сервис"), tasks[(5, "04-service")],
                     going.format(3), 23, "Страж", "")
    do_service(proj, BOT)
    assert see()[1] == tasks[(5, "04-service")]
    assert game("seen", "5", "04-service")[0] == 0
    assert see()[1] == cli.STEP_WORDS_TAKEN
    assert game("check", "5", "04-service")[0] == 0

    assert see() == (quest.format("Третье место"), tasks[(5, "05-server")],
                     going.format(4), 24, "Страж", "")
    assert game("ack", "5", "05-server")[0] == 0

    # Акт закрыт и игра пройдена: ранг вырос — Лицо покажет подпись о ранге.
    # Начинать больше нечего — фразы для поля ввода нет.
    assert see() == (
        "Что дальше: игра пройдена, все акты закрыты.",
        cli.FINALE_INVITE,
        "Акт 5. Три места кода — пройден",
        25, "Мастер", "",
    )


# --- «Одна версия»: чего игра не принимает --------------------------------------

def test_one_version_needs_a_save_made_in_this_act_and_sent(at_sync):
    """Отправка прежних сохранений — ещё не «одна версия»: нужна правка этого
    вечера, сохранённая и отправленная."""
    game, proj = at_sync  # noqa: F811
    code, out = game("check", "5", "03-sync")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Одна версия» пока не закрыт. Не сошлось:",
        "  [ ] После входа в акт есть новое сохранение",
        "      Попроси Claude поправить мелочь в продукте. Посмотри и скажи: "
        "«Сделай коммит и отправь на GitHub».",
    ]
    do_fix(proj, BOT)
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "Мелочь")
    code, out = game("check", "5", "03-sync")
    assert code == 1
    assert out.splitlines()[-2:] == [
        "  [ ] На GitHub та же версия, что на компьютере",
        "      Последнее сохранение ещё не на GitHub. Скажи Claude: «Отправь на GitHub».",
    ]
    send(proj)
    code, out = game("check", "5", "03-sync")
    assert code == 0, out
    data = st.load(game.state_path)
    assert data["acts"]["5"]["quests"]["03-sync"]["attempts"] == 3
    assert machine_words(out) == []


def test_one_version_waits_for_no_story(at_sync):
    game, _ = at_sync  # noqa: F811
    code, out = game("seen", "5", "03-sync")
    assert code == 1 and "рассказа не ждёт" in out


# --- «Чужой сервис»: рассказ раньше проверки ------------------------------------

def test_the_service_waits_for_the_story(at_service):
    game, proj = at_service  # noqa: F811
    do_service(proj, BOT)
    code, out = game("check", "5", "04-service")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Чужой сервис» пока не проверяю.",
        "Сначала посмотри, что продукт теперь умеет с новым сервисом. Потом "
        "расскажи Claude, что увидел.",
    ]
    data = st.load(game.state_path)
    assert (data["acts"]["5"]["quests"].get("04-service") or {}).get("attempts", 0) == 0
    assert machine_words(out) == []


def test_the_story_is_not_taken_while_a_key_sits_in_the_code(at_service):
    """Рассказа с ключом в коде не бывает: игра называет, что поправить, и
    сам ключ не повторяет."""
    game, proj = at_service  # noqa: F811
    do_service(proj, BOT)
    (proj / "weather.py").write_text("KEY = '{}'\n".format(WEATHER_KEY), encoding="utf-8")
    code, out = game("seen", "5", "04-service")
    assert code == 1
    assert out.splitlines() == [
        "Рассказ пока не записан: с ключами не всё на месте.",
        "Вот что поправить:",
        "  [ ] Ключей нет в коде и в других файлах",
        "      Ключ лежит здесь: weather.py. Попроси Claude: «Убери ключ из кода — "
        "пусть код берёт его из .env».",
    ]
    assert WEATHER_KEY not in out
    data = st.load(game.state_path)
    assert (data["acts"]["5"]["quests"].get("04-service") or {}).get("attempts", 0) == 0
    (proj / "weather.py").write_text(WEATHER_PY, encoding="utf-8")
    code, out = game("seen", "5", "04-service")
    assert code == 0, out
    code, out = game("check", "5", "04-service")
    assert code == 0, out


def test_a_key_written_into_the_code_after_the_story_takes_the_story_back(at_service):
    game, proj = at_service  # noqa: F811
    do_service(proj, BOT)
    assert game("seen", "5", "04-service")[0] == 0
    (proj / "weather.py").write_text("KEY = '{}'\n".format(WEATHER_KEY), encoding="utf-8")
    code, out = game("check", "5", "04-service")
    assert code == 1
    assert "  [ ] Ключей нет в коде и в других файлах" in out.splitlines()
    assert WEATHER_KEY not in out
    data = st.load(game.state_path)
    assert not data["acts"]["5"]["quests"]["04-service"].get("seen")
    (proj / "weather.py").write_text(WEATHER_PY, encoding="utf-8")
    code, out = game("check", "5", "04-service")
    assert code == 1 and "пока не проверяю" in out
    assert game("seen", "5", "04-service")[0] == 0
    assert game("check", "5", "04-service")[0] == 0


def test_act5_is_closed_by_the_tools_by_screen_names(at_sync):
    game, proj = at_sync  # noqa: F811
    do_fix(proj, BOT)
    save_and_send(proj, "Мелочь")
    code, out = game(cli.TOOL_CALL, "check", "Одна версия")
    assert code == 0 and out.startswith("Квест «Одна версия» закрыт"), out
    do_service(proj, BOT)
    code, out = game(cli.TOOL_CALL, "check", "Чужой сервис")
    assert code == 1 and "пока не проверяю" in out
    code, out = game(cli.TOOL_CALL, "seen", "Чужой сервис")
    assert code == 0, out
    code, out = game(cli.TOOL_CALL, "check", "Чужой сервис")
    assert code == 0 and out.startswith("Квест «Чужой сервис» закрыт"), out
    code, out = game(cli.TOOL_CALL, "ack", "Третье место")
    assert code == 0 and "Новый ранг: Мастер." in out
    assert cli.GAME_OVER in out

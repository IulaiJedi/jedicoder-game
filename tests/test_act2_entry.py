"""Акт 2 «Память и силы» открыт: вход, приём «Передача», первые экраны.

Той же дверью, что человек: сохранение не засевается, Акт 1 проходится
командами игры, и только потом — `enter 2`.

Целиком акт здесь не проходится. Три его квеста судят след — действие,
которого нет в папке проекта (ADR-0020 в репозитории сайта); след пишет хук
игровой сессии, проверке его передаёт команда игры. Здесь хуков нет, и
стережётся обратная сторона: без следа проверка на живой игре честно
отвечает провалом — и что именно она говорит человеку. Проход «Плана» и
«Чистого листа» с хуками — `tests/test_traces.py` (#101); «Покажи» —
`tests/test_show_traces.py` (#102); сквозной проход до ранга Падаван —
`tests/test_act2_walkthrough.py` (#103).
"""
import json

import pytest

from jedicoder import acts, cli, quests, ranks
from jedicoder import state as st
from test_act1_walkthrough import ACK as ACT1_ACK
from test_act1_walkthrough import walk_scripted
from test_act2_checks import MEMORY_OK
from test_human_screens import machine_words

ACT = 2
QUESTS = ("01-plan", "02-show", "03-memory", "04-clear", "05-powers")
TITLES = ("План", "Покажи", "Память проекта", "Чистый лист", "Силы")
#: Квесты, чья проверка ждёт следа.
TRACE_QUESTS = ("01-plan", "02-show", "04-clear")


@pytest.fixture
def game(tmp_path, content_root, quests_root, capsys):
    """Чистая установка: сохранения ещё нет, его создаёт первая команда."""
    state_path = tmp_path / "state.json"

    def jc(*argv):
        code = cli.main(
            list(argv), state_path=state_path, content_root=content_root,
            quests_root=quests_root,
        )
        return code, capsys.readouterr().out

    jc.state_path = state_path
    return jc


def close_act1(game, proj):
    """Пройти Акт 1 командами игры — как человек, без записи в сохранение."""
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    walk_scripted(game, proj)
    assert game("ack", "1", ACT1_ACK)[0] == 0


@pytest.fixture
def entered(game, project):
    """Человек прошёл Акт 1 и вошёл во второй. Отдаёт (игра, папка)."""
    proj = project()
    close_act1(game, proj)
    code, out = game("enter", "2")
    assert code == 0, out
    return game, proj


# --- реестр ------------------------------------------------------------------

def test_quest_order_declared():
    assert acts.quest_ids(ACT) == QUESTS
    assert [acts.quest_kind(ACT, quest_id) for quest_id in QUESTS] == [
        acts.KIND_SCRIPT, acts.KIND_SCRIPT, acts.KIND_SCRIPT, acts.KIND_SCRIPT,
        acts.KIND_ACK,
    ]


def test_act2_does_not_branch():
    """Развилки нет: состав отдаётся без трека и одинаков для обоих."""
    for track in (None, acts.TRACK_CRAFTSMAN, acts.TRACK_FOUNDER):
        assert acts.quest_ids(ACT, track) == QUESTS


def test_act1_has_declared_quests():
    """У Акта 1 «Знакомство» развилки нет: состав отдаётся без трека."""
    assert acts.quest_ids(1) == (
        "01-folder", "02-idea", "03-first-request", "04-save", "05-stop-undo",
    )
    assert acts.quest_ids(1, acts.TRACK_FOUNDER) == acts.quest_ids(1)
    assert acts.quest_kind(1, "01-folder") == acts.KIND_SCRIPT
    assert acts.quest_kind(1, "05-stop-undo") == acts.KIND_ACK


def test_registry_names_the_act_its_artifact_and_rank():
    info = ranks.ACTS[ACT]
    assert info == {
        "slug": "act2-pamyat-i-sily", "title": "Память и силы",
        "artifact": "handoff", "rank": "padawan",
    }
    assert ranks.MUTED_ACTS == (5,)
    assert not ranks.is_muted(ACT)


def test_clear_waits_for_words_and_nothing_else_in_the_act_does():
    assert acts.needs_words(ACT, "04-clear")
    for quest_id in QUESTS:
        if quest_id != "04-clear":
            assert not acts.needs_words(ACT, quest_id), quest_id
    # Ворота Акта 1 на месте.
    assert acts.needs_words(1, "03-first-request")


def test_every_scripted_quest_has_its_check_on_disk(quests_root):
    for quest_id in QUESTS:
        script = quests.script_path(quests_root, ranks.ACTS[ACT]["slug"], quest_id)
        scripted = acts.quest_kind(ACT, quest_id) == acts.KIND_SCRIPT
        assert script.is_file() is scripted, quest_id


def test_content_describes_the_act_as_the_registry_does(content_root):
    from jedicoder import content

    scene = next(item for item in content.load_acts(content_root) if item.act == ACT)
    assert scene.slug == "act2-pamyat-i-sily"
    assert scene.quests == QUESTS
    assert tuple(scene.quest_titles) == TITLES
    assert len(scene.quest_tasks) == len(QUESTS)
    assert scene.muted is False
    # Катсцена — ровно две фразы, каждая своим абзацем.
    paragraphs = [part for part in scene.body.split("\n\n") if part.strip()]
    assert len(paragraphs) == 2


# --- вход: Акт 1 целиком, потом `enter 2` ------------------------------------

def test_act2_is_closed_until_act1_is_done(game, project):
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    code, out = game("enter", "2")
    assert code == 1
    assert "Сначала закрой Акт 1" in out
    data = st.load(game.state_path)
    assert "2" not in data["acts"] and data["artifacts"] == ["brainstorm"]
    assert game("artifact", "handoff")[0] == 1


def test_after_act1_the_next_step_is_act2(game, project):
    close_act1(game, project())
    _, out = game("status")
    lines = out.splitlines()
    assert "  Акт 1. Знакомство — пройден" in lines
    assert "  Акт 2. Память и силы — не начат, квестов закрыто: 0/5" in lines
    assert "  Акт 3. Умения — не начат, квестов закрыто: 0/5" in lines
    assert "  Акт 4. Свой продукт — не начат, квестов закрыто: 0/5" in lines
    assert "  Акт 5 ещё не написан" in lines
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: начать Акт 2 «Память и силы» — квестов в нём 5.",
        "  Скажи Claude: «начинаем».",
    ]
    assert machine_words(out) == []


def test_enter_act2_prints_five_quests_in_words_and_gives_the_handoff(game, project):
    """Приёмка тикета: с чистого сохранения Акт 1 целиком → `enter 2`."""
    close_act1(game, project())
    code, out = game("enter", "2")

    assert code == 0, out
    lines = out.splitlines()
    assert lines[0] == "Акт 2. Память и силы — начат."
    # Две фразы катсцены — раньше списка квестов.
    assert lines[2] == (
        "В этом акте ты учишься просить план и показывать Claude то, что "
        "видишь сам."
    )
    assert lines[4] == (
        "К концу вечера у проекта появится память, а ты узнаешь, где "
        "смотреть лимит."
    )
    assert "Квесты акта (5):" in lines
    start = lines.index("Квесты акта (5):") + 1
    assert lines[start:start + 5] == [
        "  1. План. Попроси у Claude план следующего дела и одобри его.",
        "  2. Покажи. Покажи Claude файл проекта и снимок экрана.",
        "  3. Память проекта. Продиктуй Claude четыре вещи о своём проекте — "
        "он их запишет.",
        "  4. Чистый лист. Запиши передачу и начни новый разговор с того же места.",
        "  5. Силы. Открой три экрана Claude Code и расскажи об увиденном.",
    ]
    assert "Ранг за акт: Падаван. Это следующая ступень после Искателя." in lines
    assert (
        "Приём этого акта — «Передача»: помогает начать следующий разговор с "
        "того же места. Скажи Claude: «запиши передачу»."
    ) in lines
    # Человеку — слова: ни кодов квестов, ни имён ручек, ни команды приёма.
    for quest_id in QUESTS:
        assert quest_id not in out
    assert "handoff" not in out and "/jedicoder:" not in out.split("Книга")[0]

    data = st.load(game.state_path)
    assert data["current_act"] == 2
    assert data["acts"]["2"]["status"] == ranks.STATUS_IN_PROGRESS
    assert data["artifacts"] == ["brainstorm", "handoff"]
    assert data["rank"] == "seeker"


def test_handoff_lock_opens_on_entry_and_plan_is_gone(game, project):
    """Замок приёма решает кодом возврата; приём `plan` из игры ушёл."""
    proj = project()
    close_act1(game, proj)
    code, out = game("artifact", "handoff")
    assert code == 1 and "на входе в Акт 2" in out

    assert game("enter", "2")[0] == 0
    code, out = game("artifact", "handoff")
    assert code == 0 and out.strip() == "Приём handoff открыт."

    code, out = game("artifact", "plan")
    assert code == 1
    assert "Нет такого приёма: plan." in out and "handoff" in out


def test_first_screen_inside_act2_names_the_quest_and_the_artifact(entered):
    game, _ = entered
    _, out = game("status")
    lines = out.splitlines()
    assert "Ранг: Искатель" in lines
    assert "  Акт 2. Память и силы — идёт, квестов закрыто: 0/5" in lines
    # Приёмов два — строка на приём: у каждого свои слова, у второго и имя.
    start = lines.index("Приёмы: скажи Claude слова в кавычках — он применит приём.")
    assert lines[start + 1:start + 3] == [
        "  найти идею — «помоги найти идею»",
        "  «Передача»: начать следующий разговор с того же места — "
        "«запиши передачу»",
    ]
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: квест «План» — Акт 2 «Память и силы».",
        "  Попроси у Claude план следующего дела и одобри его.",
    ]
    assert machine_words(out) == []


def test_face_snapshot_follows_the_new_act(game, project):
    """Снимок для Полосы говорит о новом составе: до входа и после."""
    def face():
        code, out = game("face", "--called")
        assert code == 0, out
        return json.loads(out)

    close_act1(game, project())
    before = face()
    assert before["next"] == [
        "Что дальше: начать Акт 2 «Память и силы» — квестов в нём 5.",
        "Скажи Claude: «начинаем».",
    ]
    assert before["say"] == cli.SAY_START
    assert before["rank"] == "Искатель" and before["quests_closed"] == 5

    assert game("enter", "2")[0] == 0
    after = face()
    assert after["next"] == [
        "Что дальше: квест «План» — Акт 2 «Память и силы».",
        "Попроси у Claude план следующего дела и одобри его.",
    ]
    assert after["say"] == "" and after["quests_closed"] == 5


def test_project_screen_does_not_ask_about_what_act2_never_asks(entered):
    """База данных и тип продукта — вопросы прежнего Акта 2, он на полке."""
    game, proj = entered
    _, out = game("project")
    assert "Папка: {}".format(proj) in out
    assert "База данных" not in out and "Тип продукта" not in out
    assert "Порт" not in out


# --- квест «Память проекта» командами игры ------------------------------------

def test_memory_quest_fails_then_closes_via_cli(entered):
    game, proj = entered
    code, out = game("check", "2", "03-memory")
    assert code == 1
    assert "Квест «Память проекта» пока не закрыт. Не сошлось:" in out
    assert "  [ ] Память проекта записана в файл CLAUDE.md в папке проекта" in out
    assert machine_words(out) == []

    (proj / "CLAUDE.md").write_text(MEMORY_OK, encoding="utf-8")
    code, out = game("check", "2", "03-memory")
    assert code == 0, out
    assert out.splitlines() == [
        "Квест «Память проекта» закрыт.",
        "  [x] Память проекта записана в файл CLAUDE.md в папке проекта",
        "  [x] Записано, что это за проект",
        "  [x] Записано, как открыть проект",
        "  [x] Записано, чего не трогать",
        "  [x] Записано правило работы",
    ]
    assert machine_words(out) == []
    data = st.load(game.state_path)
    assert data["acts"]["2"]["quests"]["03-memory"]["status"] == ranks.STATUS_DONE
    assert data["acts"]["2"]["status"] == ranks.STATUS_IN_PROGRESS


def test_memory_quest_cannot_be_checked_when_the_folder_is_gone(entered, tmp_path):
    """Третий исход той же дверью: записанной папки на диске больше нет."""
    game, proj = entered
    (proj / "CLAUDE.md").write_text(MEMORY_OK, encoding="utf-8")
    proj.rename(tmp_path / "унесли")
    code, out = game("check", "2", "03-memory")
    assert code == 1
    assert "Не найдена папка проекта" in out
    assert "03-memory" not in st.load(game.state_path)["acts"]["2"]["quests"]


# --- квесты со следом: без следа — честный провал ------------------------------

HONEST_FAILURES = {
    "01-plan": (
        "План",
        ["  [ ] Claude показал план, и ты его одобрил",
         "      Игра не видела одобренного плана. Набери /plan и своё дело. "
         "Прочитай план и нажми Enter на первой строке."],
    ),
    "02-show": (
        "Покажи",
        ["  [ ] Ты показал Claude файл проекта через @",
         "      Игра не видела файла в запросе. Набери @ и выбери файл проекта "
         "из списка. Потом допиши вопрос.",
         "  [ ] Ты показал Claude снимок экрана",
         "      Игра не видела картинки. Сделай снимок экрана и покажи его "
         "Claude вместе с вопросом."],
    ),
}


@pytest.mark.parametrize("quest_id", sorted(HONEST_FAILURES))
def test_trace_quest_fails_on_the_live_game_with_a_hint_in_words(entered, quest_id):
    """Игра действия не видела — проверка говорит, какое действие повторить.

    Провал, а не «не смог проверить»: попытка тратится (спека #99).
    """
    game, _ = entered
    title, rows = HONEST_FAILURES[quest_id]
    code, out = game("check", "2", quest_id)
    assert code == 1
    assert out.splitlines() == [
        "Квест «{}» пока не закрыт. Не сошлось:".format(title),
    ] + rows
    assert machine_words(out) == []
    quest = st.load(game.state_path)["acts"]["2"]["quests"][quest_id]
    assert quest["status"] != ranks.STATUS_DONE and quest["attempts"] == 1


def test_env_for_carries_no_trace_nobody_recorded(entered):
    """Вход в акт и несошедшиеся проверки следов не оставляют: их пишет
    только хук. Что записанный след до проверки доезжает — в
    `tests/test_traces.py`."""
    game, _ = entered
    for quest_id in sorted(HONEST_FAILURES):
        assert game("check", "2", quest_id)[0] == 1
    env = cli._env_for(st.load(game.state_path), ACT)
    assert [name for name in env if name.startswith("JEDICODER_TRACE_")] == []
    assert "JEDICODER_PROJECT_PATH" in env


def test_clear_quest_asks_for_words_before_the_check(entered):
    """«Чистый лист» — слова раньше проверки, и слова о своём, а не о
    «первой версии» из Акта 1."""
    game, _ = entered
    code, out = game("check", "2", "04-clear")
    assert code == 1
    assert out.splitlines() == [
        "Квест «Чистый лист» пока не проверяю.",
        "Сначала начни новый разговор и спроси Claude, на чём остановились. "
        "Потом расскажи, что он ответил.",
    ]
    assert machine_words(out) == []
    # Ворота не тратят попытку: человек ничего не провалил.
    assert "04-clear" not in st.load(game.state_path)["acts"]["2"]["quests"]


def test_clear_quest_does_not_take_words_before_the_new_conversation(entered):
    """Рассказ не принимается заранее: нового разговора игра ещё не видела."""
    game, _ = entered
    code, out = game("seen", "2", "04-clear")
    assert code == 1
    assert out.splitlines() == [
        "Рассказывать пока не о чем: игра не видела нового разговора.",
        "Сначала запиши передачу и набери /clear. Потом спроси Claude, на "
        "чём остановились.",
    ]
    assert "первой версии" not in out
    assert machine_words(out) == []
    assert not quests.seen(st.load(game.state_path), ACT, "04-clear")


def test_words_of_the_first_request_gate_did_not_change(game, project):
    """Слова ворот Акта 1 остались прежними — буква в букву."""
    proj = project()
    assert game("project", "path", str(proj))[0] == 0
    assert game("enter", "1")[0] == 0
    assert game("check", "1", "01-folder")[0] == 0
    code, out = game("seen", "1", "03-first-request")
    assert code == 1
    assert out.splitlines() == [
        "Смотреть пока не на что: в папке проекта ещё нет первой версии.",
        "Сначала попроси Claude её сделать.",
    ]


def test_third_failed_attempt_in_act2_speaks_plainly(entered):
    """Новичок второго вечера ещё не слышал ни «новый чат», ни «ошибку
    целиком»: общий протокол ему не по словам, как и в Акте 1."""
    game, _ = entered
    for _ in range(3):
        code, out = game("check", "2", "01-plan")
        assert code == 1
    assert "Третья попытка. Остановись" in out
    assert "/jedicoder:magistr" in out
    assert "по кругу" not in out and "новый чат" not in out
    assert machine_words(out.replace("/jedicoder:magistr", "")) == []


# --- механика акта -----------------------------------------------------------

def test_next_quest_walks_in_order(entered):
    game, proj = entered
    data = st.load(game.state_path)
    assert acts.next_quest(data, ACT) == "01-plan"
    # «Память проекта» закрыта раньше «Плана» — следующий всё равно «План».
    (proj / "CLAUDE.md").write_text(MEMORY_OK, encoding="utf-8")
    assert game("check", "2", "03-memory")[0] == 0
    data = st.load(game.state_path)
    assert acts.next_quest(data, ACT) == "01-plan"
    assert acts.closed_count(data, ACT) == 1


def test_powers_quest_closes_by_words_and_the_act_stays_open(entered):
    """Квест без проверки закрывает рассказ; акт не закрыт, пока есть открытые."""
    game, _ = entered
    code, out = game("check", "2", "05-powers")
    assert code == 1 and "У квеста «Силы» нет проверки." in out

    code, out = game("ack", "2", "05-powers")
    assert code == 0, out
    assert out.strip() == "Квест «Силы» закрыт: ты рассказал, что увидел."
    data = st.load(game.state_path)
    assert acts.all_closed(data, ACT) is False
    assert data["acts"]["2"]["status"] == ranks.STATUS_IN_PROGRESS
    assert data["rank"] == "seeker"
    assert game("enter", "3")[0] == 1


def test_scripted_quests_do_not_close_by_words(entered):
    game, _ = entered
    for quest_id, title in zip(QUESTS[:4], TITLES[:4]):
        code, out = game("ack", "2", quest_id)
        assert code == 1, quest_id
        assert "У квеста «{}» есть проверка.".format(title) in out
    assert st.load(game.state_path)["acts"]["2"]["quests"] == {}


def test_finale_names_the_acts_still_ahead(entered):
    game, _ = entered
    code, out = game("finale")
    assert code == 1
    assert "Игра ещё не кончилась: Акт 5 ещё не написан." in out
    assert "Ближайший незакрытый — Акт 2 «Память и силы»." in out


def test_memo_carries_the_handoff_instruction_and_not_the_plan(entered):
    """Памятка отдаёт инструкции открытых приёмов: «Передача» среди них."""
    game, proj = entered
    code, out = game("scroll")
    assert code == 0, out
    folder = proj / "docs" / "jedicoder"
    names = sorted(path.name for path in folder.iterdir())
    assert "handoff.md" in names and "brainstorm.md" in names
    assert "plan.md" not in names
    text = (folder / "handoff.md").read_text(encoding="utf-8")
    assert "HANDOFF.md" in text
    for heading in ("## Что это", "## Когда применять", "## Как делать",
                    "## Чего не делать"):
        assert heading in text


#: Фразы первого и второго вечера на странице памятки — как в шпаргалке
#: оператора (#104): «когда → что сказать».
PHRASES_ACT1 = (
    "| Что-то заработало | Сохрани. Или: сделай коммит |",
    "| Новая правка всё сломала | Откатись к последнему сохранению |",
)
PHRASES_ACT2 = (
    "| В конце любой задачи | Если тебе что-то непонятно или не хватает "
    "информации — задай вопросы |",
    "| Контекст занят на 70% | Запиши передачу в `HANDOFF.md`, я буду "
    "делать `/clear` |",
    "| Сразу после `/clear` | На чём остановились? Продолжаем. Передача "
    "лежит в `HANDOFF.md` |",
    "| Не видишь или не понимаешь, о чём речь | Я не вижу того, о чём ты "
    "говоришь. Сделай сам |",
)
#: Слова игры, которых на странице быть не должно: её читают без плагина.
GAME_WORDS = ("Jedicoder", "jedicoder", "квест", "Квест", "акт ", "Акт ",
              "приём", "Приём", "падаван", "ранг", "Магистр")


def test_memo_of_the_second_evening_has_the_page_of_ready_phrases(entered):
    """Вошёл в Акт 2 — в памятке фразы обоих вечеров, без слов игры."""
    game, proj = entered
    assert game("scroll")[0] == 0
    folder = proj / "docs" / "jedicoder"
    page = (folder / "frazy.md").read_text(encoding="utf-8")
    assert page.splitlines()[0] == "# Готовые фразы для Claude"
    assert tuple(page.splitlines()[-6:]) == PHRASES_ACT1 + PHRASES_ACT2
    assert [word for word in GAME_WORDS if word in page] == []
    index = (folder / "README.md").read_text(encoding="utf-8")
    assert "**frazy.md** — Готовые фразы для Claude" in index


def test_memo_of_the_first_evening_has_only_its_own_phrases(game, project):
    """Искатель, не начавший Акт 2, не получает фраз про передачу."""
    proj = project()
    close_act1(game, proj)
    assert game("scroll")[0] == 0
    page = (proj / "docs" / "jedicoder" / "frazy.md").read_text(encoding="utf-8")
    assert tuple(page.splitlines()[-2:]) == PHRASES_ACT1
    assert "передач" not in page and "HANDOFF" not in page


def test_broken_phrases_content_does_not_break_the_memo(entered, tmp_path):
    """Раздел фраз не читается — памятка выдаётся без страницы, а не падает."""
    from jedicoder import content

    bad = tmp_path / "content"
    (bad / "phrases").mkdir(parents=True)
    (bad / "phrases" / "act1.md").write_text(
        "---\nact: 1\n---\nне таблица\n", encoding="utf-8"
    )
    with pytest.raises(content.ContentError):
        content.load_phrases(bad)
    game, _ = entered
    data = st.load(game.state_path)
    assert cli._phrases_page(data, bad) == ""
    assert cli._phrases_page(data, tmp_path / "нет такой папки") == ""

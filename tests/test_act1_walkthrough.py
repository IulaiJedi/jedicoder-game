"""Акт 1 проходится целиком через CLI — оба трека.

Самый ценный тест этого плана. Состояние не засевается ни разу: всё, что
делает тест, делает и живой падаван — кладёт файлы в проект и зовёт CLI.
"""
from jedicoder import cli
from jedicoder import state as st

IDEA = """# Идея

## Боль
Каждый вечер вручную свожу расходы семьи из трёх банковских приложений
в одну таблицу, и это занимает почти час времени.

## Для кого
Я и жена, плюс двое друзей просили сделать им такое же решение.

## Почему сейчас
Два банка открыли публичное API в этом году, раньше это было невозможно.
"""

SLICE = """# Срез

## Войдёт
Одна кнопка «загрузить выписку» и таблица с суммами по категориям за месяц.

## Отрезано
Графики, бюджеты, напоминания, мобильное приложение, вход через госуслуги.

## Оценка
Один вечер, часа три работы.
"""

WHO = "Я сам. Критерий простой: открываю каждый день вечером после ужина.\n"
MARKET = "TAM 50000 семей, SAM 5000 в моём городе, SOM 500 за первый год. " * 3
COMPETITORS = """# Конкуренты

- Дзен-мани — https://zenmoney.example
- Кошелёк — https://koshelek.example
- Таблица в Google — https://sheets.example
"""
ICP = " ".join(["Семья с двумя детьми и тремя картами разных банков."] * 12)
UNIT = """# Юнитка

## CAC
Привести одного пользователя — примерно 300 рублей на рекламу.

## LTV
Пользователь приносит 1200 рублей за полтора года подписки.

## Стоимость токенов
Разбор одной выписки — 4 рубля на API, плюс 500 рублей в месяц за VPS.
"""
CHANNEL = """# Канал

## Канал
Телеграм-канал про семейные финансы

## Почему он
Там уже сидит моя аудитория, и я в нём пишу третий год подряд.
"""

COMMON = {"research/IDEA.md": IDEA, "research/SLICE.md": SLICE}
CRAFT_FILES = dict(COMMON, **{"research/WHO.md": WHO})
FOUND_FILES = dict(COMMON, **{
    "research/MARKET.md": MARKET,
    "research/COMPETITORS.md": COMPETITORS,
    "research/ICP.md": ICP,
    "research/UNIT.md": UNIT,
    "research/CHANNEL.md": CHANNEL,
})

CRAFT_QUESTS = ("01-idea", "02-one-evening", "03c-who")
FOUND_QUESTS = ("01-idea", "02-one-evening", "03f-market", "04f-competitors",
                "05f-icp", "06f-unit", "07f-channel")


def runner(tmp_path, quests_root):
    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)

    def jc(*argv):
        return cli.main(list(argv), state_path=state_path, quests_root=quests_root)

    return jc, state_path


def test_craftsman_walks_act1_via_cli(tmp_path, quests_root, project):
    proj = project(files=CRAFT_FILES)
    jc, state_path = runner(tmp_path, quests_root)

    assert jc("project", "path", str(proj)) == 0
    assert jc("track", "craftsman") == 0
    assert jc("enter", "1") == 0
    for quest_id in CRAFT_QUESTS:
        assert jc("check", "1", quest_id) == 0, "квест {} не закрылся".format(quest_id)

    data = st.load(state_path)
    assert data["acts"]["1"]["status"] == "done"
    assert data["rank"] == "seeker"


def test_founder_walks_act1_via_cli(tmp_path, quests_root, project):
    proj = project(files=FOUND_FILES)
    jc, state_path = runner(tmp_path, quests_root)

    assert jc("project", "path", str(proj)) == 0
    assert jc("track", "founder") == 0
    assert jc("enter", "1") == 0
    for quest_id in FOUND_QUESTS:
        assert jc("check", "1", quest_id) == 0, "квест {} не закрылся".format(quest_id)

    data = st.load(state_path)
    assert data["acts"]["1"]["status"] == "done"
    assert data["rank"] == "seeker"


def test_act1_does_not_close_early_for_founder(tmp_path, quests_root, project):
    """Три квеста Ремесленника не закрывают акт Основателю."""
    proj = project(files=FOUND_FILES)
    jc, state_path = runner(tmp_path, quests_root)
    jc("project", "path", str(proj))
    jc("track", "founder")
    jc("enter", "1")
    for quest_id in ("01-idea", "02-one-evening", "03f-market"):
        assert jc("check", "1", quest_id) == 0
    assert st.load(state_path)["acts"]["1"]["status"] == "in_progress"


def test_enter_act1_without_track_refuses(tmp_path, quests_root, capsys):
    jc, state_path = runner(tmp_path, quests_root)
    assert jc("enter", "1") == 1
    out = capsys.readouterr().out
    assert "для себя" in out and "для людей" in out
    assert st.load(state_path)["acts"] == {}, "отказанный вход не начинает акт"


def test_status_without_track_says_so(tmp_path, quests_root, capsys):
    jc, _ = runner(tmp_path, quests_root)
    assert jc("status") == 0
    out = capsys.readouterr().out
    assert "для кого продукт" in out and "craftsman" not in out


def test_wrong_track_quest_is_refused(tmp_path, quests_root, project, capsys):
    proj = project(files=CRAFT_FILES)
    jc, _ = runner(tmp_path, quests_root)
    jc("project", "path", str(proj))
    jc("track", "craftsman")
    jc("enter", "1")
    capsys.readouterr()
    assert jc("check", "1", "03f-market") == 1
    assert "03c-who" in capsys.readouterr().out, (
        "падавану надо назвать квесты ЕГО трека"
    )


def test_closed_act_survives_track_switch(tmp_path, quests_root, project):
    """Решение спека: закрытое остаётся закрытым, ранг не падает.

    Смена трека — апселл. Отбирать за неё ранг значит наказывать ровно за
    то поведение, которого игра добивается.
    """
    proj = project(files=CRAFT_FILES)
    jc, state_path = runner(tmp_path, quests_root)
    jc("project", "path", str(proj))
    jc("track", "craftsman")
    jc("enter", "1")
    for quest_id in CRAFT_QUESTS:
        assert jc("check", "1", quest_id) == 0
    assert st.load(state_path)["rank"] == "seeker"

    assert jc("track", "founder") == 0
    data = st.load(state_path)
    assert data["acts"]["1"]["status"] == "done", "акт не должен переоткрыться"
    assert data["rank"] == "seeker", "ранг не должен упасть"
    assert jc("enter", "2") == 0, "Акт 2 остаётся доступен"


def test_track_switch_keeps_old_branch_progress(tmp_path, quests_root, project):
    proj = project(files=dict(CRAFT_FILES, **FOUND_FILES))
    jc, state_path = runner(tmp_path, quests_root)
    jc("project", "path", str(proj))
    jc("track", "craftsman")
    jc("enter", "1")
    assert jc("check", "1", "03c-who") == 0

    assert jc("track", "founder") == 0
    assert st.load(state_path)["acts"]["1"]["quests"]["03c-who"]["status"] == "done"

    assert jc("track", "craftsman") == 0
    assert st.load(state_path)["acts"]["1"]["quests"]["03c-who"]["status"] == "done"


def test_map_counts_only_current_track(tmp_path, quests_root, project, capsys):
    """После смены трека числитель не должен считать квесты старой ветки.

    Акт намеренно оставлен открытым: у закрытого акта счётчик не печатается
    вовсе, и тогда этот тест проверял бы не то, ради чего написан.
    """
    proj = project(files=dict(CRAFT_FILES, **FOUND_FILES))
    jc, _ = runner(tmp_path, quests_root)
    jc("project", "path", str(proj))
    jc("track", "craftsman")
    jc("enter", "1")
    # Только два из трёх квестов Ремесленника: акт остаётся открытым.
    for quest_id in ("01-idea", "02-one-evening"):
        assert jc("check", "1", quest_id) == 0
    jc("track", "founder")
    capsys.readouterr()
    jc("status")
    out = capsys.readouterr().out
    assert "2/7" in out, "закрыты два общих квеста из семи у Основателя, а не 3/7"


def test_closed_act_shows_no_progress_counter(tmp_path, quests_root, project, capsys):
    """У закрытого акта счётчик не печатается — галочка самодостаточна.

    До правки Ремесленник, закрывший Акт 1 и ушедший в Основатели, видел
    «[x] Акт 1. Поиск боли — квестов закрыто: 2/7». Значение правдивое, но
    читается как «осталось пять», хотя акт закрыт и эти пять на ранг уже
    не влияют.
    """
    proj = project(files=dict(CRAFT_FILES, **FOUND_FILES))
    jc, _ = runner(tmp_path, quests_root)
    jc("project", "path", str(proj))
    jc("track", "craftsman")
    jc("enter", "1")
    for quest_id in CRAFT_QUESTS:
        assert jc("check", "1", quest_id) == 0
    jc("track", "founder")
    capsys.readouterr()
    jc("status")

    act1_line = [
        line for line in capsys.readouterr().out.splitlines()
        if "Акт 1." in line
    ][0]
    assert act1_line.strip().startswith("[x]"), act1_line
    assert "квестов закрыто" not in act1_line, act1_line
    assert "/" not in act1_line, act1_line


def test_open_act_still_shows_counter(tmp_path, quests_root, project, capsys):
    """Счётчик убран только у закрытого акта, у открытого он остался."""
    proj = project(files=CRAFT_FILES)
    jc, _ = runner(tmp_path, quests_root)
    jc("project", "path", str(proj))
    jc("track", "craftsman")
    jc("enter", "1")
    assert jc("check", "1", "01-idea") == 0
    capsys.readouterr()
    jc("status")

    act1_line = [
        line for line in capsys.readouterr().out.splitlines()
        if "Акт 1." in line
    ][0]
    assert "квестов закрыто: 1/3" in act1_line, act1_line

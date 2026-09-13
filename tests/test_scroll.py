"""Свиток: сборка файлов и запись их в проект падавана.

Два слоя, и граница между ними — предмет тикета. `build` собирает Свиток из
фактов и контента и не знает про диск вовсе: её тесты гоняются на словарях и
самодельных объектах. `write` кладёт собранное в папку и отвечает за
единственное обещание ADR-0009 — чужая правка не переписывается никогда.

Живая половина пишет только во временные папки pytest. Настоящее сохранение
падавана (`~/.jedicoder/state.json`) здесь не открывается ни на чтение, ни
на запись: всё идёт через `state_path` из фикстуры.
"""
import hashlib
from collections import namedtuple
from pathlib import Path

import pytest
from test_act1_walkthrough import CRAFT_FILES, CRAFT_QUESTS

from jedicoder import cli, content, ranks, scroll
from jedicoder import state as st

TODAY = "2026-09-07"

FakeAct = namedtuple("FakeAct", "act quests quest_titles")


def instruction(artifact, title=None, summary=None, body=None):
    return content.Instruction(
        artifact=artifact,
        title=title or "Как делать {}".format(artifact),
        summary=summary or "Одна строка про {}.".format(artifact),
        body=body or "## Что это\n\nТело инструкции {}.\n".format(artifact),
        path=Path("{}.md".format(artifact)),
    )


def instructions(*names):
    return dict((name, instruction(name)) for name in names)


def facts(**over):
    """Факты Разбора в форме debrief.facts, но собранные руками.

    Руками — потому что сборка обязана быть чистой функцией от словаря:
    подставь ей другие числа, и файл изменится, а сохранения при этом нет
    вовсе.
    """
    base = {
        "rank": "seeker",
        "rank_title": "Искатель",
        "acts_completed": [1],
        "track": "craftsman",
        "deploy_path": None,
        "product_url": None,
        "days_in_path": 12,
        "quests": [
            {"act": 1, "quest": "01-idea", "attempts": 1, "closed": True},
            {"act": 1, "quest": "02-one-evening", "attempts": 3, "closed": True},
        ],
        "quests_closed": 2,
        "attempts_total": 4,
        "hardest_quest": {
            "act": 1, "quest": "02-one-evening", "attempts": 3, "closed": True,
        },
        "first_try": {"passed": 1, "attempted": 2},
        "streak": {"current": 2, "best": 5},
        "terms_unlocked": 7,
        "xp": 140,
        "dark_side": {
            "points": 0, "logged": 0, "unlogged": 0,
            "log_incomplete": False, "days": 0, "by_kind": [],
        },
    }
    base.update(over)
    return base


def texts(files):
    return dict(files)


# --- Сборка: чистая функция ------------------------------------------------


def test_build_returns_named_files_and_touches_no_disk(tmp_path):
    files = scroll.build(facts(), instructions("plan", "goal"), today=TODAY)
    assert [name for name, _ in files] == [
        scroll.INDEX_NAME, "plan.md", "goal.md", scroll.DEBRIEF_NAME,
    ]
    assert all(isinstance(text, str) and text for _, text in files)
    assert list(tmp_path.iterdir()) == []


# Имя памятки — имя ранга владельца. Слова здесь, в тесте, а не в движке:
# именительный падеж живёт в ranks.RANK_TITLES единственным источником, а
# склонение выводится правилом. Переименуют ранг — упадёт эта строка, а не
# молча разойдётся вторая таблица имён.
SCROLL_NAMES = {
    "youngling": "Памятка Юнлинга",
    "seeker": "Памятка Искателя",
    "padawan": "Памятка Падавана",
    "knight": "Памятка Рыцаря",
    "sentinel": "Памятка Стража",
    "master": "Памятка Мастера",
}


def test_build_names_the_scroll_by_rank():
    assert set(SCROLL_NAMES) == set(ranks.RANKS)
    for rank in ranks.RANKS:
        page = texts(scroll.build(
            facts(rank=rank, rank_title=ranks.RANK_TITLES[rank]),
            instructions("goal"), today=TODAY,
        ))[scroll.INDEX_NAME]
        assert SCROLL_NAMES[rank] in page


def test_rank_name_is_declined_and_not_looked_up_in_a_second_table():
    """Спека: имена рангов только из ranks.RANK_TITLES. Отсюда правило
    склонения вместо словаря падежей."""
    assert scroll.genitive("Искатель") == "Искателя"
    assert scroll.genitive("Мастер") == "Мастера"
    assert scroll.genitive("Джедай") == "Джедая"
    assert scroll.genitive("Йода") == "Йода"
    assert scroll.genitive("") == ""


def test_unknown_rank_falls_back_to_the_title_it_was_given():
    """Сохранение от плагина новее: имя не наше, но названо."""
    page = texts(scroll.build(
        facts(rank="archivist", rank_title="Архивариус"),
        instructions("goal"), today=TODAY,
    ))[scroll.INDEX_NAME]
    assert "Памятка Архивариуса" in page


def test_build_orders_instructions_by_the_engine_registry():
    given = instructions("goal", "plan", "brainstorm")
    files = scroll.build(facts(), given, today=TODAY)
    names = [name for name, _ in files]
    assert names[1:4] == ["brainstorm.md", "plan.md", "goal.md"]


def test_build_gives_only_the_instructions_it_was_handed():
    """Свиток отдаёт то, что открыто: фильтрует вызывающий, сборка не
    добирает недостающее из реестра."""
    files = texts(scroll.build(facts(), instructions("goal"), today=TODAY))
    assert "plan.md" not in files
    assert "goal.md" in files
    assert "plan.md" not in files[scroll.INDEX_NAME]


def test_instruction_page_is_title_plus_body_and_nothing_else():
    item = instruction("plan", title="Как спланировать", body="## Что это\n\nТело.\n")
    page = texts(scroll.build(facts(), {"plan": item}, today=TODAY))["plan.md"]
    assert page.startswith("# Как спланировать\n")
    assert "## Что это" in page
    assert "Свиток" not in page and "Памятка" not in page
    assert "ранг" not in page.lower()


def test_index_quotes_the_author_summaries():
    item = instruction("plan", title="Заголовок автора", summary="Строка автора.")
    page = texts(scroll.build(facts(), {"plan": item}, today=TODAY))[scroll.INDEX_NAME]
    assert "Заголовок автора" in page
    assert "Строка автора." in page
    assert TODAY in page


def test_debrief_carries_the_numbers_it_was_given():
    page = texts(scroll.build(facts(), instructions("goal"), today=TODAY))[
        scroll.DEBRIEF_NAME
    ]
    assert "Искатель" in page
    assert "Дней в пути: 12" in page
    assert "Закрыто квестов: 2" in page
    assert "Попыток потрачено: 4" in page
    assert "С первой попытки: 1 из 2" in page
    assert "XP: 140" in page
    assert "Открыто слов: 7" in page


def test_debrief_omits_what_the_save_does_not_know():
    page = texts(scroll.build(
        facts(track=None, deploy_path=None, product_url=None,
              days_in_path=None, hardest_quest=None),
        instructions("goal"), today=TODAY,
    ))[scroll.DEBRIEF_NAME]
    assert "Дней в пути" not in page
    assert "Трек" not in page
    assert "Продукт" not in page
    assert "Тяжелее всего" not in page


def test_debrief_names_quests_by_their_titles_when_acts_are_given():
    pages = texts(scroll.build(
        facts(), instructions("goal"),
        acts=[FakeAct(1, ("01-idea", "02-one-evening"), ("Идея", "Правило одного вечера"))],
        today=TODAY,
    ))
    page = pages[scroll.DEBRIEF_NAME]
    assert "Правило одного вечера" in page
    assert "Тяжелее всего" in page


def test_debrief_falls_back_to_quest_identifiers_without_acts():
    page = texts(scroll.build(facts(), instructions("goal"), today=TODAY))[
        scroll.DEBRIEF_NAME
    ]
    assert "01-idea" in page


def test_dark_side_is_named_by_kind_not_by_one_number():
    page = texts(scroll.build(
        facts(dark_side={
            "points": 3, "logged": 3, "unlogged": 0, "log_incomplete": False,
            "days": 2,
            "by_kind": [
                {"kind": st.DARK_ENV_STAGED, "points": 2, "days": 1},
                {"kind": st.DARK_VAGUE_PROMPT, "points": 1, "days": 1},
            ],
        }),
        instructions("goal"), today=TODAY,
    ))[scroll.DEBRIEF_NAME]
    assert scroll.DARK_SIDE_TITLES[st.DARK_ENV_STAGED] in page
    assert scroll.DARK_SIDE_TITLES[st.DARK_VAGUE_PROMPT] in page


def test_every_dark_side_kind_has_a_name_for_the_scroll():
    """Новый тип нарушения не должен приехать в Свиток латинским ключом."""
    for kind in st.DARK_SIDE_KINDS:
        assert kind in scroll.DARK_SIDE_TITLES


def test_unknown_dark_side_kind_is_printed_as_is_and_not_lost():
    page = texts(scroll.build(
        facts(dark_side={
            "points": 1, "logged": 1, "unlogged": 0, "log_incomplete": False,
            "days": 1,
            "by_kind": [{"kind": "future_kind", "points": 1, "days": 1}],
        }),
        instructions("goal"), today=TODAY,
    ))[scroll.DEBRIEF_NAME]
    assert "future_kind" in page


def test_incomplete_dark_side_log_is_said_out_loud():
    page = texts(scroll.build(
        facts(dark_side={
            "points": 4, "logged": 1, "unlogged": 3, "log_incomplete": True,
            "days": 1,
            "by_kind": [{"kind": st.DARK_ROOT_LOGIN, "points": 1, "days": 1}],
        }),
        instructions("goal"), today=TODAY,
    ))[scroll.DEBRIEF_NAME]
    assert "Без подробностей осталось очков: 3" in page


# --- Шов под тексты Магистра и финала --------------------------------------


def test_seam_keys_are_named_once():
    assert scroll.PARTS == ("debrief", "roadmap", "rank_card")


def test_magistr_text_lands_under_the_facts():
    page = texts(scroll.build(
        facts(), instructions("goal"), today=TODAY,
        parts={"debrief": "Ты вошёл в игру без идеи и вышел с продуктом."},
    ))[scroll.DEBRIEF_NAME]
    assert scroll.DEBRIEF_HEADING in page
    assert "Ты вошёл в игру без идеи" in page
    assert page.index("Дней в пути") < page.index(scroll.DEBRIEF_HEADING)


def test_silent_magistr_still_gives_a_scroll():
    """ADR-0010: разбор без фактов невозможен, факты без разбора — обычное
    дело."""
    page = texts(scroll.build(facts(), instructions("goal"), today=TODAY))[
        scroll.DEBRIEF_NAME
    ]
    assert scroll.DEBRIEF_HEADING not in page
    assert "Дней в пути: 12" in page


def test_blank_part_counts_as_silence():
    page = texts(scroll.build(
        facts(), instructions("goal"), today=TODAY, parts={"debrief": "   \n"},
    ))[scroll.DEBRIEF_NAME]
    assert scroll.DEBRIEF_HEADING not in page


def test_roadmap_and_rank_card_become_their_own_files():
    files = scroll.build(
        facts(), instructions("goal"), today=TODAY,
        parts={"roadmap": "Три шага.", "rank_card": "Карточка."},
    )
    names = [name for name, _ in files]
    assert names[-2:] == [scroll.ROADMAP_NAME, scroll.RANK_CARD_NAME]
    pages = texts(files)
    assert "Три шага." in pages[scroll.ROADMAP_NAME]
    assert "Карточка." in pages[scroll.RANK_CARD_NAME]
    assert scroll.ROADMAP_NAME in pages[scroll.INDEX_NAME]
    assert scroll.RANK_CARD_NAME in pages[scroll.INDEX_NAME]


def test_index_stays_silent_about_files_that_are_not_there():
    page = texts(scroll.build(facts(), instructions("goal"), today=TODAY))[
        scroll.INDEX_NAME
    ]
    assert scroll.ROADMAP_NAME not in page
    assert scroll.RANK_CARD_NAME not in page


def test_unknown_part_is_ignored_and_makes_no_file():
    files = scroll.build(
        facts(), instructions("goal"), today=TODAY, parts={"prophecy": "нет"},
    )
    assert [name for name, _ in files] == [
        scroll.INDEX_NAME, "goal.md", scroll.DEBRIEF_NAME,
    ]


# --- Запись: чужая правка не переписывается --------------------------------


def issue(directory, files, prints=None, today=TODAY):
    return scroll.write(directory, files, prints or {}, today)


def sample(**over):
    return scroll.build(facts(**over), instructions("goal"), today=TODAY)


def actions(report):
    return dict((row["name"], row["action"]) for row in report)


def test_first_issue_creates_every_file(tmp_path):
    files = sample()
    report, prints = issue(tmp_path / "docs" / "jedicoder", files)
    target = tmp_path / "docs" / "jedicoder"
    for name, text in files:
        assert (target / name).read_text(encoding="utf-8") == text
    assert set(actions(report).values()) == {"created"}
    assert set(prints) == set(name for name, _ in files)
    assert all(len(row["sha256"]) == 64 for row in prints.values())


def test_second_issue_without_edits_changes_nothing(tmp_path):
    target = tmp_path / "docs" / "jedicoder"
    files = sample()
    _, prints = issue(target, files)
    before = sorted(p.name for p in target.iterdir())
    report, prints = issue(target, files, prints)
    assert sorted(p.name for p in target.iterdir()) == before
    assert set(actions(report).values()) == {"unchanged"}


def test_new_facts_overwrite_our_own_untouched_file(tmp_path):
    target = tmp_path / "docs" / "jedicoder"
    _, prints = issue(target, sample())
    report, prints = issue(target, sample(xp=999), prints)
    assert actions(report)[scroll.DEBRIEF_NAME] == "updated"
    assert "XP: 999" in (target / scroll.DEBRIEF_NAME).read_text(encoding="utf-8")
    assert sorted(p.name for p in target.iterdir()) == sorted(
        [scroll.INDEX_NAME, "goal.md", scroll.DEBRIEF_NAME]
    )


def test_edited_file_survives_and_the_fresh_one_lies_beside_it(tmp_path):
    target = tmp_path / "docs" / "jedicoder"
    _, prints = issue(target, sample())
    mine = target / scroll.DEBRIEF_NAME
    mine.write_text("Мой абзац поверх Разбора.\n", encoding="utf-8")
    report, prints = issue(target, sample(xp=999), prints)
    assert mine.read_text(encoding="utf-8") == "Мой абзац поверх Разбора.\n"
    row = dict((r["name"], r) for r in report)[scroll.DEBRIEF_NAME]
    assert row["action"] == "kept"
    assert row["written"] == "razbor-{}.md".format(TODAY)
    beside = target / row["written"]
    assert "XP: 999" in beside.read_text(encoding="utf-8")


def test_second_edit_on_the_same_day_gets_its_own_name(tmp_path):
    target = tmp_path / "docs" / "jedicoder"
    _, prints = issue(target, sample())
    (target / scroll.DEBRIEF_NAME).write_text("Правка раз.\n", encoding="utf-8")
    _, prints = issue(target, sample(xp=999), prints)
    (target / "razbor-{}.md".format(TODAY)).write_text("Правка два.\n", encoding="utf-8")
    report, prints = issue(target, sample(xp=1000), prints)
    row = dict((r["name"], r) for r in report)[scroll.DEBRIEF_NAME]
    assert row["written"] == "razbor-{}-2.md".format(TODAY)
    assert (target / scroll.DEBRIEF_NAME).read_text(encoding="utf-8") == "Правка раз.\n"
    assert (target / "razbor-{}.md".format(TODAY)).read_text(
        encoding="utf-8"
    ) == "Правка два.\n"


def test_the_file_beside_gets_a_name_even_without_a_date(tmp_path):
    """Дату не передали — имя всё равно обязано получиться: файл рядом
    важнее красивого имени."""
    target = tmp_path / "docs" / "jedicoder"
    target.mkdir(parents=True)
    (target / scroll.DEBRIEF_NAME).write_text("Чужое.\n", encoding="utf-8")
    report, _ = scroll.write(target, sample(), {}, None)
    row = dict((r["name"], r) for r in report)[scroll.DEBRIEF_NAME]
    assert row["action"] == "kept"
    assert row["written"] == "razbor-kopiya.md"


def test_file_we_never_wrote_is_treated_as_someone_elses(tmp_path):
    """Отпечатка нет — значит файл не наш, и трогать его нельзя."""
    target = tmp_path / "docs" / "jedicoder"
    target.mkdir(parents=True)
    (target / scroll.DEBRIEF_NAME).write_text("Чужое.\n", encoding="utf-8")
    report, _ = issue(target, sample())
    assert (target / scroll.DEBRIEF_NAME).read_text(encoding="utf-8") == "Чужое.\n"
    assert actions(report)[scroll.DEBRIEF_NAME] == "kept"


def test_foreign_files_in_the_folder_are_left_alone(tmp_path):
    target = tmp_path / "docs" / "jedicoder"
    target.mkdir(parents=True)
    (target / "zametki.md").write_text("Мои заметки.\n", encoding="utf-8")
    (target / "sub").mkdir()
    (target / "sub" / "file.txt").write_text("глубже\n", encoding="utf-8")
    issue(target, sample())
    assert (target / "zametki.md").read_text(encoding="utf-8") == "Мои заметки.\n"
    assert (target / "sub" / "file.txt").read_text(encoding="utf-8") == "глубже\n"


def test_matching_content_without_a_print_is_not_a_conflict(tmp_path):
    """На диске байт в байт то, что мы собрали: переписывать нечего и
    терять нечего."""
    target = tmp_path / "docs" / "jedicoder"
    target.mkdir(parents=True)
    files = sample()
    for name, text in files:
        (target / name).write_text(text, encoding="utf-8")
    report, prints = issue(target, files)
    assert set(actions(report).values()) == {"unchanged"}
    assert sorted(p.name for p in target.iterdir()) == sorted(
        name for name, _ in files
    )


def test_prints_survive_a_restart_of_the_engine(tmp_path):
    """Отпечаток живёт в сохранении, а не в памяти процесса."""
    state_path = tmp_path / "state.json"
    target = tmp_path / "docs" / "jedicoder"
    files = sample()
    with st.update_state(state_path) as data:
        report, prints = issue(target, files)
        data["scroll"] = {"files": prints}
    reloaded = st.load(state_path)["scroll"]["files"]
    report, _ = issue(target, files, reloaded)
    assert set(actions(report).values()) == {"unchanged"}


def test_print_is_the_sha256_of_the_written_bytes(tmp_path):
    target = tmp_path / "docs" / "jedicoder"
    files = sample()
    _, prints = issue(target, files)
    for name, text in files:
        assert prints[name]["sha256"] == hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()
        assert prints[name]["date"] == TODAY


# --- Дверь падавана: команда ------------------------------------------------


@pytest.fixture
def paths(tmp_path, content_root, quests_root):
    return {
        "state_path": tmp_path / "state.json",
        "content_root": content_root,
        "quests_root": quests_root,
    }


def run(argv, paths, capsys):
    code = cli.main(argv, **paths)
    return code, capsys.readouterr().out


def test_command_without_a_project_writes_nothing(paths, capsys, tmp_path):
    code, out = run(["scroll"], paths, capsys)
    assert code == 1
    assert "Папка проекта не установлена" in out
    assert not list(tmp_path.glob("**/docs"))


def test_command_with_a_vanished_project_folder_writes_nothing(
    paths, capsys, tmp_path
):
    gone = tmp_path / "ushla"
    gone.mkdir()
    run(["project", "path", str(gone)], paths, capsys)
    gone.rmdir()
    code, out = run(["scroll"], paths, capsys)
    assert code == 1
    assert "Папка проекта не найдена" in out
    assert not gone.exists()


def test_command_lays_the_scroll_into_the_project(paths, capsys, project):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    code, out = run(["scroll"], paths, capsys)
    assert code == 0
    target = folder / "docs" / "jedicoder"
    assert (target / scroll.INDEX_NAME).exists()
    assert (target / scroll.DEBRIEF_NAME).exists()
    assert "goal.md" in out
    assert str(target) in out
    data = st.load(paths["state_path"])
    assert set(data["scroll"]["files"]) >= {scroll.INDEX_NAME, scroll.DEBRIEF_NAME}


def test_command_gives_only_the_artifacts_that_are_open(paths, capsys, project):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["scroll"], paths, capsys)
    target = folder / "docs" / "jedicoder"
    assert (target / "goal.md").exists()
    assert not (target / "plan.md").exists()
    with st.update_state(paths["state_path"]) as data:
        ranks.enter_act(data, 1)
    run(["scroll"], paths, capsys)
    assert (target / "brainstorm.md").exists()


def test_command_keeps_the_edit_and_says_so(paths, capsys, project):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["scroll"], paths, capsys)
    target = folder / "docs" / "jedicoder"
    mine = target / scroll.DEBRIEF_NAME
    mine.write_text("Дописал сам.\n", encoding="utf-8")
    with st.update_state(paths["state_path"]) as data:
        data["xp"] = 999
    code, out = run(["scroll"], paths, capsys)
    assert code == 0
    assert mine.read_text(encoding="utf-8") == "Дописал сам.\n"
    assert "Оставлено как есть" in out
    beside = list(target.glob("razbor-*.md"))
    assert len(beside) == 1
    assert "XP: 999" in beside[0].read_text(encoding="utf-8")


def test_command_repeated_the_same_day_creates_nothing_new(
    paths, capsys, project
):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["scroll"], paths, capsys)
    target = folder / "docs" / "jedicoder"
    before = sorted(p.name for p in target.iterdir())
    code, out = run(["scroll"], paths, capsys)
    assert code == 0
    assert sorted(p.name for p in target.iterdir()) == before
    assert "Без изменений" in out


def test_command_writes_nothing_outside_docs_jedicoder(paths, capsys, project):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    before = sorted(p.name for p in folder.iterdir())
    run(["scroll"], paths, capsys)
    after = sorted(p.name for p in folder.iterdir())
    assert after == sorted(before + ["docs"]) or after == before


def test_scroll_is_in_the_usage_line(paths, capsys):
    code, out = run([], paths, capsys)
    assert code == 1
    assert "scroll" in out


def test_only_the_command_writes_into_the_project(paths, capsys, project):
    """ADR-0009: ни проверка, ни вход в акт, ни первый экран файлов не
    создают. Запрет «проверка не мутирует проект падавана» этой веткой не
    задет — проверяем это дверью падавана, а не чтением кода."""
    folder = project(files=CRAFT_FILES)
    run(["project", "path", str(folder)], paths, capsys)
    run(["track", "craftsman"], paths, capsys)
    run(["enter", "1"], paths, capsys)
    for quest_id in CRAFT_QUESTS:
        run(["check", "1", quest_id], paths, capsys)
    run(["status"], paths, capsys)
    assert not (folder / "docs").exists()


def test_a_symlink_in_the_folder_is_never_written_through(tmp_path):
    """Битая ссылка на месте файла: `exists()` скажет «нет», а запись ушла бы
    по ссылке за пределы папки Свитка."""
    target = tmp_path / "docs" / "jedicoder"
    target.mkdir(parents=True)
    outside = tmp_path / "chuzhoe.md"
    (target / scroll.DEBRIEF_NAME).symlink_to(outside)
    report, _ = issue(target, sample())
    assert not outside.exists()
    assert (target / scroll.DEBRIEF_NAME).is_symlink()
    row = dict((r["name"], r) for r in report)[scroll.DEBRIEF_NAME]
    assert row["action"] == "kept"
    assert row["written"] == "razbor-{}.md".format(TODAY)


def test_undelivered_file_is_reported_as_kept_not_as_a_write_failure(tmp_path):
    """Свежий рядом не лёг — правка человека всё равно цела, и сказать надо
    именно это."""
    target = tmp_path / "docs" / "jedicoder"
    target.mkdir(parents=True)
    (target / scroll.DEBRIEF_NAME).write_text("Чужое.\n", encoding="utf-8")
    for number in range(scroll.BESIDE_LIMIT + 1):
        tail = "" if not number else "-{}".format(number + 1)
        name = "razbor-{}{}.md".format(TODAY, tail)
        (target / name).write_text("тоже чужое {}\n".format(number), encoding="utf-8")
    report, _ = issue(target, sample())
    row = dict((r["name"], r) for r in report)[scroll.DEBRIEF_NAME]
    assert row["action"] == "kept"
    assert row["written"] is None


def test_command_says_it_out_loud_when_the_folder_cannot_be_made(
    paths, capsys, project
):
    """На месте папки лежит файл: сказать словами, а не трейсбеком."""
    folder = project()
    (folder / "docs").write_text("не папка\n", encoding="utf-8")
    run(["project", "path", str(folder)], paths, capsys)
    code, out = run(["scroll"], paths, capsys)
    assert code == 1
    assert "Не смог создать папку" in out
    assert (folder / "docs").read_text(encoding="utf-8") == "не папка\n"


def test_command_returns_one_when_a_file_did_not_reach_the_padawan(
    paths, capsys, project, monkeypatch
):
    """Отчёт печатается целиком, но код нулём не врёт: файла у человека нет."""
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    original = scroll.write

    def half_written(directory, files, prints, today):
        report, marks = original(directory, files, prints, today)
        report[-1] = {
            "name": report[-1]["name"], "action": scroll.ACTION_FAILED,
            "written": report[-1]["name"],
        }
        return report, marks

    monkeypatch.setattr(scroll, "write", half_written)
    code, out = run(["scroll"], paths, capsys)
    assert code == 1
    assert "Не удалось записать:" in out
    assert "Добавлено:" in out


def test_fresh_save_already_carries_the_shape_of_the_prints():
    """Форма отпечатков названа в одном месте — в дефолтном сохранении."""
    assert st.default_state()["scroll"] == {"files": {}}


def test_old_save_without_prints_gets_the_shape_on_load(tmp_path):
    """Сохранение до Свитка: пустая форма приезжает сама, миграции не надо."""
    state_path = tmp_path / "state.json"
    data = st.default_state("local-test")
    del data["scroll"]
    st.save(data, state_path)
    assert st.load(state_path)["scroll"] == {"files": {}}


# --- Событие «Свиток выдан»: служебное, для письма бота -------------------
#
# Бот через неделю после выдачи пишет падавану письмо, и узнать о выдаче ему
# неоткуда, кроме очереди: Свиток кладётся на диск падавана, не на сервер.
# В событии только ранг и дата — ни путей, ни содержимого файлов: что лежит
# в чужой папке, бота не касается (ADR-0011 про ту же границу у Тёмной
# стороны).


def issued(paths):
    data = st.load(paths["state_path"])
    return [e for e in data.get("pending_sync", []) if e["type"] == "scroll_issued"]


def test_issuing_the_scroll_queues_one_event_with_rank_and_date(
    paths, capsys, project
):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    code, _ = run(["scroll"], paths, capsys)
    assert code == 0
    (event,) = issued(paths)
    assert event["act"] is None and event["quest"] is None
    assert event["payload"] == {
        "rank": ranks.rank_for(st.load(paths["state_path"])),
        "date": st.today_utc(),
    }


def test_the_event_carries_no_paths_and_no_file_contents(
    paths, capsys, project
):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["scroll"], paths, capsys)
    (event,) = issued(paths)
    flat = repr(event)
    assert str(folder) not in flat
    assert "docs" not in flat
    assert scroll.INDEX_NAME not in flat


def test_reissuing_the_scroll_queues_a_second_event(paths, capsys, project):
    """Повтор выдачи — повторное событие: бот отсчитывает неделю от
    последней выдачи, а не от первой."""
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["scroll"], paths, capsys)
    run(["scroll"], paths, capsys)
    assert len(issued(paths)) == 2


def test_a_failed_issue_queues_nothing(paths, capsys, project):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    (folder / "docs").write_text("файл вместо папки", encoding="utf-8")
    code, _ = run(["scroll"], paths, capsys)
    assert code == 1
    assert issued(paths) == []


def test_scroll_issued_is_a_known_event_the_scene_stays_silent_on():
    assert "scroll_issued" in st.EVENT_TYPES
    assert "scroll_issued" in st.SILENT_EVENTS
    assert "scroll_issued" not in content.MAGISTR_EVENTS


def test_debrief_counts_acts_against_the_playable_ones(monkeypatch):
    """Разбор и карточка ранга печатают одно и то же «из скольких»: число
    берётся из playable_acts, а не из полного реестра, иначе при выключенном
    Акте 5 Разбор говорит «4 из 5», а finale в той же сессии — «4 из 4».
    Найдено живым прогоном 2026-09-10."""
    monkeypatch.setattr(ranks, "MUTED_ACTS", (5,))
    page = texts(scroll.build(facts(), instructions("goal"), today=TODAY))[
        scroll.DEBRIEF_NAME
    ]
    assert "- Закрыто актов: 1 из {}".format(len(ranks.playable_acts())) in page
    assert "из {}".format(len(ranks.ACTS)) not in page


def test_debrief_names_the_track_in_words_the_padawan_heard():
    """Разбор ложится в проект падавана: трек словами «для себя» / «для
    людей», а не именем ручки craftsman (прогон 2026-09-13)."""
    page = texts(scroll.build(facts(track="craftsman"), instructions("goal"), today=TODAY))[
        scroll.DEBRIEF_NAME
    ]
    assert "- Продукт: для себя" in page
    assert "craftsman" not in page

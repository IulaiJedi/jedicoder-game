"""Финал в терминале: карточка ранга и приглашение забрать Свиток.

Два слоя, как и у Свитка. `render_rank_card` — чистая функция от фактов
Разбора: подставь ей другой словарь, и карточка изменится, а сохранения при
этом нет вовсе. `finale` — дверь, в которую входит падаван, и проверяется
она через `cli.main`, а не в обход.

Числа в карточку приходят из `debrief.facts` и ниоткуда больше: второй счёт
запрещён правилом проекта (ADR-0010 в репозитории сайта). Единственное
исключение названо вслух — коммиты считает git в папке проекта, их в
сохранении нет.

Настоящее сохранение падавана (`~/.jedicoder/state.json`) здесь не
открывается ни на чтение, ни на запись: всё идёт через `state_path` из
фикстуры.
"""
import pytest

from jedicoder import cli, debrief, ranks, scroll
from jedicoder import state as st


def facts(**over):
    """Факты Разбора в форме debrief.facts, собранные руками.

    Руками — потому что карточка обязана быть чистой функцией от словаря, а
    не от того, что лежит в сохранении на машине, где идёт тест.
    """
    base = {
        "rank": "master",
        "rank_title": "Мастер",
        "acts_completed": [1, 2, 3, 4, 5],
        "track": "founder",
        "deploy_path": "managed",
        "product_url": "https://myapp.example",
        "days_in_path": 18,
        "quests": [],
        "quests_closed": 31,
        "attempts_total": 44,
        "hardest_quest": None,
        "first_try": {"passed": 20, "attempted": 31},
        "streak": {"current": 3, "best": 9},
        "terms_unlocked": 30,
        "xp": 620,
        "dark_side": {
            "points": 3, "logged": 3, "unlogged": 0,
            "log_incomplete": False, "days": 2, "by_kind": [],
        },
    }
    base.update(over)
    return base


def midway(**over):
    """Факты того, кто до конца ещё не дошёл.

    Пока Акт 5 выключен, «конец» — это Страж, и серединой пути стал Рыцарь:
    ранг ниже финального ровно на один акт. Список закрытых актов взят
    оттуда же, а не набран руками, — иначе тест разошёлся бы с реестром в тот
    день, когда акт вернут.
    """
    last = ranks.FINAL_ACT
    midway_rank = ranks.ACTS[last - 1]["rank"]
    base = facts(
        rank=midway_rank, rank_title=ranks.RANK_TITLES[midway_rank],
        acts_completed=list(range(1, last)),
        product_url=None, days_in_path=9, terms_unlocked=12, xp=210,
    )
    base.update(over)
    return base


# --- Карточка ранга: чистая функция ----------------------------------------


def test_master_card_names_the_rank_and_every_number():
    card = cli.render_rank_card(facts(), commits=42)
    assert "=== Карточка Мастера ===" in card
    assert "Продукт: https://myapp.example" in card
    assert "Дней в пути: 18" in card
    assert "Коммитов: 42" in card
    assert "Слов открыто: 30" in card
    assert "XP: 620" in card
    assert "Штрафы: 3" in card


def test_master_card_carries_the_finale_page():
    card = cli.render_rank_card(facts(), commits=1)
    assert cli._finale_url() in card


def test_card_is_given_at_any_rank_not_only_to_the_master():
    """Свиток выдаётся на любом ранге — карточка в нём тоже."""
    card = cli.render_rank_card(midway(), commits=12)
    # Имя ранга — из реестра, а не строкой: с выключенным Актом 5 серединой
    # пути стал Рыцарь, и прибитая строка сломалась бы при каждом сдвиге.
    midway_title = ranks.RANK_TITLES[ranks.ACTS[ranks.FINAL_ACT - 1]["rank"]]
    assert "=== Карточка {} ===".format(scroll.genitive(midway_title)) in card
    # Числитель тоже из реестра: середина пути — на один акт короче финала.
    assert "Закрыто актов: {} из {}.".format(
        ranks.FINAL_ACT - 1, len(ranks.playable_acts())
    ) in card
    # Последний закрытый акт середины пути — предпоследний играбельный.
    last_closed = ranks.FINAL_ACT - 1
    assert "Акт {}. {}".format(last_closed, ranks.ACTS[last_closed]["title"]) in card
    assert "Акт 5. Выход в свет" not in card


def test_midway_card_promises_nothing_and_never_says_almost():
    """Ни утешения, ни аванса: карточка говорит про сделанное.

    Дверь в финал — тоже обещание. Тому, кто до финала не дошёл, она не
    открывается: страница начинается словами «Игра кончилась», и звать туда
    с середины пути значит соврать ему про его же прогресс.
    """
    card = cli.render_rank_card(midway(), commits=12)
    assert "почти" not in card.lower()
    assert "осталось" not in card.lower()
    assert cli._finale_url() not in card


def test_youngling_card_stands_on_an_empty_save():
    card = cli.render_rank_card(debrief.facts({}))
    assert "=== Карточка Юнлинга ===" in card
    assert "Закрыто актов: 0 из {}.".format(len(ranks.playable_acts())) in card
    assert "Дней в пути" not in card
    assert "Продукт:" not in card
    assert "Коммитов" not in card
    assert "XP: 0" in card


# Шесть имён рангов в родительном падеже, выписанные руками. Руками —
# потому что вывести их тем же кодом, что и карточка, значило бы проверить
# код им же самим: список ниже написан по-русски, а не по scroll.genitive.
GENITIVE_RANK_TITLES = {
    "youngling": "Юнлинга",
    "seeker": "Искателя",
    "padawan": "Падавана",
    "knight": "Рыцаря",
    "sentinel": "Стража",
    "master": "Мастера",
}


def test_card_names_every_rank_in_the_registry():
    """Шесть рангов — шесть имён карточки, и все склонены верно."""
    assert set(GENITIVE_RANK_TITLES) == set(ranks.RANK_TITLES)
    for rank, genitive in GENITIVE_RANK_TITLES.items():
        card = cli.render_rank_card({
            "rank": rank, "rank_title": ranks.RANK_TITLES[rank],
        })
        assert card.startswith("=== Карточка {} ===".format(genitive))


# --- Дверь падавана: команда finale ----------------------------------------


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


def seeded(paths, closed=(1, 2, 3, 4, 5), **over):
    """Сохранение с закрытыми актами. Предпосылка достижима игрой."""
    data = st.default_state("local-test")
    for act in closed:
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    data.update(over)
    st.save(data, paths["state_path"])
    return data


def test_finale_draws_the_card_and_invites_to_take_the_scroll(
    paths, capsys, project
):
    folder = project(git=True, commits=3)
    seeded(paths, project={"path": str(folder), "url": "https://myapp.example"},
           xp=620, lexicon_unlocked=["deploy", "dns"])
    code, out = run(["finale"], paths, capsys)
    assert code == 0
    assert "=== Карточка Мастера ===" in out
    assert "Продукт: https://myapp.example" in out
    assert "Коммитов: 3" in out
    assert cli._finale_url() in out
    assert "памятк" in out.lower() and "Свиток" not in out
    assert "scroll" in out


def test_finale_below_master_names_what_is_missing_and_offers_the_scroll(
    paths, capsys
):
    """Финал заперт тому, кто не закрыл последний играбельный акт.

    Номера взяты у реестра, а не вписаны: вернётся Акт 5 — тест поедет за ним
    сам, и незакрытым окажется он.
    """
    last = ranks.FINAL_ACT
    seeded(paths, closed=tuple(range(1, last)))
    code, out = run(["finale"], paths, capsys)
    assert code == 1
    assert ranks.RANK_TITLES[ranks.ACTS[last - 1]["rank"]] in out
    assert "Акт {}".format(last) in out and ranks.ACTS[last]["title"] in out
    # Памятка предлагается уже сейчас — она выдаётся на любом ранге.
    assert "памятк" in out.lower() and "Свиток" not in out
    assert "scroll" in out
    # Но не финал: карточки Мастера у него ещё нет, и страницы финала тоже.
    assert "=== Карточка" not in out
    assert cli._finale_url() not in out


def test_finale_on_an_untouched_save_points_at_the_first_act(paths, capsys):
    code, out = run(["finale"], paths, capsys)
    assert code == 1
    assert "Юнлинг" in out
    assert "Акт 1" in out and "Поиск боли" in out


def test_page_address_is_assembled_from_one_constant(paths, capsys, monkeypatch):
    """Адрес страницы собран из корня сайта, а не набран руками.

    Проверяется подменой корня: если бы адрес был вписан в текст литералом,
    он бы остался прежним и тест это увидел.
    """
    monkeypatch.setenv("JEDICODER_SITE_URL", "https://proba.test/")
    seeded(paths)
    code, out = run(["finale"], paths, capsys)
    assert code == 0
    assert "https://proba.test/finale" in out
    assert "jedicoder.store" not in out


# --- Шов: та же карточка отдельным файлом Свитка ----------------------------


def scroll_card(folder):
    return (folder / "docs" / "jedicoder" / scroll.RANK_CARD_NAME).read_text(
        encoding="utf-8"
    )


def test_the_card_in_the_scroll_is_the_one_the_finale_prints(
    paths, capsys, project
):
    """Один текст на два места: терминал и файл не имеют права разойтись."""
    folder = project(git=True, commits=3)
    seeded(paths, project={"path": str(folder), "url": "https://myapp.example"},
           xp=620, lexicon_unlocked=["deploy"])
    code, printed = run(["finale"], paths, capsys)
    assert code == 0
    assert run(["scroll"], paths, capsys)[0] == 0
    assert scroll_card(folder).strip() in printed


def test_the_scroll_carries_a_rank_card_at_any_rank(paths, capsys, project):
    """Свиток выдаётся всем — трофей внутри тоже."""
    folder = project()
    seeded(paths, closed=(1,), project={"path": str(folder)})
    assert run(["scroll"], paths, capsys)[0] == 0
    card = scroll_card(folder)
    assert "=== Карточка Искателя ===" in card
    assert "Закрыто актов: 1 из {}.".format(len(ranks.playable_acts())) in card


def test_the_scroll_names_the_card_in_its_table_of_contents(
    paths, capsys, project
):
    folder = project()
    seeded(paths, closed=(1,), project={"path": str(folder)})
    run(["scroll"], paths, capsys)
    index = (folder / "docs" / "jedicoder" / scroll.INDEX_NAME).read_text(
        encoding="utf-8"
    )
    assert scroll.RANK_CARD_NAME in index
    assert "твой трофей" in index


# --- Инварианты движка ------------------------------------------------------


def test_the_finale_prints_a_card_it_did_not_count_itself(
    paths, capsys, tmp_path
):
    """Второй счёт запрещён: команда печатает готовое, а не считает своё.

    Что доказывает этот тест: `finale` отдаёт ровно то, что собрал
    `render_rank_card` по фактам Разбора, и ничего не дописывает от себя.
    Что доказывает не он, а тесты выше: сама карточка до сохранения не
    дотягивается вовсе — они гоняют её на словаре, где сохранения нет.

    Папка проекта без git взята нарочно: коммитов тогда нет, и в карточке не
    остаётся ни одного числа, посчитанного мимо `debrief`.
    """
    folder = tmp_path / "bez-gita"
    folder.mkdir()
    seeded(paths, project={"path": str(folder), "url": "https://myapp.example"},
           xp=620, lexicon_unlocked=["deploy", "dns"], dark_side=2)
    code, out = run(["finale"], paths, capsys)
    assert code == 0
    assert "Слов открыто: 2" in out
    assert "XP: 620" in out
    assert "Штрафы: 2" in out
    assert "Коммитов" not in out

    expected = cli.render_rank_card(debrief.facts(st.load(paths["state_path"])))
    assert expected in out


def test_the_finale_event_reaches_the_queue_once(paths, capsys, tmp_path):
    """Событие финала — одно на прохождение, сколько бы раз ни звали."""
    folder = tmp_path / "bez-gita"
    folder.mkdir()
    seeded(paths, project={"path": str(folder)})
    assert run(["finale"], paths, capsys)[0] == 0
    assert run(["finale"], paths, capsys)[0] == 0
    data = st.load(paths["state_path"])
    assert data["finale_announced"] is True
    finals = [e for e in data["pending_sync"] if e["type"] == "finale"]
    assert len(finals) == 1


def test_the_scroll_reads_the_clock_and_git_once_for_the_whole_handout(
    paths, capsys, project, monkeypatch
):
    """Факты и коммиты приходят в шов сверху, а не добываются в нём заново.

    Два следствия, и оба видны отсюда. Часы: Разбор и карточка обязаны
    сойтись на «Дней в пути» — второе чтение часов развело бы их через
    полночь UTC. git: считать коммиты внутри шва значит держать файловую
    блокировку состояния на время чужого процесса, поэтому подмена ниже
    падает, если кто-то вернёт вызов обратно в шов.
    """
    folder = project(git=True, commits=2)
    seeded(paths, closed=(1, 2), project={"path": str(folder)})

    def refuse(_data):
        raise AssertionError("git позвали под замком состояния")

    monkeypatch.setattr(cli, "_project_commit_count", refuse)
    with pytest.raises(AssertionError):
        # Сам обработчик считает коммиты до замка — подмена его и ловит.
        run(["scroll"], paths, capsys)
    monkeypatch.undo()

    assert run(["scroll"], paths, capsys)[0] == 0
    target = folder / "docs" / "jedicoder"
    card = (target / scroll.RANK_CARD_NAME).read_text(encoding="utf-8")
    razbor = (target / scroll.DEBRIEF_NAME).read_text(encoding="utf-8")
    days = [
        line for line in razbor.splitlines() if line.startswith("- Дней в пути:")
    ]
    assert days, "Разбор перестал печатать дни в пути"
    assert days[0].lstrip("- ") in card


def test_the_seam_still_stands_alone_without_facts_from_above(paths, project):
    """Вызов без фактов не падает: одна карточка честнее упавшей команды."""
    folder = project()
    data = seeded(paths, closed=(1,), project={"path": str(folder)})
    parts = cli._scroll_parts(data, paths["content_root"])
    assert "=== Карточка Искателя ===" in parts[scroll.PART_RANK_CARD]

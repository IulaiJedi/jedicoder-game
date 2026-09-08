"""Факты Разбора: числа прохождения из сохранения, без диска и процессов.

Каждый тест гоняет функцию на словаре: если сюда просочится файловая
система, сеть или git, эти тесты станут медленными и хрупкими первыми.
"""
import copy
import re

from jedicoder import cli, debrief, ranks
from jedicoder import state as st


def test_empty_save_answers_honestly():
    facts = debrief.facts({})
    assert facts["rank"] == "youngling"
    assert facts["rank_title"] == "Юнлинг"
    assert facts["acts_completed"] == []
    assert facts["track"] is None
    assert facts["product_url"] is None
    assert facts["days_in_path"] is None
    assert facts["quests"] == []
    assert facts["hardest_quest"] is None


def _save(**over):
    """Сохранение-словарь: только то, что нужно тесту, остальное — дефолты."""
    data = st.default_state("local-test")
    data.update(over)
    return data


def _act(*quests, **kw):
    """Запись акта: квесты парами «идентификатор — попытки»."""
    entry = {"status": kw.get("status", "done"), "quests": {}}
    for quest_id, attempts in quests:
        entry["quests"][quest_id] = {
            "status": "done" if attempts else "in_progress",
            "attempts": attempts,
        }
    return entry


def test_quests_are_listed_in_registry_order_with_their_attempts():
    data = _save(acts={
        "2": _act(("04-git-init", 1), ("01-recipe", 3)),
        "1": _act(("01-idea", 2)),
    })
    facts = debrief.facts(data)
    assert facts["quests"] == [
        {"act": 1, "quest": "01-idea", "attempts": 2, "closed": True},
        {"act": 2, "quest": "01-recipe", "attempts": 3, "closed": True},
        {"act": 2, "quest": "04-git-init", "attempts": 1, "closed": True},
    ]


def test_hardest_quest_is_the_one_that_took_most_attempts():
    data = _save(acts={
        "1": _act(("01-idea", 2)),
        "2": _act(("01-recipe", 5), ("04-git-init", 1)),
    })
    assert debrief.facts(data)["hardest_quest"] == {
        "act": 2, "quest": "01-recipe", "attempts": 5, "closed": True,
    }


def test_hardest_quest_ties_break_towards_the_earlier_quest():
    """Ничья — за более ранним квестом: там падаван застрял впервые."""
    data = _save(acts={
        "1": _act(("01-idea", 4)),
        "3": _act(("02-feature", 4)),
    })
    assert debrief.facts(data)["hardest_quest"]["quest"] == "01-idea"


def test_quests_without_attempts_leave_the_hardest_empty():
    """Ни одной попытки — честный None, а не квест с нулём."""
    data = _save(acts={"2": _act(("06-pipeline", 0))})
    facts = debrief.facts(data)
    assert facts["quests"] == [
        {"act": 2, "quest": "06-pipeline", "attempts": 0, "closed": False},
    ]
    assert facts["hardest_quest"] is None


def test_counters_come_from_the_save_as_they_are():
    data = _save(
        xp=340,
        first_try={"passed": 7, "attempted": 11},
        streak={"current": 2, "best": 9, "last_commit_date": "2026-09-06"},
        lexicon_unlocked=["deploy", "dns", "traceback"],
        acts={"1": _act(("01-idea", 2), ("02-one-evening", 0))},
    )
    facts = debrief.facts(data)
    assert facts["xp"] == 340
    assert facts["first_try"] == {"passed": 7, "attempted": 11}
    assert facts["streak"] == {"current": 2, "best": 9}
    assert facts["terms_unlocked"] == 3
    assert facts["quests_closed"] == 1
    assert facts["attempts_total"] == 2


def test_counters_survive_a_hand_edited_save():
    facts = debrief.facts({
        "xp": "много", "first_try": "мусор", "streak": None,
        "lexicon_unlocked": "мусор",
    })
    assert facts["xp"] == 0
    assert facts["first_try"] == {"passed": 0, "attempted": 0}
    assert facts["streak"] == {"current": 0, "best": 0}
    assert facts["terms_unlocked"] == 0


def _log(*pairs):
    return [{"type": kind, "date": date} for kind, date in pairs]


def test_dark_side_counts_points_and_days_per_kind():
    """Запись — это очко, а не попытка: отправка `.env` стоит двух очков и
    оставляет две записи одной датой. Наружу идут оба числа, чтобы «дважды»
    нельзя было прочитать как два разных дня.
    """
    data = _save(dark_side=5, dark_side_log=_log(
        ("env_staged", "2026-09-01"),
        ("env_staged", "2026-09-01"),
        ("vague_prompt", "2026-09-02"),
        ("env_staged", "2026-09-03"),
        ("env_staged", "2026-09-03"),
    ))
    dark = debrief.facts(data)["dark_side"]
    assert dark["points"] == 5
    assert dark["logged"] == 5
    assert dark["days"] == 3
    assert dark["by_kind"] == [
        {"kind": "env_staged", "points": 4, "days": 2},
        {"kind": "vague_prompt", "points": 1, "days": 1},
    ]


def test_dark_side_kinds_tie_break_by_name():
    data = _save(dark_side=2, dark_side_log=_log(
        ("root_login", "2026-09-01"), ("env_staged", "2026-09-01"),
    ))
    kinds = [row["kind"] for row in debrief.facts(data)["dark_side"]["by_kind"]]
    assert kinds == ["env_staged", "root_login"]


def test_dark_side_log_younger_than_the_counter_is_named_as_such():
    """Игравший до появления журнала: очки есть, записей нет. Разница —
    отдельное число, а не ноль и не приписанный тип.
    """
    data = _save(dark_side=3, dark_side_log=_log(("root_login", "2026-09-05")))
    dark = debrief.facts(data)["dark_side"]
    assert dark["points"] == 3
    assert dark["logged"] == 1
    assert dark["unlogged"] == 2
    assert dark["log_incomplete"] is True


def test_dark_side_without_a_log_at_all_keeps_the_counter():
    dark = debrief.facts({"dark_side": 2})["dark_side"]
    assert dark == {
        "points": 2, "logged": 0, "unlogged": 2, "log_incomplete": True,
        "days": 0, "by_kind": [],
    }


def test_dark_side_of_a_clean_padawan_is_zero_and_complete():
    dark = debrief.facts({})["dark_side"]
    assert dark == {
        "points": 0, "logged": 0, "unlogged": 0, "log_incomplete": False,
        "days": 0, "by_kind": [],
    }


def test_dark_side_keeps_a_kind_it_does_not_know():
    """Запись от плагина новее переживает откат: перечень типов не сверяется."""
    data = _save(dark_side=1, dark_side_log=_log(("hardcoded_key", "2026-09-06")))
    dark = debrief.facts(data)["dark_side"]
    assert dark["by_kind"] == [{"kind": "hardcoded_key", "points": 1, "days": 1}]
    assert dark["log_incomplete"] is False


def test_dark_side_log_longer_than_the_counter_owes_nothing():
    """Счётчик правили руками вниз: долг журнала не уходит в минус."""
    data = _save(dark_side=0, dark_side_log=_log(("root_login", "2026-09-05")))
    dark = debrief.facts(data)["dark_side"]
    assert dark["unlogged"] == 0
    assert dark["log_incomplete"] is False


def _dates(started=None, completed=None):
    acts_map = {}
    if started:
        acts_map["1"] = {"status": "done", "quests": {}, "started_at": started}
    if completed:
        acts_map["5"] = {"status": "done", "quests": {}, "completed_at": completed}
    return _save(acts=acts_map)


def test_days_in_path_counts_the_first_and_the_last_day():
    data = _dates("2026-09-01T10:00:00Z", "2026-09-06T09:00:00Z")
    assert debrief.facts(data)["days_in_path"] == 6


def test_days_in_path_counts_calendar_days_not_full_days():
    """Вошёл поздно вечером, закрыл ранним утром — это два дня, а не один:
    падаван считает дни по календарю, а не по часам между отметками.
    """
    data = _dates("2026-09-01T23:00:00Z", "2026-09-02T01:00:00Z")
    assert debrief.facts(data)["days_in_path"] == 2


def test_days_in_path_runs_to_today_while_act5_is_open():
    """Свиток выдаётся на любом ранге: у не дошедшего до финала путь идёт."""
    data = _dates("2026-09-01T10:00:00Z")
    assert debrief.facts(data, today="2026-09-04")["days_in_path"] == 4


def test_days_in_path_is_empty_without_the_entry_stamp():
    assert debrief.facts(_dates(completed="2026-09-06T09:00:00Z"))["days_in_path"] is None
    assert debrief.facts({})["days_in_path"] is None


def test_days_in_path_survives_a_broken_stamp():
    assert debrief.facts(_dates("вчера"))["days_in_path"] is None
    assert debrief.facts(_dates("2026-09-01T10:00:00Z"), today="никогда")[
        "days_in_path"
    ] is None


def test_days_in_path_never_drops_below_one():
    """Отметки правили руками задом наперёд — путь всё равно длиной в день."""
    data = _dates("2026-09-06T10:00:00Z", "2026-09-01T09:00:00Z")
    assert debrief.facts(data)["days_in_path"] == 1


# --- Та же дверь, что у падавана: числа фактов против печатной карточки. ---


def _printed(text, label):
    """Числа из строки вывода CLI по её началу. Возвращает список чисел."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(label):
            return [int(n) for n in re.findall(r"\d+", line[len(label):])]
    return None


def _master_save():
    """Сохранение Мастера: пять актов пройдены, счётчики набиты руками."""
    data = _save()
    for act in (1, 2, 3, 4, 5):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    data["acts"]["1"]["started_at"] = "2026-08-20T08:00:00Z"
    data["acts"]["5"]["completed_at"] = "2026-09-06T21:00:00Z"
    data["acts"]["3"]["quests"] = {
        "03-break": {"status": "done", "attempts": 4},
        "04-fix": {"status": "done", "attempts": 1},
    }
    data["xp"] = 340
    data["dark_side"] = 5
    data["dark_side_log"] = _log(
        ("env_staged", "2026-09-01"), ("env_staged", "2026-09-01"),
        ("vague_prompt", "2026-09-02"),
    )
    data["streak"] = {"current": 2, "best": 9, "last_commit_date": "2026-09-06"}
    data["first_try"] = {"passed": 7, "attempted": 11}
    data["lexicon_unlocked"] = ["deploy", "dns", "traceback"]
    # url без path: карточка не должна звать git — процессов в этом файле нет.
    data["project"] = {"url": "https://myapp.example"}
    return data


def test_facts_agree_with_what_status_prints(tmp_path, content_root, quests_root,
                                             capsys):
    data = _master_save()
    state_path = tmp_path / "state.json"
    st.save(data, state_path)
    cli.main(["status"], state_path=state_path, content_root=content_root,
             quests_root=quests_root)
    out = capsys.readouterr().out
    facts = debrief.facts(data)

    # Литералы, а не только сверка с фактами: тест, проверяющий вывод
    # против того же кода, что его считал, согласится с любой общей ошибкой.
    assert facts["rank_title"] == "Мастер"
    assert facts["dark_side"]["points"] == 5
    assert facts["rank_title"] in out.splitlines()[0]
    assert _printed(out, "XP:") == [facts["xp"]]
    assert _printed(out, "Тёмная сторона:") == [facts["dark_side"]["points"]]
    assert _printed(out, "Серия сохранений:") == [
        facts["streak"]["current"], facts["streak"]["best"],
    ]
    assert _printed(out, "Открыто слов:") == [facts["terms_unlocked"]]
    assert _printed(out, "С первой попытки:") == [
        facts["first_try"]["passed"], facts["first_try"]["attempted"],
    ]


def test_facts_agree_with_what_finale_prints(tmp_path, content_root, quests_root,
                                             capsys):
    data = _master_save()
    state_path = tmp_path / "state.json"
    st.save(data, state_path)
    assert cli.main(["finale"], state_path=state_path, content_root=content_root,
                    quests_root=quests_root) == 0
    out = capsys.readouterr().out
    facts = debrief.facts(data)

    assert facts["days_in_path"] == 18  # с 20 августа по 6 сентября
    assert facts["product_url"] in out
    assert _printed(out, "Дней в пути:") == [facts["days_in_path"]]
    assert _printed(out, "Слов открыто:") == [facts["terms_unlocked"]]
    assert _printed(out, "XP:") == [facts["xp"]]
    assert _printed(out, "Тёмная сторона:") == [facts["dark_side"]["points"]]


def test_rank_and_closed_acts_come_from_the_registry():
    """Имя ранга — только из ranks.RANK_TITLES: второго списка имён нет."""
    data = _save()
    for act in (1, 2):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    ranks.enter_act(data, 3)
    facts = debrief.facts(data)
    assert facts["acts_completed"] == [1, 2]
    assert facts["rank"] == "padawan"
    assert facts["rank_title"] == ranks.RANK_TITLES["padawan"]


def test_track_and_product_url_come_from_the_save():
    data = _save(passport={"track": "founder"},
                 project={"url": "https://myapp.example", "path": "/tmp/p"})
    facts = debrief.facts(data)
    assert facts["track"] == "founder"
    assert facts["product_url"] == "https://myapp.example"


def test_garbage_track_and_url_read_as_absent():
    facts = debrief.facts({"passport": {"track": "джедай"}, "project": "мусор"})
    assert facts["track"] is None
    assert facts["product_url"] is None


def test_facts_do_not_touch_the_save():
    """Чистая функция: сохранение приходит параметром и уходит нетронутым."""
    data = _master_save()
    before = copy.deepcopy(data)
    debrief.facts(data, today="2026-09-07")
    assert data == before


def test_a_quest_the_registry_does_not_know_keeps_its_attempts():
    """Сохранение от плагина новее пережило откат: попытки не теряются."""
    data = _save(acts={"2": _act(("01-recipe", 1), ("07-nonesuch", 6))})
    facts = debrief.facts(data)
    assert [q["quest"] for q in facts["quests"]] == ["01-recipe", "07-nonesuch"]
    assert facts["hardest_quest"]["quest"] == "07-nonesuch"


def test_a_stray_act_key_does_not_break_the_facts():
    data = _save(acts={"1": _act(("01-idea", 1)), "заметка": {"quests": {}}})
    facts = debrief.facts(data)
    assert facts["acts_completed"] == [1]
    assert [q["quest"] for q in facts["quests"]] == ["01-idea"]


def test_nothing_is_the_hardest_when_every_quest_went_first_try():
    """Все с первой попытки — тяжёлого квеста не было.

    Назвать «самым тяжёлым» квест с одной попыткой значит подсказать
    Разбору фразу «тяжелее всего дался», которая при этих числах ложна.
    Сами попытки при этом на месте, в списке квестов.
    """
    data = _save(acts={"1": _act(("01-idea", 1), ("02-one-evening", 1))})
    facts = debrief.facts(data)
    assert facts["hardest_quest"] is None
    assert facts["attempts_total"] == 2
    assert [q["attempts"] for q in facts["quests"]] == [1, 1]


def test_days_in_path_stays_empty_when_the_path_ended_unstamped():
    """Акт 5 закрыт, а когда — не записано (бета прошлых версий).

    Досчитать такой путь до сегодня значило бы приписать закончившему в
    июле недели, которых у него не было: путь окончен, а даты нет — None,
    и карточка молча пропускает строку, как и до переноса функции.
    """
    data = _save(acts={
        "1": {"status": "done", "quests": {}, "started_at": "2026-07-01T10:00:00Z"},
        "5": {"status": "done", "quests": {}},
    })
    assert debrief.facts(data, today="2026-09-07")["days_in_path"] is None


def test_deploy_path_comes_from_the_save():
    """Ось Акта 4 — путь деплоя, и по нему шла половина его квестов."""
    data = _save(project={"deploy_path": "vps"})
    assert debrief.facts(data)["deploy_path"] == "vps"
    assert debrief.facts({})["deploy_path"] is None
    assert debrief.facts({"project": {"deploy_path": "облако"}})["deploy_path"] is None


def test_quests_of_an_act_the_registry_does_not_know_keep_their_attempts():
    """Сохранение от плагина новее пережило откат: акт 6 не исчезает.

    Правило то же, что у неизвестного квеста и у чужого ключа в актах:
    молча потерять попытки хуже, чем перечислить их не на своём месте.
    """
    data = _save(acts={"1": _act(("01-idea", 1)), "6": _act(("01-mirage", 4))})
    facts = debrief.facts(data)
    assert [q["quest"] for q in facts["quests"]] == ["01-idea", "01-mirage"]
    assert facts["hardest_quest"] == {
        "act": 6, "quest": "01-mirage", "attempts": 4, "closed": True,
    }


def test_closed_quests_count_both_branches_unlike_the_map(tmp_path, content_root,
                                                          quests_root, capsys):
    """Сменивший трек: карта считает по нынешнему треку, факты — по всему.

    Расхождение намеренное и разное по смыслу. Карта отвечает «сколько
    осталось» и обязана мерить нынешний трек. Факты отвечают «что было», а
    квест покинутого трека падаван закрыл по-настоящему.
    """
    data = _save(passport={"track": "craftsman"}, acts={"1": _act(
        ("01-idea", 1), ("02-one-evening", 1), ("03f-market", 1),
    )})
    data["acts"]["1"]["status"] = "in_progress"
    state_path = tmp_path / "state.json"
    st.save(data, state_path)
    cli.main(["status"], state_path=state_path, content_root=content_root,
             quests_root=quests_root)
    out = capsys.readouterr().out

    assert _printed(out, "[>] Акт 1.") == [2, 3]  # закрыто / всего на треке
    assert debrief.facts(data)["quests_closed"] == 3

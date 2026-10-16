import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lint_content  # noqa: E402

from jedicoder import acts as acts_registry  # noqa: E402
from jedicoder import ranks  # noqa: E402

TERM = (
    "---\n"
    "term: {term}\n"
    "title: {term}\n"
    "aliases: [{aliases}]\n"
    "act: 2\n"
    "category: git\n"
    "xp: 5\n"
    "example: Пример из жизни одной фразой.\n"
    "{extra}"
    "---\n"
    "Тело термина.\n"
    "\n"
    "**Зачем нужно:** чтобы было.\n"
)

RULE = (
    "---\n"
    "rule: {rule}\n"
    "title: {rule}\n"
    "act: 1\n"
    "severity: high\n"
    "xp: 5\n"
    "---\n"
    "Тело правила.\n"
    "\n"
    "**Что делать вместо:** иначе.\n"
)

RECIPE = (
    "---\n"
    "recipe: {recipe}\n"
    "title: {recipe}\n"
    "stack: [python]\n"
    "deploy_path: managed\n"
    "---\n"
    "Тело рецепта.\n"
)


BEHAVIOR = (
    "---\n"
    "contract: behavior\n"
    "version: 1\n"
    "---\n"
    "# Как ты работаешь с падаваном\n"
    "\n"
    "Объясняй простым языком.\n"
)


ACT = (
    "---\n"
    "act: {act}\n"
    "slug: {slug}\n"
    "title: {title}\n"
    "rank: {rank}\n"
    "rank_title: {rank_title}\n"
    "artifact: {artifact}\n"
    "axis: {axis}\n"
    "muted: {muted}\n"
    "quests: [{quests}]\n"
    "quest_titles: [{quest_titles}]\n"
    "{quest_tasks_line}"
    "quest_branches: [{quest_branches}]\n"
    "---\n"
    "{body}\n"
)

# Тело длиннее порога ACT_BODY_MIN и ровно в две фразы (правило `cutscene`):
# короткое тело и лишняя фраза — отдельные кейсы, и остальные проверки не
# должны на них спотыкаться заодно.
ACT_BODY = (
    "Тело катсцены, достаточно длинное, чтобы пройти порог длины.\n\n"
    "Вторая фраза объясняет, зачем это нужно."
)

REMARK = (
    "---\n"
    "event: {event}\n"
    "---\n"
    "{body}\n"
)

# Ровно REMARK_MIN вариантов: минимум — отдельный кейс, остальные проверки
# не должны спотыкаться о него заодно.
REMARK_BODY = "\n\n".join(
    "Вариант {} реплики, одной строкой.".format(i) for i in range(1, 4)
)


def remark_text(event, body=REMARK_BODY):
    return REMARK.format(event=event, body=body)


def default_remarks():
    """Файл на каждое событие сцены — тем же словом, что в MAGISTR_EVENTS."""
    from jedicoder import content as content_mod

    return [
        ("{}.md".format(event), remark_text(event))
        for event in content_mod.MAGISTR_EVENTS
    ]


INSTRUCTION = (
    "---\n"
    "artifact: {artifact}\n"
    "title: Как это делать\n"
    "summary: Одна строка для оглавления.\n"
    "---\n"
    "## Что это\n"
    "\n"
    "Тело инструкции.\n"
)


def instruction_text(artifact):
    return INSTRUCTION.format(artifact=artifact)


def default_instructions():
    """Файл на каждый артефакт — тем же именем, что в реестре движка."""
    return [
        ("{}.md".format(artifact), instruction_text(artifact))
        for artifact in ranks.ALL_ARTIFACTS
    ]


ROADMAP = (
    "---\n"
    "track: {track}\n"
    "title: Три шага\n"
    "lead: Адреса пока нет.\n"
    "lead_url: Продукт живёт по адресу {{url}}.\n"
    "---\n"
    "## Шаг 1\n"
    "\n"
    "Тело карты.\n"
)


def roadmap_text(track):
    return ROADMAP.format(track=track)


def default_roadmaps():
    """Карта на каждый трек реестра плюс одна для не выбравшего трек."""
    return [
        ("{}.md".format(track), roadmap_text(track))
        for track in tuple(acts_registry.TRACKS) + (lint_content.content.TRACK_ANY,)
    ]


def act_text(number, **overrides):
    """Валидная катсцена акта, собранная из тех же реестров, с которыми её
    и сверяет линтер. Дефект вносится точечно через overrides — так тест
    называет ровно одну разошедшуюся вещь, а не переписывает файл целиком.
    """
    info = ranks.ACTS[number]
    entries = acts_registry.QUESTS_BY_ACT[number]
    quests = [entry[0] for entry in entries]
    branches = [entry[2] for entry in entries]
    fields = {
        "act": number,
        "slug": info["slug"],
        "title": info["title"],
        "rank": info["rank"],
        "rank_title": ranks.RANK_TITLES[info["rank"]],
        "artifact": info["artifact"],
        "axis": lint_content.act_axis(number),
        "muted": "true" if ranks.is_muted(number) else "false",
        "quests": ", ".join(quests),
        "quest_titles": ", ".join('"К{}"'.format(i) for i in range(len(quests))),
        "quest_branches": ", ".join(branches),
        # Задание — у каждого квеста играбельного акта; выключенным их ещё
        # не написали.
        "quest_tasks_line": "" if ranks.is_muted(number) else (
            "quest_tasks: [{}]\n".format(
                ", ".join('"Задание {}."'.format(i) for i in range(len(quests)))
            )
        ),
        "body": ACT_BODY,
    }
    fields.update(overrides)
    return ACT.format(**fields)


def default_acts():
    return [
        ("{}.md".format(ranks.ACTS[number]["slug"]), act_text(number))
        for number in sorted(ranks.ACTS)
    ]


def build(root, terms=(), rules=(), recipes=(), behavior=BEHAVIOR, act_files=None,
          remark_files=None, instruction_files=None, roadmap_files=None):
    for directory in (
        "lexicon", "codex", "recipes", "acts", "magistr", "scroll", "roadmap",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    if behavior is not None:
        (root / "behavior.md").write_text(behavior, encoding="utf-8")
    for name, text in terms:
        (root / "lexicon" / name).write_text(text, encoding="utf-8")
    for name, text in rules:
        (root / "codex" / name).write_text(text, encoding="utf-8")
    for name, text in recipes:
        (root / "recipes" / name).write_text(text, encoding="utf-8")
    for name, text in (default_acts() if act_files is None else act_files):
        (root / "acts" / name).write_text(text, encoding="utf-8")
    for name, text in (default_remarks() if remark_files is None else remark_files):
        (root / "magistr" / name).write_text(text, encoding="utf-8")
    files = (
        default_instructions() if instruction_files is None else instruction_files
    )
    for name, text in files:
        (root / "scroll" / name).write_text(text, encoding="utf-8")
    cards = default_roadmaps() if roadmap_files is None else roadmap_files
    for name, text in cards:
        (root / "roadmap" / name).write_text(text, encoding="utf-8")
    return root


def lint_synth(root, **kwargs):
    """Линт синтетического дерева — без правила 3.

    Корпус правила 3 — свойство поставки: он ходит по `plugin/commands` и
    `plugin/skills`, которых у временной папки нет и быть не может. Гонять
    его на синтетическом словаре бессмысленно вдвойне: боевые файлы несут
    маркеры `lint:novelty-ok` со слагами, которых в этом словаре нет, и
    каждый такой маркер выглядел бы проблемой.

    Само правило 3 проверяется отдельно — там корпус собирается руками и
    `lint_content.lint` зовётся напрямую.
    """
    kwargs.setdefault("corpus", ())
    return lint_content.lint(root, **kwargs)


def test_real_content_is_clean(content_root):
    assert lint_content.lint(content_root) == []


def test_alias_collision_detected(tmp_path):
    build(
        tmp_path,
        terms=[
            ("a.md", TERM.format(term="aaa", aliases="коммит, aaa", extra="")),
            ("b.md", TERM.format(term="bbb", aliases="коммит, bbb", extra="")),
        ],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path)
    assert any("коммит" in p and "aaa" in p and "bbb" in p for p in problems)


def test_alias_collision_is_case_insensitive(tmp_path):
    build(
        tmp_path,
        terms=[
            ("a.md", TERM.format(term="aaa", aliases="Commit, aaa", extra="")),
            ("b.md", TERM.format(term="bbb", aliases="commit, bbb", extra="")),
        ],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert any("commit" in p.lower() for p in lint_synth(tmp_path))


def test_duplicate_term_id_detected(tmp_path):
    build(
        tmp_path,
        terms=[
            ("a.md", TERM.format(term="same", aliases="один", extra="")),
            ("b.md", TERM.format(term="same", aliases="два", extra="")),
        ],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert any("same" in p and "повтор" in p for p in lint_synth(tmp_path))


def test_unresolved_related_detected(tmp_path):
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra="related: [nope]\n"))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert any("nope" in p for p in lint_synth(tmp_path))


def test_unresolved_wiki_link_detected(tmp_path):
    body_link = TERM.format(term="aaa", aliases="один", extra="")
    body_link = body_link.replace("Тело термина.", "Смотри [[nothing-here]].")
    build(
        tmp_path,
        terms=[("a.md", body_link)],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert any("nothing-here" in p for p in lint_synth(tmp_path))


def test_missing_required_section_detected(tmp_path):
    no_section = TERM.format(term="aaa", aliases="один", extra="")
    no_section = no_section.replace("**Зачем нужно:** чтобы было.", "просто текст")
    build(
        tmp_path,
        terms=[("a.md", no_section)],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert any("Зачем" in p for p in lint_synth(tmp_path))


def test_schema_error_surfaces_as_problem(tmp_path):
    broken = TERM.format(term="aaa", aliases="один", extra="").replace("category: git\n", "")
    build(
        tmp_path,
        terms=[("a.md", broken)],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert any("category" in p for p in lint_synth(tmp_path))


def _minimal(root, **kwargs):
    return build(
        root,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
        **kwargs
    )


# --- Катсцены актов. Восемь проверок, по кейсу на каждую. -------------

def test_default_acts_are_clean(tmp_path):
    """Опора для остальных восьми: набор из реестров проходит линтер."""
    _minimal(tmp_path)
    assert lint_synth(tmp_path) == []


def test_playable_act_without_quest_tasks_detected(tmp_path):
    """Играбельный акт обязан назвать задание каждого квеста (#83)."""
    acts_ = default_acts()
    acts_[0] = (acts_[0][0], act_text(1, quest_tasks_line=""))
    _minimal(tmp_path, act_files=acts_)
    problems = lint_synth(tmp_path)
    assert any("quest_tasks" in p and "act1" in p for p in problems)


def test_quest_tasks_obey_the_language_rules(tmp_path):
    """Задание печатается человеку до первого ранга — и меряется как текст."""
    acts_ = default_acts()
    tasks = ['"Открой Книгу и вступи в клуб."'] + [
        '"Задание {}."'.format(i) for i in range(1, 5)
    ]
    acts_[0] = (acts_[0][0], act_text(
        1, quest_tasks_line="quest_tasks: [{}]\n".format(", ".join(tasks))
    ))
    _minimal(tmp_path, act_files=acts_)
    problems = lint_synth(tmp_path)
    assert any("задания квестов" in p and "Книг" in p for p in problems), problems


def test_missing_act_file_detected(tmp_path):
    """Проверка 1: множество актов совпадает с ключами ranks.ACTS."""
    _minimal(tmp_path, act_files=default_acts()[:-1])
    problems = lint_synth(tmp_path)
    assert any("нет файлов катсцен" in p and "5" in p for p in problems)


def test_act_field_diverging_from_ranks_detected(tmp_path):
    """Проверка 2: rank во фронтматтере разошёлся с ranks.ACTS."""
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, rank="padawan"))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("rank" in p and "ranks.ACTS" in p for p in problems)


def test_act_slug_must_match_filename(tmp_path):
    """Проверка 3: файл переименовали, а фронтматтер забыли."""
    broken = list(default_acts())
    broken[0] = ("act1-drugoe-imya.md", act_text(1))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("не совпадает с именем файла" in p for p in problems)


def test_duplicate_act_number_detected(tmp_path):
    """Проверка 4: два файла на один и тот же акт."""
    broken = list(default_acts())
    broken.append(("act1-kopiya.md", act_text(1)))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("повторяется" in p and "акт 1" in p for p in problems)


def test_short_act_body_detected(tmp_path):
    """Проверка 5: у катсцены нет маркера секции, её стережёт длина."""
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, body="Короткая катсцена."))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("короче" in p for p in problems)


def test_act_quests_diverging_from_registry_detected(tmp_path):
    """Проверка 6: опечатка в идентификаторе квеста."""
    broken = list(default_acts())
    broken[0] = (
        broken[0][0],
        act_text(1).replace("02-idea", "02-ideya"),
    )
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("QUESTS_BY_ACT" in p for p in problems)


def test_act_quest_titles_count_mismatch_detected(tmp_path):
    """Проверка 7: подписей меньше, чем квестов — списки разъехались."""
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, quest_titles='"Идея", "Правило одного вечера"'))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("разъехались" in p for p in problems)


def test_empty_quest_title_detected(tmp_path):
    """Проверка 8: пустая подпись — дыра в списке квестов книги."""
    quests = [entry[0] for entry in acts_registry.QUESTS_BY_ACT[1]]
    titles = ['"К{}"'.format(i) for i in range(len(quests))]
    titles[2] = '""'
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, quest_titles=", ".join(titles)))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("пустая подпись" in p for p in problems)


def test_wiki_link_from_act_body_is_checked(tmp_path):
    """Ссылка в никуда из катсцены ловится так же, как из термина."""
    broken = list(default_acts())
    broken[0] = (
        broken[0][0],
        act_text(1, body=ACT_BODY + " Смотри [[nichego-net]]."),
    )
    _minimal(tmp_path, act_files=broken)
    assert any("nichego-net" in p for p in lint_synth(tmp_path))


# --- Самоописание актов: ветка каждого квеста, ось развилки, имя ранга. --
#
# Три поля заведены для Голокрона и сайта: они собирают доску квестов из
# контента, не зная реестра движка. Значит расхождение фронтматтера с
# acts.py или ranks.py — доска, обещающая падавану чужие квесты или чужой
# ранг при зелёном суите; линтер сверяет их так же, как quests и rank.

@pytest.mark.parametrize("key", ["rank_title", "axis", "quest_branches", "muted"])
def test_act_without_self_description_detected(tmp_path, key):
    """Акт без любого из полей самоописания — ошибка схемы, и линтер её показывает."""
    text = act_text(1)
    line = next(line for line in text.splitlines() if line.startswith(key + ":"))
    broken = list(default_acts())
    broken[0] = (broken[0][0], text.replace(line + "\n", ""))
    _minimal(tmp_path, act_files=broken)
    assert any(key in p for p in lint_synth(tmp_path))


# Признак «акт выключен» (#82). Истина — ranks.MUTED_ACTS: по нему движок не
# пускает в акт. Во фронтматтере он продублирован для Голокрона, который
# движка не запускает и раньше выуживал список регуляркой из ranks.py.
# Расхождение — церемония, объявляющая открытым акт, в который игра не пустит.

def test_act_muted_diverging_from_registry_detected(tmp_path, monkeypatch):
    """Акт выключен в движке, а описание называет его играбельным."""
    monkeypatch.setattr(ranks, "MUTED_ACTS", (2,))
    broken = list(default_acts())
    broken[1] = (broken[1][0], act_text(2, muted="false"))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any(
        "act2-pamyat-i-sily.md" in p and "muted" in p and "MUTED_ACTS" in p
        for p in problems
    ), problems


def test_act_marked_muted_but_playable_in_registry_detected(tmp_path, monkeypatch):
    """Обратное расхождение: описание выключает акт, в который движок пускает."""
    monkeypatch.setattr(ranks, "MUTED_ACTS", (2,))
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, muted="true"))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any(
        "act1-znakomstvo.md" in p and "muted" in p and "MUTED_ACTS" in p
        for p in problems
    ), problems


def test_act_muted_matching_registry_is_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(ranks, "MUTED_ACTS", (2,))
    _minimal(tmp_path)
    assert not [p for p in lint_synth(tmp_path) if "muted" in p]


def test_act_quest_branches_count_mismatch_detected(tmp_path):
    """Веток меньше, чем квестов — списки разъехались, как и у подписей."""
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, quest_branches="both, both"))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("веток 2, а квестов" in p and "разъехались" in p for p in problems)


def test_act_branch_diverging_from_registry_detected(tmp_path):
    """Метка одного квеста не та, что в реестре: доска показала бы квест
    Ремесленника Основателю, а движок его бы не засчитал."""
    # Развилка по треку осталась у Акта 5: у Акта 1 «Знакомство» её нет.
    branches = [entry[2] for entry in acts_registry.QUESTS_BY_ACT[5]]
    index = branches.index(acts_registry.TRACK_CRAFTSMAN)
    branches[index] = acts_registry.TRACK_FOUNDER
    broken = list(default_acts())
    broken[4] = (broken[4][0], act_text(5, quest_branches=", ".join(branches)))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("quest_branches" in p and "QUESTS_BY_ACT" in p for p in problems)


def test_act_axis_diverging_from_registry_detected(tmp_path):
    """Акт 2 не ветвится вовсе — все квесты both, и схема сама по себе
    стерпит любую ось. Ловит только сверка с acts.ACT_AXIS: фронтматтер,
    назвавший путь деплоя, заставил бы Голокрон фильтровать доску не тем
    выбором падавана."""
    broken = list(default_acts())
    broken[1] = (broken[1][0], act_text(2, axis="deploy"))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("axis" in p and "ACT_AXIS" in p for p in problems)


def test_act_branches_of_other_axis_detected(tmp_path):
    """Акт 5 с осью деплоя — ветки craftsman и founder чужие для этой оси, и
    это ловит схема загрузчика раньше любой сверки с реестром.

    До 2026-10-14 пример был обратный: Акт 4 «Щит» с осью трека. «Щит» на
    полке (спека #117), и по пути деплоя сегодня не ветвится ни один акт."""
    broken = list(default_acts())
    broken[4] = (broken[4][0], act_text(5, axis="deploy"))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("оси 'deploy'" in p and "craftsman" in p for p in problems)


def test_act_rank_title_diverging_from_ranks_detected(tmp_path):
    """Имя ранга во фронтматтере не то, что печатает игра из RANK_TITLES."""
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, rank_title="Падаван"))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("rank_title" in p and "RANK_TITLES" in p for p in problems)


def test_unknown_branch_value_detected(tmp_path):
    """Ветка не из словаря — ошибка схемы; линтер называет чужое слово."""
    branches = [entry[2] for entry in acts_registry.QUESTS_BY_ACT[1]]
    branches[-1] = "sith"
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, quest_branches=", ".join(branches)))
    _minimal(tmp_path, act_files=broken)
    assert any("sith" in p for p in lint_synth(tmp_path))


# --- Реплики Магистра: файл на событие, три варианта, одна строка. -----
#
# Реплика — категория A, дословно падавану, одной строкой на панели сцены.
# Голокрон без файла на событие молчит, а молчание — не ошибка на его
# стороне, а дыра поставки, поэтому состав папки сторожит линтер.

def test_default_remarks_are_clean(tmp_path):
    """Опора для остальных: файл на каждое событие проходит линтер."""
    _minimal(tmp_path)
    assert lint_synth(tmp_path) == []


def test_missing_remark_file_detected(tmp_path):
    """Нет файла на событие — сцена промолчит на финале у всех падаванов."""
    _minimal(tmp_path, remark_files=default_remarks()[:-1])
    problems = lint_synth(tmp_path)
    assert any("нет файлов реплик" in p and "finale" in p for p in problems)


def test_too_few_remark_variants_detected(tmp_path):
    """Два варианта — Магистр повторяется через раз. Минимум из спеки —
    три, и он включительный: ровно три (default_remarks) — норма."""
    two = "Первый вариант.\n\nВторой вариант."
    broken = list(default_remarks())
    broken[0] = (broken[0][0], remark_text("act_started", body=two))
    _minimal(tmp_path, remark_files=broken)
    problems = lint_synth(tmp_path)
    assert any(
        "act_started" in p and "вариантов 2" in p and "минимум 3" in p
        for p in problems
    )


def test_wrapped_remark_variant_detected(tmp_path):
    """Перенос внутри варианта — ошибка схемы; линтер называет файл и
    номер варианта, чтобы автору было что чинить."""
    wrapped = REMARK_BODY.replace(
        "Вариант 2 реплики, одной строкой.",
        "Вариант 2 реплики,\nперенесённый на вторую строку.",
    )
    assert wrapped != REMARK_BODY
    broken = list(default_remarks())
    broken[1] = (broken[1][0], remark_text("quest_completed", body=wrapped))
    _minimal(tmp_path, remark_files=broken)
    problems = lint_synth(tmp_path)
    assert any(
        "quest_completed" in p and "вариант №2" in p and "не одну строку" in p
        for p in problems
    )


def test_remark_event_must_match_filename(tmp_path):
    """Файл переименовали, а фронтматтер забыли. Читателей два — по имени
    файла и по полю event, — и оба обязаны найти одно и то же, иначе одно
    из событий останется без реплики при зелёном суите."""
    broken = list(default_remarks())
    broken[1] = ("zachet.md", remark_text("quest_completed"))
    _minimal(tmp_path, remark_files=broken)
    problems = lint_synth(tmp_path)
    assert any(
        "zachet.md" in p and "не совпадает с именем файла" in p for p in problems
    )


def test_duplicate_remark_event_detected(tmp_path):
    """Два файла на одно событие — какой из них увидит падаван, решает
    порядок обхода папки, а не автор."""
    broken = list(default_remarks()) + [("finale-kopiya.md", remark_text("finale"))]
    _minimal(tmp_path, remark_files=broken)
    problems = lint_synth(tmp_path)
    assert any("event 'finale' повторяется" in p for p in problems)


def test_duplicate_remark_variant_detected(tmp_path):
    """Две одинаковые строки — два варианта по счёту и один по смыслу:
    минимум трёх иначе обходился бы копированием."""
    body = "\n\n".join((
        "Одна и та же реплика.", "Одна и та же реплика.", "Другая реплика.",
    ))
    broken = list(default_remarks())
    broken[2] = (broken[2][0], remark_text("quest_failed", body=body))
    _minimal(tmp_path, remark_files=broken)
    problems = lint_synth(tmp_path)
    assert any(
        "quest_failed" in p and "вариант №2" in p and "повторяется" in p
        for p in problems
    )


def test_remark_variant_with_comment_detected(tmp_path):
    """Служебный комментарий в теле реплики доедет до падавана буква в
    букву: панель печатает строку как есть, markdown её не прячет. Маркеры
    линтера ставятся во фронтматтере строкой-комментарием, как в Акте 4."""
    body = REMARK_BODY + "\n\n<!-- lint:novelty-ok: commit — причина -->"
    broken = list(default_remarks())
    broken[0] = (broken[0][0], remark_text("act_started", body=body))
    _minimal(tmp_path, remark_files=broken)
    problems = lint_synth(tmp_path)
    assert any(
        "act_started" in p and "вариант №4" in p and "комментарий" in p
        for p in problems
    )


def test_long_remark_variant_detected(tmp_path):
    """Реплика — категория A, и меряется тем же потолком, что катсцена:
    одна строка на панели сцены не имеет права быть стеной текста."""
    body = REMARK_BODY.replace("Вариант 1 реплики, одной строкой.", "я" * 1000)
    broken = list(default_remarks())
    broken[0] = (broken[0][0], remark_text("act_started", body=body))
    _minimal(tmp_path, remark_files=broken)
    problems = lint_synth(tmp_path)
    assert any("реплика act_started №1" in p and "1000" in p for p in problems)


def test_remark_take_corpus_position_of_their_event(tmp_path):
    """Правило 3 меряет реплику там, где её событие впервые возможно:
    события хуков — с первой сессии (позиция 0), события движка — с Акта 1,
    деплой и финал — Акт 5. Слово позднего акта в реплике раннего события
    прозвучало бы раньше объяснения."""
    _minimal(tmp_path)
    positions = {
        label: position
        for label, position, _ in lint_content.ordered_corpus(tmp_path)
    }
    # События хуков случаются с первой сессии, до входа в акт.
    for event in ("dark_side", "streak_updated", "term_unlocked"):
        assert positions["реплика Магистра " + event] == 0, event
    # События движка — не раньше входа в Акт 1.
    for event in ("act_started", "quest_completed", "quest_failed", "rank_up"):
        assert positions["реплика Магистра " + event] == 1, event
    # Ручки Акта 5: `project url`, `project post`, `finale`.
    for event in ("product_deployed", "finale"):
        assert positions["реплика Магистра " + event] == 5, event


def test_every_magistr_event_has_corpus_position():
    """Новое событие без позиции получило бы её по умолчанию молча — а
    умолчание в правиле 3 значит «строже всех», и автор не понял бы, за что
    линтер ругает реплику."""
    from jedicoder import content as content_mod

    assert set(lint_content.REMARK_POSITION) == set(content_mod.MAGISTR_EVENTS)


def test_missing_behavior_detected(tmp_path):
    """Без behavior.md первая же команда скилла падала трейсбеком."""
    _minimal(tmp_path, behavior=None)
    assert any("behavior.md" in p for p in lint_synth(tmp_path))


def test_broken_behavior_frontmatter_detected(tmp_path):
    _minimal(tmp_path, behavior="# Без фронтматтера\n\nтекст\n")
    problems = lint_synth(tmp_path)
    assert any("behavior.md" in p and "фронтматтер" in p for p in problems)


def test_empty_behavior_body_detected(tmp_path):
    _minimal(tmp_path, behavior="---\ncontract: behavior\n---\n\n")
    assert any("пустое" in p for p in lint_synth(tmp_path))


def test_good_behavior_is_clean(tmp_path):
    _minimal(tmp_path)
    assert lint_synth(tmp_path) == []


# --- Правило 1: потолок длины дословного текста. ----------------------

def recipe_with_body(name, body):
    """Рецепт с телом ровно заданной длины: длина — предмет проверки."""
    return (
        "---\n"
        "recipe: {}\n"
        "title: {}\n"
        "stack: [python]\n"
        "deploy_path: managed\n"
        "---\n"
        "{}\n"
    ).format(name, name, body)


def term_with_body(name, body, example="Пример из жизни одной фразой."):
    """Термин с телом. `example=None` — без поля: загрузчик такой отвергает."""
    return (
        "---\n"
        "term: {}\n"
        "title: {}\n"
        "aliases: [{}]\n"
        "act: 2\n"
        "category: git\n"
        "xp: 5\n"
        "{}"
        "---\n"
        "{}\n"
    ).format(
        name, name, name,
        "" if example is None else "example: {}\n".format(example), body,
    )


def skills_with(root, files):
    """Дерево plugin/skills для проверки врезок: имя папки — имя скилла."""
    for name, text in files:
        path = root / name / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_recipe_body_at_limit_is_clean(tmp_path):
    """Потолок включительный: ровно VERBATIM_MAX символов — норма."""
    body = "я" * lint_content.VERBATIM_MAX
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", recipe_with_body("ppp", body))],
    )
    assert lint_synth(tmp_path) == []


def test_recipe_body_over_limit_detected(tmp_path):
    """901 символ при потолке 900 — падаван получит стену текста."""
    body = "я" * (lint_content.VERBATIM_MAX + 1)
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", recipe_with_body("ppp", body))],
    )
    problems = lint_synth(tmp_path)
    assert any("рецепт ppp" in p and "901" in p and "900" in p for p in problems)


def test_long_act_body_detected(tmp_path):
    """Катсцена меряется тем же правилом, что рецепт."""
    broken = list(default_acts())
    broken[0] = (broken[0][0], act_text(1, body="я" * 1200))
    _minimal(tmp_path, act_files=broken)
    problems = lint_synth(tmp_path)
    assert any("катсцена act1-znakomstvo" in p and "1200" in p for p in problems)


def test_long_rule_body_detected(tmp_path):
    """Правило Кодекса — тоже дословный текст."""
    long_rule = RULE.format(rule="rrr").replace("Тело правила.", "я" * 1000)
    build(
        tmp_path,
        terms=[("a.md", TERM.format(term="aaa", aliases="один", extra=""))],
        rules=[("r.md", long_rule)],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert any("правило rrr" in p for p in lint_synth(tmp_path))


def test_long_loot_card_detected(tmp_path):
    """Карточка меряется render_card — тем кодом, которым печатается."""
    body = (
        "**ххх** — " + "я" * 950 + "\n\n**Зачем нужно:** чтобы было.\n"
    )
    build(
        tmp_path,
        terms=[("a.md", term_with_body("xxx", body))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert any("карточка xxx" in p for p in lint_synth(tmp_path))


def test_short_loot_card_without_why_section_is_fine(tmp_path):
    """Без секции «Зачем нужно» карточка короче — это не длина, а другая
    проблема, и ловить её обязана проверка секции, а не потолок."""
    body = "**ххх** — короткое определение.\n"
    build(
        tmp_path,
        terms=[("a.md", term_with_body("xxx", body))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path)
    assert not any("символов, потолок" in p for p in problems)


def test_long_skill_quote_block_detected(tmp_path):
    """Врезка `> …` в SKILL.md — категория A: её проигрывают дословно."""
    content_dir = tmp_path / "content"
    skills_dir = skills_with(
        tmp_path / "skills",
        [("act1", "# Скилл\n\n" + "\n".join("> " + "я" * 100 for _ in range(10)))],
    )
    _minimal(content_dir)
    problems = lint_synth(content_dir, skills_root=skills_dir)
    assert any("врезка" in p and "act1" in p for p in problems)


def test_two_quote_blocks_counted_separately(tmp_path):
    """Две цитаты через строку обычного текста — два блока, а не один."""
    content_dir = tmp_path / "content"
    half = "\n".join("> " + "я" * 100 for _ in range(6))
    skills_dir = skills_with(
        tmp_path / "skills",
        [("act1", "# Скилл\n\n" + half + "\n\nобычный текст\n\n" + half + "\n")],
    )
    _minimal(content_dir)
    problems = lint_synth(content_dir, skills_root=skills_dir)
    # Суммарно 1200+ символов, но каждый блок под потолком — молчим.
    assert not any("врезка" in p for p in problems)


def test_shipped_recipes_are_under_limit(content_root):
    """Живой дефект, ради которого правило заведено: три рецепта поставки.

    Меряем тем же `visible_length`, что и линтер: служебные комментарии
    (маркеры правила 3) падавану не доезжают, и своя копия расчёта здесь
    разошлась бы с прибором молча.
    """
    from jedicoder import content as content_mod

    longest = max(
        lint_content.visible_length(r.body)
        for r in content_mod.load_recipes(content_root)
    )
    assert longest <= lint_content.VERBATIM_MAX


# --- Правило 2: бюджет новизны на квест. ------------------------------

def terms_on_quest(count, quest="03-memory"):
    """count терминов Акта 2, объявивших одну и ту же точку введения."""
    return [
        (
            "t{}.md".format(i),
            TERM.format(
                term="term{}".format(i),
                aliases="слово{}".format(i),
                extra="quest: {}\n".format(quest),
            ),
        )
        for i in range(count)
    ]


def test_three_terms_on_one_quest_is_clean(tmp_path):
    """Бюджет включительный: ровно NOVELTY_MAX — норма."""
    build(
        tmp_path,
        terms=terms_on_quest(lint_content.NOVELTY_MAX),
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert lint_synth(tmp_path) == []


def test_four_terms_on_one_quest_detected(tmp_path):
    """Четвёртый термин на квесте — стена новых слов за один шаг."""
    build(
        tmp_path,
        terms=terms_on_quest(lint_content.NOVELTY_MAX + 1),
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path)
    named = [p for p in problems if "03-memory" in p and "потолке 3" in p]
    assert len(named) == 1
    for i in range(4):
        assert "term{}".format(i) in named[0]


def test_unknown_quest_detected(tmp_path):
    """quest, которого нет в реестре акта, — отдельная проблема."""
    build(
        tmp_path,
        terms=terms_on_quest(1, quest="99-nope"),
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path)
    hit = [p for p in problems if "99-nope" in p]
    assert len(hit) == 1
    # Перечислены допустимые id — иначе автору нечем себя починить.
    assert "03-memory" in hit[0] and "01-plan" in hit[0]


def test_term_without_quest_is_not_counted(tmp_path):
    """Термин без quest не участвует в бюджете вовсе: поле необязательное."""
    many = [
        ("t{}.md".format(i), TERM.format(
            term="term{}".format(i), aliases="слово{}".format(i), extra=""
        ))
        for i in range(6)
    ]
    build(
        tmp_path,
        terms=many,
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert lint_synth(tmp_path) == []


def test_quest_without_terms_is_not_a_problem(tmp_path):
    """Пустой квест нарушением не является: правило про превышение."""
    build(
        tmp_path,
        terms=terms_on_quest(1),
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    problems = lint_synth(tmp_path)
    assert not any("04-clear" in p for p in problems)
    assert problems == []


def test_novelty_problem_order_is_deterministic(tmp_path):
    """Два квеста над бюджетом — порядок сообщений повторяется."""
    terms = []
    for quest in ("04-clear", "01-plan"):
        for i in range(4):
            terms.append((
                "{}-{}.md".format(quest, i),
                TERM.format(
                    term="{}-{}".format(quest, i),
                    aliases="слово-{}-{}".format(quest, i),
                    extra="quest: {}\n".format(quest),
                ),
            ))
    build(
        tmp_path,
        terms=terms,
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    first = lint_synth(tmp_path)
    assert first == lint_synth(tmp_path)
    quests = [p for p in first if "потолке 3" in p]
    assert len(quests) == 2
    # sorted по (акт, квест): 01-plan раньше 04-clear.
    assert "01-plan" in quests[0] and "04-clear" in quests[1]


def test_shipped_content_has_no_novelty_violation(content_root):
    """Правило приезжает вхолостую: поле quest ещё никто не объявил."""
    from jedicoder import content as content_mod

    terms = content_mod.load_terms(content_root)
    assert lint_content._novelty_problems(terms) == []


# --- Правило 3: запрет опережающего употребления. ---------------------

def corpus_file(tmp_path, name, position, text):
    """Один файл корпуса правила 3: (подпись, позиция, путь)."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return (name, position, path)


def early_terms(tmp_path, act=3, aliases="порт", extra=""):
    """Один термин заданного акта — минимум для правила 3."""
    build(
        tmp_path / "content",
        terms=[("t.md", TERM.format(
            term="port", aliases=aliases, extra=extra,
        ).replace("act: 2", "act: {}".format(act)))],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    from jedicoder import content as content_mod

    return content_mod.load_terms(tmp_path / "content")


def test_early_use_detected(tmp_path):
    """Слово акта 3 в тексте позиции 0 — одна проблема с именем термина."""
    terms = early_terms(tmp_path)
    corpus = [corpus_file(tmp_path, "start.md", 0, "Запомнить порт проекта.")]
    problems = lint_content._early_use_problems(terms, corpus)
    assert len(problems) == 1
    assert "port" in problems[0] and "start.md" in problems[0]
    assert "порт" in problems[0]


def test_early_use_inside_skip_region_is_silent(tmp_path):
    """Тот же текст внутри региона-справочника — не проблема."""
    terms = early_terms(tmp_path)
    corpus = [corpus_file(
        tmp_path, "start.md", 0,
        "{}\nЗапомнить порт проекта.\n{}\n".format(
            lint_content.NOVELTY_SKIP_OPEN, lint_content.NOVELTY_SKIP_CLOSE
        ),
    )]
    assert lint_content._early_use_problems(terms, corpus) == []


def test_novelty_ok_marker_allows_term(tmp_path):
    """Маркер novelty-ok со слагом термина снимает ровно этот термин."""
    terms = early_terms(tmp_path)
    corpus = [corpus_file(
        tmp_path, "start.md", 0,
        "<!-- lint:novelty-ok: port — причина -->\nЗапомнить порт.\n",
    )]
    assert lint_content._early_use_problems(terms, corpus) == []


def test_novelty_ok_marker_is_file_scoped(tmp_path):
    """Маркер разрешает слово в своём файле, но не в следующем.

    Иначе одна пометка глушила бы правило по всему корпусу — а маркер
    объявлен как разрешение на одно слово в одном файле.
    """
    terms = early_terms(tmp_path)
    corpus = [
        corpus_file(tmp_path, "start.md", 0,
                    "<!-- lint:novelty-ok: port — причина -->\nпорт\n"),
        corpus_file(tmp_path, "core.md", 0, "и снова порт\n"),
    ]
    problems = lint_content._early_use_problems(terms, corpus)
    assert len(problems) == 1
    assert "core.md" in problems[0]


def test_unknown_novelty_ok_slug_is_a_problem(tmp_path):
    """Слаг, которого нет среди терминов, — отдельная проблема."""
    terms = early_terms(tmp_path)
    corpus = [corpus_file(
        tmp_path, "start.md", 0, "<!-- lint:novelty-ok: nosuchterm -->\n",
    )]
    problems = lint_content._early_use_problems(terms, corpus)
    assert len(problems) == 1
    assert "nosuchterm" in problems[0]


def test_unclosed_skip_marker_is_a_problem_and_cuts_nothing(tmp_path):
    """Незакрытый маркер — проблема, а не молчаливое вырезание хвоста.

    Молчаливое вырезание отключило бы правило до конца файла, и заметить
    это было бы нечем: линтер остался бы зелёным.
    """
    terms = early_terms(tmp_path)
    corpus = [corpus_file(
        tmp_path, "start.md", 0,
        "{}\nЗапомнить порт проекта.\n".format(lint_content.NOVELTY_SKIP_OPEN),
    )]
    problems = lint_content._early_use_problems(terms, corpus)
    assert any("не закрыт" in p for p in problems)
    # Хвост не вырезан: слово по-прежнему найдено.
    assert any("port" in p and "позиция 0" in p for p in problems)


def test_use_in_own_or_later_act_is_clean(tmp_path):
    """Слово в тексте своего акта и позже — норма, ради этого всё и было."""
    terms = early_terms(tmp_path)
    corpus = [
        corpus_file(tmp_path, "act3.md", 3, "Запомнить порт проекта."),
        corpus_file(tmp_path, "act5.md", 5, "И снова порт."),
    ]
    assert lint_content._early_use_problems(terms, corpus) == []


def test_term_absent_everywhere_is_clean(tmp_path):
    """Термин, не встречающийся нигде, правилу не мешает.

    Шесть терминов поставки (interface, script, localhost, subagent,
    dependencies, hook) намеренно не лежат ни в одном нашем файле — они
    заведены под лут. Правило запрещает раннее появление, а не отсутствие.
    """
    terms = early_terms(tmp_path)
    corpus = [corpus_file(tmp_path, "start.md", 0, "Ни слова по теме.")]
    assert lint_content._early_use_problems(terms, corpus) == []


def test_missing_corpus_file_is_skipped_silently(tmp_path):
    """Файла из корпуса нет на диске — молчим; пустой файл не проблема."""
    terms = early_terms(tmp_path)
    corpus = [
        ("нет-такого.md", 0, tmp_path / "нет-такого.md"),
        corpus_file(tmp_path, "пусто.md", 0, ""),
    ]
    assert lint_content._early_use_problems(terms, corpus) == []


def test_early_use_reports_only_first_position(tmp_path):
    """Сообщается первое вхождение, а не все: чинится всё равно первое."""
    terms = early_terms(tmp_path)
    corpus = [
        corpus_file(tmp_path, "start.md", 0, "порт"),
        corpus_file(tmp_path, "behavior.md", 0, "порт"),
        corpus_file(tmp_path, "act1.md", 1, "порт"),
    ]
    problems = lint_content._early_use_problems(terms, corpus)
    assert len(problems) == 1
    assert "start.md" in problems[0]


def test_early_use_order_is_deterministic(tmp_path):
    """Термины перебираются по (акт, термин) — вывод повторяется."""
    build(
        tmp_path / "content",
        terms=[
            ("a.md", TERM.format(term="zzz", aliases="зет", extra="")),
            ("b.md", TERM.format(term="aaa", aliases="эй", extra="")),
        ],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    from jedicoder import content as content_mod

    terms = content_mod.load_terms(tmp_path / "content")
    corpus = [corpus_file(tmp_path, "start.md", 0, "зет и эй")]
    first = lint_content._early_use_problems(terms, corpus)
    assert first == lint_content._early_use_problems(terms, corpus)
    assert len(first) == 2
    assert first[0].startswith("aaa") and first[1].startswith("zzz")


def test_corpus_positions_are_ordered(content_root):
    """Корпус поставки идёт по возрастанию позиции — иначе «первое»
    вхождение считалось бы не в том порядке."""
    corpus = lint_content.ordered_corpus(content_root)
    positions = [position for _, position, _ in corpus]
    assert positions == sorted(positions)
    assert positions[0] == 0
    labels = [label for label, _, _ in corpus]
    assert "start.md" in labels and "core/SKILL.md" in labels


def test_shipped_corpus_has_no_early_use(content_root):
    """Поставка чиста по правилу 3 — то, ради чего план и писался."""
    from jedicoder import content as content_mod

    terms = content_mod.load_terms(content_root)
    assert lint_content._early_use_problems(
        terms, lint_content.ordered_corpus(content_root)
    ) == []


def test_visible_length_ignores_comments():
    """Служебный комментарий в счёт длины не идёт: падаван его не видит."""
    text = "Текст.<!-- lint:novelty-ok: port — причина -->"
    assert lint_content.visible_length(text) == len("Текст.")


def test_main_exit_codes(tmp_path, content_root, capsys):
    assert lint_content.main([str(content_root)]) == 0
    build(
        tmp_path,
        terms=[
            ("a.md", TERM.format(term="aaa", aliases="дубль", extra="")),
            ("b.md", TERM.format(term="bbb", aliases="дубль", extra="")),
        ],
        rules=[("r.md", RULE.format(rule="rrr"))],
        recipes=[("p.md", RECIPE.format(recipe="ppp"))],
    )
    assert lint_content.main([str(tmp_path)]) == 1
    assert "дубль" in capsys.readouterr().out


# --- Инструкции артефактов. Линтер сверяет состав, а не текст. ----------
#
# Текст инструкции читает человек, и стережёт его тоже человек: линтер не
# берётся судить, понятна ли она. Его дело — что инструкция есть у каждого
# артефакта реестра и что лишних файлов в разделе нет.


def test_default_instructions_are_clean(tmp_path):
    """Опора для остальных: набор, собранный из реестра, проходит линтер."""
    _minimal(tmp_path)
    assert lint_synth(tmp_path) == []


def test_missing_instruction_detected(tmp_path):
    """Убрали инструкцию — линтер называет осиротевший артефакт.

    Без этой проверки дыра нашлась бы только в проекте у человека: Свиток
    собрался бы на один файл короче, и никто бы не заметил.
    """
    _minimal(tmp_path, instruction_files=default_instructions()[:-1])
    problems = lint_synth(tmp_path)
    assert any("нет инструкций" in p and ranks.ALL_ARTIFACTS[-1] in p
               for p in problems)


def test_extra_instruction_detected(tmp_path):
    """Лишний файл — тоже дефект: артефакта с таким именем в игре нет, и
    инструкция к нему попала бы в Свиток обещанием несуществующего."""
    extra = list(default_instructions()) + [
        ("vydumka.md", instruction_text("vydumka"))
    ]
    _minimal(tmp_path, instruction_files=extra)
    problems = lint_synth(tmp_path)
    assert any("vydumka" in p and "артефакт" in p for p in problems)


def test_instruction_artifact_must_match_filename(tmp_path):
    """Читателей два — по имени файла и по полю artifact, — и оба обязаны
    найти одно и то же."""
    broken = list(default_instructions())
    broken[1] = ("drugoe-imya.md", instruction_text(ranks.ALL_ARTIFACTS[1]))
    _minimal(tmp_path, instruction_files=broken)
    problems = lint_synth(tmp_path)
    assert any("drugoe-imya.md" in p and "не совпадает с именем файла" in p
               for p in problems)


def test_duplicate_instruction_artifact_detected(tmp_path):
    """Два файла на один артефакт: `instructions_by_artifact` отдал бы один
    из них, и какой именно — зависело бы от порядка имён файлов."""
    doubled = list(default_instructions()) + [
        ("handoff-kopiya.md", instruction_text("handoff"))
    ]
    _minimal(tmp_path, instruction_files=doubled)
    problems = lint_synth(tmp_path)
    assert any("handoff" in p and "повторяется" in p for p in problems)


def test_instruction_text_is_not_measured(tmp_path):
    """Граница прибора: длинную инструкцию линтер не трогает.

    Потолок дословного текста (VERBATIM_MAX) написан под реплику в
    терминале, а инструкцию человек читает у себя в проекте и в своём
    темпе. Мерить её тем же потолком значило бы запретить полноценный текст
    ровно там, где он и нужен.
    """
    long_body = "Строка инструкции, вполне обычной длины. " * 80
    stretched = list(default_instructions())
    stretched[0] = (
        stretched[0][0],
        instruction_text(ranks.ALL_ARTIFACTS[0]) + long_body,
    )
    _minimal(tmp_path, instruction_files=stretched)
    assert lint_synth(tmp_path) == []


# --- Состав дорожных карт ---------------------------------------------------
#
# То же правило, что у инструкций: линтер сверяет состав, а не текст. Карта
# ищется по слагу трека из сохранения, и её отсутствие не видно вовсе —
# Свиток выдастся на файл короче и промолчит.


def test_default_roadmaps_are_clean(tmp_path):
    _minimal(tmp_path)
    assert lint_synth(tmp_path) == []


def test_missing_roadmap_detected(tmp_path):
    """Убрали карту трека — линтер называет трек, оставшийся без неё."""
    _minimal(tmp_path, roadmap_files=default_roadmaps()[:-1])
    problems = lint_synth(tmp_path)
    assert any("нет дорожных карт" in p for p in problems)


def test_roadmap_for_the_unchosen_track_is_required(tmp_path):
    """Карта без трека — не украшение: Свиток выдаётся на любом ранге, в том
    числе до выбора трека."""
    only_tracks = [
        (name, text) for name, text in default_roadmaps()
        if not name.startswith(lint_content.content.TRACK_ANY)
    ]
    _minimal(tmp_path, roadmap_files=only_tracks)
    problems = lint_synth(tmp_path)
    assert any(lint_content.content.TRACK_ANY in p for p in problems)


def test_roadmap_track_must_match_filename(tmp_path):
    broken = list(default_roadmaps())
    broken[0] = ("drugoe-imya.md", roadmap_text("craftsman"))
    _minimal(tmp_path, roadmap_files=broken)
    problems = lint_synth(tmp_path)
    assert any("drugoe-imya.md" in p and "не совпадает с именем файла" in p
               for p in problems)


def test_duplicate_roadmap_track_detected(tmp_path):
    doubled = list(default_roadmaps()) + [
        ("craftsman-kopiya.md", roadmap_text("craftsman"))
    ]
    _minimal(tmp_path, roadmap_files=doubled)
    problems = lint_synth(tmp_path)
    assert any("craftsman" in p and "повторяется" in p for p in problems)


def test_roadmap_lead_url_without_the_address_detected(tmp_path):
    """Вводная строка на случай «адрес есть» обязана его называть: без
    подстановки падаван прочитал бы про свой продукт фразу без продукта."""
    broken = list(default_roadmaps())
    broken[0] = (
        "craftsman.md",
        roadmap_text("craftsman").replace(
            "lead_url: Продукт живёт по адресу {url}.\n",
            "lead_url: Продукт уже где-то живёт.\n",
        ),
    )
    _minimal(tmp_path, roadmap_files=broken)
    problems = lint_synth(tmp_path)
    assert any("craftsman.md" in p and "{url}" in p for p in problems)


def test_roadmap_text_is_not_measured(tmp_path):
    """Граница прибора та же, что у инструкции: карту человек читает у себя
    в проекте, а не слышит репликой в терминале."""
    long_body = "Строка карты, вполне обычной длины. " * 80
    stretched = list(default_roadmaps())
    stretched[0] = ("craftsman.md", roadmap_text("craftsman") + long_body)
    _minimal(tmp_path, roadmap_files=stretched)
    assert lint_synth(tmp_path) == []

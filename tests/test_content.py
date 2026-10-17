import re

import pytest

from conftest import needs_shelf

from jedicoder import content


def write(root, relative, text):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


TERM_OK = (
    "---\n"
    "term: commit\n"
    "title: Коммит\n"
    "aliases: [коммит, commit]\n"
    "act: 2\n"
    "category: git\n"
    "xp: 5\n"
    "example: Сохранил игру перед боссом — можно вернуться.\n"
    "---\n"
    "**Коммит** — точка сохранения.\n"
    "\n"
    "**Зачем нужно:** откатиться, если сломал.\n"
)


def test_loads_real_content(content_root):
    terms = content.load_terms(content_root)
    rules = content.load_rules(content_root)
    recipes = content.load_recipes(content_root)
    assert {t.term for t in terms} >= {"commit", "repository", "env"}
    assert any(r.rule == "one-task-one-chat" for r in rules)
    # Три рецепта первой поставки — обещание дизайн-спека (§5.5).
    assert {r.recipe for r in recipes} >= {"telegram-bot", "landing", "web-service"}
    assert {r.deploy_path for r in recipes} == {"managed", "vps"}


def test_term_fields_parsed(tmp_path):
    write(tmp_path, "lexicon/commit.md", TERM_OK)
    term = content.load_terms(tmp_path)[0]
    assert term.term == "commit"
    assert term.aliases == ("коммит", "commit")
    assert term.act == 2
    assert term.xp == 5
    assert term.rank == ""
    assert term.related == ()
    assert "точка сохранения" in term.body


def test_term_quest_parsed(tmp_path):
    """Точка введения термина — необязательное поле quest."""
    write(tmp_path, "lexicon/commit.md", TERM_OK.replace(
        "xp: 5\n", "xp: 5\nquest: 04-git-init\n"
    ))
    assert content.load_terms(tmp_path)[0].quest == "04-git-init"


def test_term_without_quest_loads(tmp_path):
    """Поле необязательное: 55 терминов поставки грузятся как раньше."""
    write(tmp_path, "lexicon/commit.md", TERM_OK)
    assert content.load_terms(tmp_path)[0].quest == ""


def test_quest_is_not_required(tmp_path):
    """quest не в TERM_REQUIRED — иначе фаза обязана разметить все 55."""
    assert "quest" not in content.TERM_REQUIRED


def test_term_example_parsed(tmp_path):
    """Пример из жизни — вторая строка карточки в терминале (#66)."""
    write(tmp_path, "lexicon/commit.md", TERM_OK)
    term = content.load_terms(tmp_path)[0]
    assert term.example == "Сохранил игру перед боссом — можно вернуться."


def test_term_without_example_is_a_schema_error(tmp_path):
    """Поле обязательное с #72: все термины поставки его несут, и термин без
    примера не доедет до карточки в терминале."""
    write(tmp_path, "lexicon/commit.md", TERM_OK.replace(
        "example: Сохранил игру перед боссом — можно вернуться.\n", ""
    ))
    with pytest.raises(content.ContentError) as exc:
        content.load_terms(tmp_path)
    assert "example" in str(exc.value)
    assert "example" in content.TERM_REQUIRED


def test_example_words_limit_is_the_sentence_limit():
    """Пример — одна фраза, предел тот же, что у фразы в language.md."""
    assert content.EXAMPLE_WORDS_MAX == 15


@pytest.mark.parametrize("value, hint", [
    ("[а, б]", "строкой"),
    ("''", "обязательных"),
    (" ".join("слово{}".format(i) for i in range(16)), "16 слов"),
    ("Первая фраза. Вторая фраза.", "одна фраза"),
])
def test_bad_example_is_a_schema_error(tmp_path, value, hint):
    """Список, пустая строка, 16 слов или две фразы — ошибка схемы с причиной."""
    write(tmp_path, "lexicon/commit.md", TERM_OK.replace(
        "example: Сохранил игру перед боссом — можно вернуться.\n",
        "example: {}\n".format(value),
    ))
    with pytest.raises(content.ContentError) as exc:
        content.load_terms(tmp_path)
    assert "example" in str(exc.value)
    assert hint in str(exc.value)


def test_terms_sorted_by_filename(tmp_path):
    write(tmp_path, "lexicon/b.md", TERM_OK.replace("term: commit", "term: bbb"))
    write(tmp_path, "lexicon/a.md", TERM_OK.replace("term: commit", "term: aaa"))
    assert [t.term for t in content.load_terms(tmp_path)] == ["aaa", "bbb"]


def test_missing_required_field(tmp_path):
    write(tmp_path, "lexicon/x.md", TERM_OK.replace("category: git\n", ""))
    with pytest.raises(content.ContentError, match="category"):
        content.load_terms(tmp_path)


def test_unknown_category(tmp_path):
    write(tmp_path, "lexicon/x.md", TERM_OK.replace("category: git", "category: magic"))
    with pytest.raises(content.ContentError, match="category"):
        content.load_terms(tmp_path)


def test_act_out_of_range(tmp_path):
    write(tmp_path, "lexicon/x.md", TERM_OK.replace("act: 2", "act: 9"))
    with pytest.raises(content.ContentError, match="act"):
        content.load_terms(tmp_path)


def test_aliases_must_be_list(tmp_path):
    write(tmp_path, "lexicon/x.md", TERM_OK.replace("aliases: [коммит, commit]", "aliases: коммит"))
    with pytest.raises(content.ContentError, match="aliases"):
        content.load_terms(tmp_path)


def test_empty_body_rejected(tmp_path):
    head = TERM_OK.split("---\n")[1]
    write(tmp_path, "lexicon/x.md", "---\n" + head + "---\n\n")
    with pytest.raises(content.ContentError, match="пустое тело"):
        content.load_terms(tmp_path)


def test_missing_directory(tmp_path):
    with pytest.raises(content.ContentError, match="нет папки"):
        content.load_terms(tmp_path)


def test_bad_frontmatter_reports_path(tmp_path):
    write(tmp_path, "lexicon/x.md", "нет фронтматтера\n")
    with pytest.raises(content.ContentError, match="lexicon/x.md"):
        content.load_terms(tmp_path)


def test_rule_and_recipe_validation(tmp_path):
    write(
        tmp_path,
        "codex/r.md",
        "---\nrule: r\ntitle: T\nact: 1\nseverity: sometimes\nxp: 1\n---\nтело\n",
    )
    with pytest.raises(content.ContentError, match="severity"):
        content.load_rules(tmp_path)

    write(
        tmp_path,
        "recipes/p.md",
        "---\nrecipe: p\ntitle: T\nstack: [python]\ndeploy_path: moon\n---\nтело\n",
    )
    with pytest.raises(content.ContentError, match="deploy_path"):
        content.load_recipes(tmp_path)


# Слова Акта 1 «Знакомство» (спека #75): то, во что человек упирается в
# первый вечер с Claude Code. Перечислены поимённо, как и слова Акта 0 ниже:
# десятое слово попадёт сюда руками, то есть осознанно.
#
# `commit` приехал из Акта 2 вместе с квестом «Сохранение»,
# `permission-mode` — из Акта 0: режим называет первый квест. `env` вернулся
# в Акт 2 (#87): паролей в первый вечер нет, и карточка о них не звучит —
# проверка сохранения стережёт `.env` молча.
# `tool` и `api` остались от прежнего Акта 1 — «одна работа» и «чужая
# программа, у которой просят» нужны идее на вечер и первому запросу.
# `repository` уехал в Акт 5 (#126): в первый вечер скилл запрещает это
# слово, а по шпаргалке оператора репозиторий — та же папка, только на
# GitHub. Квест «Приватный репозиторий» вводит его там.
ACT1_TERMS = (
    "project-folder", "permission-mode",
    "tool",
    "prompt", "api",
    "commit",
    "rollback",
)

# Слова прежнего Акта 1 «Поиск боли», уехавшие на полку вместе с ним:
# бизнес-исследование уходит в клуб, работа над идеей вернётся будущим
# Актом 4. В игре их нет — ни карточкой, ни алиасом.
SHELVED_ACT1_TERMS = (
    "mvp", "ca", "icp", "pmf", "tam-sam-som", "vertical-slice",
    "cac", "ltv", "arpu", "channel",
    "pain", "crystal", "hutt-filter", "estimate",
)

# Шесть слов, уехавших из Акта 1 планом 01.2-05: у Ремесленника было
# пятнадцать доступных терминов при бюджете девять. Ни одно не удалено —
# переехали по смыслу. Пять из них жили в прежнем Акте 2 «Чертёж» и ушли с
# ним на полку (SHELVED_ACT2_TERMS ниже); шестое, `interface`, жило в прежнем
# Акте 3 «Первая кровь» и 2026-10-13 ушло на полку с ним (SHELVED_ACT3_TERMS).
RELOCATED_FROM_ACT1 = ()

# Слова прежнего Акта 2 «Чертёж», уехавшие на полку вместе с ним 2026-10-13
# (спека #99): язык выбора стека, первого коммита и пайплайна. В игре их нет
# — ни карточкой, ни алиасом; вернутся с актом. Седьмое слово прежнего акта,
# `env`, осталось в игре: квест «Сохранение» Акта 1 стережёт этот файл, и
# карточка обещана Акту 2.
SHELVED_ACT2_TERMS = (
    "stack", "dependencies", "script", "git-history", "index", "pipeline",
)


# Слова прежнего Акта 3 «Первая кровь», уехавшие на полку вместе с ним
# 2026-10-13 (спека #108): язык запуска, поломки и чужих инструментов. В
# игре их нет — ни карточкой, ни алиасом. Из десяти слов прежнего акта в игре
# остались четыре: `skill` и `hook` — слова нового Акта 3 «Умения» (квесты
# «Скилл» и «Хук»), `compact` и `context-window` — слова второго акта: оба
# звучат в квесте «Чистый лист» (переехали тикетами #111 и #104).
SHELVED_ACT3_TERMS = (
    "port", "localhost", "interface", "traceback", "mcp", "subagent",
)
KEPT_FROM_OLD_ACT3 = {
    "skill": (3, "01-skill"), "hook": (3, "04-hook"), "compact": (2, "04-clear"),
    "context-window": (2, "04-clear"),
}
#: Три слова полок вернулись в игру карточками Акта 4 «Свой продукт» (#120):
#: сайт там открывается по адресу на своём компьютере (`localhost`, `port` —
#: из «Первой крови»), первая версия продукта зовётся MVP (`mvp` — из «Поиска
#: боли»). Карточки написаны заново; на полках остались прежние.
RETURNED_IN_ACT4 = {
    "localhost": (4, "04-run"), "port": (4, "04-run"), "mvp": (4, "02-plan"),
}
#: Слово полки, вернувшееся карточкой Акта 5 «Три места кода» (#126):
#: первый вопрос о чужом сервисе — есть ли у него API или MCP (шпаргалка
#: оператора, раздел 15). Карточка написана заново; на полке — прежняя.
RETURNED_IN_ACT5 = {"mcp": (5, "04-service")}


def test_shelved_act3_terms_left_the_game_and_lie_on_the_shelf(content_root):
    """Слова прежнего Акта 3 не удалены, а переложены: в игре их нет, на
    полке — все шесть, и каждый файл по-прежнему читается схемой."""
    from pathlib import Path

    from jedicoder import content

    by_term = {item.term: item for item in content.load_terms(content_root)}
    left = set(SHELVED_ACT3_TERMS) - set(RETURNED_IN_ACT4) - set(RETURNED_IN_ACT5)
    assert sorted(set(by_term) & left) == []
    for name, (act, quest) in (list(KEPT_FROM_OLD_ACT3.items())
                               + list(RETURNED_IN_ACT4.items())
                               + list(RETURNED_IN_ACT5.items())):
        assert name in by_term, "слово «{}» пропало из игры".format(name)
        assert (by_term[name].act, by_term[name].quest) == (act, quest), name

    shelf = Path(__file__).resolve().parents[1] / "shelf" / "act3-pervaya-krov" / "content"
    if not shelf.is_dir():
        # Полка наружу не едет: в выгрузке (`build_release.py`) её нет.
        pytest.skip("полки прежнего Акта 3 нет в этом дереве")
    on_shelf = sorted(item.term for item in content.load_terms(shelf))
    assert on_shelf == sorted(SHELVED_ACT3_TERMS)


def test_shelved_act3_holds_its_cutscene():
    """Катсцена «Первой крови» лежит на полке и читается тем же загрузчиком."""
    from pathlib import Path

    from jedicoder import content

    shelf = Path(__file__).resolve().parents[1] / "shelf" / "act3-pervaya-krov" / "content"
    if not shelf.is_dir():
        pytest.skip("полки прежнего Акта 3 нет в этом дереве")
    scenes = list(content.load_acts(shelf))
    assert [item.slug for item in scenes] == ["act3-pervaya-krov"]
    assert scenes[0].quests == (
        "01-launch", "02-feature", "03-break", "04-fix", "05-decisions",
        "06-context7", "07-git-safety", "08-skill", "09-loop-protocol",
        "10-boss",
    )


def test_act1_terms_present(content_root):
    from jedicoder import content

    terms = {item.term for item in content.load_terms(content_root)}
    missing = [name for name in ACT1_TERMS + RELOCATED_FROM_ACT1
               if name not in terms]
    assert missing == [], "нет терминов Акта 1: {}".format(missing)


def test_act1_terms_marked_with_act_one(content_root):
    from jedicoder import content

    for item in content.load_terms(content_root):
        if item.term in ACT1_TERMS:
            assert item.act == 1, "{}: act должен быть 1".format(item.term)


def test_act1_terms_are_exactly_the_named_ones(content_root):
    """Состав слов первого вечера прибит поимённо, в обе стороны."""
    from jedicoder import content

    named = sorted(
        item.term for item in content.load_terms(content_root) if item.act == 1
    )
    assert named == sorted(ACT1_TERMS)


def test_shelved_terms_left_the_game_and_lie_on_the_shelf(content_root):
    """Слова прежнего Акта 1 не удалены, а переложены: в игре их нет, на
    полке — все четырнадцать, и каждый файл по-прежнему читается схемой."""
    from pathlib import Path

    from jedicoder import content

    live = {item.term for item in content.load_terms(content_root)}
    assert sorted(live & (set(SHELVED_ACT1_TERMS) - set(RETURNED_IN_ACT4))) == []

    # Тем же загрузчиком, что и живой словарь: полка обязана оставаться
    # читаемой схемой, иначе вернуть слова значило бы сначала их чинить.
    shelf = Path(__file__).resolve().parents[1] / "shelf" / "act1-poisk-boli" / "content"
    if not shelf.is_dir():
        # Полка наружу не едет: в выгрузке (`build_release.py`) её нет.
        pytest.skip("полки прежнего Акта 1 нет в этом дереве")
    on_shelf = sorted(item.term for item in content.load_terms(shelf))
    assert on_shelf == sorted(SHELVED_ACT1_TERMS)


def test_shelved_act2_terms_left_the_game_and_lie_on_the_shelf(content_root):
    """Слова прежнего Акта 2 не удалены, а переложены: в игре их нет, на
    полке — все шесть, и каждый файл по-прежнему читается схемой."""
    from pathlib import Path

    from jedicoder import content

    live = {item.term for item in content.load_terms(content_root)}
    assert sorted(live & set(SHELVED_ACT2_TERMS)) == []
    assert "env" in live

    shelf = Path(__file__).resolve().parents[1] / "shelf" / "act2-chertezh" / "content"
    if not shelf.is_dir():
        # Полка наружу не едет: в выгрузке (`build_release.py`) её нет.
        pytest.skip("полки прежнего Акта 2 нет в этом дереве")
    on_shelf = sorted(item.term for item in content.load_terms(shelf))
    assert on_shelf == sorted(SHELVED_ACT2_TERMS)


def test_shelved_act2_holds_its_cutscene_and_the_plan_instruction():
    """Катсцена «Чертежа» и инструкция приёма `plan` лежат на полке и
    читаются теми же загрузчиками, что живой контент."""
    from pathlib import Path

    from jedicoder import content

    shelf = Path(__file__).resolve().parents[1] / "shelf" / "act2-chertezh" / "content"
    if not shelf.is_dir():
        pytest.skip("полки прежнего Акта 2 нет в этом дереве")
    scenes = list(content.load_acts(shelf))
    assert [item.slug for item in scenes] == ["act2-chertezh"]
    assert scenes[0].quests == (
        "01-recipe", "02-claude-md", "03-db-schema", "04-git-init",
        "05-env-guard", "06-pipeline",
    )
    assert sorted(content.instructions_by_artifact(shelf)) == ["plan"]


# Слова Актов 1–3, которые не вводит ни один квест. Список именной: второе
# такое слово попадёт сюда руками, то есть осознанно.
#
# `env` (#104): паролей нет ни в первый, ни во второй вечер, и ни один квест
# Акта 2 этого слова не говорит. Прежняя приписка к квесту «Память проекта»
# была обещанием, которого никто не выполнял. Карточка открыта с Акта 2 и
# выпадает, когда слово прозвучит само: защита остановила файл с паролями
# или проекту понадобился чужой ключ.
TERMS_WITHOUT_A_QUEST = ("env",)


def test_terms_without_a_quest_are_named_and_really_have_none(content_root):
    """Исключение живое: слово есть, оно в Актах 1–3 и квеста не называет."""
    from jedicoder import content

    by_term = {item.term: item for item in content.load_terms(content_root)}
    for name in TERMS_WITHOUT_A_QUEST:
        assert name in by_term, "термин «{}» пропал из словаря".format(name)
        assert by_term[name].act in (1, 2, 3)
        assert not by_term[name].quest, (
            "«{}» называет квест — убери его из исключений".format(name)
        )


def test_acts_1_to_3_terms_declare_quest(content_root):
    """Каждый термин Актов 1–3 называет квест, и квест — из реестра.

    Исключения перечислены поимённо в `TERMS_WITHOUT_A_QUEST`.

    Дубль правила 2 линтера, и дубль намеренный: линтер защищает CI, а тест
    защищает от того, что правило линтера кто-то отключит или обойдёт. Оба
    сразу молча не пропадут.

    Акты 4 и 5 сюда не входят: охват аудита языка ограничен Актами 1–3
    решением автора (D-08). Про их плотность зелёный суит не говорит ничего.
    """
    from jedicoder import acts, content

    bad = []
    for item in content.load_terms(content_root):
        if item.act not in (1, 2, 3) or item.term in TERMS_WITHOUT_A_QUEST:
            continue
        known = [q for q, _, _ in acts.QUESTS_BY_ACT[item.act]]
        if not item.quest:
            bad.append("{}: акт {}, а quest не объявлен".format(item.term, item.act))
        elif item.quest not in known:
            bad.append(
                "{}: quest '{}' нет в акте {} — есть {}".format(
                    item.term, item.quest, item.act, ", ".join(known)
                )
            )
    assert bad == [], "\n".join(bad)


# Исключений больше нет — и это сказано словами, а не выражено пустотой.
#
# Единственным исключением был `permission-mode`: план 01.2-06 привязал его к
# квесту `01-remote` под требование TOOL-03. План 01.4-03 увёз этот термин в
# Акт 0 (TOOL-05): режим разрешений — боль первого вечера, а не Акта 4, и за
# стеной оплаты он приходил на несколько вечеров позже, чем человек начинает
# жать «да» на каждое действие. Вместе с ним ушла и разметка: квестов у Акта 0
# нет.
#
# Значит разметка Актов 4–5 полем `quest` не имеет сегодня ни одного
# исключения. Кортеж пуст намеренно; следующее исключение попадёт сюда руками,
# то есть осознанно.
#
# Акт 4 «Свой продукт» играется с 2026-10-15, и слова его вечера размечены
# квестом, как в Актах 1–3 (#120): охват бюджета новизны дорос до Акта 4.
# Без квеста остаётся «Цель» — приём акта, карточка выпадает на входе.
ACT4_TERMS_WITH_QUEST = ("mvp", "bot-token", "localhost", "port")
#: Слова Акта 5 «Три места кода» (#126) размечены квестом, как в Акте 4.
ACT5_TERMS_WITH_QUEST = ("github", "repository", "api-key", "mcp")


def test_acts_4_and_5_terms_have_no_quest(content_root):
    """Акты 4 и 5 не размечены — и это решение, а не забывчивость (D-08).

    Тест стоит здесь, чтобы разметка не расползлась туда молча: если
    следующая фаза расширит охват, она обязана снять этот тест руками и тем
    самым признать, что бюджет Актов 4–5 теперь тоже измеряется.

    Исключения перечислены поимённо в `ACT4_TERMS_WITH_QUEST`. Именной
    список, а не «Акт 4 разрешён целиком»: второе слово Акта 4 с полем
    `quest` обязано попасть в этот же список руками — то есть осознанно.
    """
    from jedicoder import content

    named = ACT4_TERMS_WITH_QUEST + ACT5_TERMS_WITH_QUEST
    marked = sorted(
        t.term for t in content.load_terms(content_root)
        if t.act in (4, 5) and t.quest and t.term not in named
    )
    assert marked == [], "Акты 4–5 размечены, а охват аудита их не включает: {}".format(
        marked
    )


def test_act4_terms_present(content_root):
    """Акт 4 «Свой продукт» (спека #117, слова — #120): приём «Цель» и четыре
    слова вечера — MVP («План»), ключ бота («Сборка»), localhost и порт
    («Работает»). `.env` — карточка Акта 2: открыта раньше и выпадает, когда
    слово прозвучит.

    Девять слов прежнего «Щита» — на полке: `SHELVED_ACT4_TERMS`.
    """
    from jedicoder import content
    by_term = {t.term: t for t in content.load_terms(content_root) if t.act == 4}
    assert set(by_term) == {"goal", "mvp", "bot-token", "localhost", "port"}
    assert {name: by_term[name].quest for name in ACT4_TERMS_WITH_QUEST} == {
        "mvp": "02-plan", "bot-token": "03-build",
        "localhost": "04-run", "port": "04-run",
    }
    assert not by_term["goal"].quest


#: Слова прежнего Акта 4 «Щит» — на полке с ним (спека #117, тикет #118).
SHELVED_ACT4_TERMS = (
    "push-pull", "remote", "ssh-key", "sudo", "root",
    "firewall", "fail2ban", "rotation", "2fa",
)


@needs_shelf
def test_shelved_act4_terms_left_the_game_and_lie_on_the_shelf(content_root):
    from pathlib import Path

    from jedicoder import content

    live = {item.term for item in content.load_terms(content_root)}
    assert sorted(live & set(SHELVED_ACT4_TERMS)) == []
    shelf = Path(__file__).resolve().parents[1] / "shelf" / "act4-shchit" / "content"
    on_shelf = sorted(item.term for item in content.load_terms(shelf))
    assert on_shelf == sorted(SHELVED_ACT4_TERMS)
    scenes = list(content.load_acts(shelf))
    assert [(scene.act, scene.slug) for scene in scenes] == [(4, "act4-shchit")]
    # Инструкция приёма `cso` вернулась в игру с Актом 5 (спека #123).
    assert not (shelf / "scroll").exists()


# Именной список-страж Акта 0 — взамен исключения, снятого выше.
#
# Линтер Акт 0 не меряет, и это факт кода, а не недосмотр: правило 2
# (`_novelty_problems`) считает термины по полю `quest` и термин без него
# пропускает, а квестов у Акта 0 нет и быть не может — исход квеста решает
# exit-код `check.sh`, а Акт 0 ничего не засчитывает.
#
# Поэтому бюджет новизны первого вечера держится ЭТИМ списком, а не ревью и
# не обещанием (D-03). Четвёртое слово Акта 0 попадёт сюда руками — то есть
# осознанно, с ответом на вопрос, что именно человек не выдержит в первый
# вечер, если слов станет четыре.
#
# Сегодня их два: лимит и `terminal`, который человек открывает здесь
# впервые. Режим разрешений с 2026-10-08 — слово Акта 1: его называет и
# показывает первый квест «Знакомства» (спека #75), а не подготовка.
# Карточка «модель и уровень усилий» с 2026-10-13 — слово Акта 2 (#104):
# экран `/model` человек открывает в квесте «Силы». Лимит остался здесь
# намеренно: кончиться он может в любой вечер, и карточка обязана выпасть.
ACT0_TERMS = ("terminal", "usage")


def test_act0_terms_named_and_questless(content_root):
    """Термины Акта 0 перечислены поимённо и не размечены квестом.

    Две проверки в одном тесте намеренно: они про одну и ту же вещь —
    что Акт 0 остаётся измеримым руками. Объявленный `quest` у термина с
    актом 0 к тому же уронил бы правило 2 линтера сообщением про
    несуществующий квест: `QUESTS_BY_ACT.get(0)` возвращает None.
    """
    from jedicoder import content

    terms = [t for t in content.load_terms(content_root) if t.act == 0]
    assert sorted(t.term for t in terms) == sorted(ACT0_TERMS)
    marked = sorted(t.term for t in terms if t.quest)
    assert marked == [], "у терминов Акта 0 объявлен quest: {}".format(marked)


# Матчасть Claude Code (TOOL-01…04): термин → (акт, квест). Точки введения
# не произвольные — они там, где падаван в это упирается, и с планом 01.4-03
# они переехали в начало Акта 3: контекстное окно — в первый квест, где
# разговор впервые становится длинным, чистый чат и расход — во второй, где
# он становится длинным по-настоящему. У босса `10-boss` не осталось ни
# одного нового слова: предупреждение, приходящее последним квестом акта,
# приходит после того, как всё уже случилось (TOOL-04). Режим разрешений в
# этом словаре не значится: он уехал в Акт 0, где квестов нет вовсе, и
# сторожит его теперь `ACT0_TERMS` выше.
#
# Числа сюда не попадают намеренно: летучие факты живут в командах
# `/context` и `/usage`, а не в тексте (см. тест на летучие числа в
# tests/test_language.py).
# `usage` из этой карты ушёл в Акт 0 (2026-09-10, вместе со строкой состояния):
# в лимит падаван упирается не тогда, когда разговор стал длинным по-настоящему,
# а когда угодно — и узнать про него обязан до того, а не после.
# `clear` переехал в Акт 2 (2026-10-13, спека #99): командой `/clear` там
# закрывается квест «Чистый лист», и его код звучит в самоописании акта.
# Тем же вечером (#104) к нему переехал `context-window`: слово «контекст»
# человек слышит в том же квесте, раньше команды. Режим плана, файл
# `CLAUDE.md` и модель с уровнем усилий — слова своих квестов Акта 2.
CLAUDE_CODE_TERMS = {
    "plan-mode": (2, "01-plan"),
    "claude-md": (2, "03-memory"),
    "context-window": (2, "04-clear"),
    "clear": (2, "04-clear"),
    "model-effort": (2, "05-powers"),
}


def test_claude_code_terms_exist(content_root):
    """Термины матчасти на месте, и их точки введения — из реестра.

    Проверяется и то, что квест вообще существует в акте: опечатка в поле
    `quest` не уронила бы ни линтера правила 2 (он ловит только чужой
    квест), ни игру — она просто сделала бы обещание про точку введения
    ложным молча.
    """
    from jedicoder import acts, content

    by_term = {t.term: t for t in content.load_terms(content_root)}
    for slug, (act, quest) in sorted(CLAUDE_CODE_TERMS.items()):
        assert slug in by_term, "термин «{}» пропал из словаря".format(slug)
        item = by_term[slug]
        assert item.act == act, "«{}»: акт {}, ожидался {}".format(
            slug, item.act, act
        )
        assert item.quest == quest, "«{}»: quest '{}', ожидался '{}'".format(
            slug, item.quest, quest
        )
        known = [q for q, _, _ in acts.QUESTS_BY_ACT[act]]
        assert quest in known, "квеста '{}' нет в акте {} — есть {}".format(
            quest, act, ", ".join(known)
        )


#: Слова прежнего Акта 5 «Выход в свет» — на полке с ним (спека #123,
#: тикет #124). Слова нового Акта 5 «Три места кода» — ниже (#126).
SHELVED_ACT5_TERMS = (
    "deploy", "nginx", "reverse-proxy", "dns", "a-record",
    "ssl", "healthcheck", "ci-cd", "virality",
)


#: Слова пятого вечера (#126) — по словарику шпаргалки оператора, без
#: перегруза: GitHub, репозиторий (с «приватным» внутри карточки), API-ключ и
#: MCP. «API» — карточка Акта 1: выпадает здесь, если не выпала раньше.
ACT5_TERMS = {
    "github": "01-github", "repository": "02-private",
    "api-key": "04-service", "mcp": "04-service",
}


def test_act5_terms_present(content_root):
    """Слова Акта 5 — ровно названные, каждое при своём квесте."""
    from jedicoder import acts, content
    terms = {t.term: t for t in content.load_terms(content_root) if t.act == 5}
    assert sorted(terms) == sorted(ACT5_TERMS)
    known = [q for q, _, _ in acts.QUESTS_BY_ACT[5]]
    for name, quest in ACT5_TERMS.items():
        assert terms[name].quest == quest, name
        assert quest in known, quest
        assert terms[name].rank == "master", name


@needs_shelf
def test_shelved_act5_terms_left_the_game_and_lie_on_the_shelf(content_root):
    from pathlib import Path

    from jedicoder import content

    live = {item.term for item in content.load_terms(content_root)}
    assert sorted(live & set(SHELVED_ACT5_TERMS)) == []
    shelf = Path(__file__).resolve().parents[1] / "shelf" / "act5-vyhod-v-svet" / "content"
    on_shelf = sorted(item.term for item in content.load_terms(shelf))
    assert on_shelf == sorted(SHELVED_ACT5_TERMS)
    scenes = list(content.load_acts(shelf))
    assert [(scene.act, scene.slug) for scene in scenes] == [(5, "act5-vyhod-v-svet")]
    instructions = content.instructions_by_artifact(shelf)
    assert sorted(instructions) == ["deploy"]


def test_content_lints_clean():
    """Пересечение алиасов не видно глазами при ревью — только линтером.

    Гоняем сам скрипт, а не его внутренности: в CI запускается именно он,
    и расхождение между «линтер в тесте» и «линтер в CI» скрыло бы поломку.
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    done = subprocess.run(
        [sys.executable, str(root / "scripts" / "lint_content.py")],
        capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr


ACT_OK = (
    "---\n"
    "act: 1\n"
    "slug: act1-poisk-boli\n"
    "title: Поиск боли\n"
    "rank: seeker\n"
    "rank_title: Искатель\n"
    "artifact: brainstorm\n"
    "axis: track\n"
    "muted: false\n"
    "quests: [01-idea, 02-one-evening]\n"
    'quest_titles: ["Идея", "Фильтр Хатта"]\n'
    "quest_branches: [both, both]\n"
    "---\n"
    "Ты пришёл строить. Начнём с того, что строить пока нечего.\n"
)


def test_loads_real_acts(content_root):
    items = content.load_acts(content_root)
    assert [item.act for item in items] == [1, 2, 3, 4, 5]
    first = items[0]
    assert first.slug == "act1-znakomstvo"
    assert first.rank == "seeker"
    assert first.artifact == "brainstorm"
    assert first.quests[0] == "01-folder"
    assert set(first.quest_branches) == {"both"}
    assert len(first.quest_titles) == len(first.quests)
    assert first.body


def test_act_quests_match_registry(content_root):
    """Единственный источник правды для списка квестов книги — фронтматтер,
    но разъехаться с реестром движка он не имеет права."""
    from jedicoder import acts

    for item in content.load_acts(content_root):
        expected = tuple(quest_id for quest_id, _, _ in acts.QUESTS_BY_ACT[item.act])
        assert item.quests == expected, item.path.name


def test_act_quest_branches_match_registry(content_root):
    """Ветка каждого квеста во фронтматтере — та же, что метка на квесте в
    acts.QUESTS_BY_ACT, позиция в позицию. Голокрон собирает доску из
    контента, движок фильтрует состав акта по реестру: разойдись они, доска
    обещала бы падавану чужие квесты при полностью зелёном суите."""
    from jedicoder import acts

    for item in content.load_acts(content_root):
        expected = tuple(branch for _, _, branch in acts.QUESTS_BY_ACT[item.act])
        assert item.quest_branches == expected, item.path.name


def test_act_axis_matches_registry(content_root):
    """Ось развилки во фронтматтере совпадает с acts.ACT_AXIS: не названная
    там ось — трек, названная AXIS_DEPLOY — путь деплоя. Сегодня это один
    Акт 4, и именно поэтому расхождение не заметить глазами."""
    from jedicoder import acts

    for item in content.load_acts(content_root):
        if acts.ACT_AXIS.get(item.act) == acts.AXIS_DEPLOY:
            assert item.axis == "deploy", item.path.name
        else:
            assert item.axis == "track", item.path.name


def test_act_rank_title_matches_ranks_module(content_root):
    """Русское имя ранга во фронтматтере — то же, что печатает игра из
    ranks.RANK_TITLES: сцена Голокрона и терминал обязаны звать ранг одним
    словом."""
    from jedicoder import ranks

    for item in content.load_acts(content_root):
        assert item.rank_title == ranks.RANK_TITLES[item.rank], item.path.name


def test_branch_and_axis_vocabulary_agrees_with_registry():
    """Словари схемы — копии констант движка, а не импорт (слоистость та же,
    что у ACT_RANKS), поэтому совпадение обязано быть видимым тестом."""
    from jedicoder import acts

    assert set(content.AXES) == {"track", acts.AXIS_DEPLOY}
    assert set(content.BRANCHES_BY_AXIS) == set(content.AXES)
    assert set(content.BRANCHES_BY_AXIS["track"]) == (
        {acts.BRANCH_BOTH} | set(acts.TRACKS)
    )
    assert set(content.BRANCHES_BY_AXIS["deploy"]) == (
        {acts.BRANCH_BOTH} | set(acts.DEPLOYS)
    )


def test_act_ranks_agree_with_ranks_module():
    """Союз держится линтером, а не импортом: content.py — нижний слой
    схемы, и обратный импорт из ranks.py перевернул бы слоистость. Раз
    импорта нет, расхождение обязано быть видимым тестом."""
    from jedicoder import ranks

    assert set(content.ACT_RANKS) == {info["rank"] for info in ranks.ACTS.values()}


def test_act_fields_parsed(tmp_path):
    write(tmp_path, "acts/act1-poisk-boli.md", ACT_OK)
    act = content.load_acts(tmp_path)[0]
    assert act.act == 1
    assert act.title == "Поиск боли"
    assert act.quests == ("01-idea", "02-one-evening")
    assert act.quest_titles == ("Идея", "Фильтр Хатта")


def test_act_self_description_parsed(tmp_path):
    """Акт описывает себя сам: ветка каждого квеста, ось развилки и русское
    имя ранга читаются из фронтматтера, а не выводятся из реестра движка.
    Ради этого поля и заведены — Голокрон и сайт собирают доску квестов из
    контента, не зная acts.py."""
    write(tmp_path, "acts/act1-poisk-boli.md", ACT_OK)
    act = content.load_acts(tmp_path)[0]
    assert act.quest_branches == ("both", "both")
    assert act.axis == "track"
    assert act.rank_title == "Искатель"


@pytest.mark.parametrize("line", [
    "rank_title: Искатель\n",
    "axis: track\n",
    "quest_branches: [both, both]\n",
    "muted: false\n",
])
def test_act_without_self_description_rejected(tmp_path, line):
    """Каждое поле самоописания обязательно: акт без него — не самоописание,
    а половина карты, и Голокрон нарисовал бы доску без веток."""
    assert line in ACT_OK
    write(tmp_path, "acts/act1-poisk-boli.md", ACT_OK.replace(line, ""))
    key = line.split(":")[0]
    with pytest.raises(content.ContentError, match=key):
        content.load_acts(tmp_path)


@pytest.mark.parametrize("written, expected", [("false", False), ("true", True)])
def test_act_muted_flag_parsed(tmp_path, written, expected):
    """Выключен ли акт, он говорит сам — булевым полем (#82). Голокрон
    читает его из фронтматтера и не лезет в ranks.py."""
    write(
        tmp_path,
        "acts/act1-poisk-boli.md",
        ACT_OK.replace("muted: false", "muted: " + written),
    )
    assert content.load_acts(tmp_path)[0].muted is expected


@pytest.mark.parametrize("written", ["yes", "0", "1", '"true"'])
def test_act_muted_must_be_boolean(tmp_path, written):
    """Свой парсер знает только true и false: «yes» он прочёл бы строкой, а
    непустая строка — истина. Акт выключился бы от любого слова."""
    write(
        tmp_path,
        "acts/act1-poisk-boli.md",
        ACT_OK.replace("muted: false", "muted: " + written),
    )
    with pytest.raises(content.ContentError, match="muted"):
        content.load_acts(tmp_path)


def test_act_unknown_axis_rejected(tmp_path):
    write(
        tmp_path,
        "acts/act1-poisk-boli.md",
        ACT_OK.replace("axis: track", "axis: moon"),
    )
    with pytest.raises(content.ContentError, match="axis"):
        content.load_acts(tmp_path)


def test_act_unknown_quest_branch_rejected(tmp_path):
    """Ветка не из словаря — опечатка, из-за которой квест не попал бы ни в
    одну ветку доски и молча исчез бы у всех падаванов."""
    write(
        tmp_path,
        "acts/act1-poisk-boli.md",
        ACT_OK.replace("quest_branches: [both, both]", "quest_branches: [both, sith]"),
    )
    with pytest.raises(content.ContentError, match="quest_branches.*sith"):
        content.load_acts(tmp_path)


@pytest.mark.parametrize("axis, branch", [
    ("track", "managed"),
    ("deploy", "craftsman"),
])
def test_act_branch_of_other_axis_rejected(tmp_path, axis, branch):
    """Ветка чужой оси — ошибка схемы, а не незнакомое слово: у одного акта
    не бывает квестов, ветвящихся по разным осям, и читатель без движка
    (Голокрон) обязан узнать это из самой схемы, а не из реестра."""
    text = ACT_OK.replace("axis: track", "axis: " + axis).replace(
        "quest_branches: [both, both]", "quest_branches: [both, {}]".format(branch)
    )
    write(tmp_path, "acts/act1-poisk-boli.md", text)
    with pytest.raises(
        content.ContentError, match="quest_branches.*{}.*{}".format(branch, axis)
    ):
        content.load_acts(tmp_path)


def test_act_quest_branches_must_be_list(tmp_path):
    write(
        tmp_path,
        "acts/act1-poisk-boli.md",
        ACT_OK.replace("quest_branches: [both, both]", "quest_branches: both"),
    )
    with pytest.raises(content.ContentError, match="quest_branches"):
        content.load_acts(tmp_path)


def test_act_without_quest_titles_rejected(tmp_path):
    write(
        tmp_path,
        "acts/act1-poisk-boli.md",
        ACT_OK.replace('quest_titles: ["Идея", "Фильтр Хатта"]\n', ""),
    )
    with pytest.raises(content.ContentError, match="quest_titles"):
        content.load_acts(tmp_path)


def test_act_unknown_rank_rejected(tmp_path):
    write(
        tmp_path,
        "acts/act1-poisk-boli.md",
        ACT_OK.replace("rank: seeker", "rank: youngling"),
    )
    with pytest.raises(content.ContentError, match="rank"):
        content.load_acts(tmp_path)


def test_act_number_out_of_range_rejected(tmp_path):
    write(tmp_path, "acts/act7.md", ACT_OK.replace("act: 1", "act: 7"))
    with pytest.raises(content.ContentError, match="act"):
        content.load_acts(tmp_path)


def test_act_quests_must_be_list(tmp_path):
    write(
        tmp_path,
        "acts/act1-poisk-boli.md",
        ACT_OK.replace("quests: [01-idea, 02-one-evening]", "quests: 01-idea"),
    )
    with pytest.raises(content.ContentError, match="quests"):
        content.load_acts(tmp_path)


def test_dark_side_rules_present(content_root):
    from jedicoder import content
    rules = {r.rule for r in content.load_rules(content_root) if r.dark_side}
    assert {
        "env-never-in-git", "rm-rf-outside-project",
        "no-root-in-production", "vague-prompt",
    } <= rules


# --- Реплики Магистра: по файлу на событие, варианты по одному на абзац. --
#
# Голокрон подбирает реплику к событию сцены, и событие у него — то же
# слово, что в очереди state.EVENT_TYPES. Реплика доезжает до падавана
# дословно, одной строкой на панели: перенос внутри варианта — не стиль, а
# сломанная строка.

REMARK_OK = (
    "---\n"
    "event: quest_completed\n"
    "# Служебная заметка: парсер её пропускает, в варианты она не попадает.\n"
    "---\n"
    "Зачёт. Такую проверку я, помню, проходил с третьего раза.\n"
    "\n"
    "Первую зелёную проверку я никому не показал. Зря: было чем.\n"
    "\n"
    "После зачёта я всегда бежал дальше, не глядя.\n"
)


def test_magistr_events_agree_with_state_module():
    """Реплика есть на каждое событие сцены, кроме привязки: linked — факт
    про бота, а не про путь падавана, и сцена на него не отзывается.
    Словарь событий — копия из state.py, а не импорт: content.py — нижний
    слой схемы, поэтому совпадение держит тест."""
    from jedicoder import state

    assert set(content.MAGISTR_EVENTS) == set(state.EVENT_TYPES) - set(state.SILENT_EVENTS)
    assert set(state.SILENT_EVENTS) == {"linked", "scroll_issued"}
    assert len(content.MAGISTR_EVENTS) == 9


def test_remark_variants_parsed_per_paragraph(tmp_path):
    """Варианты — абзацы тела, по одному на пустую строку между ними.
    Запятая внутри варианта остаётся на месте: ради этого варианты и лежат
    в теле, а не в inline-списке фронтматтера (долг №12 режет список по
    запятой до снятия кавычек)."""
    write(tmp_path, "magistr/quest_completed.md", REMARK_OK)
    items = content.load_remarks(tmp_path)
    assert len(items) == 1
    item = items[0]
    assert item.event == "quest_completed"
    assert item.variants == (
        "Зачёт. Такую проверку я, помню, проходил с третьего раза.",
        "Первую зелёную проверку я никому не показал. Зря: было чем.",
        "После зачёта я всегда бежал дальше, не глядя.",
    )


def test_remark_wrapped_variant_rejected(tmp_path):
    """Вариант, перенесённый на вторую строку, — не два варианта и не один
    длинный: загрузчик не угадывает, а отказывается. Иначе привычный
    перенос по 80 колонок, которым набран весь остальной контент, молча дал
    бы падавану половину фразы."""
    wrapped = REMARK_OK.replace(
        "Первую зелёную проверку я никому не показал. Зря: было чем.",
        "Первую зелёную проверку я никому не показал.\nЗря: было чем.",
    )
    write(tmp_path, "magistr/quest_completed.md", wrapped)
    with pytest.raises(content.ContentError, match="вариант №2.*строк"):
        content.load_remarks(tmp_path)


def test_remark_for_linked_event_rejected(tmp_path):
    """linked — единственное событие очереди без реплики, и файл на него —
    ошибка схемы, а не лишний файл: сцена такого события не знает."""
    write(
        tmp_path,
        "magistr/linked.md",
        REMARK_OK.replace("event: quest_completed", "event: linked"),
    )
    with pytest.raises(content.ContentError, match="event 'linked'"):
        content.load_remarks(tmp_path)


def test_remark_without_event_rejected(tmp_path):
    """event — единственное обязательное поле: без него реплику некуда
    отнести. Больше во фронтматтере ничего не требуется — заметка о том,
    когда реплика звучит, живёт строкой-комментарием."""
    write(
        tmp_path, "magistr/quest_completed.md",
        REMARK_OK.replace("event: quest_completed\n", ""),
    )
    with pytest.raises(content.ContentError, match="event"):
        content.load_remarks(tmp_path)


def test_remarks_by_event_keyed_like_the_event_queue(content_root):
    """Реплики отдаются по типу события — тем же словом, что кладёт в
    очередь движок: читатель события не листает список."""
    by_event = content.remarks_by_event(content_root)
    assert set(by_event) == set(content.MAGISTR_EVENTS)
    assert by_event["quest_failed"].event == "quest_failed"
    assert len(by_event["quest_failed"].variants) >= 3


def test_remark_directory_is_required(tmp_path):
    """Папки реплик нет — ошибка, а не пустой список: Голокрон без реплик
    молчит, и молчание поставки должно быть видно линтеру, а не падавану."""
    with pytest.raises(content.ContentError, match="нет папки"):
        content.load_remarks(tmp_path)


def test_loads_real_remarks(content_root):
    """Поставка: файл на каждое из девяти событий, не меньше трёх вариантов,
    каждый — одна строка. Дубль правил линтера намеренный, как у терминов:
    линтер защищает CI, тест — от того, что правило линтера кто-то снимет."""
    items = content.load_remarks(content_root)
    assert sorted(item.event for item in items) == sorted(content.MAGISTR_EVENTS)
    for item in items:
        assert item.event == item.path.stem, item.path.name
        assert len(item.variants) >= 3, item.path.name
        assert len(set(item.variants)) == len(item.variants), item.path.name
        for text in item.variants:
            assert "\n" not in text, item.path.name


# Признаки первого лица. Правило голоса из спеки героя — «одна строка, от
# первого лица, про свою ошибку» — линтер прочитать не умеет, и тест не
# притворяется, что умеет: он декларативный и ловит только самый громкий
# сбой — реплику-открытку («Поздравляю, так держать»), в которой Магистра
# нет вовсе. Голос проверяется чтением автора, а не этим списком.
FIRST_PERSON = re.compile(
    r"(?<!\w)(я|мне|меня|мной|мною|мо[йяёие]|мо(?:его|ей|их|им|ему|ём|ею|ими))(?!\w)",
    re.IGNORECASE,
)


def test_real_remarks_speak_in_first_person(content_root):
    """В каждой реплике есть местоимение первого лица."""
    silent = [
        "{}: {}".format(item.path.name, text)
        for item in content.load_remarks(content_root)
        for text in item.variants
        if not FIRST_PERSON.search(text)
    ]
    assert silent == [], "реплики без первого лица:\n" + "\n".join(silent)


# --- Инструкции артефактов: раздел, который человек уносит из игры. ------
#
# Файл на артефакт, имя файла — имя артефакта. Текст пишется для человека и
# его коллег, а не для модели: слов игры в нём нет вовсе, и работает он на
# машине, где игра не установлена. Загрузчик проверяет схему; состав
# сверяет с реестром движка линтер, а текст стережёт автор.

INSTRUCTION_OK = (
    "---\n"
    "artifact: plan\n"
    "title: Как спланировать работу до кода\n"
    "summary: Четыре вопроса, после которых у работы есть граница.\n"
    "---\n"
    "## Что это\n"
    "\n"
    "Четыре вопроса до первой строки кода.\n"
)


def test_instruction_fields_parsed(tmp_path):
    """Схема плоская: имя артефакта, заголовок и строка для оглавления.

    `summary` — не украшение: оглавление Свитка собирается из этих строк, и
    без поля его пришлось бы сочинять на месте, то есть выдумывать текст,
    которого автор не писал.
    """
    write(tmp_path, "scroll/plan.md", INSTRUCTION_OK)
    items = content.load_instructions(tmp_path)
    assert len(items) == 1
    item = items[0]
    assert item.artifact == "plan"
    assert item.title == "Как спланировать работу до кода"
    assert item.summary == "Четыре вопроса, после которых у работы есть граница."
    assert item.body.startswith("## Что это")
    assert item.path.name == "plan.md"


@pytest.mark.parametrize("line", (
    "artifact: plan\n", "title: Как спланировать работу до кода\n",
    "summary: Четыре вопроса, после которых у работы есть граница.\n",
))
def test_instruction_without_required_field_rejected(tmp_path, line):
    write(tmp_path, "scroll/plan.md", INSTRUCTION_OK.replace(line, ""))
    with pytest.raises(content.ContentError, match="обязательных полей"):
        content.load_instructions(tmp_path)


def test_instruction_with_unknown_field_rejected(tmp_path):
    """Лишний ключ во фронтматтере — ошибка, и это не педантизм.

    Значение здесь обязано быть одной физической строкой: свёрнутых
    скаляров парсер не умеет (и не должен). Перенос с отступом он ловит
    сам, а вот перенос БЕЗ отступа, где во второй строке есть двоеточие,
    он молча разбирает как новый ключ — и `summary` доезжает обрезанным.
    Оглавление Свитка при этом собирается без единой жалобы. У инструкции
    необязательных полей нет вовсе, поэтому неизвестный ключ ловится
    строго — единственная форма, в которой этот обрыв виден.
    """
    wrapped = INSTRUCTION_OK.replace(
        "summary: Четыре вопроса, после которых у работы есть граница.\n",
        "summary: Четыре вопроса, после которых\nу работы есть граница: и проверка.\n",
    )
    write(tmp_path, "scroll/plan.md", wrapped)
    with pytest.raises(content.ContentError, match="неизвестные поля"):
        content.load_instructions(tmp_path)


def test_instruction_frontmatter_comment_allowed(tmp_path):
    """Строка-комментарий полем не считается: парсер её пропускает, и
    заметка автору остаётся возможной — как у реплик Магистра."""
    noted = INSTRUCTION_OK.replace(
        "artifact: plan\n", "artifact: plan\n# Заметка автору.\n",
    )
    write(tmp_path, "scroll/plan.md", noted)
    assert content.load_instructions(tmp_path)[0].artifact == "plan"


def test_instruction_with_empty_body_rejected(tmp_path):
    """Пустая инструкция хуже отсутствующей: состав сойдётся, а человек
    получит заголовок без текста."""
    head, _, _ = INSTRUCTION_OK.partition("## Что это")
    write(tmp_path, "scroll/plan.md", head)
    with pytest.raises(content.ContentError, match="пустое тело"):
        content.load_instructions(tmp_path)


def test_instruction_directory_is_required(tmp_path):
    """Папки нет — ошибка, а не пустой список: раздел входит в поставку, и
    его пропажу обязан увидеть линтер, а не человек с пустой папкой в
    проекте."""
    with pytest.raises(content.ContentError, match="нет папки"):
        content.load_instructions(tmp_path)


def test_loader_does_not_police_artifact_names(tmp_path):
    """Загрузчик не знает списка имён артефактов — и не должен.

    Копия реестра здесь была бы вторым списком имён: он разошёлся бы с
    `ranks.ALL_ARTIFACTS` молча. Состав сверяет линтер, который реестр и так
    импортирует. Загрузчику остаётся схема.
    """
    write(
        tmp_path, "scroll/vydumka.md",
        INSTRUCTION_OK.replace("artifact: plan", "artifact: vydumka"),
    )
    assert content.load_instructions(tmp_path)[0].artifact == "vydumka"


def test_instructions_by_artifact_keyed_by_name(content_root):
    """Инструкции отдаются по имени артефакта: читатель, собирающий Свиток,
    берёт нужную ключом, а не листает список."""
    from jedicoder import ranks

    by_artifact = content.instructions_by_artifact(content_root)
    assert set(by_artifact) == set(ranks.ALL_ARTIFACTS)
    assert by_artifact["goal"].artifact == "goal"


def test_real_instructions_match_the_artifact_registry(content_root):
    """Поставка: файл на каждый артефакт реестра, лишних нет.

    Дубль правила линтера намеренный, как у реплик Магистра: линтер
    защищает CI, тест — само правило от того, что его снимут.
    """
    from jedicoder import ranks

    items = content.load_instructions(content_root)
    assert sorted(item.artifact for item in items) == sorted(ranks.ALL_ARTIFACTS)
    for item in items:
        assert item.artifact == item.path.stem, item.path.name
        assert item.title, item.path.name
        assert item.summary, item.path.name


# Разделы, из которых состоит инструкция. Требование «самодостаточна» —
# это они: что это, когда применять, как делать, чего не делать. Проверка
# структурная, а не вкусовая: она не читает текст, а следит, что человеку
# не досталась инструкция без раздела «когда применять» — то есть без
# ответа на вопрос, ради которого он её и открыл.
INSTRUCTION_SECTIONS = (
    "## Что это",
    "## Когда применять",
    "## Как делать",
    "## Чего не делать",
)


def test_real_instructions_carry_all_four_sections(content_root):
    """Заголовок сверяется строкой целиком, а не подстрокой: иначе «## Что
    это такое» сошло бы за «## Что это», и раздел считался бы на месте при
    любом продолжении заголовка."""
    missing = []
    for item in content.load_instructions(content_root):
        headings = set(
            line.strip() for line in item.body.split("\n")
            if line.startswith("## ")
        )
        missing += [
            "{}: нет раздела «{}»".format(item.path.name, section)
            for section in INSTRUCTION_SECTIONS
            if section not in headings
        ]
    assert missing == [], "\n".join(missing)


# --- Дорожная карта: карта на трек, не текст модели -------------------------
#
# Три шага «довести продукт до людей» модель не пишет вовсе: они зависят от
# трека и от того, есть ли у продукта адрес, а не от того, как прошло
# прохождение. Значит это контент, а не разбор, — и тогда карта одинаково
# хороша у всех и проверяема составом, а не вкусом.

ROADMAP_OK = (
    "---\n"
    "track: craftsman\n"
    "title: Три шага, чтобы продуктом начали пользоваться\n"
    "lead: Адреса у продукта пока нет — с этого и начинается первый шаг.\n"
    "lead_url: Продукт уже живёт по адресу {url} — дело за людьми.\n"
    "---\n"
    "## Шаг 1. Три живых человека\n"
    "\n"
    "Не рассылка, а три имени.\n"
)


def test_roadmap_fields_parsed(tmp_path):
    write(tmp_path, "roadmap/craftsman.md", ROADMAP_OK)
    items = content.load_roadmaps(tmp_path)
    assert len(items) == 1
    card = items[0]
    assert card.track == "craftsman"
    assert card.title == "Три шага, чтобы продуктом начали пользоваться"
    assert card.lead.startswith("Адреса у продукта пока нет")
    assert "{url}" in card.lead_url
    assert card.body.startswith("## Шаг 1.")


@pytest.mark.parametrize("line", (
    "track: craftsman\n",
    "title: Три шага, чтобы продуктом начали пользоваться\n",
    "lead: Адреса у продукта пока нет — с этого и начинается первый шаг.\n",
    "lead_url: Продукт уже живёт по адресу {url} — дело за людьми.\n",
))
def test_roadmap_without_required_field_rejected(tmp_path, line):
    write(tmp_path, "roadmap/craftsman.md", ROADMAP_OK.replace(line, ""))
    with pytest.raises(content.ContentError, match="обязательных полей"):
        content.load_roadmaps(tmp_path)


def test_roadmap_with_unknown_field_rejected(tmp_path):
    """Схема закрытая по той же причине, что у инструкции: значение каждого
    поля — одна физическая строка, и перенос без отступа доезжает обрезанным,
    а вводная строка карты собирается из половины фразы молча."""
    extra = ROADMAP_OK.replace("track: craftsman\n", "track: craftsman\nnote: да\n")
    write(tmp_path, "roadmap/craftsman.md", extra)
    with pytest.raises(content.ContentError, match="неизвестные поля"):
        content.load_roadmaps(tmp_path)


def test_roadmap_with_unknown_track_rejected(tmp_path):
    """Карта на трек, которого в игре нет, не досталась бы никому: движок
    ищет её по слагу трека из сохранения."""
    write(
        tmp_path, "roadmap/vydumka.md",
        ROADMAP_OK.replace("track: craftsman\n", "track: vydumka\n"),
    )
    with pytest.raises(content.ContentError, match="track"):
        content.load_roadmaps(tmp_path)


def test_roadmaps_indexed_by_track(tmp_path):
    write(tmp_path, "roadmap/craftsman.md", ROADMAP_OK)
    write(
        tmp_path, "roadmap/any.md",
        ROADMAP_OK.replace("track: craftsman\n", "track: any\n"),
    )
    cards = content.roadmaps_by_track(tmp_path)
    assert set(cards) == {"craftsman", content.TRACK_ANY}
    assert cards["craftsman"].path.name == "craftsman.md"


def test_roadmap_tracks_agree_with_the_registry():
    """Копия слагов в схеме сверяется с реестром движка тестом, а не
    импортом: content.py — нижний слой, acts.py берёт из него."""
    from jedicoder import acts

    assert set(content.ROADMAP_TRACKS) == set(acts.TRACKS) | {content.TRACK_ANY}


def test_real_roadmaps_cover_both_tracks_and_the_unchosen_one(content_root):
    cards = content.roadmaps_by_track(content_root)
    assert set(cards) == {"craftsman", "founder", content.TRACK_ANY}


# Шагов в карте ровно три — это состав, а не вкус, и потому проверяется, как
# четыре раздела инструкции выше. Карта на два шага прошла бы и загрузчик, и
# линтер молча, а заметил бы её человек, у которого третьего шага уже нет.
ROADMAP_STEPS = 3


def test_real_roadmaps_carry_exactly_three_steps(content_root):
    """Заголовок сверяется началом строки «## Шаг », а не словом «шаг»:
    иначе «## Шаги» и упоминание шага в тексте считались бы разделом."""
    wrong = []
    for card in content.load_roadmaps(content_root):
        steps = [
            line for line in card.body.split("\n") if line.startswith("## Шаг ")
        ]
        if len(steps) != ROADMAP_STEPS:
            wrong.append("{}: шагов {}".format(card.path.name, len(steps)))
    assert wrong == [], "\n".join(wrong)


# --- Задания квестов: одна фраза простыми словами (#83, пункт 6) -----------

ACT_TASKS = 'quest_tasks: ["Назови папку своего проекта.", "Выбери одно дело на вечер."]\n'


def _act_with(tmp_path, line=""):
    """Загрузить акт-образец, вставив строку во фронтматтер."""
    write(
        tmp_path, "acts/act1-poisk-boli.md",
        ACT_OK.replace("quest_branches:", line + "quest_branches:"),
    )
    return content.load_acts(tmp_path)[0]


def test_act_quest_tasks_parsed(tmp_path):
    act = _act_with(tmp_path, ACT_TASKS)
    assert act.quest_tasks == (
        "Назови папку своего проекта.", "Выбери одно дело на вечер.",
    )


def test_act_without_quest_tasks_loads_with_none(tmp_path):
    """Выключенные акты перестраиваются — заданий у них пока нет."""
    act = _act_with(tmp_path)
    assert act.quest_tasks == ()


def test_act_quest_tasks_count_must_match_quests(tmp_path):
    """Запятая в задании рвёт список (долг №12) — ошибка называет причину."""
    line = 'quest_tasks: ["Назови папку, где проект.", "Выбери одно дело."]\n'
    with pytest.raises(content.ContentError, match="запят"):
        _act_with(tmp_path, line)


def test_act_quest_task_is_one_short_phrase(tmp_path):
    long_task = " ".join(["слово"] * 16) + "."
    line = 'quest_tasks: ["{}", "Выбери одно дело."]\n'.format(long_task)
    with pytest.raises(content.ContentError, match="quest_tasks"):
        _act_with(tmp_path, line)
    line = 'quest_tasks: ["Назови папку. Потом вторую.", "Выбери одно дело."]\n'
    with pytest.raises(content.ContentError, match="одна фраза"):
        _act_with(tmp_path, line)


def test_playable_acts_carry_a_task_for_every_quest(content_root):
    for item in content.load_acts(content_root):
        if not item.muted:
            assert len(item.quest_tasks) == len(item.quests), item.slug

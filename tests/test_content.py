import pytest

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


ACT1_TERMS = (
    "mvp", "ca", "icp", "pmf", "tam-sam-som", "vertical-slice",
    "cac", "ltv", "arpu", "channel",
    # Семь терминов из языка самого Акта 1 (LOOP-03). Десятка выше —
    # лексика Основателя, которую контракт Ремесленника запрещает
    # произносить; на треке Ремесленника словарь молчал именно поэтому.
    # `terminal` из этого списка ушёл планом 01.4-03: слово переехало в Акт 0,
    # где человек и открывает терминал в первый раз. Доступность для него не
    # изменилась — хук лута фильтрует по `t.act <= current_act`, — поэтому из
    # бюджета Ремесленника оно НЕ выпало; см. CRAFTSMAN_ACT1_POOL.
    "pain", "crystal", "hutt-filter", "estimate",
    "tool", "api",
)

# Шесть слов, уехавших из Акта 1 планом 01.2-05: у Ремесленника было
# пятнадцать доступных терминов при бюджете девять. Ни одно не удалено —
# переехали по смыслу, и что они на месте, стережёт
# test_language.test_relocated_terms_stay_relocated.
RELOCATED_FROM_ACT1 = ("stack", "script", "git-history", "index", "pipeline",
                       "interface")


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


def test_acts_1_to_3_terms_declare_quest(content_root):
    """Каждый термин Актов 1–3 называет квест, и квест — из реестра.

    Дубль правила 2 линтера, и дубль намеренный: линтер защищает CI, а тест
    защищает от того, что правило линтера кто-то отключит или обойдёт. Оба
    сразу молча не пропадут.

    Акты 4 и 5 сюда не входят: охват аудита языка ограничен Актами 1–3
    решением автора (D-08). Про их плотность зелёный суит не говорит ничего.
    """
    from jedicoder import acts, content

    bad = []
    for item in content.load_terms(content_root):
        if item.act not in (1, 2, 3):
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
ACT4_TERMS_WITH_QUEST = ()


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

    marked = sorted(
        t.term for t in content.load_terms(content_root)
        if t.act in (4, 5) and t.quest and t.term not in ACT4_TERMS_WITH_QUEST
    )
    assert marked == [], "Акты 4–5 размечены, а охват аудита их не включает: {}".format(
        marked
    )


def test_act4_terms_present(content_root):
    """Девять терминов, а не десять: `permission-mode` уехал в Акт 0 (TOOL-05)."""
    from jedicoder import content
    terms = {t.term for t in content.load_terms(content_root) if t.act == 4}
    assert terms == {
        "push-pull", "remote", "ssh-key", "sudo", "root",
        "firewall", "fail2ban", "rotation", "2fa",
    }


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
# Сегодня их три. Два — новая матчасть по D-07: режим разрешений и одна
# ручка на две темы, модель с мощностью рассуждения. Третье, `terminal`, —
# не новое слово: оно существовало в пуле Акта 1 и по фильтру хука лута
# (`t.act <= current_act`) было доступно добычей с первой же сессии. Переезд
# сменил объявленную точку введения на ту, где человек действительно
# впервые открывает терминал, и снял два маркера `lint:novelty-ok` из узлов
# Акта 0 — подавление правила ради слова, которое встречается именно здесь.
ACT0_TERMS = ("model-effort", "permission-mode", "terminal")


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
CLAUDE_CODE_TERMS = {
    "context-window": (3, "01-launch"),
    "clear": (3, "02-feature"),
    "usage": (3, "02-feature"),
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


def test_act5_terms_present(content_root):
    from jedicoder import content
    terms = {t.term for t in content.load_terms(content_root) if t.act == 5}
    assert terms == {
        "deploy", "nginx", "reverse-proxy", "dns", "a-record",
        "ssl", "healthcheck", "ci-cd", "goal", "virality",
    }


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
    "artifact: brainstorm\n"
    "quests: [01-idea, 02-one-evening]\n"
    'quest_titles: ["Идея", "Фильтр Хатта"]\n'
    "---\n"
    "Ты пришёл строить. Начнём с того, что строить пока нечего.\n"
)


def test_loads_real_acts(content_root):
    items = content.load_acts(content_root)
    assert [item.act for item in items] == [1, 2, 3, 4, 5]
    first = items[0]
    assert first.slug == "act1-poisk-boli"
    assert first.rank == "seeker"
    assert first.artifact == "brainstorm"
    assert first.quests[0] == "01-idea"
    assert len(first.quest_titles) == len(first.quests)
    assert first.body


def test_act_quests_match_registry(content_root):
    """Единственный источник правды для списка квестов книги — фронтматтер,
    но разъехаться с реестром движка он не имеет права."""
    from jedicoder import acts

    for item in content.load_acts(content_root):
        expected = tuple(quest_id for quest_id, _, _ in acts.QUESTS_BY_ACT[item.act])
        assert item.quests == expected, item.path.name


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

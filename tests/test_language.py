"""Языковые инварианты фазы 01.2 — чем игра говорить не должна.

Это дом для всех проверок языка, а не только для замены мифологии:
планы 01.2-03, 01.2-04 и 01.2-05 дописывают сюда, а не заводят свой файл.

Проверяется **видимый русский текст**: катсцены, термины, правила, рецепты,
скиллы и команды. Идентификаторы под этот запрет не попадают и попасть не
могут — они набраны латиницей (`hutt-filter`, `crystal`), а ищем мы
кириллицу. Обратная сторона того же — `test_identifiers_unchanged`: слова
уходят, ключи остаются, иначе правка превращается в миграцию состояния у
всех, кто уже играет (решение D-06).

Регистр складывается через `re.IGNORECASE`. Запрет `grep -i` из CLAUDE.md
касается shell и awk, где складывание кириллицы зависит от локали падавана;
в Python оно идёт по Unicode-таблицам и от локали не зависит — тем же
приёмом уже пользуется `lexicon_loot._alias_pattern`.

## Граница прибора — читать до того, как поверить зелёному суиту

Эти тесты меряют **наши файлы**: состав словаря, поля фронтматтера, тексты
скиллов и команд. Плотность речи модели ими не проверяется и проверена быть
не может — у квеста может не быть ни строчки статического текста, а восемь
новых слов за квест рождаются в импровизации.

Отсюда буквально: зелёный суит здесь **не означает**, что падаван встретил
не больше трёх новых слов за квест. Он означает ровно одно — что столько мы
пообещали и что обещание не откатится молча. Сколько слов падаван услышал
на самом деле, показывает только **живой прогон** (план 01.2-07).
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "plugin"
# Полка прежнего Акта 1 «Поиск боли» (спека #75): слова и квесты лежат там
# теми же именами и читаются тем же загрузчиком.
SHELF_CONTENT = ROOT / "shelf" / "act1-poisk-boli" / "content"
SHELF_QUESTS = ROOT / "shelf" / "act1-poisk-boli" / "quests" / "act1-poisk-boli"

# Полка наружу не едет (`scripts/build_release.py`, SHIP_TOP): в выгрузке её
# нет, и тест о ней честно пропускается, а не падает.
needs_shelf = pytest.mark.skipif(
    not SHELF_CONTENT.is_dir(),
    reason="полки прежнего Акта 1 нет в этом дереве — она живёт только в рабочем репозитории",
)
sys.path.insert(0, str(PLUGIN_ROOT / "hooks"))
sys.path.insert(0, str(ROOT / "scripts"))

import lexicon_loot  # noqa: E402
import lint_content  # noqa: E402

from jedicoder import acts, content, ranks  # noqa: E402

CONTENT_ROOT = PLUGIN_ROOT / "content" / "ru"

# Три корня видимого текста. `plugin/quests/` сюда не входит намеренно:
# исход квеста решает exit-код, и языковое правило не вправе его менять.
VISIBLE_ROOTS = (
    CONTENT_ROOT,
    PLUGIN_ROOT / "skills",
    PLUGIN_ROOT / "commands",
)

# Всё, что читает модель помимо контракта. Разговорное правило сюда попадать
# не должно: оно живёт в behavior.md ровно один раз, а скиллы ссылаются
# строкой-указателем. Шесть разошедшихся копий — тот же класс дефекта, что
# породил долг №11.
RESTATEMENT_ROOTS = (
    PLUGIN_ROOT / "skills",
    PLUGIN_ROOT / "commands",
)

# Маркеры правил, которым запрещено расползаться. Первые два — из фазы
# 01.2-03; «900» ловится подстрокой намеренно: копия числа опасна в любой
# обёртке. Третий — от правила 10: скиллу положено на него ссылаться, а не
# пересказывать своими словами, иначе через полгода в игре будет два разных
# запрета выдумывать числа.
RESTATEMENT_MARKERS = (
    "900", "не больше трёх новых слов", "ни округлением, ни пересчётом",
)

# Правил в контракте девять. Число прибито намеренно: на «правило 7
# контракта» ссылаются по номеру шесть файлов, и вставка правила в середину
# сделает все шесть молча ложными. Новое правило приписывается в конец, и
# тогда это число правится осознанно — вместе с проверкой указателей.
CONTRACT_RULES = 10

RULE_LINE = re.compile(r"^(\d+)\. \*\*")


def visible_markdown():
    files = []
    for root in VISIBLE_ROOTS:
        files.extend(sorted(root.rglob("*.md")))
    return files


def occurrences(word):
    """Строки видимого текста, где встретилось слово в любом регистре."""
    pattern = re.compile(re.escape(word), re.IGNORECASE)
    hits = []
    for path in visible_markdown():
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            if pattern.search(line):
                hits.append("{}:{}: {}".format(
                    path.relative_to(ROOT), number, line.strip()
                ))
    return hits


@pytest.mark.parametrize("root", VISIBLE_ROOTS, ids=lambda p: p.name)
def test_every_visible_root_has_files(root):
    """Страж самого стража: опечатка в пути дала бы пустой список файлов и
    зелёные запреты ниже, не проверив ни одной строки."""
    assert list(root.rglob("*.md")), "нет .md в {}".format(root)


def test_franchise_word_hutt_absent():
    """«Хатт» прозвучал в живом прогоне за шесть часов до врезки, где
    объясняется, — то есть не объяснён вовсе. Нарицательное из франшизы,
    вещью не является: по тесту D-04 заменяется, а не поясняется."""
    assert occurrences("хатт") == []


def test_franchise_word_crystal_absent():
    """«Кристалл» стоял первым словом Акта 1 и требовал знания, что такое
    кайбер-кристалл. Произвольная метафора, а не имя вещи: заменяется
    целиком, вместе с телом термина, а не только заголовком (D-15)."""
    assert occurrences("кристалл") == []


@needs_shelf
def test_identifiers_unchanged():
    """Граница частичной отмены D-06 — что осталось неизменным и почему.

    D-06 запрещал трогать идентификаторы: правка ключа превращается в миграцию
    состояния «у всех, кто уже играет». Довод проверен фактом 2026-08-06 и не
    подтвердился — установка одна, маркетплейс это локальная папка, гейт и
    оплата не построены; «все, кто уже играет» — один человек с резервной
    копией на диске. Запрет снят **ровно с одного идентификатора** — квеста 02
    Акта 1, — потому что холодный прогон замерил, как франшиза возвращается в
    речь игры через слаг, который печатает сама игра.

    Всё остальное под отмену не попадает и прибито здесь: слаги терминов
    падавану не печатаются, утечь через речь не могут, а их переименование
    стоило бы миграции без единой выгоды.
    """
    # С 2026-10-08 прежний Акт 1 лежит на полке (спека #75) — и слова, и
    # квесты. Идентификаторы прибиты там же: вернутся они теми же именами.
    terms = {item.term for item in content.load_terms(SHELF_CONTENT)}
    assert "hutt-filter" in terms
    assert "crystal" in terms

    quest_ids = sorted(path.name for path in SHELF_QUESTS.iterdir())
    assert "02-one-evening" in quest_ids
    assert "02-hutt-filter" not in quest_ids

    quest_dir = SHELF_QUESTS / "02-one-evening"
    assert quest_dir.is_dir()


# Список короткий и буквальный: имена собственные из франшизы, а не общие
# слова. Латиница — потому что идентификаторы набраны латиницей;
# кириллические вхождения в видимом тексте ловят тесты выше.
#
# Чего в списке намеренно НЕТ и почему: `jedi` — имя продукта (Jedicoder),
# `padawan` и `sith` — собственный словарь игры (ранг и агент-ревьюер),
# каждое объяснено падавану при первом употреблении. Запрет — на отсылки,
# которые игра не объясняет и объяснять не собирается.
FRANCHISE_IN_IDENTIFIERS = (
    "hutt", "yoda", "kyber", "wookie", "vader", "saber", "ewok",
    "tatooine", "skywalker", "droid",
)


def test_no_quest_identifier_carries_franchise():
    """Ни один из 38 идентификаторов не несёт имени из франшизы.

    Тест структурный, а не про один квест: дефект вернётся при заведении
    следующего, если проверять только исправленное место. Механизм замерен
    холодным прогоном 2026-08-06 — игра печатает идентификатор, падаван
    набирает его же, модель читает слаг, узнаёт отсылку и восстанавливает
    выпиленную метафору из собственных знаний. Контент при этом был чист.
    """
    guilty = []
    for act_num, entries in acts.QUESTS_BY_ACT.items():
        for quest_id, _kind, _track in entries:
            for word in FRANCHISE_IN_IDENTIFIERS:
                if re.search(word, quest_id, re.IGNORECASE):
                    guilty.append((act_num, quest_id, word))
    assert guilty == [], (
        "идентификатор с именем из франшизы: игра его печатает, "
        "и модель достроит по нему отсылку: {}".format(guilty)
    )


def test_quest_scripts_carry_no_franchise():
    """Bash-квестов не видит ни один тест видимого текста — а слово выжило
    именно там.

    `occurrences()` сканирует только `.md` по трём корням: `plugin/quests/`
    в VISIBLE_ROOTS не входит намеренно, исход квеста решает exit-код. Из-за
    этого единственное вхождение «Хатт» во всей поставке — комментарий в
    `check.sh` — не поймал никто, при 777 зелёных тестах.
    """
    guilty = []
    for script in sorted((PLUGIN_ROOT / "quests").rglob("*.sh")):
        text = script.read_text(encoding="utf-8")
        if re.search("хатт|кристалл", text, re.IGNORECASE):
            guilty.append(str(script.relative_to(PLUGIN_ROOT)))
        for word in FRANCHISE_IN_IDENTIFIERS:
            if re.search(word, text, re.IGNORECASE):
                guilty.append("{}: {}".format(script.relative_to(PLUGIN_ROOT),
                                              word))
    assert guilty == [], "франшиза в скриптах квестов: {}".format(guilty)


def test_retired_quest_identifier_is_gone_from_the_game():
    """Прежний идентификатор не живёт нигде, кроме этого стража.

    До #78 он оставался в карте миграции 2→3: переименовать ключ, не назвав
    его, нельзя. Сохранения прежней игры больше не мигрируют — уходят в
    архив целиком, — и карта ушла вместе с миграцией. Последнее вхождение —
    здесь, как имя того, что ищется.
    """
    allowed = {
        ROOT / "tests" / "test_language.py",
    }
    guilty = []
    for root in (PLUGIN_ROOT, ROOT / "tests", ROOT / "scripts"):
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path in allowed:
                continue
            if path.suffix not in (".py", ".sh", ".md", ".json", ".txt"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "02-hutt-filter" in text:
                guilty.append(str(path.relative_to(ROOT)))
    assert guilty == [], "прежний идентификатор жив: {}".format(guilty)


def test_retired_franchise_aliases_do_not_unlock_terms():
    """Слово ушло вместе с алиасом: фраза старого прогона больше не открывает
    карточку. Иначе карточка объясняла бы отсылку, а не приём (D-05)."""
    terms = content.load_terms(CONTENT_ROOT)
    state = {"current_act": 5, "lexicon_unlocked": [], "xp": 0}
    found = [
        item.term
        for item in lexicon_loot.find_terms("Квест 02 — «Фильтр Хатта».", terms, state)
    ]
    assert "hutt-filter" not in found


def test_idea_is_not_an_alias_of_crystal():
    """«Идея» термину не выдана намеренно. Квест называется `01-idea`, и
    слово стоит почти в каждой реплике — начиная с самой катсцены («Идея
    есть у каждого, и стоит она ноль»). Карточка выпала бы до того, как
    падавану есть что к ней привязать."""
    terms = content.load_terms(CONTENT_ROOT)
    state = {"current_act": 5, "lexicon_unlocked": [], "xp": 0}
    found = [
        item.term
        for item in lexicon_loot.find_terms("Идея есть у каждого.", terms, state)
    ]
    assert "crystal" not in found


def test_language_rules_stated_once():
    """Разговорное правило сформулировано в одном месте, а не в семи.

    Скиллы грузят контракт первым шагом, поэтому копия там ничего не
    добавляет — она только заводит место, которое разойдётся с оригиналом.
    Тест держит границу за нас: ни числа 900, ни формулировки бюджета вне
    behavior.md быть не может.
    """
    offenders = []
    for root in RESTATEMENT_ROOTS:
        for path in sorted(root.rglob("*.md")):
            text = path.read_text(encoding="utf-8")
            for marker in RESTATEMENT_MARKERS:
                if marker in text:
                    offenders.append("{}: копия «{}»".format(
                        path.relative_to(ROOT), marker
                    ))
    assert offenders == [], "правило пересказано вне контракта: {}".format(offenders)


def test_rule_seven_still_magistr():
    """Нумерация правил контракта несущая — она не имеет права сдвинуться.

    На «правило 7 контракта» ссылаются по номеру шесть файлов. Сдвиг не
    ломает ни одного теста и не роняет ни одной команды: указатели просто
    начинают показывать не туда, и находится это живым прогоном.
    """
    text = (CONTENT_ROOT / "behavior.md").read_text(encoding="utf-8")
    numbers = [
        int(match.group(1))
        for match in (RULE_LINE.match(line) for line in text.splitlines())
        if match
    ]
    assert numbers == list(range(1, CONTRACT_RULES + 1)), (
        "правила контракта пронумерованы не подряд: {}".format(numbers)
    )

    seventh = [line for line in text.splitlines() if line.startswith("7. ")]
    assert len(seventh) == 1, "правило 7 не найдено или задвоено: {}".format(seventh)
    assert "Возражение Магистра" in seventh[0], (
        "правило 7 больше не «Возражение Магистра»: {}".format(seventh[0])
    )


def test_pointers_to_rule_seven_survive():
    """Обратная сторона предыдущего теста: сами указатели на месте.

    Неподвижная нумерация бессмысленна, если указатели тихо исчезли; их
    шесть, и это число — часть инварианта, а не совпадение.
    """
    pointing = [
        path.relative_to(ROOT)
        for path in sorted((PLUGIN_ROOT / "skills").rglob("SKILL.md"))
        if "правило 7 контракта" in path.read_text(encoding="utf-8")
    ]
    assert len(pointing) == 6, "указателей на правило 7 стало {}: {}".format(
        len(pointing), pointing
    )


@needs_shelf
def test_hutt_filter_aliases_stay_clear_of_vertical_slice():
    """Ловушка, которую линтер не поймает: `_alias_collisions` видит только
    совпадение строк, а два термина об одном приёме — совпадение смысла.
    У `vertical-slice` занято поле «отрезать/отрезано/срез»; «правило одного
    вечера» называет правило, а не срез, и в это поле не лезет."""
    by_term = {item.term: item for item in content.load_terms(SHELF_CONTENT)}
    ours = {alias.lower() for alias in by_term["hutt-filter"].aliases}
    theirs = {alias.lower() for alias in by_term["vertical-slice"].aliases}
    assert ours & theirs == set()
    assert not [alias for alias in ours if "рез" in alias or "отреза" in alias]


# --- Мифология, оставленная в игре тестом D-04: глоссы на месте. ---

# Слово → (файл, чем в нём опознаётся глосса). Файлы разные потому, что
# «первое употребление» у каждого слова своё: Книгу падаван видит из
# CLI, Магистра — из хука, штрафы — с первого экрана, ранг — в пересказе модели.
# «Голокрон» с 2026-09-10 — имя десктопного приложения, как в словаре сайта
# (CONTEXT.md); браузерная книга зовётся Книгой, и глосса теперь у неё.
GLOSSES = (
    ("Книга", "plugin/lib/jedicoder/cli.py", "страницами в браузере"),
    ("Магистр", "plugin/hooks/_shared.py", "наставник"),
    ("Штрафы", "plugin/lib/jedicoder/cli.py", "счёт промахов; очков не отнимают"),
    ("падаван", "plugin/commands/start.md", "значит «ученик»"),
)


@pytest.mark.parametrize("word,relpath,marker", GLOSSES)
def test_retained_myth_words_are_glossed(word, relpath, marker):
    """Глосса стоит там, где падаван встречает слово впервые.

    **Тест декларативный, и это надо читать буквально:** он проверяет, что
    пояснение поставлено, а не что оно понятно. Понятность проверяется
    живым прогоном (план 01.2-07) — механического прибора для неё нет и
    быть не может.

    Четыре слова оставлены в игре тестом D-04 (имена вещей и ролей,
    читаются без посвящения во франшизу) под обязательство объяснять их
    при первом употреблении. Это обязательство здесь и пришито.
    """
    text = (ROOT / relpath).read_text(encoding="utf-8")
    assert marker in text, "глосса слова «{}» пропала из {}".format(word, relpath)


def test_myth_words_are_not_renamed():
    """Голокрон и Магистр не переименованы (D-07), а «Тёмная сторона» — да.

    ADR-0014 заменил три имени обычными словами: Тёмная сторона → штрафы,
    артефакт → приём, Свиток → памятка. Хук на пятом очке говорит «штрафы»,
    а ключ состояния не трогается никогда (D-06): переименование означало бы
    миграцию ~/.jedicoder/state.json у всех, кто уже играет.
    """
    cli_text = (ROOT / "plugin/lib/jedicoder/cli.py").read_text(encoding="utf-8")
    shared = (ROOT / "plugin/hooks/_shared.py").read_text(encoding="utf-8")
    assert "Голокрон" in cli_text
    assert "Магистр" in shared
    assert "Тёмная сторона" not in shared
    assert "штраф" in shared.lower()
    state_text = (ROOT / "plugin/lib/jedicoder/state.py").read_text(encoding="utf-8")
    assert "dark_side" in state_text


# --- Бюджет новизны: замер плана 01.2-05, прибитый к файлам. ---

# Сколько слов Акта 1 доступно новичку за первый вечер. В акте пять квестов
# и потолок новизны три слова на квест — пятнадцать было бы законно, но
# вечер один, и читатель впервые открыл Claude Code. Девять — столько, во
# что он упирается руками: папка и режим, одна работа, запрос и чужая
# программа, три слова сохранения и откат. Поимённо — ACT1_TERMS в
# tests/test_content.py.
#
# Прежний счёт был по треку: рыночные слова Основателя из пула Ремесленника
# вычитались. Трека в акте больше нет, и вычитать нечего: прежние слова
# лежат на полке вместе с актом.
#
# Считается по `act <= 1`, а не `act == 1`, и это не придирка: ровно так
# фильтрует хук лута, а значит ровно столько слов человек и увидит. План
# 01.4-03 увёл `terminal` в Акт 0 — из ВЫДАЧИ слово при этом никуда не
# делось. Разгружает пул только переезд в поздний акт; переезд в ранний не
# разгружает ничего.
#
# Было девять: `env` вернулся в Акт 2 (#87) — паролей в первый вечер нет.
ACT1_POOL = 8

# Плюс Акт 0, который выдаётся с первой же сессии по тому же фильтру:
# терминал, ручка «модель + мощность рассуждения» и лимит запросов. Режим
# разрешений с 2026-10-08 считается в Акте 1 — его называет первый квест.
#
# Число стоит отдельным слагаемым, а не растворено в сумме, ровно затем,
# чтобы четвёртое слово Акта 0 уронило этот тест. Бюджет первого вечера
# линтер не меряет (D-03), и это второй страж на него — не по именам, как
# ACT0_TERMS в tests/test_content.py, а по тому, сколько карточек человек
# реально увидит.
ACT0_POOL = 3

# Куда уехали шесть лишних. Переезд именной, по смыслу, а не по счёту:
# «стек» и «скрипт» — язык квеста «Стек по рецепту», «история git» —
# первого коммита, «индекс» — защиты .env, «пайплайн» — одноимённого
# квеста, «интерфейс» — второй фичи.
RELOCATED_TERMS = {
    "stack": 2,
    "script": 2,
    "git-history": 2,
    "index": 2,
    "pipeline": 2,
    "interface": 3,
}


def test_act1_pool_size():
    """Новичок в Акте 1 видит ровно одиннадцать слов — восемь своих и три Акта 0.

    Настоящий рычаг плотности — состав пула акта, а не поле `quest`:
    `lexicon_loot.find_terms` фильтрует по `t.act <= current_act` и про
    квесты не знает. Поэтому единственный способ разгрузить Акт 1 — увести
    слово в поздний акт, и этот тест сторожит результат.

    Условие здесь то же самое, `act <= 1`: слово, уехавшее в Акт 0, из
    выдачи не исчезает, и мерить его отсутствие значило бы отчитаться о
    разгрузке, которой не было.

    Превышение читается однозначно: кто-то вернул слово в Акт 1 или завёл
    новое, не заметив, что бюджет первого вечера уже выбран.
    """
    pool = sorted(
        item.term for item in content.load_terms(CONTENT_ROOT) if item.act <= 1
    )
    budget = ACT1_POOL + ACT0_POOL
    assert len(pool) == budget, (
        "у новичка к концу Акта 1 {} слов при бюджете {} ({} + {} за "
        "Акт 0) — {}".format(
            len(pool), budget, ACT1_POOL, ACT0_POOL, ", ".join(pool)
        )
    )


@pytest.mark.parametrize("slug,expected_act", sorted(RELOCATED_TERMS.items()))
def test_relocated_terms_stay_relocated(slug, expected_act):
    """Шесть переехавших слов остаются в своих актах.

    Сообщение называет слово и акт намеренно: тест читает человек, который
    через полгода не помнит эту фазу, и «2 != 1» ему не скажет ничего.

    Заодно это проверка, что слово вообще на месте: содержание не режется
    ради бюджета (D-10), лишнее разносится по соседним квестам.
    """
    by_term = {item.term: item for item in content.load_terms(CONTENT_ROOT)}
    assert slug in by_term, "термин «{}» пропал из словаря — его переносили, а не удаляли".format(slug)
    actual = by_term[slug].act
    assert actual == expected_act, (
        "«{}» должен жить в Акте {}, а стоит акт {} — переезд 01.2-05 откатили".format(
            slug, expected_act, actual
        )
    )


def test_no_quest_exceeds_novelty_budget():
    """Ни за одним квестом Актов 1–3 не закреплено больше трёх слов.

    Дубль правила 2 линтера, и дубль намеренный: линтер защищает CI, тест
    защищает само правило от отключения. Число берётся импортом
    `lint_content.NOVELTY_MAX` — третьей копии константы в проекте быть не
    должно, иначе потолок разъедется молча.
    """
    buckets = {}
    for item in content.load_terms(CONTENT_ROOT):
        if not item.quest:
            continue
        buckets.setdefault((item.act, item.quest), []).append(item.term)
    over = [
        "акт {}, квест {}: {} слов — {}".format(
            key[0], key[1], len(names), ", ".join(sorted(names))
        )
        for key, names in sorted(buckets.items())
        if len(names) > lint_content.NOVELTY_MAX
    ]
    assert over == [], "потолок {}:\n{}".format(
        lint_content.NOVELTY_MAX, "\n".join(over)
    )


# --- Матчасть Claude Code: команды и механизмы кладём, числа — нет. ---

# Тексты, которые учат работе с самим Claude Code. Только они: остальной
# контент про инструмент не рассказывает, и запрещать ему цифры незачем.
LORE_FILES = (
    "plugin/content/ru/lexicon/context-window.md",
    "plugin/content/ru/lexicon/clear.md",
    "plugin/content/ru/lexicon/usage.md",
    "plugin/content/ru/lexicon/permission-mode.md",
    "plugin/content/ru/lexicon/model-effort.md",
    "plugin/skills/act3-pervaya-krov/SKILL.md",
    "plugin/skills/act4-shchit/SKILL.md",
)

# Акт 0 — про сам Claude Code целиком, от первой строки до последней, и
# летучая величина там опаснее всего: это первый текст, который человек
# читает, и проверить его он не может ничем.
#
# Собираются файлы по каталогу, а не перечисляются поимённо: планы 01.4-02 и
# 01.4-03 добавят узлы, и именной список молча отстал бы — запрет остался бы
# зелёным, не прочитав новых файлов. Ровно этот класс дефекта здесь уже
# сторожит `test_every_visible_root_has_files`.
ONBOARDING_DIR = CONTENT_ROOT / "onboarding"


def onboarding_lore_files():
    """Файлы Акта 0 как относительные пути — в том же виде, что LORE_FILES."""
    return [
        str(path.relative_to(ROOT))
        for path in sorted(ONBOARDING_DIR.glob("*.md"))
    ]

# Каждый образец — факт, который ресерч фазы 01.2 сверил с официальной
# документацией и отметил как **летучий**: он верен сегодня и протухнет
# молча.
#
# - размер окна: 200 000 токенов уже не универсален — у части моделей 1M,
#   и список этих моделей меняется каждый релиз;
# - номер версии: метка режима «Manual» требует 2.1.200 и новее, до 2.1.203
#   строка статуса в нём не показывала ничего;
# - имена моделей: расширенное окно привязано к конкретным моделям, состав
#   набора живёт один релиз;
# - `docs.claude.com`: адрес теперь редиректит на `code.claude.com`, то
#   есть ссылка в контенте устареет вслед за ним.
#
# Запрет не про аккуратность, а про то, чему учится падаван: занятость
# окна он смотрит командой `/context`, расход — `/usage`, текущий режим —
# в строке статуса. Цифра в тексте заменила бы навык проверять на память,
# которая устареет раньше, чем он дойдёт до Акта 4.
VOLATILE_PATTERNS = (
    ("размер контекстного окна", r"200[\s ]?000|\b200K\b|\b1M\b"),
    ("номер версии Claude Code", r"\b\d+\.\d+\.\d+\b"),
    ("имя модели", r"\bOpus\b|\bSonnet\b|\bHaiku\b|\bFable\b"),
    ("устаревший адрес документации", r"docs\.claude\.com"),
)


def test_no_volatile_numbers_in_lore():
    """Во врезках и терминах про Claude Code нет летучих чисел и имён.

    Тест защищает не от опечатки, а от доброго намерения: следующий, кто
    захочет «уточнить» врезку конкретной цифрой окна или именем модели,
    получит красный тест и эту причину вместе с ним.

    Первым делом проверяется, что файлы вообще на месте: опечатка в пути
    дала бы зелёный запрет, не прочитавший ни строки, — ровно тот дефект,
    от которого выше стоит `test_every_visible_root_has_files`.
    """
    onboarding = onboarding_lore_files()
    # Сбор по каталогу обязан что-то собрать. Пустой сбор дал бы зелёный
    # запрет, не прочитавший ни строки Акта 0 — тот же дефект, что опечатка
    # в имени файла, только тише.
    assert onboarding, "нет файлов в {} — запрет мерил бы пустоту".format(
        ONBOARDING_DIR
    )
    assert len(onboarding) == len(list(ONBOARDING_DIR.glob("*.md")))

    offenders = []
    for relpath in list(LORE_FILES) + onboarding:
        path = ROOT / relpath
        assert path.is_file(), "нет файла {} — запрет мерил бы пустоту".format(relpath)
        text = path.read_text(encoding="utf-8")
        for label, pattern in VOLATILE_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                offenders.append("{}:{}: {} — «{}»".format(
                    relpath, line, label, match.group(0)
                ))
    assert offenders == [], (
        "летучий факт в контенте про Claude Code:\n{}\n"
        "Учить падавана командой (`/context`, `/usage`), а не цифрой.".format(
            "\n".join(offenders)
        )
    )


# --- Инструкции артефактов: язык рабочий, слов игры нет вовсе. ----------
#
# Инструкцию человек уносит из игры к себе в проект и открывает её через
# месяц, когда игры на машине уже нет, — и при коллеге или заказчике.
# Слово игры в таком тексте не «неудачный стиль», а поломка: читатель, не
# игравший, спотыкается о него и не знает, что оно значит. Ровно то же
# самое случилось бы, будь инструкция копией скилла: скилл написан для
# модели и говорит словами игры законно.
SCROLL_DIR = CONTENT_ROOT / "scroll"

# Слово → на что оно похоже в тексте. Регулярка, а не подстрока: «акт»
# подстрокой ловит «факт», «контакт» и «характер», а запрет, срабатывающий
# на «фактически», сняли бы первым же коммитом.
#
# Первые семь — из тикета. Остальные добавлены здесь: это тот же словарь
# игры, и он ломает чтение ровно так же. Список именно поэтому и разделён
# — чтобы было видно, что чьё, и чтобы правка одной половины не выглядела
# правкой другой.
GAME_WORDS = (
    ("падаван", r"падаван\w*"),
    ("акт", r"акт(?:а|е|у|ом|ы|ов|ам|ами|ах)?"),
    ("квест", r"квест\w*"),
    # Окончания перечислены, а не `\w*`: иначе запрет ловил бы «магистраль».
    ("Магистр", r"магистр(?:а|е|у|ом|ы|ов|ам|ами|ах)?"),
    ("Тёмная сторона", r"т[её]мн\w*\s+сторон\w*"),
    ("ранг", r"ранг(?:а|е|у|ом|и|ов|ам|ами|ах)?"),
    ("XP", r"xp"),
    # Добавлено сверх тикета: тот же словарь игры.
    ("артефакт", r"артефакт\w*"),
    ("Свиток", r"свит(?:ок|ка|ке|ку|ком|ки|ков)"),
    ("Кодекс", r"кодекс\w*"),
    ("Голокрон", r"голокрон\w*"),
    ("джедай", r"джедай\w*"),
    ("ситх", r"ситх\w*"),
    ("Jedicoder", r"jedicoder|джедайкодер\w*"),
    # Отсылка к самой установке. Инструкция обязана работать на машине, где
    # игры нет, — это её главное свойство, и «запусти /plan» ломает его
    # ровно так же, как слово игры: читателю некуда это набрать.
    ("плагин", r"плагин\w*"),
    ("скилл", r"скилл\w*"),
)


def slash_command_words():
    """Слэш-команды артефактов — по реестру движка, а не списком.

    Имена берутся из `ranks.ALL_ARTIFACTS`: заведут седьмой артефакт — его
    команда попадёт под запрет сама. Косая черта перед именем обязательна,
    поэтому адрес вида `https://узел/plan` под правило не попадает.
    """
    return [
        ("/{}".format(name), r"/{}".format(re.escape(name)))
        for name in ranks.ALL_ARTIFACTS
    ]


GAME_WORDS = GAME_WORDS + tuple(slash_command_words())


def test_scroll_section_has_files():
    """Страж самого стража: пустой раздел дал бы зелёный запрет, не
    прочитавший ни строки."""
    assert list(SCROLL_DIR.glob("*.md")), "нет .md в {}".format(SCROLL_DIR)


def game_word_offenders(directory, pattern):
    """Где в разделе встретилось слово игры: «файл:строка: слово»."""
    rule = re.compile(r"(?<!\w)(?:{})(?!\w)".format(pattern), re.IGNORECASE)
    offenders = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        for match in rule.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append("{}:{}: «{}»".format(
                path.relative_to(ROOT), line, match.group(0)
            ))
    return offenders


@pytest.mark.parametrize("word,pattern", GAME_WORDS, ids=[w for w, _ in GAME_WORDS])
def test_instructions_carry_no_game_words(word, pattern):
    offenders = game_word_offenders(SCROLL_DIR, pattern)
    assert offenders == [], (
        "слово игры «{}» в инструкции, которую человек откроет без игры и "
        "при коллеге:\n{}".format(word, "\n".join(offenders))
    )


# --- Дорожная карта: тот же запрет, и по той же причине ---------------------
#
# Карта ложится в тот же `docs/jedicoder/` и переживает удаление игры так же,
# как инструкция. Читает её, в отличие от инструкции, сам человек, а не его
# коллега, — но открывает он её через месяц, когда «войти в акт» уже ничего
# не значит, а «выложить продукт» значит по-прежнему.
ROADMAP_DIR = CONTENT_ROOT / "roadmap"


def test_roadmap_section_has_files():
    """Страж самого стража: пустой раздел дал бы зелёный запрет, не
    прочитавший ни строки."""
    assert list(ROADMAP_DIR.glob("*.md")), "нет .md в {}".format(ROADMAP_DIR)


@pytest.mark.parametrize("word,pattern", GAME_WORDS, ids=[w for w, _ in GAME_WORDS])
def test_roadmaps_carry_no_game_words(word, pattern):
    offenders = game_word_offenders(ROADMAP_DIR, pattern)
    assert offenders == [], (
        "слово игры «{}» в дорожной карте, которую человек откроет, когда "
        "игры на машине уже нет:\n{}".format(word, "\n".join(offenders))
    )

"""Памятка (в коде — scroll): что падаван уносит из игры к себе в проект.

Игра до сих пор ничего после себя не оставляла: артефакты живут ровно
столько, сколько установлен плагин. Свиток — папка `docs/jedicoder/` в
проекте падавана, которая переживает удаление игры: внутри обычный текст,
и читается он на машине, где ни плагина, ни Claude Code нет вовсе.

Модуль разложен на два слоя, и граница между ними — не стиль, а условие
ADR-0009 в репозитории сайта.

`build` — чистая функция: факты Разбора и контент на входе, список пар
«имя файла → содержимое» на выходе. Диска, часов и сохранения внутри нет.
Дату сборки она тоже не узнаёт сама — её передают параметром, иначе одна и
та же выдача давала бы разные файлы в разные минуты.

`write` — единственное место, которое трогает файловую систему, и всё
обещание Свитка держится здесь: **изменённый человеком файл не
переписывается никогда**. Отпечаток снимается при выдаче и хранится в
сохранении; без него «изменён» не отличить от «просто старый».

Чего здесь нет и быть не должно: вызовов из хуков и проверок. Пишет одна
команда игры — по просьбе человека (ADR-0009), и запрет «проверка не
мутирует проект падавана» этим не задет — у команды его никогда и не было.
"""
import hashlib
from pathlib import Path

from . import acts, ranks
from . import state as st

# Папка Свитка внутри проекта падавана. Корень чужого проекта не трогаем:
# там живут его конфиги, и файл рядом с package.json читается как мусор.
RELATIVE_DIR = ("docs", "jedicoder")

INDEX_NAME = "README.md"
DEBRIEF_NAME = "razbor.md"
ROADMAP_NAME = "roadmap.md"
RANK_CARD_NAME = "rank.md"

# Шов под тексты, которых сборка не пишет сама: разбор пишет Магистр (он
# приходит командой `debrief write` и ждёт выдачи в сохранении), дорожная
# карта приезжает из контент-ядра, карточку ранга собирает финал, страницу о
# пройденном — `path_page` по слову вызывающего. Ключи названы
# здесь один раз, чтобы тот, кто их заполняет, сверялся с перечнем, а не с
# памятью.
# Пустая строка и пробелы считаются молчанием: Свиток выдаётся и без них
# (ADR-0010), обратное невозможно — разбор без фактов это гадание.
PART_DEBRIEF = "debrief"
PART_ROADMAP = "roadmap"
PART_RANK_CARD = "rank_card"
PART_PHRASES = "phrases"
#: Страница «что пройдено и что впереди» (#114). Ложится в тот же файл, что
#: дорожная карта, и приходит вместо неё, пока акт карты выключен: карта
#: говорит о продукте и его адресе, а новичка об этом ещё никто не спрашивал.
#: Какая из двух страниц нужна, решает вызывающий; пришли обе — ляжет эта.
PART_PATH = "path"
PARTS = (PART_DEBRIEF, PART_ROADMAP, PART_RANK_CARD, PART_PHRASES, PART_PATH)

#: Подписи страницы `roadmap.md` в оглавлении — по тому, что в ней лежит.
ROADMAP_NOTE = "три шага, чтобы довести продукт до людей"
PATH_TITLE = "Что пройдено и что впереди"
PATH_NOTE = PATH_TITLE[0].lower() + PATH_TITLE[1:]
#: Раздел «Впереди» в конце игры: ни акта впереди, ни ненаписанного.
PATH_ALL_DONE = "Все акты пройдены: это конец игры."

#: Страница готовых фраз (#104). Лежит рядом с инструкциями и написана так
#: же, без слов игры: её открывают, когда игры на машине уже нет.
PHRASES_NAME = "frazy.md"
PHRASES_TITLE = "Готовые фразы для Claude"
PHRASES_SUMMARY = "Что сказать, когда не знаешь, как попросить."
PHRASES_LEAD = (
    "Говорить можно своими словами: важен смысл, а не точная фраза.",
)
PHRASES_HEAD = ("| Когда | Что сказать |", "|---|---|")

# Заголовок, под который ложится текст Магистра. Вынесен константой,
# потому что на него смотрят два тикета сразу: тот, кто пишет текст, и
# тот, кто проверяет, что текст встал ПОД фактами, а не вместо них.
DEBRIEF_HEADING = "## Что это значит"

#: Что считает строка «С первой попытки» (#114). Квест, который закрывает
#: рассказ, проверки не имеет, и в счёт попыток с первого раза не идёт: при
#: десяти закрытых квестах строка честно говорит «8 из 8», и без подписи число
#: читалось как ошибка счёта. Первую половину печатает и первый экран.
FIRST_TRY_COUNTS = "в счёте только квесты с проверкой"
FIRST_TRY_LEAVES_OUT = (
    "Квесты без проверки, которые закрывает рассказ, в этот счёт не входят"
)

# Гласные — для склонения имени ранга, см. genitive.
_VOWELS = "аеёиоуыэюя"

# Чем было каждое очко Тёмной стороны. До Свитка эти четыре строки жили
# комментариями у констант state.DARK_*: типов было четыре, а слов для
# человека не было ни одного — счётчик показывал число и молчал о том, что
# за ним. Здесь они впервые названы, и названы у печатающего, а не в
# state.py: там лежат ключи, тексты живут у того, кто печатает (тем же
# правилом, что NOTICE_* и NOTICES).
#
# Тип, которого здесь нет, печатается ключом как есть: очко, заработанное
# на плагине новее сохранения, лучше назвать латиницей, чем потерять.
DARK_SIDE_TITLES = {
    st.DARK_ENV_STAGED: ".env отправлен в индекс git",
    st.DARK_RM_OUTSIDE_PROJECT: "rm -rf мимо папки проекта",
    st.DARK_ROOT_LOGIN: "вход на сервер под root",
    st.DARK_VAGUE_PROMPT: "заказ по настроению вместо задачи",
}

# Сколько раз пробовать имя «рядом», прежде чем сдаться. Первый файл дня —
# `razbor-2026-09-07.md`, дальше `-2`, `-3`. Двадцать выдач за один день,
# каждая поверх правки руками, — это уже не Свиток, а что-то другое;
# упереться в предел честнее, чем плодить файлы без конца.
BESIDE_LIMIT = 20

ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_UNCHANGED = "unchanged"
ACTION_KEPT = "kept"
ACTION_FAILED = "failed"


def directory_for(project_path):
    """Папка Свитка в проекте падавана. Одно место, где собран этот путь."""
    return Path(project_path).joinpath(*RELATIVE_DIR)


def genitive(title):
    """Имя ранга в родительном падеже: Искатель → Искателя.

    Склонение, а не второй словарь имён. Списка «Юнлинга, Искателя,
    Падавана…» тут нет намеренно: имена рангов живут в одном месте
    (ranks.RANK_TITLES), и таблица падежей рядом с ними разошлась бы молча —
    переименовали ранг, а Свиток зовёт по-старому.

    Правило школьное и на всех шести именах верное: мягкий знак и «й»
    уходят в «я», прочий согласный получает «а». Имя на гласную не
    склоняется вовсе — вернём как есть: «Памятка Йода» криво, «Памятка Йодаа»
    неверно, и первое честнее.
    """
    if not title:
        return title
    last = title[-1].lower()
    if last in _VOWELS:
        return title
    if last in ("ь", "й"):
        return title[:-1] + "я"
    return title + "а"


def scroll_title(facts):
    """«Памятка Искателя» — имя носит ранг владельца (language.md: Свиток → памятка)."""
    facts = facts if isinstance(facts, dict) else {}
    rank = facts.get("rank")
    name = facts.get("rank_title") or ranks.RANK_TITLES.get(rank) or rank
    return "Памятка {}".format(genitive(name)) if name else "Памятка"


def debrief_page(facts, acts=(), today=None):
    """Страница фактов — ровно то, что ляжет в `razbor.md` над текстом.

    Одна функция на двух читателей. Файл собирает `build`, а модель видит
    вывод этой же функции в терминале до того, как напишет разбор: она
    пишет поверх готового текста, а не поверх словаря, из которого числа
    пришлось бы произносить заново. Второй способ напечатать те же числа
    стал бы вторым источником правды и разошёлся бы с файлом молча —
    ровно то, что запрещает ADR-0010.

    Текста Магистра здесь нет намеренно: он пишется ПОВЕРХ этой страницы,
    и подсовывать ему его же вчерашние слова значило бы звать его спорить
    с самим собой.
    """
    facts = facts if isinstance(facts, dict) else {}
    return _debrief_page(facts, _quest_titles(acts), None, today)


def fingerprint(text):
    """Отпечаток текста — тем же способом, что отпечатки выданных файлов.

    Нужен ровно для одного вопроса: поверх ЭТИХ ли фактов писал Магистр.
    Страница фактов меняется от каждого закрытого квеста и от каждого
    прожитого дня, поэтому «текст написан вчера» и «текст отвечает другим
    числам» — один и тот же вопрос, и отвечает на него сравнение отпечатков,
    а не дата.
    """
    return _digest(text.encode("utf-8"))


def phrases_page(rows):
    """Страница готовых фраз: заголовок, вводная строка и таблица.

    `rows` — готовые строки таблицы из контента, уже отобранные вызывающим:
    какие акты человек начал, знает сохранение, а не сборка. Строк нет —
    пустая строка, и страницы в памятке не будет.
    """
    rows = [row for row in rows or () if isinstance(row, str) and row.strip()]
    if not rows:
        return ""
    lines = ["# {}".format(PHRASES_TITLE), ""]
    lines += list(PHRASES_LEAD) + [""]
    lines += list(PHRASES_HEAD) + rows
    return "\n".join(lines) + "\n"


def roadmap_page(card, url=None):
    """Дорожная карта: заголовок, вводная строка и три шага автора.

    Из контента здесь всё, кроме одного — какая из двух вводных строк
    прозвучит. Адрес продукта известен, значит первый шаг уже не про
    «выложи хоть куда-нибудь», и карта обязана начинаться иначе; выбор
    делает движок, потому что адрес лежит в сохранении, а не в тексте.

    Подстановка — `replace`, а не `format`: `{url}` стоит внутри авторской
    строки, и любая другая фигурная скобка, которую автор в неё поставит,
    уронила бы `format` посреди выдачи Свитка. `replace` не умеет падать.
    """
    lead = card.lead_url.replace("{url}", url) if url else card.lead
    return "# {}\n\n{}\n\n{}".format(
        card.title, lead, card.body.strip("\n") + "\n"
    )


def path_page(facts, not_written=""):
    """Страница «что пройдено и что впереди» — из фактов и реестра актов.

    Пройденное — закрытые акты с рангом, который дал каждый. Впереди — акты,
    в которые можно войти, и строка `not_written` о тех, которых ещё нет: её
    слова приходят от вызывающего, теми же, какими игра говорит об этом на
    первом экране. Имён выключенных актов и сроков страница не называет.
    """
    facts = facts if isinstance(facts, dict) else {}
    # Только играемые: закрытый акт, который теперь выключен (сохранение
    # правили руками), назвал бы по имени то, что «ещё не написано».
    playable = ranks.playable_acts()
    done = [number for number in facts.get("acts_completed") or []
            if number in playable]
    lines = ["# {}".format(PATH_TITLE), "", "## Пройдено", ""]
    for number in done:
        entry = ranks.ACTS[number]
        rank = ranks.RANK_TITLES.get(entry["rank"], entry["rank"])
        lines.append("- Акт {} «{}» — ранг {}.".format(
            number, entry["title"], rank
        ))
    if not done:
        lines.append("Пока ни одного акта.")
    lines += ["", "## Впереди", ""]
    open_acts = [number for number in playable if number not in done]
    for number in open_acts:
        lines.append("- Акт {} «{}» — ещё не пройден.".format(
            number, ranks.ACTS[number]["title"]
        ))
    if open_acts:
        lines.append("")
    if not_written:
        lines += ["{}. Сроков игра не называет.".format(not_written), ""]
    if not open_acts and not not_written:
        # Конец игры: впереди ни акта, ни ненаписанного. Пустой раздел
        # читался бы как недописанная страница.
        lines += [PATH_ALL_DONE, ""]
    lines += [
        "Проект от игры не зависит: продолжай его с Claude тем, что уже умеешь.",
    ]
    return "\n".join(lines) + "\n"


def build(facts, instructions, acts=(), parts=None, today=None):
    """Свиток списком пар «имя файла → содержимое». Чистая функция.

    `facts` — ответ debrief.facts: числа считает только он, здесь их
    произносят, а не пересчитывают.

    `instructions` — словарь «имя артефакта → content.Instruction», уже
    отфильтрованный вызывающим. Отбор именно там: Свиток отдаёт то, что
    открыто, а знает об открытом сохранение, а не сборка. Порядок задаёт
    реестр движка (ranks.ALL_ARTIFACTS), незнакомые имена встают в хвост по
    алфавиту — потерять инструкцию хуже, чем перечислить не на своём месте.

    `acts` — объекты content.Act, нужны ровно для одного: назвать квесты
    по-человечески. Не передали — в Разборе останутся идентификаторы, и
    Свиток всё равно соберётся.

    `parts` — шов под тексты, которых движок не пишет: см. PARTS.

    `today` — дата сборки строкой «ГГГГ-ММ-ДД». Часов внутри нет намеренно:
    дата попадает в текст, и функция, читающая их сама, не была бы чистой.
    Не передали — строки с датой просто не будет.
    """
    facts = facts if isinstance(facts, dict) else {}
    parts = _parts(parts)
    instructions = instructions or {}
    titles = _quest_titles(acts)

    pages = []
    listed = []
    for artifact in _ordered(instructions):
        item = instructions[artifact]
        pages.append(("{}.md".format(artifact), _instruction_page(item)))
        listed.append((
            "{}.md".format(artifact), item.title, item.summary,
        ))

    if parts.get(PART_PHRASES):
        pages.append((PHRASES_NAME, parts[PART_PHRASES]))
        listed.append((PHRASES_NAME, PHRASES_TITLE, PHRASES_SUMMARY))

    personal = [(
        DEBRIEF_NAME,
        _debrief_page(facts, titles, parts.get(PART_DEBRIEF), today),
        "факты твоего прохождения, посчитанные по сохранению",
    )]
    if parts.get(PART_PATH):
        personal.append((ROADMAP_NAME, parts[PART_PATH], PATH_NOTE))
    elif parts.get(PART_ROADMAP):
        personal.append((ROADMAP_NAME, parts[PART_ROADMAP], ROADMAP_NOTE))
    if parts.get(PART_RANK_CARD):
        personal.append((
            RANK_CARD_NAME, parts[PART_RANK_CARD], "твой трофей",
        ))

    index = _index_page(
        facts, listed, [(name, note) for name, _, note in personal], today
    )
    return (
        [(INDEX_NAME, index)]
        + pages
        + [(name, text) for name, text, _ in personal]
    )


def write(directory, files, prints, today):
    """Положить собранное в папку, не тронув ни одной чужой правки.

    `prints` — отпечатки прошлой выдачи, «имя файла → {sha256, date}».
    Отвечают они ровно на один вопрос: лежит ли сейчас на диске в точности
    то, что мы сами туда положили. Совпал — файл наш, переписать его нечем
    навредить. Не совпал или отпечатка нет вовсе — значит файл человека,
    и свежий уходит в имя рядом.

    Возвращает пару (отчёт, отпечатки). Отчёт — список записей
    {"name", "action", "written"}: name — каноническое имя файла Свитка,
    written — куда содержимое легло на самом деле, action — одно из
    ACTION_*. Печатает отчёт вызывающий: этот модуль в терминал не говорит.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    prints = dict(prints or {})
    report = []
    for name, text in files:
        report.append(_place(directory, name, text, prints, today))
    return report, prints


def _place(directory, name, text, prints, today):
    payload = text.encode("utf-8")
    digest = _digest(payload)
    for number, candidate in enumerate(_names(name, today)):
        outcome = _claim(directory, candidate, payload, digest, prints, today)
        if outcome is None:
            # Имя занято чужим содержимым — пробуем следующее.
            continue
        if number == 0:
            return {"name": name, "action": outcome[0], "written": outcome[1]}
        # Канонический файл остался нетронутым. Свежий лёг рядом — или не
        # лёг вовсе, и тогда написанное человеком всё равно цело: сказать
        # надо про это, а не про одну неудачу записи.
        return {
            "name": name, "action": ACTION_KEPT,
            "written": None if outcome[0] == ACTION_FAILED else outcome[1],
        }
    return {"name": name, "action": ACTION_KEPT, "written": None}


def _claim(directory, candidate, payload, digest, prints, today):
    """Занять имя под свежее содержимое. Ответ — пара (действие, имя).

    None вместо пары значит одно: имя занято не нами, и трогать его нельзя.
    Три причины сойтись на этом — ссылка, чужое содержимое, нечитаемый файл;
    исход у всех трёх один, поэтому и ответ один.

    Занять удалось — исходов четыре: файла не было (created), файл был наш и
    устарел (updated), файл был наш и совпал байт в байт (unchanged),
    записать не вышло (failed).
    """
    target = directory / candidate
    if target.is_symlink():
        # Ссылка — всегда чужая, даже битая. `exists()` на битой ссылке
        # отвечает False, а `write_bytes` пошёл бы по ней и записал файл
        # вне папки Свитка — то самое «только в docs/jedicoder/», которое
        # обещает ADR-0009. Не наше — не трогаем.
        return None
    if target.exists():
        current = _read(target)
        if current is None:
            # Прочитать не смогли — значит и судить не можем, чьё это.
            # Не уверен — не трогай: то же правило, что у хуков.
            return None
        if _digest(current) == digest:
            # На диске байт в байт то, что мы собрали. Отпечатка могло и не
            # быть (падаван перенёс папку, откатил плагин) — это не повод
            # объявлять файл чужим: терять в нём нечего, он наш дословно.
            prints[candidate] = _print(digest, today)
            return ACTION_UNCHANGED, candidate
        recorded = prints.get(candidate)
        if not isinstance(recorded, dict) or recorded.get("sha256") != _digest(
            current
        ):
            return None
        action = ACTION_UPDATED
    else:
        action = ACTION_CREATED
    try:
        target.write_bytes(payload)
    except OSError:
        return ACTION_FAILED, candidate
    prints[candidate] = _print(digest, today)
    return action, candidate


def _names(name, today):
    """Каноническое имя, затем имена «рядом» — с датой и порядковым."""
    yield name
    stem, dot, suffix = name.rpartition(".")
    if not dot:
        stem, suffix = name, ""
    tail = ".{}".format(suffix) if dot else ""
    # Даты нет (вызов без неё) — имя всё равно должно получиться: файл
    # рядом важнее красивого имени, потерять его нельзя.
    stamp = today or "kopiya"
    yield "{}-{}{}".format(stem, stamp, tail)
    for number in range(2, BESIDE_LIMIT + 1):
        yield "{}-{}-{}{}".format(stem, stamp, number, tail)


def _print(digest, today):
    return {"sha256": digest, "date": today}


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _read(path):
    try:
        return path.read_bytes()
    except OSError:
        return None


def _parts(parts):
    """Шов, приведённый к делу: пустое и не строки — молчание."""
    if not isinstance(parts, dict):
        return {}
    ready = {}
    for key in PARTS:
        value = parts.get(key)
        if isinstance(value, str) and value.strip():
            # Хвостовой перевод строки возвращается: файл без него git
            # показывает падавану как «\\ No newline at end of file», и
            # части шва выглядели бы иначе, чем README и Разбор, которые
            # собирает сам движок.
            ready[key] = value.strip("\n") + "\n"
    return ready


def _ordered(instructions):
    """Порядок инструкций: реестр движка, незнакомое — в хвост."""
    known = [name for name in ranks.ALL_ARTIFACTS if name in instructions]
    tail = sorted(set(instructions) - set(ranks.ALL_ARTIFACTS))
    return known + tail


def _quest_titles(acts):
    """Подписи квестов по паре (акт, идентификатор)."""
    titles = {}
    for act in acts or ():
        try:
            pairs = zip(act.quests, act.quest_titles)
            number = act.act
        except AttributeError:
            # Не объект акта. Подписи — украшение Разбора, а не его смысл:
            # без них останутся идентификаторы, и Свиток всё равно выдастся.
            continue
        for quest_id, title in pairs:
            titles[(number, quest_id)] = title
    return titles


def _instruction_page(item):
    """Страница инструкции: заголовок автора и его же текст.

    Ни строки от Свитка сверху и снизу. Инструкцию человек открывает через
    месяц, когда игры на машине нет, — и при коллеге; слово игры в ней
    ломает ровно то, ради чего она написана, а приписка «из Свитка» — это
    слово игры.
    """
    return "# {}\n\n{}".format(item.title, item.body.strip("\n") + "\n")


def _index_page(facts, instructions, personal, today):
    lines = ["# {}".format(scroll_title(facts)), ""]
    if today:
        lines.append(
            "Собрана {} по твоему прохождению игры Jedicoder.".format(today)
        )
    else:
        lines.append("Собрана по твоему прохождению игры Jedicoder.")
    lines += [
        "",
        "Папка твоя. Игру можно удалить, а файлы останутся: внутри обычный",
        "текст, он открывается где угодно и ничего не требует.",
    ]
    if instructions:
        lines += [
            "",
            "## Инструкции",
            "",
            "Написаны рабочим языком, без слов игры: такую можно открыть при",
            "коллеге и отдать заказчику.",
            "",
        ]
        for name, title, summary in instructions:
            lines.append("- **{}** — {}".format(name, title))
            if summary:
                lines.append("  {}".format(summary))
    lines += ["", "## Про тебя", ""]
    for name, note in personal:
        lines.append("- **{}** — {}.".format(name, note))
    lines += [
        "",
        "## Откуда это берётся",
        "",
        "Памятку кладёт сюда Claude, когда ты его просишь. Сама, без просьбы,",
        "игра в твой проект ничего не пишет.",
        "",
        "Твои правки здесь не пропадут. Игра помнит отпечаток каждого",
        "выданного файла и изменённый не переписывает: свежий ложится рядом,",
        "с датой в имени.",
        "",
    ]
    return "\n".join(lines)


def _debrief_page(facts, titles, magistr, today):
    lines = ["# Разбор", ""]
    if today:
        lines.append(
            "Собрано {}. Ниже только факты: их посчитала игра по твоему".format(
                today
            )
        )
    else:
        lines.append("Ниже только факты: их посчитала игра по твоему")
    lines += [
        "сохранению, и назвать их иначе она не вправе.",
        "",
    ]
    lines += _path_section(facts)
    lines += _quests_section(facts, titles)
    lines += _streak_section(facts)
    lines += _lexicon_section(facts)
    lines += _dark_side_section(facts)
    if magistr:
        lines += [DEBRIEF_HEADING, "", magistr, ""]
    return "\n".join(lines)


def _path_section(facts):
    lines = ["## Путь", ""]
    rank = facts.get("rank")
    title = facts.get("rank_title") or ranks.RANK_TITLES.get(rank) or rank
    # Только имя, как на первом экране: страница ложится Разбором в проект
    # падавана, и слаг в скобках читался бы там как опечатка (#73).
    lines.append("- Ранг: {}".format(title))
    done = facts.get("acts_completed") or []
    # Знаменатель — играбельные акты, как у карточки ранга в cli.py: полный
    # реестр при выключенном Акте 5 давал «4 из 5» в Разборе против
    # «4 из 4» на карточке в той же сессии (живой прогон 2026-09-10).
    lines.append("- Закрыто актов: {} из {}".format(
        len(done), len(ranks.playable_acts())
    ))
    for number in done:
        entry = ranks.ACTS.get(number) or {}
        name = entry.get("title")
        lines.append(
            "  - Акт {}. {}".format(number, name) if name
            else "  - Акт {}".format(number)
        )
    track = facts.get("track")
    if track:
        # Словами, как их слышит падаван в игре: «для себя» / «для людей».
        lines.append("- Продукт: {}".format(acts.TRACK_WORDS.get(track, track)))
    deploy = facts.get("deploy_path")
    if deploy:
        lines.append("- Путь деплоя: {}".format(deploy))
    url = facts.get("product_url")
    if url:
        lines.append("- Продукт: {}".format(url))
    days = facts.get("days_in_path")
    if days is not None:
        lines.append("- Дней в пути: {}".format(days))
    lines.append("")
    return lines


def _quests_section(facts, titles):
    lines = ["## Квесты", ""]
    lines.append("- Закрыто квестов: {}".format(facts.get("quests_closed") or 0))
    lines.append("- Попыток потрачено: {}".format(facts.get("attempts_total") or 0))
    counters = facts.get("first_try") or {}
    if counters.get("attempted"):
        # Две строки, а не одна: фраза длиннее пятнадцати слов (language.md).
        lines.append("- С первой попытки: {} из {} — {}".format(
            counters.get("passed") or 0, counters["attempted"],
            FIRST_TRY_COUNTS,
        ))
        lines.append("  - {}".format(FIRST_TRY_LEAVES_OUT))
    hardest = facts.get("hardest_quest")
    if hardest:
        lines.append("- Тяжелее всего дался «{}» (Акт {}): попыток {}".format(
            _quest_name(hardest, titles), hardest.get("act"),
            hardest.get("attempts"),
        ))
    records = facts.get("quests") or []
    if records:
        lines += [
            "",
            "| Акт | Квест | Попыток | Закрыт |",
            "|---|---|---|---|",
        ]
        for record in records:
            lines.append("| {} | {} | {} | {} |".format(
                record.get("act"), _quest_name(record, titles),
                record.get("attempts") or 0,
                "да" if record.get("closed") else "нет",
            ))
    lines.append("")
    return lines


def _streak_section(facts):
    streak = facts.get("streak") or {}
    return [
        "## Серия сохранений",
        "",
        "- Текущая: {}".format(streak.get("current") or 0),
        "- Лучшая: {}".format(streak.get("best") or 0),
        "",
    ]


def _lexicon_section(facts):
    return [
        "## Словарь и очки",
        "",
        "- Открыто слов: {}".format(facts.get("terms_unlocked") or 0),
        "- Очки: {}".format(facts.get("xp") or 0),
        "",
    ]


def _dark_side_section(facts):
    dark = facts.get("dark_side")
    if not isinstance(dark, dict):
        dark = {}
    lines = ["## Штрафы", ""]
    lines.append("- Очков: {}".format(dark.get("points") or 0))
    if dark.get("days"):
        lines.append("- Дней, когда это случалось: {}".format(dark["days"]))
    by_kind = dark.get("by_kind") or []
    if by_kind:
        lines += [
            "",
            "| Что случилось | Очков | Дней |",
            "|---|---|---|",
        ]
        for row in by_kind:
            kind = row.get("kind")
            lines.append("| {} | {} | {} |".format(
                DARK_SIDE_TITLES.get(kind, kind),
                row.get("points") or 0, row.get("days") or 0,
            ))
    if dark.get("log_incomplete"):
        lines += [
            "",
            "Без подробностей осталось очков: {}. Они заработаны до того, как"
            " игра".format(dark.get("unlogged") or 0),
            "начала вести журнал, и восстановить, чем они были, уже нечем.",
        ]
    lines.append("")
    return lines


def _quest_name(record, titles):
    key = (record.get("act"), record.get("quest"))
    return titles.get(key) or record.get("quest")


"""Проверки Акта 1 на фикстурах.

Гоняются через quests.run_check — тем же путём, каким их запускает CLI.
На каждый квест: проход, провал и граница. Границы здесь не формальность:
промах на единицу в «не меньше трёх» — дефект ровно того сорта, который
178 тестов A1 не поймали.
"""
import pytest
from jedicoder import quests

SLUG = "act1-poisk-boli"

IDEA_OK = """# Идея

## Боль
Каждый вечер вручную свожу расходы семьи из трёх банковских приложений
в одну таблицу, и это занимает почти час времени.

## Для кого
Я и жена, плюс двое друзей просили сделать им такое же решение.

## Почему сейчас
Два банка открыли публичное API в этом году, раньше это было невозможно.
"""

IDEA_STUBS = """# Идея

## Боль
TODO

## Для кого
TODO

## Почему сейчас
TODO
"""

IDEA_PROSE = """# Идея

Каждый вечер свожу расходы семьи из трёх банков в таблицу. Нужно мне и жене,
друзья тоже просили. Банки только в этом году открыли API, раньше было нельзя.
"""

SLICE_OK = """# Срез

## Войдёт
Одна кнопка «загрузить выписку» и таблица с суммами по категориям за месяц.

## Отрезано
Графики, бюджеты, напоминания, мобильное приложение, вход через госуслуги.

## Оценка
Один вечер, часа три работы.
"""

WHO_OK = "Я сам. Критерий простой: открываю каждый день вечером после ужина.\n"
MARKET_OK = "TAM 50000 семей, SAM 5000 в моём городе, SOM 500 за первый год. " * 3
COMPETITORS_OK = """# Конкуренты

- Дзен-мани — https://zenmoney.example
- Кошелёк — https://koshelek.example
- Таблица в Google — https://sheets.example
"""
ICP_OK = " ".join(["Семья с двумя детьми и тремя картами разных банков."] * 12)
UNIT_OK = """# Юнитка

## CAC
Привести одного пользователя — примерно 300 рублей на рекламу.

## LTV
Пользователь приносит 1200 рублей за полтора года подписки.

## Стоимость токенов
Разбор одной выписки — 4 рубля на API, плюс 500 рублей в месяц за VPS.
"""
CHANNEL_OK = """# Канал

## Канал
Телеграм-канал про семейные финансы

## Почему он
Там уже сидит моя аудитория, и я в нём пишу третий год подряд.
"""


def run(quests_root, project, quest_id, files):
    """Файлы кладутся в research/ — именно там их ищут проверки."""
    proj = project(files={"research/" + name: text for name, text in files.items()})
    return quests.run_check(quests_root, SLUG, quest_id, proj)


# --- 01-idea ---

def test_idea_passes(quests_root, project):
    result = run(quests_root, project, "01-idea", {"IDEA.md": IDEA_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_idea_fails_without_file(quests_root, project):
    result = run(quests_root, project, "01-idea", {})
    assert result.ok is False
    assert result.exit_code == 1


def test_idea_fails_on_stub_sections(quests_root, project):
    """Три заголовка на месте, под каждым TODO — самый частый способ соврать."""
    result = run(quests_root, project, "01-idea", {"IDEA.md": IDEA_STUBS})
    assert result.ok is False
    failed = {c["id"] for c in quests.failed_checks(result)}
    assert {"idea_pain", "idea_who", "idea_why_now"} <= failed


def test_idea_fails_on_good_prose_without_headings(quests_root, project):
    """Осознанный ложный провал: формат диктует скилл, подсказка его называет."""
    result = run(quests_root, project, "01-idea", {"IDEA.md": IDEA_PROSE})
    assert result.ok is False


def test_idea_missing_one_section(quests_root, project):
    text = IDEA_OK.split("## Почему сейчас")[0]
    result = run(quests_root, project, "01-idea", {"IDEA.md": text})
    assert result.ok is False
    failed = {c["id"] for c in quests.failed_checks(result)}
    assert failed == {"idea_why_now"}


# --- 02-one-evening ---

def test_one_evening_passes(quests_root, project):
    result = run(quests_root, project, "02-one-evening", {"SLICE.md": SLICE_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_one_evening_fails_with_empty_cut_list(quests_root, project):
    """Фильтр, который ничего не отрезал, не сработал."""
    text = SLICE_OK.replace(
        "Графики, бюджеты, напоминания, мобильное приложение, вход через госуслуги.",
        "",
    )
    result = run(quests_root, project, "02-one-evening", {"SLICE.md": text})
    assert result.ok is False
    assert "slice_cut" in {c["id"] for c in quests.failed_checks(result)}


def test_one_evening_fails_without_estimate(quests_root, project):
    text = SLICE_OK.replace("Один вечер, часа три работы.", "когда-нибудь потом")
    result = run(quests_root, project, "02-one-evening", {"SLICE.md": text})
    assert result.ok is False
    assert "slice_estimate" in {c["id"] for c in quests.failed_checks(result)}


# --- 03c-who ---

# Квест называется «назван измеримый критерий», и до 2026-09-10 число в нём
# НЕ засчитывалось: список принимал только слова. «3–4 раза в неделю»
# проваливало квест, «постоянно» проходило. Найдено прогоном падаваном.
MEASURABLE = [
    "Пользуюсь 3–4 раза в неделю.",
    "Пользуюсь 3-4 раза в неделю.",
    "Открываю 2 раза в день.",
    "Захожу 1 раз в месяц.",
    "Дважды в неделю.",
    "Каждый день, утром.",
    "Раз в неделю по выходным.",
    "Пользуюсь постоянно.",
]

VAGUE = [
    "Иногда захожу.",
    "Когда вспомню.",
    "Часто пользуюсь.",
]


@pytest.mark.parametrize("line", MEASURABLE)
def test_who_accepts_measurable_frequency(quests_root, project, line):
    body = "# Для кого\n\nДля себя. " + line + "\n"
    assert run(quests_root, project, "03c-who", {"WHO.md": body}).ok is True


@pytest.mark.parametrize("line", VAGUE)
def test_who_rejects_vague_frequency(quests_root, project, line):
    body = "# Для кого\n\nДля себя. " + line + "\n"
    result = run(quests_root, project, "03c-who", {"WHO.md": body})
    assert "who_frequency" in {c["id"] for c in quests.failed_checks(result)}


def test_who_passes(quests_root, project):
    result = run(quests_root, project, "03c-who", {"WHO.md": WHO_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_who_fails_without_frequency(quests_root, project):
    result = run(
        quests_root, project, "03c-who",
        {"WHO.md": "Я сам и, наверное, кто-то ещё из знакомых.\n"},
    )
    assert result.ok is False
    assert "who_frequency" in {c["id"] for c in quests.failed_checks(result)}


def test_who_accepts_weekly(quests_root, project):
    result = run(
        quests_root, project, "03c-who",
        {"WHO.md": "Только я. Открываю раз в неделю, по воскресеньям.\n"},
    )
    assert result.ok is True, quests.failed_checks(result)


# --- 03f-market ---

def test_market_passes(quests_root, project):
    result = run(quests_root, project, "03f-market", {"MARKET.md": MARKET_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_market_fails_on_two_numbers(quests_root, project):
    """Граница: два числа — мало, три — достаточно."""
    text = "TAM 50000 семей, SAM 5000 в городе. " * 6
    result = run(quests_root, project, "03f-market", {"MARKET.md": text})
    assert result.ok is True, "шесть повторов дают двенадцать чисел"

    result = run(quests_root, project, "03f-market",
                 {"MARKET.md": "Рынок примерно 50000 семей, из них 5000 рядом. "
                               "Оценка грубая, но порядок понятен и этого хватит "
                               "чтобы понять, стоит ли вообще браться за это дело."})
    assert result.ok is False
    assert "market_numbers" in {c["id"] for c in quests.failed_checks(result)}


def test_market_fails_when_only_a_date(quests_root, project):
    """Дата даёт три числа — но не даёт объёма мысли."""
    result = run(quests_root, project, "03f-market", {"MARKET.md": "2026-07-26\n"})
    assert result.ok is False


# --- 04f-competitors ---

def test_competitors_passes_on_three_urls(quests_root, project):
    result = run(quests_root, project, "04f-competitors",
                 {"COMPETITORS.md": COMPETITORS_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_competitors_fails_on_two_urls(quests_root, project):
    text = COMPETITORS_OK.replace("- Таблица в Google — https://sheets.example\n", "")
    result = run(quests_root, project, "04f-competitors", {"COMPETITORS.md": text})
    assert result.ok is False


def test_competitors_fails_on_same_url_three_times(quests_root, project):
    result = run(
        quests_root, project, "04f-competitors",
        {"COMPETITORS.md": "https://a.example\nhttps://a.example\nhttps://a.example\n"},
    )
    assert result.ok is False


# --- 05f-icp ---

def test_icp_passes(quests_root, project):
    result = run(quests_root, project, "05f-icp", {"ICP.md": ICP_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_icp_boundary_at_sixty_words(quests_root, project):
    assert run(quests_root, project, "05f-icp",
               {"ICP.md": " ".join(["слово"] * 60)}).ok is True
    assert run(quests_root, project, "05f-icp",
               {"ICP.md": " ".join(["слово"] * 59)}).ok is False


# --- 06f-unit ---

def test_unit_passes(quests_root, project):
    result = run(quests_root, project, "06f-unit", {"UNIT.md": UNIT_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_unit_fails_without_token_cost(quests_root, project):
    """Пункт, который вайбкодеры пропускают всегда."""
    text = UNIT_OK.split("## Стоимость токенов")[0]
    result = run(quests_root, project, "06f-unit", {"UNIT.md": text})
    assert result.ok is False
    assert "unit_tokens" in {c["id"] for c in quests.failed_checks(result)}


def test_unit_fails_when_section_has_no_number(quests_root, project):
    text = UNIT_OK.replace(
        "Привести одного пользователя — примерно 300 рублей на рекламу.",
        "Пока не считал, но вроде недорого.",
    )
    result = run(quests_root, project, "06f-unit", {"UNIT.md": text})
    assert result.ok is False
    assert "unit_cac" in {c["id"] for c in quests.failed_checks(result)}


# --- 07f-channel ---

def test_channel_passes(quests_root, project):
    result = run(quests_root, project, "07f-channel", {"CHANNEL.md": CHANNEL_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_channel_fails_on_three_channels(quests_root, project):
    """Распыление на пять каналов — самая частая ошибка этого шага."""
    text = CHANNEL_OK.replace(
        "Телеграм-канал про семейные финансы",
        "- телеграм\n- ютуб\n- хабр",
    )
    result = run(quests_root, project, "07f-channel", {"CHANNEL.md": text})
    assert result.ok is False
    assert "channel_one" in {c["id"] for c in quests.failed_checks(result)}


def test_channel_fails_without_reason(quests_root, project):
    text = CHANNEL_OK.split("## Почему он")[0]
    result = run(quests_root, project, "07f-channel", {"CHANNEL.md": text})
    assert result.ok is False
    assert "channel_why" in {c["id"] for c in quests.failed_checks(result)}


# --- заголовок документа в тон квесту ---
#
# Падаван почти всегда называет файл словом из квеста, и заголовок документа
# оказывается написан теми же словами, что искомая секция. jc_section искал
# первое совпадение на любом уровне решёток — им оказывался заголовок
# документа, под которым пусто, и проверка валила написанное, а подсказка
# звала добавить раздел, который уже есть. Тупик: правило, по которому судят,
# невидимо тому, кого судят.

IDEA_TITLED_LIKE_SECTION = "# Боль\n\n" + IDEA_OK
SLICE_TITLED_LIKE_SECTION = SLICE_OK.replace("# Срез", "# Оценка среза", 1)
UNIT_TITLED_LIKE_SECTION = UNIT_OK.replace(
    "# Юнитка", "# CAC, LTV и стоимость токенов", 1
)
# У CHANNEL_OK заголовок документа совпадает с секцией с самого начала —
# 07f-channel жил с локальным лекарством (лишняя решётка в паттерне). Оно
# снято, паттерн общий, и держит фикстуру теперь само правило jc_section.


def test_idea_passes_when_document_titled_like_section(quests_root, project):
    result = run(quests_root, project, "01-idea",
                 {"IDEA.md": IDEA_TITLED_LIKE_SECTION})
    assert result.ok is True, quests.failed_checks(result)


def test_one_evening_passes_when_document_titled_like_section(quests_root, project):
    result = run(quests_root, project, "02-one-evening",
                 {"SLICE.md": SLICE_TITLED_LIKE_SECTION})
    assert result.ok is True, quests.failed_checks(result)


def test_unit_passes_when_document_titled_like_section(quests_root, project):
    result = run(quests_root, project, "06f-unit",
                 {"UNIT.md": UNIT_TITLED_LIKE_SECTION})
    assert result.ok is True, quests.failed_checks(result)


def test_channel_passes_when_document_titled_like_section(quests_root, project):
    result = run(quests_root, project, "07f-channel", {"CHANNEL.md": CHANNEL_OK})
    assert result.ok is True, quests.failed_checks(result)


def test_channel_still_fails_on_three_channels_under_titled_document(
        quests_root, project):
    """Снятое лекарство не должно ослабить сам квест: три канала — провал,
    даже когда заголовок документа называется так же, как секция."""
    text = CHANNEL_OK.replace(
        "Телеграм-канал про семейные финансы",
        "- телеграм\n- ютуб\n- хабр",
    )
    result = run(quests_root, project, "07f-channel", {"CHANNEL.md": text})
    assert result.ok is False
    assert "channel_one" in {c["id"] for c in quests.failed_checks(result)}


# --- заголовок документа С ТЕКСТОМ под ним ---
#
# Фикстуры выше оставляли под заголовком документа пусто — и в этом дыра:
# при пустом теле «первое непустое совпадение» ведёт себя правильно, и
# сторож пропускает подмену раздела вступлением. Здесь под заголовком
# документа обязательно есть текст, и обе стороны прибиты гвоздями: с
# верным разделом квест закрывается, с неверным — нет. Судят раздел «##»,
# ровно тот, который называет подсказка.

IDEA_TITLE_FILLED = (
    "# Боль\n"
    "Пока формулирую: каждый вечер вручную свожу расходы семьи из трёх банков.\n"
    "\n" + IDEA_OK
)
IDEA_TITLE_FILLED_THIN_SECTION = IDEA_TITLE_FILLED.replace(
    "Каждый вечер вручную свожу расходы семьи из трёх банковских приложений\n"
    "в одну таблицу, и это занимает почти час времени.",
    "непонятно",
)

SLICE_TITLE_FILLED = SLICE_OK.replace(
    "# Срез",
    "# Оценка среза\nПрикидываю: скорее всего это займёт один вечер, максимум два.",
    1,
)
SLICE_TITLE_FILLED_NO_ESTIMATE = SLICE_TITLE_FILLED.replace(
    "Один вечер, часа три работы.", "когда-нибудь потом"
)

UNIT_TITLE_FILLED = UNIT_OK.replace(
    "# Юнитка",
    "# CAC, LTV и стоимость токенов\nСчитал грубо: 300 рублей привести, 1200 отдаёт.",
    1,
)
UNIT_TITLE_FILLED_NO_NUMBER = UNIT_TITLE_FILLED.replace(
    "Привести одного пользователя — примерно 300 рублей на рекламу.",
    "Пока не считал, но вроде недорого.",
)

# Дословно тот файл падавана, на котором квест засчитывал три канала.
CHANNEL_TITLE_FILLED_THREE = (
    "# Канал\n"
    "Пока не решил окончательно.\n"
    "\n"
    "## Канал\n"
    "- телеграм\n"
    "- ютуб\n"
    "- хабр\n"
    "\n"
    "## Почему он\n"
    "Там уже сидит моя аудитория, и я в нём пишу третий год подряд.\n"
)
CHANNEL_TITLE_FILLED_ONE = (
    "# Канал\n"
    "Долго выбирал между вариантами.\n"
    "В итоге остановился на одном.\n"
    "\n"
    "## Канал\n"
    "Телеграм-канал про семейные финансы\n"
    "\n"
    "## Почему он\n"
    "Там уже сидит моя аудитория, и я в нём пишу третий год подряд.\n"
)


def test_idea_passes_under_filled_document_title(quests_root, project):
    result = run(quests_root, project, "01-idea", {"IDEA.md": IDEA_TITLE_FILLED})
    assert result.ok is True, quests.failed_checks(result)


def test_idea_fails_when_section_thin_under_filled_document_title(
        quests_root, project):
    """Вступление под «# Боль» не должно закрывать пустоту в «## Боль»."""
    result = run(quests_root, project, "01-idea",
                 {"IDEA.md": IDEA_TITLE_FILLED_THIN_SECTION})
    assert result.ok is False
    assert "idea_pain" in {c["id"] for c in quests.failed_checks(result)}


def test_one_evening_passes_under_filled_document_title(quests_root, project):
    result = run(quests_root, project, "02-one-evening",
                 {"SLICE.md": SLICE_TITLE_FILLED})
    assert result.ok is True, quests.failed_checks(result)


def test_one_evening_fails_when_estimate_only_in_document_title(
        quests_root, project):
    """Срок назван во вступлении, а в «## Оценка» его нет — это не зачёт."""
    result = run(quests_root, project, "02-one-evening",
                 {"SLICE.md": SLICE_TITLE_FILLED_NO_ESTIMATE})
    assert result.ok is False
    assert "slice_estimate" in {c["id"] for c in quests.failed_checks(result)}


def test_unit_passes_under_filled_document_title(quests_root, project):
    result = run(quests_root, project, "06f-unit", {"UNIT.md": UNIT_TITLE_FILLED})
    assert result.ok is True, quests.failed_checks(result)


def test_unit_fails_when_number_only_in_document_title(quests_root, project):
    """Числа во вступлении не считаются за число в разделе «## CAC»."""
    result = run(quests_root, project, "06f-unit",
                 {"UNIT.md": UNIT_TITLE_FILLED_NO_NUMBER})
    assert result.ok is False
    assert "unit_cac" in {c["id"] for c in quests.failed_checks(result)}


def test_channel_fails_on_three_channels_under_filled_document_title(
        quests_root, project):
    """Несущее: квест существует ради правила «пять каналов — это ноль
    каналов». Одна строка вступления под «# Канал» не имеет права выиграть
    у настоящего раздела с тремя каналами."""
    result = run(quests_root, project, "07f-channel",
                 {"CHANNEL.md": CHANNEL_TITLE_FILLED_THREE})
    assert result.ok is False
    assert "channel_one" in {c["id"] for c in quests.failed_checks(result)}


def test_channel_passes_on_one_channel_under_wordy_document_title(
        quests_root, project):
    """Обратная сторона: раздел оформлен верно — значит зачёт, сколько бы
    строк ни было во вступлении. Иначе падаван проваливается, уже выполнив
    ровно то, что велела подсказка."""
    result = run(quests_root, project, "07f-channel",
                 {"CHANNEL.md": CHANNEL_TITLE_FILLED_ONE})
    assert result.ok is True, quests.failed_checks(result)


def test_idea_passes_when_sections_use_one_hash(quests_root, project):
    """Разделы одной решёткой — рабочий путь, и правило его не отбирает."""
    text = (
        "# Боль\nКаждый вечер свожу расходы семьи из трёх банков в таблицу вручную.\n\n"
        "# Для кого\nЯ и жена, ещё двое друзей просили сделать им такое же.\n\n"
        "# Почему сейчас\nДва банка открыли публичное API, раньше это было нельзя.\n"
    )
    result = run(quests_root, project, "01-idea", {"IDEA.md": text})
    assert result.ok is True, quests.failed_checks(result)


def test_idea_passes_on_section_larger_than_pipe_buffer(quests_root, project):
    """Полностью написанный раздел не имеет права считаться пустым.

    Разбор секции шёл через конвейер с ранним выходом под `set -o pipefail`:
    писатель получал EPIPE, конвейер отдавал 141, и большая секция читалась
    как пустая. 200 КБ — с запасом от 64 КБ буфера трубы, чтобы поймать не
    гонку, а факт.
    """
    line = "Каждый вечер вручную свожу расходы семьи из трёх банков в таблицу.\n"
    fat = line * (200 * 1024 // len(line.encode("utf-8")) + 1)
    text = IDEA_OK.replace(
        "Каждый вечер вручную свожу расходы семьи из трёх банковских приложений\n"
        "в одну таблицу, и это занимает почти час времени.",
        fat,
    )
    assert len(text.encode("utf-8")) > 200 * 1024
    result = run(quests_root, project, "01-idea", {"IDEA.md": text})
    assert result.ok is True, quests.failed_checks(result)


def test_idea_still_fails_when_titled_section_is_empty(quests_root, project):
    """Пусто и в заголовке документа, и в секции — значит пусто."""
    text = (
        "# Боль\n\n## Боль\n\n"
        "## Для кого\nЯ и жена, плюс двое друзей просили сделать такое же.\n\n"
        "## Почему сейчас\nДва банка открыли API в этом году, раньше было нельзя.\n"
    )
    result = run(quests_root, project, "01-idea", {"IDEA.md": text})
    assert result.ok is False
    assert "idea_pain" in {c["id"] for c in quests.failed_checks(result)}


# --- общий контракт ---

def test_act1_checks_survive_hostile_locale(quests_root, project):
    """Регрессия на переезд подбора локали из md.sh в emit.sh.

    Акт 1 переживал LC_ALL=C и до переезда — локаль чинил md.sh. Проверки
    сорсят оба файла, и после переезда защита обязана остаться на месте.
    """
    proj = project(files={"research/IDEA.md": IDEA_OK, "research/UNIT.md": UNIT_OK})
    hostile = {"LC_ALL": "C"}
    idea = quests.run_check(quests_root, SLUG, "01-idea", proj, env_extra=hostile)
    assert idea.ok is True, quests.failed_checks(idea)
    unit = quests.run_check(quests_root, SLUG, "06f-unit", proj, env_extra=hostile)
    assert unit.ok is True, quests.failed_checks(unit)



def test_every_check_is_read_only(quests_root, project):
    """check.sh никогда не мутирует проект падавана."""
    import os

    proj = project(files={
        "research/IDEA.md": IDEA_OK, "research/SLICE.md": SLICE_OK,
        "research/WHO.md": WHO_OK, "research/MARKET.md": MARKET_OK,
        "research/COMPETITORS.md": COMPETITORS_OK, "research/ICP.md": ICP_OK,
        "research/UNIT.md": UNIT_OK, "research/CHANNEL.md": CHANNEL_OK,
    })
    before = sorted(os.listdir(str(proj / "research")))
    before_root = sorted(os.listdir(str(proj)))
    for quest_id in ("01-idea", "02-one-evening", "03c-who", "03f-market",
                     "04f-competitors", "05f-icp", "06f-unit", "07f-channel"):
        quests.run_check(quests_root, SLUG, quest_id, proj)
    assert sorted(os.listdir(str(proj / "research"))) == before
    assert sorted(os.listdir(str(proj))) == before_root

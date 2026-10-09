"""Хук словаря-лута: матчинг с границей слова, отбор, карточка.

Чистые функции тестируются импортом; сквозной subprocess-тест — в
test_lexicon_loot_e2e (Task 2).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "hooks"))

import lexicon_loot  # noqa: E402

from jedicoder import content  # noqa: E402
from jedicoder import ranks, state as st  # noqa: E402


def term(name, aliases, act=1, xp=5, title=None, body="", example=""):
    return content.Term(
        term=name, title=title or name.upper(), aliases=tuple(aliases),
        act=act, category="product", xp=xp, body=body,
        path=Path("/dev/null"), rank="seeker", related=(), example=example,
    )


def fresh_state(current_act=1, unlocked=()):
    return {"current_act": current_act, "lexicon_unlocked": list(unlocked), "xp": 0}


TRAP_TERM = term("tam-sam-som", ["tam", "sam", "som", "сэм", "ца", ".env"])


@pytest.mark.parametrize("text", [
    "timestamp пишем в лог",
    "the same sample again",
    "some awesome text",
    "возьми сэмпл записи",
    "чистим cache и cached-слои",
    "закажи пица-мигелица",
    "конфиг лежит в file.env рядом",
])
def test_substring_traps_do_not_fire(text):
    assert lexicon_loot.find_terms(text, [TRAP_TERM], fresh_state()) == []


@pytest.mark.parametrize("text", [
    "не забудь про ЦА до старта",
    "считаем TAM по рынку",
    "сначала SAM, потом SOM",
    "положи ключ в .env сразу",
])
def test_whole_word_aliases_fire_any_case(text):
    assert lexicon_loot.find_terms(text, [TRAP_TERM], fresh_state()) == [TRAP_TERM]


# Фразы Акта 1 «Знакомство» (спека #75). Шесть первых — те, что скилл акта
# велит произнести: они стоят во врезках `SKILL.md` буква в букву, и если
# словарь их не слышит, карточка не выпадет ровно там, где слово объясняют.
# Живого транскрипта нового акта ещё нет: первый прогон новичком заменит
# их настоящей речью.
#
# Две последние — из прогона прежнего Акта 1 (транскрипт 2026-08-01): их
# слова в игре остались. Остальные фразы того прогона ушли вместе со своими
# словами на полку, `shelf/act1-poisk-boli/`.
#
# Четыре фразы уехали отсюда в RELOCATED_LIVE_SPEECH планом 01.2-05: их
# слова теперь живут в Акте 2, и в Акте 1 карточка по ним не выпадает.
# Фразы не выброшены — они проверяются ниже, на своём акте.
ACT1_LIVE_SPEECH = [
    ("Так делают только в папке проекта.", "project-folder"),
    ("Ты работаешь в режиме без вопросов.", "permission-mode"),
    ("Хороший запрос отвечает на три вопроса.", "prompt"),
    ("Коммит — точка сохранения.", "commit"),
    ("Меню отката возвращает правки этого разговора.", "rollback"),
    (
        "скармливаю агенту часовое видео одной командой в терминале, "
        "без всякого интерфейса",
        "terminal",
    ),
    ("Накопилось? Появился инструмент, которого раньше не было?", "tool"),
]


# Фразы того же прогона, чьи слова уехали в другие акты планом 01.2-05.
# Тройка: (фраза, термин, акт, в котором термин теперь живёт).
#
# Уехали они не по счёту, а по смыслу: «стек» и «скрипт» — язык квеста
# 01-recipe Акта 2, «индекс» — квеста 05-env-guard, «пайплайн» — квеста
# 06-pipeline. Фраза при этом не изменилась ни на букву: проверяем, что
# словарь по-прежнему её слышит — просто теперь на своём шаге.
RELOCATED_LIVE_SPEECH = [
    ("Квест 06 — «Пайплайн».", "pipeline", 2),
    (
        "Проверка смотрит четыре вещи: `.env` не лежит в индексе, "
        "и в истории нет строк, похожих на ключи.",
        "index",
        2,
    ),
    (
        "по `SLICE.md` ты строишь скрипт для командной строки, который "
        "запускается у тебя на машине",
        "script",
        2,
    ),
    (
        "`## Стек` — из чего собирается: язык, чем расшифровывается речь, "
        "чем режется видео.",
        "stack",
        2,
    ),
]


@pytest.mark.parametrize("text,expected", ACT1_LIVE_SPEECH)
def test_act1_speech_unlocks_act1_terms(content_root, text, expected):
    """Страж LOOP-03: словарь обязан слышать язык, которым говорит Акт 1.

    Инцидент: за весь Акт 1 живого прогона хук запустился 21 раз, ни разу
    не упал (`hookErrors: []`, 76–279 мс) и выдал ноль карточек. Механика
    была исправна — в 16 295 символах речи модели не встретилось ни одного
    из десяти алиасов Акта 1. Причина в составе словаря: он состоял из
    рыночной лексики Основателя (arpu, cac, icp, ltv, pmf, tam/sam/som), а
    контракт Ремесленника прямым текстом велит модели не заводить разговор
    о рынке. Игра запретила произносить ровно те слова, которых ждал её
    измерительный прибор, и заглушила его.

    Термины грузятся из настоящей поставки, а не из синтетического
    TRAP_TERM: смысл теста — проверить контент, а не выдумку.

    Ассерт на вхождение, а не на равенство списку: фраза вправе задеть
    соседний термин, и требование точного списка прибило бы к тесту
    сегодняшний состав словаря.
    """
    terms = content.load_terms(content_root)
    found = [t.term for t in lexicon_loot.find_terms(text, terms, fresh_state())]
    assert expected in found, "«{}» не открыла {}: {}".format(text, expected, found)


@pytest.mark.parametrize("text,expected,act", RELOCATED_LIVE_SPEECH)
def test_relocated_speech_unlocks_on_its_own_act(content_root, text, expected, act):
    """Страж того же LOOP-03 после переезда 01.2-05: слово слышно на своём шаге.

    Переезд слова в поздний акт обязан менять **когда** карточка выпадет, а
    не **выпадет ли вообще**. Если бы алиас перестал совпадать — например,
    правка тела задела бы список форм, — эта проверка упала бы, и молчание
    словаря не выдало бы себя за «так задумано».
    """
    terms = content.load_terms(content_root)
    found = [
        t.term
        for t in lexicon_loot.find_terms(text, terms, fresh_state(current_act=act))
    ]
    assert expected in found, "«{}» не открыла {}: {}".format(text, expected, found)


@pytest.mark.parametrize("text,expected,act", RELOCATED_LIVE_SPEECH)
def test_relocated_speech_stays_silent_in_act1(content_root, text, expected, act):
    """Обратная сторона переезда: в Акте 1 этих карточек больше нет.

    Это и есть настоящий рычаг плотности, о котором говорит план 01.2-05.
    Поле `quest` — декларация для линтера; `find_terms` про квесты не знает
    и фильтрует по `t.act <= current_act`. Значит единственный способ
    убрать шесть лишних слов из Акта 1 — увести их в поздний акт, и вот
    доказательство, что уведённое действительно молчит.

    Тест — не дубль предыдущего наоборот: тот проверяет, что слово не
    потерялось, этот — что бюджет Акта 1 реально разгружен. Обвалиться они
    могут по разным причинам.
    """
    assert act > 1
    terms = content.load_terms(content_root)
    found = [t.term for t in lexicon_loot.find_terms(text, terms, fresh_state())]
    assert expected not in found, (
        "«{}» открыла {} ещё в Акте 1 — переезд не сработал: {}".format(
            text, expected, found
        )
    )


def test_multiword_alias_matches_with_boundaries():
    t = term("cac", ["стоимость привлечения"])
    assert lexicon_loot.find_terms(
        "какая стоимость привлечения клиента?", [t], fresh_state()
    ) == [t]
    assert lexicon_loot.find_terms(
        "себестоимость привлечения", [t], fresh_state()
    ) == []


def test_unlocked_and_future_acts_filtered():
    t1 = term("mvp", ["mvp"], act=1)
    t3 = term("hook", ["хук"], act=3)
    state = fresh_state(current_act=1, unlocked=["mvp"])
    assert lexicon_loot.find_terms("mvp и хук", [t1, t3], state) == []


def test_no_current_act_means_silence():
    t = term("mvp", ["mvp"])
    assert lexicon_loot.find_terms("mvp", [t], {"lexicon_unlocked": []}) == []


def test_priority_act_then_xp_then_term():
    a = term("b-cheap", ["браво"], act=1, xp=5)
    b = term("a-rich", ["альфа"], act=1, xp=10)
    c = term("c-late", ["чарли"], act=2, xp=99)
    state = fresh_state(current_act=2)
    got = lexicon_loot.find_terms("альфа браво чарли", [a, b, c], state)
    assert [t.term for t in got] == ["a-rich", "b-cheap", "c-late"]


def test_max_cards_is_one():
    """Одна карточка за ход: под ответом не стена текста (спека #64, US5)."""
    assert lexicon_loot.MAX_CARDS == 1


def test_queue_holds_at_most_two_words():
    """Пять слов в ответе: одна карточка, два ждут, остальные не копятся.

    Прогон новичком 2026-09-13: очередь из восьми слов раздавала карточки о
    словах, прозвучавших восемь ходов назад. Слово сверх двух откроется
    при следующем упоминании.
    """
    words = [term(name, [name]) for name in ("aa", "bb", "cc", "dd", "ee")]
    cards, queue = lexicon_loot.pick_cards("aa bb cc dd ee", words, fresh_state())
    assert [t.term for t in cards] == ["aa"]
    assert queue == ["bb", "cc"]


def test_long_queue_of_an_old_save_is_cut_to_two():
    """Сохранение прошлой версии несёт очередь длиннее двух: она обрезается."""
    words = [term(name, [name]) for name in ("aa", "bb", "cc", "dd")]
    state = fresh_state()
    state["lexicon_queue"] = ["aa", "bb", "cc", "dd"]
    cards, queue = lexicon_loot.pick_cards("", words, state)
    assert [t.term for t in cards] == ["aa"]
    assert queue == ["bb", "cc"]


def test_word_beyond_the_queue_opens_on_next_mention():
    """Не попавшее в очередь слово не потеряно: упомянули снова — ждёт своей очереди."""
    words = [term(name, [name]) for name in ("aa", "bb", "cc", "dd")]
    state = fresh_state()
    cards, queue = lexicon_loot.pick_cards("aa bb cc dd", words, state)
    assert "dd" not in queue
    state["lexicon_unlocked"] = [t.term for t in cards]
    state["lexicon_queue"] = queue
    cards, queue = lexicon_loot.pick_cards("снова dd", words, state)
    assert [t.term for t in cards] == ["bb"]
    assert queue == ["cc", "dd"]


BODY = (
    "**MVP** — самая маленькая версия продукта, которой уже можно "
    "пользоваться.\nНе «половина», а целая, но узкая.\n\n"
    "**Зачем нужно:** проверить идею за вечер, а не за три месяца.\n\n"
    "**Как выглядит:** одна кнопка.\n\n"
    "**Проверь, что понял:** что ты выкинешь из идеи?\n"
)
EXAMPLE = "Калькулятор с одной кнопкой «посчитать», без истории и тем."


def card_lines(card):
    return [line for line in card.split("\n") if line.strip()]


def test_render_card_is_header_and_two_lines():
    """Заголовок с названием и XP, потом ровно две строки: что это и пример."""
    card = lexicon_loot.render_card(
        term("mvp", ["mvp"], xp=5, title="MVP", body=BODY, example=EXAMPLE)
    )
    lines = card_lines(card)
    assert lines[0] == "✦ Новое слово: MVP (очки: +5)"
    assert len(lines) == 3
    assert lines[1].startswith("Самая маленькая версия продукта")
    assert lines[2] == "Пример: " + EXAMPLE
    assert "**" not in card  # разметка снята
    assert "Зачем нужно" not in card  # остаётся Полке и Книге
    assert "Проверь" not in card


def test_render_card_lines_fit_fifteen_words(content_root):
    """Обе строки короче 15 слов — тот же предел, что у фразы (language.md)."""
    terms = {t.term: t for t in content.load_terms(content_root)}
    for name in ACT1_AND_FIRST_SCREEN:
        lines = card_lines(lexicon_loot.render_card(terms[name]))
        assert len(lines) == 3, name
        for line in lines[1:]:
            words = [w for w in line.split() if any(ch.isalnum() for ch in w)]
            assert len(words) <= 15, (name, line)


ACT1_AND_FIRST_SCREEN = (
    "model-effort", "usage", "terminal",
    "project-folder", "permission-mode", "tool", "prompt", "api",
    "commit", "repository", "env", "rollback",
)


def test_render_card_without_example_keeps_old_sections():
    """Термин без example ещё не переписан (#72): печатается как раньше,
    и линтер видит длинную карточку — по ней и снимают LEGACY."""
    card = lexicon_loot.render_card(term("mvp", ["mvp"], xp=5, title="MVP", body=BODY))
    assert "Новое слово: MVP (очки: +5)" in card
    assert "самая маленькая версия продукта" in card
    assert "Зачем нужно: проверить идею" in card
    assert "Проверь себя: что ты выкинешь" in card
    assert "Как выглядит" not in card


def test_render_card_survives_unparsed_body():
    card = lexicon_loot.render_card(term("x", ["x"], xp=5, title="X", body="просто текст"))
    assert "Новое слово: X (очки: +5)" in card


WRAPPED_BODY = (
    "**MVP** — самая маленькая версия продукта.\n\n"
    "**Зачем нужно:** проверить, нужна ли идея вообще, за вечер,\n"
    "а не за три месяца. Большинство идей не выживают.\n\n"
    "**Проверь, что понял:** что ты выкинешь из идеи,\nчтобы осталось на один вечер?\n"
)


def test_render_card_joins_wrapped_sections():
    card = lexicon_loot.render_card(
        term("mvp", ["mvp"], xp=5, title="MVP", body=WRAPPED_BODY)
    )
    assert "за вечер, а не за три месяца. Большинство идей не выживают." in card
    assert "чтобы осталось на один вечер?" in card
    assert "\nа не" not in card  # секция склеена в одну строку


def test_render_card_joins_wrapped_definition():
    """Определение в файле перенесено по 80 колонок — в терминале одна строка."""
    card = lexicon_loot.render_card(term(
        "pain", ["боль"], xp=10, title="Боль",
        body="**Боль** — место, где человеку\nсейчас плохо и дорого.\n",
        example="Каждый вечер час ищу нужный кусок записи.",
    ))
    assert card_lines(card)[1] == "Место, где человеку сейчас плохо и дорого."


def test_render_card_full_sections_on_real_content(content_root):
    terms = {t.term: t for t in content.load_terms(content_root)}
    card = lexicon_loot.render_card(terms["commit"])
    # Карточка поставки — две строки после заголовка: что это и пример.
    # «Зачем нужно» остаётся на Полке (language.md), в терминал не идёт.
    lines = card.split("\n")
    assert len(lines) == 3
    assert lines[1].startswith("Точка сохранения")
    assert lines[2].startswith(lexicon_loot.EXAMPLE_PREFIX)
    assert "Зачем" not in card


HOOK = ROOT / "plugin" / "hooks" / "lexicon_loot.py"


def run_hook(payload, state_path, transcript=None):
    env = dict(**__import__("os").environ)
    env["JEDICODER_STATE_PATH"] = str(state_path)
    env["CLAUDE_PLUGIN_ROOT"] = str(ROOT / "plugin")
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=raw,
        capture_output=True, text=True, timeout=30, env=env,
    )


def seeded_state_file(tmp_path, current_act=1):
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    if current_act >= 2:
        ranks.close_act(data, 1)
        ranks.enter_act(data, 2)
    path = tmp_path / "state.json"
    st.save(data, path)
    return path


def test_e2e_card_awarded_and_persisted(tmp_path):
    state_path = seeded_state_file(tmp_path)
    payload = {"last_assistant_message": "Начнём с API: одна кнопка."}
    done = run_hook(payload, state_path)
    assert done.returncode == 0
    out = json.loads(done.stdout)
    assert "Новое слово: API" in out["systemMessage"]
    data = st.load(state_path)
    assert "api" in data["lexicon_unlocked"]
    assert data["xp"] == 5  # xp термина api

    # повторный ход с тем же словом молчит: термин уже открыт
    again = run_hook(payload, state_path)
    assert again.returncode == 0
    assert again.stdout.strip() == ""
    assert st.load(state_path)["xp"] == 5


def test_e2e_second_term_waits_in_queue(tmp_path):
    """Два слова в одном ответе: одна карточка сейчас, вторая — следующим ходом.

    Очередь, а не тихое начисление: слово без карточки падаван не заметит,
    а XP без объяснения — цифра ни о чём. Засчитывается термин в тот ход,
    когда напечатан, поэтому событие term_unlocked одно на ход и xp в нём —
    итог на момент именно этого начисления.
    """
    state_path = seeded_state_file(tmp_path)
    text = "Сравним API и режим разрешений на живом примере."
    done = run_hook({"last_assistant_message": text}, state_path)
    out = json.loads(done.stdout)
    assert out["systemMessage"].count("Новое слово:") == 1
    # xp 10 против 5 — раньше
    assert "Новое слово: Режим разрешений" in out["systemMessage"]
    data = st.load(state_path)
    assert data["lexicon_unlocked"] == ["permission-mode"]
    assert data["lexicon_queue"] == ["api"]
    events = [e for e in data["pending_sync"] if e["type"] == "term_unlocked"]
    assert [e["payload"]["term"] for e in events] == ["permission-mode"]
    assert events[0]["payload"]["xp"] == data["xp"]

    # Следующий ход про другое: очередь выдаёт API без нового упоминания.
    later = run_hook({"last_assistant_message": "Идём дальше."}, state_path)
    out = json.loads(later.stdout)
    assert out["systemMessage"].count("Новое слово:") == 1
    assert "Новое слово: API" in out["systemMessage"]
    data = st.load(state_path)
    assert data["lexicon_unlocked"] == ["permission-mode", "api"]
    assert data["lexicon_queue"] == []
    events = [e for e in data["pending_sync"] if e["type"] == "term_unlocked"]
    assert [e["payload"]["term"] for e in events] == ["permission-mode", "api"]
    assert events[1]["payload"]["xp"] > events[0]["payload"]["xp"]
    assert events[1]["payload"]["xp"] == data["xp"]


def test_e2e_queue_goes_before_new_words(tmp_path):
    """Слово из очереди печатается раньше нового: оно ждёт дольше.

    Режим разрешений дороже коммита (10 против 5), но коммит уже ждал ход —
    и идёт первым.
    """
    state_path = seeded_state_file(tmp_path)
    run_hook({"last_assistant_message": "API и коммит."}, state_path)
    done = run_hook(
        {"last_assistant_message": "Теперь режим разрешений."}, state_path
    )
    assert "Новое слово: Коммит" in json.loads(done.stdout)["systemMessage"]
    data = st.load(state_path)
    assert data["lexicon_unlocked"] == ["api", "commit"]
    assert data["lexicon_queue"] == ["permission-mode"]


def test_e2e_password_file_has_no_card_on_the_first_evening(tmp_path):
    """Паролей в первый вечер нет (#87): слово `.env` в Акте 1 карточки не
    даёт, даже если модель его произнесла. Карточка ждёт Акта 2."""
    state_path = seeded_state_file(tmp_path)
    done = run_hook(
        {"last_assistant_message": "Файл `.env` хранит пароли и ключи."},
        state_path,
    )
    assert done.returncode == 0 and done.stdout.strip() == ""
    data = st.load(state_path)
    assert data["lexicon_unlocked"] == [] and data["lexicon_queue"] == []


def test_e2e_queue_skips_term_unlocked_meanwhile(tmp_path):
    """Термин, открытый пока ждал, из очереди выпадает без карточки."""
    state_path = seeded_state_file(tmp_path)
    run_hook({"last_assistant_message": "API и режим разрешений."}, state_path)
    with st.update_state(state_path) as data:
        data["lexicon_unlocked"].append("api")
    done = run_hook({"last_assistant_message": "Идём дальше."}, state_path)
    assert done.returncode == 0
    assert done.stdout.strip() == ""
    assert st.load(state_path)["lexicon_queue"] == []


def test_e2e_act_gate(tmp_path):
    state_path = seeded_state_file(tmp_path, current_act=1)
    done = run_hook({"last_assistant_message": "поставь хук на Stop"}, state_path)
    assert done.stdout.strip() == ""  # термин акта 3 в акте 1 не открывается


def test_e2e_transcript_fallback(tmp_path):
    state_path = seeded_state_file(tmp_path)
    transcript = tmp_path / "t.jsonl"
    lines = [
        {"type": "user", "message": {"content": [{"type": "text", "text": "а?"}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "x", "name": "Bash", "input": {}},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Это чужой API."},
        ]}},
    ]
    transcript.write_text(
        "\n".join(json.dumps(l) for l in lines), encoding="utf-8"
    )
    done = run_hook(
        {"transcript_path": str(transcript)}, state_path
    )
    out = json.loads(done.stdout)
    assert "Новое слово: API" in out["systemMessage"]


def test_e2e_tool_output_not_scanned(tmp_path):
    """Термин в выводе инструмента (tool_result у user-записи) не открывается."""
    state_path = seeded_state_file(tmp_path)
    transcript = tmp_path / "t.jsonl"
    lines = [
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "тут api в логе"},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Готово, смотри лог."},
        ]}},
    ]
    transcript.write_text(
        "\n".join(json.dumps(l) for l in lines), encoding="utf-8"
    )
    done = run_hook({"transcript_path": str(transcript)}, state_path)
    assert done.stdout.strip() == ""


@pytest.mark.parametrize("payload", [
    "не json вовсе",
    "{}",
    json.dumps({"last_assistant_message": 42}),
    json.dumps({"transcript_path": "/нет/такого/файла"}),
])
def test_e2e_broken_payload_silent_success(tmp_path, payload):
    state_path = seeded_state_file(tmp_path)
    done = run_hook(payload, state_path)
    assert done.returncode == 0
    assert done.stdout.strip() == ""


def test_unlocked_term_enqueues_event(tmp_path):
    state_path = seeded_state_file(tmp_path)
    payload = {"last_assistant_message": "Начнём с API: одна кнопка."}
    run_hook(payload, state_path)
    state = st.load(state_path)
    assert state["lexicon_unlocked"]  # термин выдан
    events = [e for e in state["pending_sync"] if e["type"] == "term_unlocked"]
    assert events and events[0]["payload"]["term"] == state["lexicon_unlocked"][0]
    assert events[0]["payload"]["xp"] == state["xp"]


def test_e2e_status_shows_loot(tmp_path, content_root, quests_root, capsys):
    from jedicoder import cli

    state_path = seeded_state_file(tmp_path)
    run_hook({"last_assistant_message": "зовём чужой API"}, state_path)
    code = cli.main(
        ["status"], state_path=state_path,
        content_root=content_root, quests_root=quests_root,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Открыто слов: 1" in out
    assert "Очки: 5 " in out

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


def term(name, aliases, act=1, xp=5, title=None, body=""):
    return content.Term(
        term=name, title=title or name.upper(), aliases=tuple(aliases),
        act=act, category="product", xp=xp, body=body,
        path=Path("/dev/null"), rank="seeker", related=(),
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


# Живые фразы Акта 1 из прогона (транскрипт 2026-08-01, разбор 2026-08-02).
# Слова взяты в тех формах, которыми акт говорил на самом деле, а не в
# словарных: «болит», «в терминале», «не лежит в индексе».
#
# Три фразы обновлены переименованием 01.2-02: транскрипт снят ДО правки, и
# «Фильтр Хатта» с «работой Хатта» в нём стоят там, где акт теперь говорит
# «правило одного вечера», а «кристалл» — там, где стоит «замысел». Дословно
# эти три строки уже не воспроизводятся — на их месте формы, которыми акт
# говорит после замены.
#
# Четыре фразы уехали отсюда в RELOCATED_LIVE_SPEECH планом 01.2-05: их
# слова теперь живут в Акте 2, и в Акте 1 карточка по ним не выпадает.
# Фразы не выброшены — они проверяются ниже, на своём акте.
ACT1_LIVE_SPEECH = [
    ("Мы ищем то, что у кого-то болит.", "pain"),
    ("Поэтому первым тебе дают не меч, а замысел.", "crystal"),
    ("Квест 02 — «Правило одного вечера».", "hutt-filter"),
    (
        "Смысл правила одного вечера не в том чтобы успеть за вечер, "
        "а в том чтобы понять, чего ты на самом деле хотел.",
        "hutt-filter",
    ),
    (
        "`## Отрезано` — всё остальное. Раздел обязателен и пустым быть "
        "не может.",
        "vertical-slice",
    ),
    (
        "Заодно там всплывёт твоя оценка в 30 минут — сравним её с "
        "настоящим объёмом работ.",
        "estimate",
    ),
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


def test_max_cards_is_two():
    assert lexicon_loot.MAX_CARDS == 2


BODY = (
    "**MVP** — самая маленькая версия продукта, которой уже можно "
    "пользоваться.\nНе «половина», а целая, но узкая.\n\n"
    "**Зачем нужно:** проверить идею за вечер, а не за три месяца.\n\n"
    "**Как выглядит:** одна кнопка.\n\n"
    "**Проверь, что понял:** что ты выкинешь из идеи?\n"
)


def test_render_card_shape():
    card = lexicon_loot.render_card(term("mvp", ["mvp"], xp=5, title="MVP", body=BODY))
    assert "Новое слово: MVP (+5 XP)" in card
    assert "самая маленькая версия продукта" in card
    assert "Зачем нужно: проверить идею" in card
    assert "Проверь себя: что ты выкинешь" in card
    assert "**" not in card  # разметка снята
    assert "Как выглядит" not in card  # лишние секции не тащим


def test_render_card_survives_unparsed_body():
    card = lexicon_loot.render_card(term("x", ["x"], xp=5, title="X", body="просто текст"))
    assert "Новое слово: X (+5 XP)" in card


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


def test_render_card_full_sections_on_real_content(content_root):
    terms = {t.term: t for t in content.load_terms(content_root)}
    card = lexicon_loot.render_card(terms["mvp"])
    assert "за вечер, а не за три месяца" in card


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
    payload = {"last_assistant_message": "Начнём с MVP: одна кнопка."}
    done = run_hook(payload, state_path)
    assert done.returncode == 0
    out = json.loads(done.stdout)
    assert "Новое слово: MVP" in out["systemMessage"]
    data = st.load(state_path)
    assert "mvp" in data["lexicon_unlocked"]
    assert data["xp"] == 5  # xp термина mvp

    # повторный ход с тем же словом молчит: термин уже открыт
    again = run_hook(payload, state_path)
    assert again.returncode == 0
    assert again.stdout.strip() == ""
    assert st.load(state_path)["xp"] == 5


def test_e2e_two_cards_max_one_write(tmp_path):
    state_path = seeded_state_file(tmp_path)
    text = "Сравним MVP, PMF и ICP на живом примере."
    done = run_hook({"last_assistant_message": text}, state_path)
    out = json.loads(done.stdout)
    assert out["systemMessage"].count("Новое слово:") == 2
    data = st.load(state_path)
    assert len(data["lexicon_unlocked"]) == 2
    # Два термина за один ход — два события term_unlocked, и xp в каждом —
    # накопленный итог на момент начисления именно этого термина: второе
    # событие обязано нести xp строго больше первого, иначе бот увидел бы
    # одинаковый (или убывающий) итог там, где на самом деле два начисления.
    events = [e for e in data["pending_sync"] if e["type"] == "term_unlocked"]
    assert len(events) == 2
    assert events[0]["payload"]["term"] == data["lexicon_unlocked"][0]
    assert events[1]["payload"]["term"] == data["lexicon_unlocked"][1]
    assert events[1]["payload"]["xp"] > events[0]["payload"]["xp"]
    assert events[1]["payload"]["xp"] == data["xp"]


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
            {"type": "text", "text": "Это твой MVP."},
        ]}},
    ]
    transcript.write_text(
        "\n".join(json.dumps(l) for l in lines), encoding="utf-8"
    )
    done = run_hook(
        {"transcript_path": str(transcript)}, state_path
    )
    out = json.loads(done.stdout)
    assert "Новое слово: MVP" in out["systemMessage"]


def test_e2e_tool_output_not_scanned(tmp_path):
    """Термин в выводе инструмента (tool_result у user-записи) не открывается."""
    state_path = seeded_state_file(tmp_path)
    transcript = tmp_path / "t.jsonl"
    lines = [
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "тут mvp в логе"},
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
    payload = {"last_assistant_message": "Начнём с MVP: одна кнопка."}
    run_hook(payload, state_path)
    state = st.load(state_path)
    assert state["lexicon_unlocked"]  # термин выдан
    events = [e for e in state["pending_sync"] if e["type"] == "term_unlocked"]
    assert events and events[0]["payload"]["term"] == state["lexicon_unlocked"][0]
    assert events[0]["payload"]["xp"] == state["xp"]


def test_e2e_status_shows_loot(tmp_path, content_root, quests_root, capsys):
    from jedicoder import cli

    state_path = seeded_state_file(tmp_path)
    run_hook({"last_assistant_message": "делаем MVP"}, state_path)
    code = cli.main(
        ["status"], state_path=state_path,
        content_root=content_root, quests_root=quests_root,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Открыто слов: 1" in out
    assert "XP: 5" in out

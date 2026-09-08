"""Шов Свитка: текст Магистра поверх фактов и дорожная карта.

Движок модель не зовёт и звать не может — `cli.py` обычный python без сети.
Поэтому текст Магистра попадает в Свиток в два приёма, и оба приёма — двери,
которыми ходит модель: `debrief` печатает готовые факты, `debrief write`
принимает написанный поверх них текст со stdin. Между приёмами текст лежит в
сохранении, и в Свиток его подставляет `cli._scroll_parts`.

Дорожная карта в этот шов входит с другой стороны: её три шага модель не
пишет вовсе. Они зависят от трека и от того, есть ли у продукта адрес, —
значит это контент (`content/ru/roadmap/`), а движок только выбирает карту и
подставляет адрес.

Настоящее сохранение падавана здесь не открывается: всё идёт через
`state_path` из фикстуры.
"""
import io
import shutil
import sys
from pathlib import Path

import pytest

from jedicoder import cli, content, debrief, scroll
from jedicoder import state as st


@pytest.fixture
def paths(tmp_path, content_root, quests_root):
    return {
        "state_path": tmp_path / "state.json",
        "content_root": content_root,
        "quests_root": quests_root,
    }


def run(argv, paths, capsys, stdin=None):
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        code = cli.main(argv, **paths)
    finally:
        sys.stdin = sys.__stdin__
    return code, capsys.readouterr().out


# --- Первый приём: модель читает факты --------------------------------------


def test_debrief_prints_the_facts_the_engine_counted(paths, capsys):
    code, out = run(["debrief"], paths, capsys)
    assert code == 0
    assert out.startswith("# Разбор")
    assert "Ранг: Юнлинг (youngling)" in out
    assert "- XP: 0" in out


def test_debrief_names_every_number_the_facts_carry(paths, capsys):
    """Проверка ADR-0010 с той стороны, с которой её читает модель.

    Числа сверяются с ответом `debrief.facts`, а не с константами теста:
    иначе тест доказывал бы, что страница совпадает сама с собой.
    """
    with st.update_state(paths["state_path"]) as data:
        data["xp"] = 320
        data["streak"] = {"current": 4, "best": 9, "last_commit_date": None}
        data["lexicon_unlocked"] = ["boль", "commit", "deploy"]
    _, out = run(["debrief"], paths, capsys)
    numbers = debrief.facts(st.load(paths["state_path"]))
    assert "- XP: {}".format(numbers["xp"]) in out
    assert "- Текущая: {}".format(numbers["streak"]["current"]) in out
    assert "- Лучшая: {}".format(numbers["streak"]["best"]) in out
    assert "- Открыто слов: {}".format(numbers["terms_unlocked"]) in out


def test_unknown_verb_changes_nothing_and_says_so(paths, capsys):
    code, out = run(["debrief", "vydumka"], paths, capsys)
    assert code == 1
    assert "debrief write" in out
    assert st.load(paths["state_path"])["debrief"] == {"text": "", "facts": ""}


def test_extra_words_are_refused_and_not_swallowed(paths, capsys):
    """Хвост после известного слова — опечатка, а не украшение: соседние
    ручки на неизвестный аргумент отвечают отказом, и эта обязана тоже."""
    code, _ = run(["debrief", "write", "lishnee"], paths, capsys, stdin=RAZBOR)
    assert code == 1
    assert st.load(paths["state_path"])["debrief"]["text"] == ""


# --- Второй приём: Магистр отдаёт текст --------------------------------------


RAZBOR = (
    "Три попытки на одном квесте — это не слабость, это место, где ты "
    "перестал угадывать.\n\nВозьми в следующий акт то же терпение."
)


def test_written_debrief_is_kept_in_the_save(paths, capsys):
    code, out = run(["debrief", "write"], paths, capsys, stdin=RAZBOR + "\n")
    assert code == 0
    assert "Разбор записан" in out
    kept = st.load(paths["state_path"])["debrief"]
    assert kept["text"] == RAZBOR
    # Вместе с текстом — отпечаток страницы фактов, поверх которой он
    # написан: по нему видно, тем ли числам этот текст отвечает.
    assert kept["facts"] == scroll.fingerprint(
        cli._debrief_facts(st.load(paths["state_path"]), paths["content_root"])
    )


def test_empty_input_keeps_what_was_written_and_refuses(paths, capsys):
    """Пустой ввод — не «сотри», а «текста не приехало».

    Команду запускает модель из markdown-инструкции, где рядом лежит строка
    `… debrief write` без heredoc: скопировав её, модель получила бы пустой
    stdin и стёрла бы написанное молча, кодом 0.
    """
    run(["debrief", "write"], paths, capsys, stdin=RAZBOR)
    code, out = run(["debrief", "write"], paths, capsys, stdin="   \n")
    assert code == 1
    assert "debrief clear" in out
    assert st.load(paths["state_path"])["debrief"]["text"] == RAZBOR


def test_clear_wipes_the_text_deliberately(paths, capsys):
    """Вернуться к молчанию Магистра — отдельным словом, а не пустым вводом."""
    run(["debrief", "write"], paths, capsys, stdin=RAZBOR)
    code, out = run(["debrief", "clear"], paths, capsys)
    assert code == 0
    assert "стёрт" in out
    assert st.load(paths["state_path"])["debrief"] == {"text": "", "facts": ""}


def test_debrief_keeps_reading_the_facts_after_the_text_is_written(
    paths, capsys
):
    """Факты и текст не смешиваются: модель пишет ПОВЕРХ фактов, а не поверх
    своего вчерашнего разбора."""
    run(["debrief", "write"], paths, capsys, stdin=RAZBOR)
    _, out = run(["debrief"], paths, capsys)
    assert RAZBOR not in out
    assert scroll.DEBRIEF_HEADING not in out


# --- Шов: текст доезжает до файла -------------------------------------------


def test_text_lands_under_the_facts_in_the_file(paths, capsys, project):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["debrief", "write"], paths, capsys, stdin=RAZBOR)
    code, _ = run(["scroll"], paths, capsys)
    assert code == 0
    page = (folder / "docs" / "jedicoder" / scroll.DEBRIEF_NAME).read_text(
        encoding="utf-8"
    )
    assert RAZBOR in page
    assert page.index(scroll.DEBRIEF_HEADING) > page.index("## Тёмная сторона")


def test_facts_in_the_file_are_word_for_word_what_the_model_read(
    paths, capsys, project
):
    """Требование тикета: факты в файле дословно совпадают с выводом движка.

    Дословно — значит страница, которую прочитала модель, лежит в файле
    целиком и без правок, а текст Магистра начинается ровно там, где она
    кончилась.
    """
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    _, facts_page = run(["debrief"], paths, capsys)
    run(["debrief", "write"], paths, capsys, stdin=RAZBOR)
    run(["scroll"], paths, capsys)
    page = (folder / "docs" / "jedicoder" / scroll.DEBRIEF_NAME).read_text(
        encoding="utf-8"
    )
    assert page.startswith(facts_page.rstrip("\n"))


def test_silent_magistr_still_gives_a_scroll(paths, capsys, project):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    code, _ = run(["scroll"], paths, capsys)
    assert code == 0
    page = (folder / "docs" / "jedicoder" / scroll.DEBRIEF_NAME).read_text(
        encoding="utf-8"
    )
    assert "## Путь" in page
    assert scroll.DEBRIEF_HEADING not in page


# --- Дорожная карта: контент, а не текст модели ------------------------------


ROADMAP_NAME = scroll.ROADMAP_NAME


def card(track="craftsman"):
    return content.Roadmap(
        track=track,
        title="Три шага",
        lead="Адреса пока нет.",
        lead_url="Продукт живёт по адресу {url}.",
        body="## Шаг 1. Люди\n\nТри имени.\n",
        path=Path("{}.md".format(track)),
    )


def test_roadmap_page_takes_the_lead_for_a_product_without_an_address():
    page = scroll.roadmap_page(card())
    assert page.startswith("# Три шага\n\nАдреса пока нет.")
    assert "## Шаг 1. Люди" in page


def test_roadmap_page_names_the_address_when_there_is_one():
    page = scroll.roadmap_page(card(), "https://moy-produkt.ru")
    assert "Продукт живёт по адресу https://moy-produkt.ru." in page
    assert "Адреса пока нет." not in page


def test_roadmap_page_survives_braces_in_the_body():
    """Фигурные скобки в теле карты — обычный пример, а не поле шаблона:
    подстановка через format уронила бы выдачу Свитка на нём."""
    with_braces = content.Roadmap(
        track="craftsman", title="Три шага", lead="Адреса пока нет.",
        lead_url="Адрес: {url}.",
        body="## Шаг 1\n\nОтвет вида {\"ok\": true}.\n",
        path=Path("craftsman.md"),
    )
    assert '{"ok": true}' in scroll.roadmap_page(with_braces, "https://a.ru")


@pytest.mark.parametrize("track", ("craftsman", "founder"))
def test_scroll_carries_the_card_of_the_chosen_track(
    paths, capsys, project, track
):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["track", track], paths, capsys)
    run(["scroll"], paths, capsys)
    page = (folder / "docs" / "jedicoder" / ROADMAP_NAME).read_text(
        encoding="utf-8"
    )
    cards = content.roadmaps_by_track(paths["content_root"])
    assert cards[track].title in page
    assert cards[track].body.strip("\n") in page


def test_scroll_without_a_track_carries_the_common_card(
    paths, capsys, project
):
    """Свиток выдаётся на любом ранге, в том числе до выбора трека: дыра
    вместо карты не заметна никому, а общая карта работает у всех."""
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["scroll"], paths, capsys)
    page = (folder / "docs" / "jedicoder" / ROADMAP_NAME).read_text(
        encoding="utf-8"
    )
    common = content.roadmaps_by_track(paths["content_root"])[content.TRACK_ANY]
    assert common.title in page


def test_scroll_names_the_product_address_in_the_card(paths, capsys, project):
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["track", "founder"], paths, capsys)
    run(["project", "url", "https://moy-produkt.ru"], paths, capsys)
    run(["scroll"], paths, capsys)
    page = (folder / "docs" / "jedicoder" / ROADMAP_NAME).read_text(
        encoding="utf-8"
    )
    # Тот же факт, что в Разборе, и добыт он оттуда же: второй способ
    # достать адрес из сохранения был бы вторым источником правды, и
    # разойтись два места могли бы молча.
    counted = debrief.facts(st.load(paths["state_path"]))["product_url"]
    assert counted in page


def test_missing_roadmap_section_does_not_sink_the_scroll(
    paths, capsys, project, tmp_path
):
    """Карта — часть Свитка, а не его условие: раздела нет вовсе (плагин
    установлен не целиком), а факты и инструкции падаван всё равно уносит."""
    bare = tmp_path / "content"
    shutil.copytree(str(paths["content_root"]), str(bare))
    shutil.rmtree(str(bare / "roadmap"))
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    code, _ = run(
        ["scroll"], dict(paths, content_root=bare), capsys
    )
    assert code == 0
    target = folder / "docs" / "jedicoder"
    assert (target / scroll.DEBRIEF_NAME).exists()
    assert not (target / ROADMAP_NAME).exists()


def test_write_from_a_terminal_refuses_instead_of_hanging(paths, capsys):
    """Без перенаправления `debrief write` ждал бы ввода молча — то есть
    повесил бы терминал падавана на команде, которую набрала модель."""
    class Terminal(io.StringIO):
        def isatty(self):
            return True

    sys.stdin = Terminal("")
    try:
        code = cli.main(["debrief", "write"], **paths)
    finally:
        sys.stdin = sys.__stdin__
    out = capsys.readouterr().out
    assert code == 1
    assert "stdin" in out
    assert st.load(paths["state_path"])["debrief"]["text"] == ""


def test_debrief_written_over_other_numbers_stays_out_of_the_scroll(
    paths, capsys, project
):
    """Разбор отвечает числам, поверх которых написан, и только им.

    Падаван играет дальше, а текст лежит в сохранении: через десять квестов
    «тяжелее всего дался» будет уже про другой квест. Пустить такой текст в
    файл — это и есть «назвать число иначе», от чего ADR-0010. Молчание
    здесь законно, ложь — нет; сам текст при этом никуда не девается.
    """
    folder = project()
    run(["project", "path", str(folder)], paths, capsys)
    run(["debrief", "write"], paths, capsys, stdin=RAZBOR)
    with st.update_state(paths["state_path"]) as data:
        data["xp"] = 500
    code, out = run(["scroll"], paths, capsys)
    assert code == 0
    page = (folder / "docs" / "jedicoder" / scroll.DEBRIEF_NAME).read_text(
        encoding="utf-8"
    )
    assert RAZBOR not in page
    assert scroll.DEBRIEF_HEADING not in page
    assert "по другим числам" in out
    assert st.load(paths["state_path"])["debrief"]["text"] == RAZBOR

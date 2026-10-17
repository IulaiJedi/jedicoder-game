import re
from pathlib import Path

import pytest

from conftest import needs_shelf

from jedicoder import cli, ranks

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"

CALL = re.compile(r'cli\.py"?\s+([a-z]+)')
CLI_PATH = re.compile(r'(?:\$JC|\$\(cat ~/\.jedicoder/plugin_root\))(/[^"\s]*cli\.py)')
BACKTICKED = re.compile(r"`([^`]+)`")
CUTSCENE_HEADING = re.compile(r"^##\s*Катсцен", re.MULTILINE)
# Маркеры воспроизведения механики начала квеста. IGNORECASE обязателен:
# историческая строка начиналась с заглавной — «Перескажи задачу квеста
# своими словами», — и строчный маркер её не поймал бы. Имени «Возражение
# Магистра» в списке нет намеренно: указателю положено механику называть.
ECHO_MARKERS = re.compile(
    r"Эхо|перескажи задачу|дождись «да»|дождись подтверждения", re.IGNORECASE
)
# Кто набирает текст файлов. Контракт (правило 8) исходит из того, что пишет
# модель, а суперсила падавана — точно формулировать.
TYPES_FILES = re.compile(r"пишет сам|пишешь сам|набирает сам")


def markdown_files():
    return sorted(PLUGIN.glob("commands/*.md")) + sorted(PLUGIN.glob("skills/*/SKILL.md"))


def test_markdown_files_exist():
    names = {path.name for path in markdown_files()}
    # Точка входа падавана. Имя файла = имя команды: /jedicoder:start.
    # Совпадать с именем скилла оно не имеет права (см. CLAUDE.md), поэтому
    # тест держит именно start.md, а не что-нибудь производное от «jedicoder».
    assert "start.md" in names
    assert "SKILL.md" in names


def test_every_cli_call_in_markdown_is_real():
    unknown = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for name in CALL.findall(text):
            if name not in cli.SUBCOMMANDS:
                unknown.append("{}: {}".format(path.name, name))
    assert unknown == [], "в markdown вызываются несуществующие подкоманды"


def subcommands_in(path):
    """Подкоманды, названные в одном файле: вызовом cli.py или в бэктиках."""
    names = set()
    text = path.read_text(encoding="utf-8")
    names.update(CALL.findall(text))
    for span in BACKTICKED.findall(text):
        words = span.strip().split()
        if words:
            names.add(words[0])
    return names


def documented_subcommands():
    """Подкоманды, упомянутые в markdown: вызовом cli.py или в бэктиках."""
    names = set()
    for path in markdown_files():
        names.update(subcommands_in(path))
    return names


def test_every_subcommand_is_documented():
    """Обратная проверка: подкоманда, которой нет в markdown, недостижима.

    Проверка «markdown -> CLI» ловит только опечатки в вызовах. Так `project`
    и `root` уехали незадокументированными при зелёном суите: ассистент не
    знал, чем записать ответ падавана, и лез в state.json руками.
    """
    documented = documented_subcommands()
    missing = [name for name in cli.SUBCOMMANDS if name not in documented]
    assert missing == [], "подкоманды не описаны ни в одном md плагина: {}".format(
        missing
    )


def test_db_answer_command_named_in_the_shelved_act2_skill():
    """Скилл обязан называть команду, а не только ключ состояния.

    Квест 03-db-schema без записанного project.has_db — тупик, а состояние
    разрешено менять только через CLI. Квест и его скилл — прежний Акт 2
    «Чертёж», с 2026-10-13 на полке (shelf/act2-chertezh/); команда
    `project db` в игре осталась, и вернувшийся скилл обязан звать её же.
    """
    skill = PLUGIN.parent / "shelf" / "act2-chertezh" / "skill" / "SKILL.md"
    if not skill.is_file():
        # Полка наружу не едет: в выгрузке (`build_release.py`) её нет.
        pytest.skip("полки прежнего Акта 2 нет в этом дереве")
    assert "project db" in skill.read_text(encoding="utf-8")


def test_skills_have_frontmatter_with_name_and_description():
    for path in sorted(PLUGIN.glob("skills/*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), path
        head = text.split("---", 2)[1]
        assert "name:" in head, path
        assert "description:" in head, path


def test_core_skill_reads_plugin_root_from_marker():
    text = (PLUGIN / "skills" / "core" / "SKILL.md").read_text(encoding="utf-8")
    assert ".jedicoder/plugin_root" in text
    assert "cli.py" in text


def test_core_skill_requires_contract():
    text = (PLUGIN / "skills" / "core" / "SKILL.md").read_text(encoding="utf-8")
    assert "contract" in text


def test_every_cli_path_in_markdown_resolves():
    missing = []
    found_any = False
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for suffix in CLI_PATH.findall(text):
            found_any = True
            target = PLUGIN / suffix.lstrip("/")
            if not target.is_file():
                missing.append("{}: {} -> нет файла {}".format(path.name, suffix, target))
    assert found_any, "в markdown не найдено ни одного вызова cli.py — регексп сломан"
    assert missing == [], missing


ACT1_SKILL = PLUGIN / "skills" / "act1-znakomstvo" / "SKILL.md"


def test_act1_skill_records_the_folder_before_any_work_in_the_project():
    """Запись папки — действие первого квеста и первое дело в проекте: без
    неё защитный хук не стережёт `.env` (замер 2026-10-08, спека #75). До
    #83 она шла шагом до входа в акт, и квесту «Папка» нечего было
    засчитывать. Состояние меняется только через CLI — если скилл не назовёт
    команду, ассистент полезет в state.json руками, как это было с
    project db."""
    text = ACT1_SKILL.read_text(encoding="utf-8")
    assert "project path" in text
    assert text.index("cli.py\" enter 1") < text.index("project path")
    assert text.index("project path") < text.index("cli.py\" check 1 01-folder")
    assert "До записи в папке не работай" in text


def test_act1_skill_does_not_ask_for_track():
    """У акта нет развилки: команды выбора трека в скилле нет вовсе."""
    text = ACT1_SKILL.read_text(encoding="utf-8")
    assert "track craftsman" not in text
    assert "track founder" not in text


def test_act1_skill_lists_all_five_quests_from_the_registry():
    from jedicoder import acts

    text = ACT1_SKILL.read_text(encoding="utf-8")
    for quest_id in acts.quest_ids(1):
        assert quest_id in text, "квест {} не описан в скилле".format(quest_id)
    assert "ack 1 05-stop-undo" in text


def test_act1_skill_names_the_idea_file_and_its_sections():
    """Падаван должен знать, что и куда класть: проверка читает IDEA.md в
    корне папки и ищет эти два раздела."""
    text = ACT1_SKILL.read_text(encoding="utf-8")
    assert "`IDEA.md`" in text
    assert "research/" not in text
    assert "## Делаю сегодня" in text
    assert "## Не сегодня" in text


def test_act1_skill_names_the_mode_honestly():
    """Решение 3 спеки #75: первый квест называет режим без вопросов и
    команду запуска для играющих в терминале без приложения. Английскую
    строку режима человек не ищет (#87): режим называет игра."""
    text = ACT1_SKILL.read_text(encoding="utf-8")
    assert "режиме без вопросов" in text
    assert "bypass permissions on" not in text
    assert "`claude --dangerously-skip-permissions`" in text
    # Три режима и их переключение — материал следующего акта (#83).
    assert "`Shift+Tab`" not in text
    assert "только в папке проекта" in text


def test_act1_skill_teaches_stop_and_both_ways_back():
    text = ACT1_SKILL.read_text(encoding="utf-8")
    assert "`Esc`" in text
    assert "`/rewind`" in text
    assert "к последнему\nсохранению" in text or "к последнему сохранению" in text


@needs_shelf
def test_act4_skill_no_longer_forbids_naming_the_mode():
    """Запрет «как включить режим без проверок, не рассказывай» снят
    решением 3 спеки #75: Акт 1 называет режим сам."""
    # Скилл «Щита» с 2026-10-14 на полке (спека #117): запрет не должен
    # вернуться и оттуда, вместе с актом.
    text = (PLUGIN.parent / "shelf" / "act4-shchit" / "skill" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "не рассказывай" not in text
    assert "Акт 1" in text or "Акта 1" in text


def test_hub_skill_names_every_act_skill():
    """Хаб-скилл обязан знать про каждый акт, у которого есть скилл — иначе
    он отправит падавана дальше по несуществующей карте (см. Акт 3, который
    хаб долго не упоминал вовсе, хотя игра уже была им проходима)."""
    hub = (PLUGIN / "skills" / "core" / "SKILL.md").read_text(encoding="utf-8")
    act_dirs = sorted(p.parent.name for p in PLUGIN.glob("skills/act*/SKILL.md"))
    missing = [d for d in act_dirs if d not in hub]
    assert missing == [], "хаб-скилл не знает акты: {}".format(missing)


def test_act_skill_points_at_its_own_cutscene_source():
    """Скилл обязан назвать путь до катсцены СВОЕГО акта.

    Катсцену печатает CLI из контент-ядра, а скилл читает её падавану
    дословно. Без явного пути ассистент пересказывает по памяти — и книга,
    терминал и скилл начинают расходиться (так и вырос долг №11).
    """
    missing = []
    for number, info in sorted(ranks.ACTS.items()):
        slug = info["slug"]
        path = PLUGIN / "skills" / slug / "SKILL.md"
        if not path.is_file():
            missing.append("нет скилла акта {}: {}".format(number, path))
            continue
        source = "content/ru/acts/{}.md".format(slug)
        if source not in path.read_text(encoding="utf-8"):
            missing.append("{}: не назван источник {}".format(path.name, source))
    assert missing == [], missing


def test_no_skill_carries_an_act_cutscene():
    """Страж долга №11: катсцена акта живёт ровно в одном месте.

    Раньше act4-shchit/SKILL.md нёс собственный раздел «## Катсцена» с
    текстом, не совпадающим с content/ru/acts/act4-shchit.md, — терминал
    рассказывал одно, скилл другое. Без этого теста правка вернётся молча.
    Врезки уровня квеста (Акт 1 квест 02, Акт 2 квест 05) не запрещены:
    они не катсцены акта и так и называются.
    """
    offenders = [
        path.parent.name
        for path in sorted(PLUGIN.glob("skills/*/SKILL.md"))
        if CUTSCENE_HEADING.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], "текст катсцены акта в скиллах: {}".format(offenders)


def test_no_skill_repeats_the_objection_mechanic():
    """Механика начала квеста живёт ровно в одном месте — правило 7 контракта.

    До этого она жила в шести копиях: behavior.md плюс пять скиллов актов и
    хаб. Прибивал её текст ровно один тест (`test_contract.py`), и о скиллах
    он ничего не знал — шесть копий разошлись бы молча. Это тот же класс
    дефекта, что долг №11: у одного текста должен быть один владелец.
    Указателю разрешено механику называть; запрещено её излагать заново.
    """
    offenders = [
        path.parent.name
        for path in sorted(PLUGIN.glob("skills/*/SKILL.md"))
        if ECHO_MARKERS.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], "вторая формулировка механики в скиллах: {}".format(
        offenders
    )


def test_no_skill_claims_the_padawan_types_files():
    """Скилл не имеет права утверждать, что файлы падаван набирает руками.

    `act1-poisk-boli/SKILL.md:96` говорил «Файлы падаван пишет сам» — прямо
    против правила 8 контракта, по которому модель пишет после подтверждения
    плана, а суперсила падавана в том, чтобы точно назвать, что должно быть
    в файле. Противоречие прожило до живого прогона, и ни один из 690 тестов
    его не заметил.
    """
    offenders = [
        path.parent.name
        for path in sorted(PLUGIN.glob("skills/*/SKILL.md"))
        if TYPES_FILES.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], "скилл велит падавану набирать файлы руками: {}".format(
        offenders
    )


def test_book_answer_command_named_in_every_act_skill():
    """input() из cli.py невозможен: TTY нет. Ответ про Голокрон пишет
    только ручка, и назвать её обязан скилл — иначе вопрос без ответа."""
    missing = []
    for info in sorted(ranks.ACTS.values(), key=lambda item: item["slug"]):
        text = (PLUGIN / "skills" / info["slug"] / "SKILL.md").read_text(
            encoding="utf-8"
        )
        if "book yes" not in text or "book no" not in text:
            missing.append(info["slug"])
    assert missing == [], "скиллы не называют ручку book: {}".format(missing)


def test_both_subcommand_lists_name_every_subcommand():
    """Парадные списки падавана обязаны знать все тринадцать подкоманд.

    `test_every_subcommand_is_documented` собирает имена со всех markdown
    плагина разом, поэтому `book` числился задокументированным по упоминанию
    `book yes` в скиллах актов — а оба списка, которые модель читает, когда
    ищет, чем записать ответ, его не знали: в `commands/start.md` не было
    `book`, в блоке «Команды» хаба — ещё и `artifact`, `link`, `sync`.
    """
    missing = []
    for path in (
        PLUGIN / "commands" / "start.md",
        PLUGIN / "skills" / "core" / "SKILL.md",
    ):
        named = subcommands_in(path)
        missing += [
            "{}: {}".format(path.name, name)
            for name in cli.SUBCOMMANDS
            if name not in named
        ]
    assert missing == [], "парадный список не называет подкоманды: {}".format(missing)


def test_hub_skill_documents_project_two_word_verbs():
    """`project` — двусловные подкоманды: одинарный regex CALL их не ловит,
    и test_every_subcommand_is_documented считает `project` документированным
    по одному упоминанию слова, даже если конкретная ручка (например, `port`)
    в хабе не названа вовсе."""
    hub = (PLUGIN / "skills" / "core" / "SKILL.md").read_text(encoding="utf-8")
    for verb in ("project path", "project db", "project port"):
        assert verb in hub, "хаб не называет `{}`".format(verb)


#: Слово игры в кавычках — «начинаем» или „начинаем“ внутри цитаты.
SAY_WORD = re.compile(r"[«„]{}[»“]".format(re.escape(cli.SAY_START)))


def test_the_next_act_is_offered_with_the_word_of_the_game():
    """Полоса и подсказка в поле ввода говорят «начинаем» (`cli.SAY_START`),
    а модель звала «Скажи «да»» — живая приёмка 0.11.0 (#122). Слово одно:
    его называют вход в игру, ядро и финал каждого акта, за которым есть
    следующий."""
    texts = {
        "start.md": (PLUGIN / "commands" / "start.md").read_text(encoding="utf-8"),
        "core": (PLUGIN / "skills" / "core" / "SKILL.md").read_text(encoding="utf-8"),
    }
    for number in ranks.playable_acts():
        if number == ranks.FINAL_ACT:
            continue
        slug = ranks.ACTS[number]["slug"]
        skill = (PLUGIN / "skills" / slug / "SKILL.md").read_text(encoding="utf-8")
        texts[slug] = skill.split("## Финал акта", 1)[1]
    for name, text in texts.items():
        assert SAY_WORD.search(text), name
        assert "Продолжим сейчас или в другой день?" not in text, name

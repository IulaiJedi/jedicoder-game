import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from test_act1_walkthrough import (
    ACK, ACT1_FILES, ACT1_PROJECT, SCRIPTED, WORDS_FIRST, close_act1,
)

from jedicoder import acts, cli, content, quests, ranks, state as st

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "plugin" / "hooks"


@pytest.fixture
def paths(tmp_path, content_root, quests_root):
    return {
        "state_path": tmp_path / "state.json",
        "content_root": content_root,
        "quests_root": quests_root,
    }


def _seeker_state():
    """Сохранение того, кто закрыл Акт 1: ранг Искатель, трек выбран."""
    data = st.default_state("local-test")
    data["passport"] = {"track": "craftsman"}
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    return data


def run(argv, paths, capsys):
    code = cli.main(argv, **paths)
    return code, capsys.readouterr().out


def _start_act(paths, act):
    """Завести акт в состоянии напрямую, в обход ranks.enter_act.

    Пишет только state["acts"][str(act)] — ту же форму записи, что и
    ranks.enter_act для этого под-объекта (status/quests), но, в отличие от
    него, НЕ трогает state["current_act"] и state["artifacts"]: юнит-тестам
    этого файла они не нужны, а порядок входа в акты (и то, что enter сам их
    выставляет) проверяют test_check_requires_entering_act,
    test_ack_requires_entering_act и сквозные тесты в test_act1_walkthrough.py
    / test_act2_walkthrough.py. Здесь достаточно факта «акт начат», который
    с Задачи 5 требует guard _act_started в cli.py.
    """
    data = st.load(paths["state_path"])
    data.setdefault("acts", {})[str(act)] = {"status": "in_progress", "quests": {}}
    st.save(data, paths["state_path"])


PHANTOM_ACT = {
    "slug": "act6-phantom", "title": "Фантом",
    "artifact": "phantom", "rank": "master",
}


def _with_phantom_act(monkeypatch):
    """Акт, который есть в реестре актов, но без квестов.

    С Актом 5 таких в поставке не осталось; guard «квесты не завезены»
    обязан пережить это — следующая версия игры снова породит такой акт.
    Патчатся оба модуля: acts.py держит собственную ссылку на ACTS.
    """
    phantom = dict(ranks.ACTS)
    phantom[6] = PHANTOM_ACT
    monkeypatch.setattr(ranks, "ACTS", phantom)
    monkeypatch.setattr(acts, "ACTS", phantom)


def test_subcommands_declared():
    assert cli.SUBCOMMANDS == (
        "status", "contract", "enter", "check", "seen", "ack", "project", "track",
        "artifact", "debrief", "scroll", "link", "sync", "finale", "book",
        "root", "reset", "recipe",
    )


def test_status_on_fresh_state(paths, capsys):
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Юнлинг" in out
    assert "Акт 1" in out
    assert "Знакомство" in out


def test_status_hides_zero_xp(paths, capsys):
    """Начисление XP приезжает только с хуками A2. До тех пор «XP: 0» —
    счётчик, который никогда не двигается, и читается как сломанная механика.
    """
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "XP" not in out


def test_status_creates_padawan_id(paths, capsys):
    run(["status"], paths, capsys)
    data = st.load(paths["state_path"])
    assert data["padawan_id"].startswith("local-")


def test_status_shows_rank_and_counters_after_progress(paths, capsys):
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    ranks.enter_act(data, 2)
    data["xp"] = 55
    data["dark_side"] = 2
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Искатель" in out
    assert "55" in out
    assert "Штрафы: 2" in out
    assert "plan" in out


def test_default_roots_exist_on_disk():
    """Раскладка путей держится ни на чём: cli.py ищет content/ на три
    каталога вверх от себя. Переезд content/ или plugin/ ломает contract на
    живой установке, а суита этого не видит.
    """
    assert cli.DEFAULT_CONTENT_ROOT.is_dir(), cli.DEFAULT_CONTENT_ROOT
    assert (cli.DEFAULT_CONTENT_ROOT / "behavior.md").is_file()
    assert cli.DEFAULT_QUESTS_ROOT.is_dir(), cli.DEFAULT_QUESTS_ROOT
    assert (cli.DEFAULT_QUESTS_ROOT / "act2-chertezh").is_dir()


def test_marketplace_manifest_points_at_plugin():
    """Без marketplace.json в корне репозитория плагин нечем установить."""
    manifest = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    assert manifest["name"]
    entries = manifest["plugins"]
    sources = [entry["source"] for entry in entries]
    assert "./plugin" in sources
    for entry in entries:
        assert (ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()


def test_contract_missing_behavior_explains_instead_of_traceback(paths, capsys, tmp_path):
    empty = tmp_path / "нет-контента"
    empty.mkdir()
    code = cli.main(
        ["contract"],
        state_path=paths["state_path"],
        content_root=empty,
        quests_root=paths["quests_root"],
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "behavior.md" in out
    assert "переустанови" in out.lower()


def test_contract_broken_behavior_explains(paths, capsys, tmp_path):
    broken = tmp_path / "битый"
    broken.mkdir()
    (broken / "behavior.md").write_text("нет фронтматтера\n", encoding="utf-8")
    code = cli.main(
        ["contract"],
        state_path=paths["state_path"],
        content_root=broken,
        quests_root=paths["quests_root"],
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "испорчен" in out


def test_contract_unknown_passport_knob_explains(paths, capsys):
    data = st.default_state("local-test")
    data["passport"] = {"track": "инопланетянин"}
    st.save(data, paths["state_path"])
    code, out = run(["contract"], paths, capsys)
    assert code == 1
    assert "настройках" in out
    assert "track" in out


def test_project_path_is_stored_absolute(paths, capsys, project, monkeypatch):
    """Относительный путь позже разрешится от чужого каталога.

    Проверено вручную: с записанным «.» проверка 04-git-init из каталога
    выше говорила «запусти git init» на репозитории с коммитом.
    """
    proj = project(git=True, commits=1)
    monkeypatch.chdir(proj)
    code, out = run(["project", "path", "."], paths, capsys)
    assert code == 0
    stored = st.load(paths["state_path"])["project"]["path"]
    assert Path(stored).is_absolute()
    assert Path(stored) == proj.resolve()

    _start_act(paths, 2)
    monkeypatch.chdir(proj.parent)
    code, out = run(["check", "2", "04-git-init"], paths, capsys)
    assert code == 0, out


def test_project_port_is_stored(paths, capsys):
    code, out = run(["project", "port", "8000"], paths, capsys)
    assert code == 0
    assert "8000" in out
    data = st.load(paths["state_path"])
    assert data["project"]["port"] == 8000


def test_project_port_rejects_garbage(paths, capsys):
    for bad in ("abc", "0", "65536", "-1"):
        code, out = run(["project", "port", bad], paths, capsys)
        assert code == 1, bad
        assert "1" in out and "65535" in out
    data = st.load(paths["state_path"])
    assert "port" not in (data.get("project") or {})


def test_project_status_shows_port(paths, capsys):
    run(["project", "port", "3000"], paths, capsys)
    code, out = run(["project"], paths, capsys)
    assert code == 0
    assert "3000" in out


def test_project_deploy_is_stored(paths, capsys):
    code, out = run(["project", "deploy", "vps"], paths, capsys)
    assert code == 0
    assert "vps" in out
    data = st.load(paths["state_path"])
    assert data["project"]["deploy_path"] == "vps"


def test_project_deploy_rejects_garbage(paths, capsys):
    run(["project", "deploy", "managed"], paths, capsys)
    code, out = run(["project", "deploy", "heroku"], paths, capsys)
    assert code == 1
    assert "managed" in out and "vps" in out
    data = st.load(paths["state_path"])
    assert data["project"]["deploy_path"] == "managed", \
        "мусор не должен затирать выбор"


def test_project_ssh_is_stored(paths, capsys):
    code, out = run(["project", "ssh", "myvps"], paths, capsys)
    assert code == 0
    assert "myvps" in out
    data = st.load(paths["state_path"])
    assert data["project"]["ssh_alias"] == "myvps"


def test_project_ssh_rejects_option_looking_alias(paths, capsys):
    # Алиас уходит аргументом в ssh: строка, начинающаяся с «-», стала бы
    # опцией (-oProxyCommand=…) — это инъекция команды, а не алиас.
    for bad in ("-oProxyCommand=evil", "два слова", "a/b", ""):
        code, _ = run(["project", "ssh", bad], paths, capsys)
        assert code == 1, bad
    data = st.load(paths["state_path"])
    assert "ssh_alias" not in (data.get("project") or {})


def test_project_status_shows_deploy_and_ssh(paths, capsys, all_acts_open):
    code, out = run(["project"], paths, capsys)
    assert "Путь деплоя: не назван" in out
    run(["project", "deploy", "vps"], paths, capsys)
    run(["project", "ssh", "myvps"], paths, capsys)
    code, out = run(["project"], paths, capsys)
    assert code == 0
    assert "Путь деплоя: vps" in out
    assert "SSH-алиас: myvps" in out


def test_status_counts_quests_against_declared_total(paths, capsys, project, old_acts_open):
    """Знаменатель — из реестра акта, а не из записанных квестов.

    Найдено прогоном по пути падавана: после первого закрытого квеста карта
    писала «квестов закрыто: 1/1», то есть недопройденный акт выглядел
    пройденным.
    """
    proj = project(files=ACT1_FILES, **ACT1_PROJECT)
    assert run(["project", "path", str(proj)], paths, capsys)[0] == 0
    assert run(["enter", "1"], paths, capsys)[0] == 0
    assert run(["check", "1", SCRIPTED[0]], paths, capsys)[0] == 0
    _start_act(paths, 2)
    assert run(["check", "2", "04-git-init", str(proj)], paths, capsys)[0] == 0
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Акт 2. Чертёж — идёт, квестов закрыто: 1/6" in out
    assert "Акт 1. Знакомство — идёт, квестов закрыто: 1/5" in out


def test_contract_renders_with_passport(paths, capsys):
    data = st.default_state("local-test")
    data["passport"] = {"track": "founder", "explain_depth": "max"}
    st.save(data, paths["state_path"])
    code, out = run(["contract"], paths, capsys)
    assert code == 0
    assert "нулевым опытом" in out
    assert "на рынок" in out


def test_enter_act_persists(paths, capsys):
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "Знакомство" in out
    assert "brainstorm" in out
    data = st.load(paths["state_path"])
    assert data["acts"]["1"]["status"] == "in_progress"


# --- Голокрон: катсцена, ссылка, разовый вопрос ------------------------

def _book_line(out):
    for line in out.splitlines():
        if line.startswith("Книга — "):
            return line
    return None


def test_enter_prints_cutscene_from_content(paths, capsys, content_root):
    """Тело катсцены сверяется с контент-ядром, а не с вырезанной строкой:
    иначе тест ломается на первой же правке текста, ничего не доказав."""
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    scene = next(item for item in content.load_acts(content_root) if item.act == 1)
    assert scene.body in out


def test_enter_prints_cutscene_without_link_key(paths, capsys):
    """CUT-04: повествование — часть игры, а не награда за привязку."""
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert st.load(paths["state_path"])["link_key"] is None
    assert "знакомишься с Claude Code" in out


def test_enter_prints_book_link_without_key(paths, capsys, monkeypatch):
    """Ссылка на Книгу — после первого ранга (ADR-0014): порог — ранг, а не
    номер акта, поэтому Искатель слышит её и на входе в Акт 1."""
    monkeypatch.setenv("JEDICODER_SITE_URL", "https://example.test")
    st.save(_seeker_state(), paths["state_path"])
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert _book_line(out) == "Книга — те же акты страницами в браузере: https://example.test/kniga"


def test_enter_prints_book_link_with_key(paths, capsys, monkeypatch):
    """Ключ уходит сегментом пути: explorer.exe не открывает URL с '?'."""
    monkeypatch.setenv("JEDICODER_SITE_URL", "https://example.test")
    monkeypatch.setenv("JEDICODER_SYNC_URL", "http://127.0.0.1:1/x")
    st.save(_seeker_state(), paths["state_path"])
    assert run(["link", "testkey1"], paths, capsys)[0] == 0
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert _book_line(out) == "Книга — те же акты страницами в браузере: https://example.test/kniga/testkey1/1"


def test_book_url_names_the_act(monkeypatch):
    """Страж LOOP-04: у каждой главы свой адрес.

    В живом прогоне `enter 2` напечатал ту же ссылку, что `enter 1`, и падаван
    открыл главу первого акта, войдя во второй: номер акта в адрес не уезжал
    вовсе. Долг BOOK-07 был объявлен закрытым при зелёном суите — потому что
    ни один тест не сравнивал два адреса между собой.

    Без ключа номер не подставляется намеренно: /kniga/2 попал бы в роут
    kniga/:linkKey, «2» прочиталось бы как ключ, и вместо витрины падаван
    получил бы «Эта глава не открылась».
    """
    monkeypatch.setenv("JEDICODER_SITE_URL", "https://example.test")
    linked = {"link_key": "testkey1"}
    first = cli._book_url(linked, 1)
    second = cli._book_url(linked, 2)
    assert first != second
    assert first == "https://example.test/kniga/testkey1/1"
    assert second == "https://example.test/kniga/testkey1/2"
    assert cli._book_url(linked) == "https://example.test/kniga/testkey1"
    assert cli._book_url({"link_key": None}, 2) == "https://example.test/kniga"


def test_inside_golokron_book_is_not_offered(paths, capsys, monkeypatch):
    """Внутри десктопного Голокрона Книга в браузере не предлагается.

    Живой прогон 2026-09-10: падаван в Голокроне на входе в акт читал
    «Голокрон — книга твоего пути в браузере, открывать?» — приложение, в
    котором он сидит, предлагало открыть само себя в браузере. Сцена справа
    показывает то же, что Книга; ни ссылки, ни вопроса, ни вкладки.
    Флаг «спрошено» не ставится: выйдя в обычный терминал, падаван вопрос
    услышит.
    """
    monkeypatch.setenv(cli.GOLOKRON_MARK, "1")
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "Акт 1." in out
    assert "book yes" not in out
    assert "Книга" not in out
    assert "браузер" not in out
    assert "book_asked" not in st.load(paths["state_path"]) or \
        st.load(paths["state_path"])["book_asked"] is not True


# --- Тип продукта и рецепты (прогон падаваном 2026-09-10) ---
#
# Три рецепта лежали в контент-ядре, линтер их валидировал, тесты прибивали
# состав — и ни одна команда их не показывала. Ручки типа не было вовсе, а в
# контракт модели всегда уходило «Тип продукта: unknown». Квест 01 Акта 2 при
# этом велит «выбрать стек по рецепту своего типа продукта».

def test_project_type_writes_and_shows(paths, capsys):
    code, out = run(["project", "type", "telegram-bot"], paths, capsys)
    assert code == 0
    assert "Телеграм-бот" in out
    assert st.load(paths["state_path"])["project"]["type"] == "telegram-bot"
    code, out = run(["project"], paths, capsys)
    assert code == 0
    assert "Телеграм-бот" in out


def test_project_type_rejects_unknown_and_keeps_previous(paths, capsys):
    run(["project", "type", "landing"], paths, capsys)
    code, out = run(["project", "type", "квадрокоптер"], paths, capsys)
    assert code == 1
    assert "telegram-bot" in out and "landing" in out and "web-service" in out
    # Мусор не затирает выбор — то же правило, что у трека и пути деплоя.
    assert st.load(paths["state_path"])["project"]["type"] == "landing"


def test_project_type_names_the_deploy_path_the_recipe_expects(paths, capsys):
    """Рецепт знает путь деплоя; падавану про это говорят сразу, а не в Акте 4."""
    code, out = run(["project", "type", "web-service"], paths, capsys)
    assert code == 0
    assert "vps" in out


def test_recipe_prints_the_recipe_of_the_chosen_type(paths, capsys):
    run(["project", "type", "telegram-bot"], paths, capsys)
    code, out = run(["recipe"], paths, capsys)
    assert code == 0
    assert "Телеграм-бот" in out
    assert "aiogram" in out
    # Тело рецепта, а не только заголовок: грабли и есть главное в нём.
    assert "грабел" in out.lower()
    # Служебные пометки линтера адресованы автору, а не падавану.
    assert "lint:" not in out


def test_recipe_without_type_lists_what_there_is(paths, capsys):
    code, out = run(["recipe"], paths, capsys)
    assert code == 0
    assert "telegram-bot" in out and "landing" in out and "web-service" in out
    assert "project type" in out


def test_recipe_by_name_without_choosing(paths, capsys):
    """Посмотреть чужой рецепт можно, не назначая его себе: падаван выбирает
    из трёх, а не вслепую."""
    code, out = run(["recipe", "landing"], paths, capsys)
    assert code == 0
    assert "Лендинг" in out
    assert st.load(paths["state_path"]).get("project", {}).get("type") is None


def test_contract_carries_the_chosen_type(paths, capsys):
    run(["project", "type", "web-service"], paths, capsys)
    code, out = run(["contract"], paths, capsys)
    assert code == 0
    assert "Тип продукта: web-service" in out
    assert "unknown" not in out


def test_reset_without_confirm_changes_nothing(paths, capsys):
    """«Начни заново», сказанное вскользь, не стирает путь: без подтверждения
    ручка только показывает, что уйдёт в архив."""
    data = st.default_state("local-test")
    data["xp"] = 80
    st.save(data, paths["state_path"])
    before = Path(paths["state_path"]).read_bytes()
    code, out = run(["reset"], paths, capsys)
    assert code == 0
    assert "reset confirm" in out
    assert "XP: 80" in out
    assert Path(paths["state_path"]).read_bytes() == before


def test_reset_confirm_archives_save_next_to_it(paths, capsys):
    """Архив, а не удаление: файл переименован рядом с датой в имени, содержимое
    то же, и назван путь обратно."""
    data = st.default_state("local-test")
    data["xp"] = 80
    st.save(data, paths["state_path"])
    before = Path(paths["state_path"]).read_bytes()
    code, out = run(["reset", "confirm"], paths, capsys)
    assert code == 0
    assert not Path(paths["state_path"]).exists()
    archives = list(Path(paths["state_path"]).parent.glob("state.json.arhiv-*"))
    archives = [a for a in archives if not a.name.endswith(".bak")]
    assert len(archives) == 1
    assert archives[0].read_bytes() == before
    assert str(archives[0]) in out
    assert "mv " in out
    # Дальше — чистый лист: первый экран новичка.
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Юнлинг" in out and "XP" not in out


def test_reset_confirm_names_lost_link_and_events(paths, capsys):
    data = st.default_state("local-test")
    data["link_key"] = "abcd1234"
    data["pending_sync"] = [{"type": "x"}, {"type": "y"}]
    st.save(data, paths["state_path"])
    code, out = run(["reset", "confirm"], paths, capsys)
    assert code == 0
    assert "link <ключ>" in out
    assert "было 2" in out


def test_reset_without_save_is_a_no_op(paths, capsys):
    code, out = run(["reset", "confirm"], paths, capsys)
    assert code == 0
    assert "нечего" in out
    assert list(Path(paths["state_path"]).parent.glob("state.json.arhiv-*")) == []


def test_reset_inside_golokron_says_to_restart(paths, capsys, monkeypatch):
    """Голокрон закрывает Подготовку в одну сторону: заново спросить папку он
    сможет только с перезапуска, и об этом говорится сразу."""
    monkeypatch.setenv(cli.GOLOKRON_MARK, "1")
    st.save(st.default_state("local-test"), paths["state_path"])
    code, out = run(["reset", "confirm"], paths, capsys)
    assert code == 0
    assert "закрой Голокрон" in out


def test_book_question_asked_once(paths, capsys):
    st.save(_seeker_state(), paths["state_path"])
    code, first = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "book yes" in first and "Книга" in first
    assert st.load(paths["state_path"])["book_asked"] is True
    code, again = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "book yes" not in again


def test_book_handle_records_answer(paths, capsys):
    assert run(["book", "yes"], paths, capsys)[0] == 0
    assert st.load(paths["state_path"])["book_open"] is True
    assert run(["book", "no"], paths, capsys)[0] == 0
    assert st.load(paths["state_path"])["book_open"] is False


def test_book_handle_rejects_garbage_without_touching_state(paths, capsys):
    run(["book", "yes"], paths, capsys)
    code, out = run(["book", "maybe"], paths, capsys)
    assert code == 1
    assert "yes" in out and "no" in out
    assert st.load(paths["state_path"])["book_open"] is True


def test_book_without_args_reports_current_answer(paths, capsys):
    code, out = run(["book"], paths, capsys)
    assert code == 0
    assert "не отвечено" in out
    run(["book", "yes"], paths, capsys)
    code, out = run(["book"], paths, capsys)
    assert code == 0 and "открывается сам" in out


def test_missing_opener_binary_changes_nothing(paths, capsys, monkeypatch):
    """HAND-03: не сработало — печатаем ссылку и молчим."""
    monkeypatch.setattr(cli, "_openers", lambda: [["net-takogo-binarya"]])
    run(["track", "craftsman"], paths, capsys)
    run(["book", "yes"], paths, capsys)
    capsys.readouterr()
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "net-takogo-binarya" not in out


def test_opener_raising_oserror_changes_nothing(paths, capsys, monkeypatch):
    """Popen может не запуститься — это не повод ронять вход в акт."""
    def boom(*args, **kwargs):
        raise OSError("не запустилось")

    monkeypatch.setattr(cli, "_openers", lambda: [["sh"]])
    monkeypatch.setattr(cli.subprocess, "Popen", boom)
    run(["track", "craftsman"], paths, capsys)
    run(["book", "yes"], paths, capsys)
    capsys.readouterr()
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "не запустилось" not in out


def test_opener_exploding_anywhere_is_swallowed(paths, capsys, monkeypatch):
    """Закон хуков, применённый к опенеру: чужой сбой не мешает падавану.

    _open_in_browser сам себя и стережёт — снаружи его исход не проверяет
    никто, поэтому проверяем именно то, что он ничего не выпускает наружу.
    """
    def boom(*args, **kwargs):
        raise RuntimeError("совсем всё сломалось")

    monkeypatch.setattr(cli.shutil, "which", boom)
    run(["track", "craftsman"], paths, capsys)
    run(["book", "yes"], paths, capsys)
    capsys.readouterr()
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "сломалось" not in out


def test_open_in_browser_never_raises(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("любой сбой")

    monkeypatch.setattr(cli, "_openers", boom)
    assert cli._open_in_browser("https://example.test/kniga") is None


def test_broken_act_content_does_not_break_enter(paths, capsys, tmp_path):
    """T-01-03: битый контент отнимает абзац, а не вход в акт."""
    broken_root = tmp_path / "content"
    (broken_root / "acts").mkdir(parents=True)
    (broken_root / "acts" / "act1-znakomstvo.md").write_text(
        "тут нет фронтматтера\n", encoding="utf-8"
    )
    local = dict(paths)
    local["content_root"] = broken_root
    code, out = run(["enter", "1"], local, capsys)
    assert code == 0
    assert "Знакомство" in out
    assert "Квесты акта" in out
    assert st.load(paths["state_path"])["acts"]["1"]["status"] == "in_progress"


def test_passport_snapshot_carries_deploy_path(paths, capsys):
    """Pitfall 8: без deploy_path книга нарисует чужую ветку Акта 4."""
    data = st.load(paths["state_path"])
    assert cli._passport_snapshot(data)["deploy_path"] is None
    data["project"] = {"deploy_path": "vps"}
    assert cli._passport_snapshot(data)["deploy_path"] == "vps"


def test_enter_blocked_act_reports_reason(paths, capsys, old_acts_open):
    code, out = run(["enter", "3"], paths, capsys)
    assert code == 1
    assert "Акт 2" in out


def test_enter_unknown_act(paths, capsys):
    code, out = run(["enter", "9"], paths, capsys)
    assert code == 1
    assert "нет акта" in out


def test_enter_second_act_requires_first_closed(paths, capsys, old_acts_open):
    # Порядок актов жёсткий: без закрытого Акта 1 вход во второй запрещён.
    code, out = run(["enter", "2"], paths, capsys)
    assert code == 1
    assert "Акт 1" in out

    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    st.save(data, paths["state_path"])
    code, out = run(["enter", "2"], paths, capsys)
    assert code == 0
    assert "Чертёж" in out


def test_enter_act_without_quests_refuses(paths, capsys, monkeypatch):
    """Акт-фантом существует в реестре актов, но квестов для него нет.

    Раньше вход туда разрешался: игра объявляла акт начатым, выдавала
    артефакт, а первый же check отвечал «квесты ещё не завезены». Скилл при
    этом обязан акты 6+ не обещать — а CLI их раздавал.
    """
    _with_phantom_act(monkeypatch)
    data = st.default_state("local-test")
    for act in (1, 2, 3, 4, 5):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    st.save(data, paths["state_path"])

    code, out = run(["enter", "6"], paths, capsys)
    assert code == 1
    assert "Фантом" in out, "акт надо назвать по имени, а не номером"
    assert "пока нет" in out
    after = st.load(paths["state_path"])
    assert "6" not in after["acts"], "отказанный вход не начинает акт"
    assert "phantom" not in (after.get("artifacts") or [])


def test_artifact_of_unwritten_act_stays_locked(paths, capsys, monkeypatch):
    """Второе следствие того же входа: артефакт без скилла отвечал «открыт».

    Когда /phantom появится, он отпёрся бы у падавана, который акт-фантом
    не проходил.
    """
    _with_phantom_act(monkeypatch)
    data = st.default_state("local-test")
    for act in (1, 2, 3, 4, 5):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    st.save(data, paths["state_path"])
    run(["enter", "6"], paths, capsys)
    assert run(["artifact", "phantom"], paths, capsys)[0] == 1


def test_enter_blocked_act_still_explains_the_order_first(paths, capsys, old_acts_open):
    """Не закрыл Акт 2 — слышишь про Акт 2, а не про ненаписанный Акт 3.

    Порядок отказов важен: про то, что Акта 3 ещё нет, человек узнает,
    когда дойдёт.
    """
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    st.save(data, paths["state_path"])
    code, out = run(["enter", "3"], paths, capsys)
    assert code == 1
    assert "Акт 2" in out


def test_ack_closes_quest(paths, capsys):
    # С Задачи 5 ack требует enter (закрыт долг «check и ack закрывали акт
    # без входа в него») — акт заводится напрямую в состоянии, а не через
    # enter: этот тест проверяет закрытие ack-квеста, а не порядок входа в
    # акт, его проверяют test_ack_requires_entering_act и сквозные тесты.
    _start_act(paths, 2)
    code, out = run(["ack", "2", "06-pipeline"], paths, capsys)
    assert code == 0
    # Квест назван так, как его зовёт человек: кода на экране нет (#83).
    assert out.startswith("Квест «") and "06-pipeline" not in out
    data = st.load(paths["state_path"])
    assert data["acts"]["2"]["quests"]["06-pipeline"]["status"] == "done"


def test_ack_refuses_script_quest(paths, capsys):
    """Скриптовый квест нельзя закрыть словом: исход решает exit-код.

    Без этого ранг Падаван выдавался за шесть подтверждений подряд, включая
    05-env-guard — квест, который как раз и проверяет, что секреты защищены.
    """
    _start_act(paths, 2)
    code, out = run(["ack", "2", "05-env-guard"], paths, capsys)
    assert code == 1
    assert "есть проверка. Словами его не закрыть" in out
    assert "05-env-guard" not in out
    data = st.load(paths["state_path"])
    assert data["acts"]["2"]["quests"] == {}, "отказ не должен создавать запись квеста"


def test_ack_rejects_unknown_act(paths, capsys):
    code, out = run(["ack", "99", "01-x"], paths, capsys)
    assert code == 1
    assert "нет акта" in out
    assert st.load(paths["state_path"])["acts"] == {}


def test_ack_rejects_act_without_quests(paths, capsys, monkeypatch):
    # Акт 6 существует в ranks.ACTS, но для него ещё не объявлены квесты —
    # это отдельная причина отказа от «акт не начат», поэтому акт заводится
    # напрямую: guard пропускает дальше, а _quest_kind объясняет про квесты.
    _with_phantom_act(monkeypatch)
    _start_act(paths, 6)
    code, out = run(["ack", "6", "01-x"], paths, capsys)
    assert code == 1
    assert "Акта 6" in out
    assert st.load(paths["state_path"])["acts"]["6"]["quests"] == {}


def test_ack_rejects_unknown_quest_and_lists_real_ones(paths, capsys):
    _start_act(paths, 2)
    code, out = run(["ack", "2", "06-pipelien"], paths, capsys)
    assert code == 1
    assert "06-pipeline" in out
    assert st.load(paths["state_path"])["acts"]["2"]["quests"] == {}


def test_check_rejects_typo_in_quest_id(paths, capsys, project):
    """Опечатка — не «квест без проверки», иначе её закроют подтверждением."""
    proj = project(git=True, commits=1)
    _start_act(paths, 2)
    code, out = run(["check", "2", "04-git-nit", str(proj)], paths, capsys)
    assert code == 1
    assert "04-git-init" in out
    assert "ack" not in out
    assert st.load(paths["state_path"])["acts"]["2"]["quests"] == {}


def test_check_on_ack_quest_sends_to_ack(paths, capsys, project):
    proj = project(git=True, commits=1)
    _start_act(paths, 2)
    code, out = run(["check", "2", "06-pipeline", str(proj)], paths, capsys)
    assert code == 1
    assert "нет проверки. Его закрывает рассказ" in out
    assert "06-pipeline" not in out


def test_check_requires_entering_act(tmp_path, quests_root, project, capsys):
    """Без входа в акт квест не проверяется.

    Раньше check не требовал enter — это был долг движка. Без этой защиты
    Акт 2 закрывается, минуя Акт 1: артефакт выдаётся, а трек так и не
    спрошен, и падаван не знает, из каких квестов состоит его игра.
    """
    proj = project(files={"CLAUDE.md": "# Проект\n\n" + "текст " * 60})
    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)
    cli.main(["project", "path", str(proj)], state_path=state_path)

    assert cli.main(
        ["check", "2", "02-claude-md"],
        state_path=state_path, quests_root=quests_root,
    ) == 1
    out = capsys.readouterr().out
    assert "Акт 2 ещё не начат. Сначала войди в него." in out
    assert st.load(state_path)["acts"] == {}


def test_ack_requires_entering_act(tmp_path, capsys):
    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)
    assert cli.main(["ack", "2", "06-pipeline"], state_path=state_path) == 1
    assert "Акт 2 ещё не начат. Сначала войди в него." in capsys.readouterr().out
    assert st.load(state_path)["acts"] == {}


def test_check_allowed_in_closed_act(tmp_path, quests_root, project):
    """Перепройти проверку в закрытом акте нормально — это не обход порядка."""
    proj = project(files=ACT1_FILES, **ACT1_PROJECT)
    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)

    def jc(*argv):
        return cli.main(list(argv), state_path=state_path, quests_root=quests_root)

    jc("project", "path", str(proj))
    close_act1(jc)
    assert st.load(state_path)["acts"]["1"]["status"] == "done"

    assert jc("check", "1", SCRIPTED[0]) == 0, "закрытый акт не должен запрещать проверку"


def test_last_quest_closes_act_one_and_opens_act_two(paths, capsys, project, old_acts_open):
    """Живой путь: последний квест Акта 1 закрывает акт, дальше открыт Акт 2.

    Закрывает акт та же команда, которой закрыт его последний квест, —
    отдельной команды «закрыть акт» нет. У Акта 1 «Знакомство» последний
    квест подтверждается словами, поэтому акт закрывает `ack`.

    Вторая половина — про дверь, которая сегодня закрыта (`MUTED_ACTS`):
    порядок актов обязан пережить день, когда Акт 2 вернётся.
    """
    proj = project(files=ACT1_FILES, **ACT1_PROJECT)
    assert run(["project", "path", str(proj)], paths, capsys)[0] == 0
    assert run(["enter", "1"], paths, capsys)[0] == 0
    for quest_id in SCRIPTED:
        if quest_id == WORDS_FIRST:
            assert run(["seen", "1", quest_id], paths, capsys)[0] == 0
        assert run(["check", "1", quest_id], paths, capsys)[0] == 0, quest_id
    code, out = run(["ack", "1", ACK], paths, capsys)
    assert code == 0
    assert "Искатель" in out
    data = st.load(paths["state_path"])
    assert data["acts"]["1"]["status"] == "done"
    assert data["rank"] == "seeker"
    code, out = run(["enter", "2"], paths, capsys)
    assert code == 0
    assert "Чертёж" in out


def test_closing_act_announces_rank_from_state(paths, capsys, project):
    """Объявленный ранг обязан совпадать с рангом в состоянии.

    Проверено прогоном: закрыв Акт 2 в обход Акта 1, игра печатала «Новый
    ранг: Падаван», а в состоянии оставался youngling — ранг считается по
    непрерывной цепочке закрытых актов. Именно этот обход и был долгом
    движка «check и ack закрывали акт без входа в него»; с Задачи 5 CLI сам
    его не допускает (test_check_requires_entering_act,
    test_ack_requires_entering_act), поэтому Акт 2 здесь заводится напрямую в
    состоянии — тест защищает инвариант «объявленный ранг из state», а не
    достижимость обхода через интерфейс падавана.
    """
    proj = project(
        files={"ARCHITECTURE.md": "# А\n\n## Стек\n\n" + "текст " * 200,
               "CLAUDE.md": "# П\n\n" + "текст " * 100},
        gitignore=".env\n", git=True, commits=1,
    )
    assert run(["project", "path", str(proj)], paths, capsys)[0] == 0
    assert run(["project", "db", "no"], paths, capsys)[0] == 0
    _start_act(paths, 2)
    for quest_id in ("01-recipe", "02-claude-md", "03-db-schema",
                     "04-git-init", "05-env-guard"):
        assert run(["check", "2", quest_id], paths, capsys)[0] == 0, quest_id
    code, out = run(["ack", "2", "06-pipeline"], paths, capsys)
    assert code == 0
    assert "Акт 2. Чертёж — закрыт." in out
    assert "Падаван" not in out, "ранг Падаван без закрытого Акта 1 не выдаётся"
    assert "Новый ранг: Юнлинг." in out
    assert st.load(paths["state_path"])["rank"] == "youngling"


# --- Прогон новичком Актов 2–3, #73 «Перед выпуском» ----------------------

def _act_line(out, number):
    return next(l for l in out.splitlines() if "Акт {}.".format(number) in l)


def test_map_keeps_quiet_about_deploy_until_act3_is_closed(paths, capsys, old_acts_open):
    """Строка пути деплоя у Акта 4 новичку ни о чём: до Акта 4 два акта, а
    слова «хостинг» и «сервер» он ещё не слышал. До закрытия Акта 3 у Акта 4
    только название."""
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert _act_line(out, 4) == "  Акт 4. Щит — не начат"
    assert "project deploy" not in out
    st.save(_seeker_state(), paths["state_path"])
    _, out = run(["status"], paths, capsys)
    assert _act_line(out, 4) == "  Акт 4. Щит — не начат"


def test_map_asks_for_deploy_once_the_act_is_current(old_acts_open):
    """Второе условие строки: текущий акт дошёл до развилки, даже если запись
    о закрытом Акте 3 потеряна (сохранение правили руками)."""
    data = st.default_state("local-test")
    data["current_act"] = 4
    out = cli.render_status(data, None, None)
    assert "где будет жить продукт" in _act_line(out, 4)
    data["current_act"] = 3
    assert _act_line(cli.render_status(data, None, None), 4) == "  Акт 4. Щит — не начат"


def test_map_names_the_recipes_deploy_path(paths, capsys, old_acts_open):
    """Тип продукта выбран — строка называет путь рецепта, как `project`."""
    _close_acts(paths, 3)
    assert run(["project", "type", "telegram-bot"], paths, capsys)[0] == 0
    _, out = run(["status"], paths, capsys)
    line = _act_line(out, 4)
    assert "где будет жить продукт" in line
    assert "Телеграм-бот" in line
    assert "project deploy managed" in line
    assert "project deploy vps" not in line


BOT_URL = "https://t.me/Jedicoderstore_bot"


def test_enter_names_the_bot_by_link(paths, capsys):
    """«Ключ выдаёт бот командой /link» — какой бот, новичок не знает."""
    st.save(_seeker_state(), paths["state_path"])
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if "/link" in l)
    assert BOT_URL in line
    assert "разворот" not in out


def test_link_and_sync_name_the_bot_by_link(paths, capsys):
    code, out = run(["link"], paths, capsys)
    assert code == 1
    assert BOT_URL in out
    code, out = run(["sync"], paths, capsys)
    assert code == 1
    assert BOT_URL in out


def test_reset_names_the_bot_by_link(paths, capsys):
    """Ключ уехал в архив — где взять новый, строка говорит тем же адресом."""
    data = st.default_state("local-test")
    data["link_key"] = "abcd1234"
    st.save(data, paths["state_path"])
    code, out = run(["reset", "confirm"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if "link <ключ>" in l)
    assert BOT_URL in line


@pytest.mark.parametrize("doc", ["plugin/commands/start.md", "plugin/skills/core/SKILL.md"])
def test_markdown_names_the_same_bot_as_cli(doc):
    """Описание ручки link для модели — тем же адресом, что печатает CLI:
    копия в markdown иначе разошлась бы с движком молча."""
    text = (ROOT / doc).read_text(encoding="utf-8")
    assert "/link" in text
    assert cli.BOT_URL in text


def test_book_no_does_not_say_spread(paths, capsys):
    code, out = run(["book", "no"], paths, capsys)
    assert code == 0
    assert "разворот" not in out


@pytest.mark.parametrize("state", [
    lambda: st.default_state("local-test"),
    _seeker_state,
])
def test_status_names_rank_without_slug(paths, capsys, state):
    """«Ранг: Искатель (seeker)» — слаг ушёл на экран падавана."""
    data = state()
    st.save(data, paths["state_path"])
    _, out = run(["status"], paths, capsys)
    title = ranks.RANK_TITLES[data["rank"]]
    # У ранга новичка в той же строке пояснение — «Юнлинг» слово игры.
    assert out.splitlines()[0].split(" — ")[0] == "Ранг: {}".format(title)
    assert "({})".format(data["rank"]) not in out


def test_enter_marks_ack_quests_in_words(paths, capsys, old_acts_open):
    """Квест без проверки помечен прямо в списке: иначе падаван будет гонять
    check там, где нужен ack (в прогоне так и было с 04m-guard).

    Помечен словами, а не ручкой: « (без проверки: ack 2 06-pipeline)»
    новичок читал как команду себе. Ручку `ack` модель знает из скилла."""
    st.save(_seeker_state(), paths["state_path"])
    _, out = run(["enter", "2"], paths, capsys)
    marked = [l for l in out.splitlines() if l.endswith(" — подтверждается словами")]
    assert len(marked) == 1
    assert "ack" not in marked[0] and "06-pipeline" not in marked[0]
    # Квесты с проверкой не помечены: строка списка у них — номер и название.
    assert marked[0].startswith("  6. ")


def test_status_survives_broken_notices_entry(paths, capsys):
    """Битый элемент в notices не должен ронять самую частую команду игры.

    Проверка «notices — список» есть, а на то, что его элементы вообще
    годятся в ключи словаря, — нет: словарь или список внутри даёт
    TypeError: unhashable type. Требует испорченного руками JSON, но
    трейсбек в лицо новичку недопустим в любом случае.
    """
    data = st.default_state("local-test")
    data["notices"] = [{"мусор": 1}, ["тоже мусор"], st.NOTICE_GAME_REBUILT]
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Ранг:" in out
    assert "порядок актов изменился" in out, "годное объяснение всё равно показано"
    assert st.load(paths["state_path"])["notices"] == []


def test_status_stays_quiet_for_untouched_progress(paths, capsys):
    """Ничего не отобрали — не о чем и говорить."""
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "порядок актов изменился" not in out


def test_check_reports_failures_and_persists_attempt(paths, capsys, project):
    proj = project(files={}, git=False)
    _start_act(paths, 2)
    code, out = run(["check", "2", "04-git-init", str(proj)], paths, capsys)
    assert code == 1
    assert "Репозитор" in out
    data = st.load(paths["state_path"])
    assert data["acts"]["2"]["quests"]["04-git-init"]["attempts"] == 1


def test_check_success_closes_quest(paths, capsys, project):
    proj = project(git=True, commits=1)
    _start_act(paths, 2)
    code, out = run(["check", "2", "04-git-init", str(proj)], paths, capsys)
    assert code == 0
    assert "закрыт" in out
    data = st.load(paths["state_path"])
    assert data["acts"]["2"]["quests"]["04-git-init"]["status"] == "done"
    assert data["first_try"]["passed"] == 1


def test_check_shows_loop_protocol_on_third_failure(paths, capsys, project):
    proj = project(files={}, git=False)
    _start_act(paths, 2)
    for _ in range(2):
        run(["check", "2", "04-git-init", str(proj)], paths, capsys)
    code, out = run(["check", "2", "04-git-init", str(proj)], paths, capsys)
    assert code == 1
    assert "по кругу" in out


def test_check_timeout_not_counted_as_attempt(paths, capsys, project, monkeypatch):
    # Контроллерская доработка: run_check может повиснуть (ssh, curl в
    # поздних актах) и поднять subprocess.TimeoutExpired. Падаван должен
    # получить русское объяснение, а не сырой traceback, и попытка не
    # должна засчитаться — это не его ошибка.
    proj = project(files={}, git=False)
    _start_act(paths, 2)

    def fake_run_check(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="bash check.sh", timeout=60)

    monkeypatch.setattr(quests, "run_check", fake_run_check)
    code, out = run(["check", "2", "04-git-init", str(proj)], paths, capsys)
    assert code == 1
    assert "слишком долго" in out
    assert "не засчитана" in out
    data = st.load(paths["state_path"])
    assert (
        data["acts"].get("2", {}).get("quests", {}).get("04-git-init", {}).get(
            "attempts", 0
        )
        == 0
    )


def test_check_reports_crashed_script_as_cannot_check(paths, capsys, project, monkeypatch):
    """Код 127 — инфраструктурный сбой, а не непройденный квест."""
    proj = project(git=True, commits=1)
    _start_act(paths, 2)

    def fake_run_check(*args, **kwargs):
        return quests.CheckResult(
            quest="04-git-init", kind=quests.KIND_SCRIPT, exit_code=127, ok=False,
            checks=(), stderr="", countable=False,
        )

    monkeypatch.setattr(quests, "run_check", fake_run_check)
    code, out = run(["check", "2", "04-git-init", str(proj)], paths, capsys)
    assert code == 1
    assert "Не смог проверить" in out
    assert "127" in out
    assert "не засчитана" in out
    data = st.load(paths["state_path"])
    assert data["acts"]["2"]["quests"]["04-git-init"]["attempts"] == 0


def test_root_prints_plugin_root(paths, capsys, tmp_path):
    marker = tmp_path / "plugin_root"
    marker.write_text("/somewhere/jedicoder\n", encoding="utf-8")
    code = cli.main(["root"], plugin_root_path=marker, **paths)
    assert code == 0
    assert "/somewhere/jedicoder" in capsys.readouterr().out


def test_root_missing_marker_explains(paths, capsys, tmp_path):
    code = cli.main(["root"], plugin_root_path=tmp_path / "nope", **paths)
    assert code == 1
    assert "перезапусти" in capsys.readouterr().out.lower()


def test_artifact_locked_before_act(tmp_path, capsys):
    from jedicoder import cli
    from jedicoder import state as st

    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)
    assert cli.main(["artifact", "brainstorm"], state_path=state_path) == 1
    assert "brainstorm" in capsys.readouterr().out


def test_artifact_unlocked_after_entering_act1(tmp_path):
    from jedicoder import cli
    from jedicoder import state as st

    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)
    assert cli.main(["track", "craftsman"], state_path=state_path) == 0
    assert cli.main(["enter", "1"], state_path=state_path) == 0
    assert cli.main(["artifact", "brainstorm"], state_path=state_path) == 0


def test_artifact_of_later_act_stays_locked(tmp_path):
    from jedicoder import cli
    from jedicoder import state as st

    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)
    cli.main(["track", "craftsman"], state_path=state_path)
    cli.main(["enter", "1"], state_path=state_path)
    assert cli.main(["artifact", "deploy"], state_path=state_path) == 1


def test_artifact_unknown_name_is_a_bug_not_a_lock(tmp_path, capsys):
    """Неизвестное имя — баг вызывающего скилла, и это должно быть видно."""
    from jedicoder import cli
    from jedicoder import state as st

    state_path = tmp_path / "state.json"
    st.save(st.default_state(), state_path)
    assert cli.main(["artifact", "lightsaber"], state_path=state_path) == 1
    assert "нет такого приёма" in capsys.readouterr().out.lower()


def test_artifact_without_name(tmp_path):
    from jedicoder import cli

    assert cli.main(["artifact"], state_path=tmp_path / "state.json") == 1


def test_artifact_is_in_subcommands():
    from jedicoder import cli

    assert "artifact" in cli.SUBCOMMANDS


def test_unknown_subcommand(paths, capsys):
    code, out = run(["полёт"], paths, capsys)
    assert code == 1
    assert "неизвестная команда" in out.lower()


def test_no_subcommand_prints_usage(paths, capsys):
    code, out = run([], paths, capsys)
    assert code == 1
    assert "status" in out


def _fake_plugin_root(tmp_path):
    """Каталог, похожий на установленный плагин: с lib/jedicoder/cli.py."""
    root = tmp_path / "plugins" / "jedicoder"
    (root / "lib" / "jedicoder").mkdir(parents=True)
    (root / "lib" / "jedicoder" / "cli.py").write_text("# заглушка\n", encoding="utf-8")
    return root


def _run_hook(marker, root, payload="{}"):
    env = {"JEDICODER_PLUGIN_ROOT_FILE": str(marker), "PATH": "/usr/bin:/bin"}
    if root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(root)
    return subprocess.run(
        ["python3", str(HOOKS / "session_start.py")],
        input=payload, capture_output=True, text=True, env=env,
    )


def test_session_start_hook_writes_plugin_root(tmp_path):
    marker = tmp_path / "plugin_root"
    root = _fake_plugin_root(tmp_path)
    payload = json.dumps({"hook_event_name": "SessionStart", "cwd": str(tmp_path)})
    result = _run_hook(marker, root, payload)
    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8").strip() == str(root)


def test_session_start_hook_ignores_root_without_cli(tmp_path):
    """Устаревший корень писать нельзя: скиллы получат «can't open file».

    Так уже ломалась игра один раз; после обновления или переноса плагина
    сломалась бы снова, только через устаревание маркера.
    """
    marker = tmp_path / "plugin_root"
    marker.write_text("/старый/корень\n", encoding="utf-8")
    result = _run_hook(marker, tmp_path / "уехавший-плагин")
    assert result.returncode == 0
    assert marker.read_text(encoding="utf-8").strip() == "/старый/корень"


def test_hooks_json_covers_resume(tmp_path):
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    matcher = config["hooks"]["SessionStart"][0]["matcher"]
    for event in ("startup", "clear", "compact", "resume"):
        assert event in matcher


def test_session_start_hook_silent_without_env(tmp_path):
    marker = tmp_path / "plugin_root"
    result = subprocess.run(
        ["python3", str(HOOKS / "session_start.py")],
        input="{}", capture_output=True, text=True,
        env={"JEDICODER_PLUGIN_ROOT_FILE": str(marker), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0
    assert not marker.exists()


def test_session_start_hook_survives_unreadable_stdin(tmp_path):
    # На этой платформе python3 без LANG/LC_ALL сам уходит в UTF-8 mode и
    # читает stdin с errors="surrogateescape" — невалидные байты молча
    # проглатываются, sys.stdin.read() не падает. Чтобы честно воспроизвести
    # сценарий «stdin не в UTF-8» (он реален на других локалях/контейнерах),
    # декодирование форсируется в строгий режим через PYTHONIOENCODING.
    marker = tmp_path / "plugin_root"
    result = subprocess.run(
        ["python3", str(HOOKS / "session_start.py")],
        input=b"\xff\xfe not utf-8",
        capture_output=True,
        env={
            "CLAUDE_PLUGIN_ROOT": "/plugins/jedicoder",
            "JEDICODER_PLUGIN_ROOT_FILE": str(marker),
            "PATH": "/usr/bin:/bin",
            "PYTHONIOENCODING": "utf-8:strict",
        },
    )
    assert result.returncode == 0
    assert result.stderr == b""


def test_plugin_manifest_valid():
    manifest = json.loads(
        (ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "jedicoder"
    assert manifest["version"]
    assert manifest["description"]


def test_hooks_json_wires_session_start():
    config = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))
    entries = config["hooks"]["SessionStart"]
    command = entries[0]["hooks"][0]["command"]
    assert "${CLAUDE_PLUGIN_ROOT}" in command
    assert "session_start.py" in command


def test_claude_md_sha_of_project(tmp_path):
    proj = tmp_path / "p"
    proj.mkdir()
    assert cli._claude_md_sha(proj) == ""
    (proj / "CLAUDE.md").write_text("память проекта\n", encoding="utf-8")
    sha = cli._claude_md_sha(proj)
    assert len(sha) == 40
    # содержимое то же — sha тот же (git hash-object детерминирован)
    assert cli._claude_md_sha(proj) == sha


def test_claude_md_sha_matches_in_repo_hashing(tmp_path, monkeypatch):
    """Хэш обязан считаться из каталога проекта: git hash-object применяет
    eol-фильтры репозитория, найденного от cwd, и хэш «снаружи» расходится
    с хэшем check.sh, считающим изнутри проекта."""
    proj = tmp_path / "p"
    proj.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(proj), check=True)
    (proj / ".gitattributes").write_text("*.md text eol=crlf\n", encoding="utf-8")
    # write_bytes, не write_text: платформенная трансляция \n могла бы сама
    # подсунуть CRLF или съесть его. CRLF нужен взаправду — clean-фильтр
    # eol=crlf на LF-содержимом no-op, и тест не отличил бы старый cwd-баг
    # от исправления (оба хэша совпали бы одинаково на пустой операции).
    (proj / "CLAUDE.md").write_bytes("# Память\r\nстрока\r\n".encode("utf-8"))
    monkeypatch.chdir(tmp_path)  # cwd НЕ проект
    outside = cli._claude_md_sha(proj)
    inside = subprocess.run(
        ["git", "hash-object", "CLAUDE.md"], cwd=str(proj),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert outside == inside


def test_env_for_check_passes_port_and_prev_sha():
    data = st.default_state("local-test")
    assert cli._env_for(data, 3) == {}
    data["project"] = {"port": 8000, "has_db": True}
    data["acts"] = {"2": {"status": "done", "claude_md_sha": "abc123"}}
    env = cli._env_for(data, 3)
    assert env["JEDICODER_PORT"] == "8000"
    assert env["JEDICODER_PREV_CLAUDE_MD_SHA"] == "abc123"
    assert env["JEDICODER_HAS_DB"] == "yes"
    # для другого акта sha берётся у его предыдущего
    assert "JEDICODER_PREV_CLAUDE_MD_SHA" not in cli._env_for(data, 2)


def test_enter_backfills_prev_act_sha(paths, capsys, project, old_acts_open):
    proj = project(files={"CLAUDE.md": "# Проект\n"})
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    ranks.close_act(data, 1)  # закрыт библиотекой — sha не записан
    data["project"] = {"path": str(proj)}
    st.save(data, paths["state_path"])

    code, _ = run(["enter", "2"], paths, capsys)
    assert code == 0
    reloaded = st.load(paths["state_path"])
    assert len(reloaded["acts"]["1"]["claude_md_sha"]) == 40


def _close_acts(paths, up_to):
    data = st.load(paths["state_path"])
    if not data.get("padawan_id"):
        data["padawan_id"] = "local-test"
    for act in range(1, up_to + 1):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    st.save(data, paths["state_path"])


def test_enter_act4_without_deploy_asks_for_it(paths, capsys, old_acts_open):
    _close_acts(paths, 3)
    code, out = run(["enter", "4"], paths, capsys)
    assert code == 1
    assert "project deploy" in out
    assert "managed" in out and "vps" in out
    after = st.load(paths["state_path"])
    assert "4" not in after["acts"], "отказанный вход не начинает акт"
    assert "cso" not in (after.get("artifacts") or [])


def test_enter_act4_with_deploy_starts_and_grants_cso(paths, capsys, old_acts_open):
    _close_acts(paths, 3)
    run(["project", "deploy", "managed"], paths, capsys)
    code, out = run(["enter", "4"], paths, capsys)
    assert code == 0
    assert "Щит" in out
    assert "cso" in out
    data = st.load(paths["state_path"])
    assert data["acts"]["4"]["status"] == "in_progress"
    assert "cso" in data["artifacts"]


def test_status_map_asks_for_deploy_on_act4(paths, capsys, old_acts_open):
    """Строка звучит с закрытым Актом 3 (#73) и уходит, когда путь назван."""
    _close_acts(paths, 3)
    code, out = run(["status"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if "Акт 4." in l)
    assert "где будет жить продукт" in line
    assert "project deploy managed" in line and "project deploy vps" in line
    run(["project", "deploy", "vps"], paths, capsys)
    code, out = run(["status"], paths, capsys)
    assert "где будет жить продукт" not in out
    assert "0/5" in out


def test_check_act4_quest_without_deploy_explains(paths, capsys):
    _close_acts(paths, 3)
    _start_act(paths, 4)
    code, out = run(["check", "4", "01-remote"], paths, capsys)
    assert code == 1
    assert "project deploy" in out


def test_env_for_passes_ssh_alias():
    assert cli._env_for(
        {"project": {"ssh_alias": "myvps"}}, 4
    )["JEDICODER_SSH_ALIAS"] == "myvps"
    assert "JEDICODER_SSH_ALIAS" not in cli._env_for({"project": {}}, 4)
    # Ведущий «-» в ssh_alias возможен только правкой state.json руками —
    # но и тогда он не должен доехать до ssh опцией.
    assert "JEDICODER_SSH_ALIAS" not in cli._env_for(
        {"project": {"ssh_alias": "-oProxyCommand=evil"}}, 4
    )


def test_project_url_is_stored(paths, capsys):
    code, out = run(["project", "url", "https://myapp.example"], paths, capsys)
    assert code == 0
    data = st.load(paths["state_path"])
    assert data["project"]["url"] == "https://myapp.example"


def test_project_url_rejects_garbage(paths, capsys):
    for bad in ("myapp.example", "ftp://x", "https://a b", "",
                "https://a\tb", "https://a\nb"):
        code, _ = run(["project", "url", bad], paths, capsys)
        assert code == 1, bad
    assert "url" not in (st.load(paths["state_path"]).get("project") or {})


def test_project_service_is_stored_and_validated(paths, capsys):
    assert run(["project", "service", "myapp"], paths, capsys)[0] == 0
    assert st.load(paths["state_path"])["project"]["service"] == "myapp"
    for bad in ("-oProxy", "два слова", "a/b", "", "a$(touch pwned)", "a;b", "юнит"):
        code, _ = run(["project", "service", bad], paths, capsys)
        assert code == 1, bad
    assert st.load(paths["state_path"])["project"]["service"] == "myapp", \
        "мусор не должен затирать выбор"


def test_project_post_is_stored(paths, capsys):
    code, _ = run(["project", "post", "https://vc.ru/p/123"], paths, capsys)
    assert code == 0
    assert st.load(paths["state_path"])["project"]["post_url"] == "https://vc.ru/p/123"
    assert run(["project", "post", "не-ссылка"], paths, capsys)[0] == 1


def test_project_status_shows_url(paths, capsys, all_acts_open):
    code, out = run(["project"], paths, capsys)
    assert "URL продукта: не назван" in out
    run(["project", "url", "https://myapp.example"], paths, capsys)
    run(["project", "service", "myapp"], paths, capsys)
    run(["project", "post", "https://vc.ru/p/123"], paths, capsys)
    code, out = run(["project"], paths, capsys)
    assert "URL продукта: https://myapp.example" in out
    assert "Сервис: myapp" in out
    assert "Публикация: https://vc.ru/p/123" in out


def test_env_for_passes_act5_values():
    env = cli._env_for({"project": {
        "url": "https://myapp.example/", "service": "myapp",
        "post_url": "https://vc.ru/p/1", "deploy_path": "vps",
    }}, 5)
    assert env["JEDICODER_URL"] == "https://myapp.example", \
        "хвостовой / срезается — скрипты клеят к URL пути"
    assert env["JEDICODER_SERVICE"] == "myapp"
    assert env["JEDICODER_POST_URL"] == "https://vc.ru/p/1"
    assert env["JEDICODER_DEPLOY_PATH"] == "vps"
    empty = cli._env_for({"project": {}}, 5)
    for key in ("JEDICODER_URL", "JEDICODER_SERVICE",
                "JEDICODER_POST_URL", "JEDICODER_DEPLOY_PATH"):
        assert key not in empty
    # Рукописный state.json не должен доехать до команд опасным значением.
    # Тест 1: ведущий дефис (ssh-опция вместо алиаса).
    dirty = cli._env_for({"project": {"service": "-oEvil", "url": "нет"}}, 5)
    assert "JEDICODER_SERVICE" not in dirty
    assert "JEDICODER_URL" not in dirty
    # Тест 2: метасимволы (command injection в удалённом shell).
    dirty_meta = cli._env_for({"project": {"service": "a$(x)"}}, 5)
    assert "JEDICODER_SERVICE" not in dirty_meta


def test_finale_refuses_before_master(paths, capsys):
    code, out = run(["finale"], paths, capsys)
    assert code == 1
    assert "Юнлинг" in out


def test_finale_draws_master_card(paths, capsys, all_acts_open):
    data = st.default_state("local-test")
    for act in (1, 2, 3, 4, 5):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    data["project"] = {"url": "https://myapp.example"}
    data["lexicon_unlocked"] = ["deploy", "dns"]
    data["xp"] = 120
    st.save(data, paths["state_path"])
    code, out = run(["finale"], paths, capsys)
    assert code == 0
    assert "Мастер" in out
    assert "https://myapp.example" in out
    assert "Дней в пути: 1" in out
    assert "Слов открыто: 2" in out
    assert "XP: 120" in out


def test_finale_card_survives_missing_url_and_dates(paths, capsys, all_acts_open):
    data = st.default_state("local-test")
    for act in (1, 2, 3, 4, 5):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
        # у бет прошлых версий started_at нет
        data["acts"][str(act)].pop("started_at", None)
    st.save(data, paths["state_path"])
    code, out = run(["finale"], paths, capsys)
    assert code == 0
    assert "Дней в пути" not in out
    assert "Продукт:" not in out


# --- Первый экран: жаргон, до которого линтер контента не дотягивается. ---


def _loot_hook():
    """Матчер хука лута — тот же, которым слова подсвечиваются падавану."""
    sys.path.insert(0, str(HOOKS))
    import lexicon_loot

    return lexicon_loot


def test_first_screen_has_no_late_terms(paths, capsys, content_root):
    """Первый экран не произносит слов, которые объясняются позже.

    Прибор фазы — контент-линтер — ходит по content/ru и до Python-литералов
    render_status не дотягивается никогда. Именно здесь и стоял самый громкий
    дефект LANG-02: «Серия коммитов» на первом же экране, а слово «коммит»
    объясняется только в Акте 2. Расширять линтер на cli.py отвергнуто —
    чтение литералов регулярками хрупко (тот же класс ошибки, что долг №10);
    закрывается тестом.
    """
    loot = _loot_hook()
    code, out = run(["status"], paths, capsys)
    assert code == 0

    late = []
    for term in content.load_terms(content_root):
        if term.act < 2:
            continue
        for alias in term.aliases:
            if loot._alias_pattern(alias).search(out):
                late.append((term.term, alias))
    assert late == []


def test_status_never_says_commit(paths, capsys):
    """Именованный дефект прогона: слово «коммит» с первого экрана.

    Отдельным тестом, а не внутри предыдущего: тот падёт и от любого другого
    позднего слова, а этот называет ровно тот случай, который нашёл живой
    падаван.
    """
    data = st.default_state("local-test")
    # Счётчик серии на нуле молчит, поэтому слово надо чем-то вызвать: имя
    # проверяется у появившегося счётчика, а не у отсутствующего.
    data["streak"] = {"current": 2, "best": 3}
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "коммит" not in out.lower()
    assert "Серия сохранений" in out


def test_first_screen_hides_zero_counters(paths, capsys):
    """Первый экран новичка не перечисляет нули.

    Живой заход 2026-09-10: падаван впервые открыл игру и получил список из
    пяти незнакомых величин — Тёмная сторона 0, серия 0 (лучшая 0) — и прочёл
    его как приборную панель чужого самолёта. Правило для XP было записано
    давно и обосновано теми же словами; здесь оно распространено на остальные.
    """
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Штрафы" not in out
    assert "Серия сохранений" not in out
    # Ранг при этом на месте: он не счётчик, он ответ на «кто я сейчас».
    assert "Юнлинг" in out


def test_first_screen_shows_dark_side_once_earned(paths, capsys):
    """Появившееся очко называется сразу: молчит нуль, а не механика."""
    data = st.default_state("local-test")
    data["dark_side"] = 1
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Штрафы: 1" in out


def test_first_screen_names_both_costs_when_no_path(paths, capsys):
    """Пути нет вовсе: первый экран называет следствие и лечение.

    Молчание здесь читается как «игра знает, где мой проект» — а она не
    знает. Квесты Акта 1 без названной папки не закрыть. Второе следствие —
    защитный хук стережёт только записанную папку — на экране не звучит
    (#87): «не защитит твои файлы» пугало человека, который ещё ничего не
    сделал. О нём знает модель из скилла акта.
    """
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Папка проекта ещё не названа." in out
    assert "игра не проверит квесты" in out
    assert "не защитит" not in out and "удал" not in out
    # Про серию здесь ни слова: счётчик на нуле молчит, а слово «серия» без
    # объяснения на первом экране читалось как поломка (прогон 2026-09-12).
    assert "серия" not in out.lower()
    # Лечение — словами: ручку `project path` знает модель из скилла (#83).
    assert "скажешь Claude, где лежит твой проект" in out
    assert "project path" not in out


def test_first_screen_names_the_project_folder(paths, capsys, tmp_path):
    """Папка на месте: первый экран называет её и ничем не пугает.

    Дверь та же, в которую входит падаван: сначала project path, потом
    status — а не засев пути прямо в сохранение.
    """
    project_dir = tmp_path / "moy-produkt"
    project_dir.mkdir()
    code, _ = run(["project", "path", str(project_dir)], paths, capsys)
    assert code == 0

    code, out = run(["status"], paths, capsys)
    assert code == 0
    # Именем, без дороги до папки (#87).
    assert "Папка проекта: moy-produkt" in out.splitlines()
    assert str(tmp_path) not in out
    assert "не найдена" not in out


def test_first_screen_warns_when_project_folder_is_gone(paths, capsys, tmp_path):
    """Главный случай тикета: путь в сохранении есть, папки по нему нет.

    Так выглядел живой заход 2026-09-06: путь указывал на песочницу прошлой
    сессии, карта показывала «0 из 6» на сделанном акте, серия стояла на
    нуле, и выяснять это пришлось через файловую систему. Первый экран
    обязан назвать причину сам.
    """
    project_dir = tmp_path / "pesochnica"
    project_dir.mkdir()
    code, _ = run(["project", "path", str(project_dir)], paths, capsys)
    assert code == 0
    project_dir.rmdir()

    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Папка проекта не найдена: pesochnica" in out.splitlines()
    assert str(tmp_path) not in out
    assert "Скажи Claude, где проект лежит теперь." in out
    assert "project path" not in out


def test_render_status_takes_the_folder_fact_as_a_parameter():
    """Три случая — словарями, без единого обращения к диску.

    Диск читает вызывающий (_cmd_status), render_status остаётся чистой
    функцией от сохранения. Доказательство здесь и есть: на пути, которого
    заведомо нет, экран спокоен, когда ему сказали «есть». Иначе тесты
    первого экрана зависели бы от того, что лежит на машине с pytest.
    """
    ghost = "/net/net-takoy-papki/nikogda"
    data = st.default_state("local-test")
    data["project"] = {"path": ghost}

    assert "Папка проекта: nikogda\n" in cli.render_status(data, True, None)
    assert "Папка проекта не найдена: nikogda\n" in cli.render_status(
        data, False, None
    )
    assert "Папка проекта ещё не названа." in cli.render_status(
        st.default_state("local-test"), None, None
    )

    # Факт обязателен: умолчание вернуло бы в сигнатуру то самое молчание,
    # ради которого заведён тикет — на мёртвом пути экран сказал бы
    # успокаивающее «Папка проекта: X».
    with pytest.raises(TypeError):
        cli.render_status(data)
    # Рецепт — второй факт мимо сохранения (его читает _cmd_status), и он
    # обязателен по той же причине: забытый рецепт молча дал бы общую строку.
    with pytest.raises(TypeError):
        cli.render_status(data, True)


@pytest.mark.parametrize("project", [{"path": ["/tmp"]}, {"path": ""}, []])
def test_first_screen_reads_a_broken_project_path_as_none(paths, capsys,
                                                          project):
    """Сохранение правили руками: путь не строка, пуст или раздела нет.

    Мусор читается как отсутствие — тем же правилом, что track_of и
    deploy_of в acts.py. Двумя причинами: Path() на списке роняет TypeError
    в самой частой команде игры, а напечатанный как есть список выдал бы
    падавану «Папка проекта: ['/tmp']» — питоновский литерал, поданный как
    исправный путь, то есть ложное успокоение вместо предупреждения.
    """
    data = st.default_state("local-test")
    data["project"] = project
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Папка проекта ещё не названа." in out
    assert "[" not in out.split("Карта:")[0]


def test_main_without_a_path_writes_where_the_variable_points(
    tmp_path, content_root, quests_root, monkeypatch, capsys
):
    """Та же дверь, в которую входит падаван: `cli.py status` без пути.

    Именно этот вызов до правки уходил в боевое сохранение автора — долг
    №0. Путь не передан, значит его считает state.state_path(), а не
    прибитый ~/.jedicoder/state.json.
    """
    target = tmp_path / "своя-папка" / "state.json"
    monkeypatch.setenv("JEDICODER_STATE_PATH", str(target))
    code = cli.main(["status"], content_root=content_root, quests_root=quests_root)
    capsys.readouterr()
    assert code == 0
    assert target.exists(), "движок не увидел JEDICODER_STATE_PATH"
    assert json.loads(target.read_text(encoding="utf-8"))["padawan_id"]


# --- Вход в акт печатает состав ветки --------------------------------------

def test_enter_lists_the_quests_of_the_branch(paths, capsys):
    """Падаван после катсцены должен знать, что делать, из самой игры, а не
    из скилла. Печатаются квесты его ветки с подписями из контент-ядра;
    чужой ветки нет. Найдено живым прогоном 2026-09-10: после `enter 4`
    список квестов узнавали из SKILL.md.

    Чужую ветку держат тесты Акта 4 (tests/test_act4_walkthrough.py): у
    Акта 1 развилки нет, и «чужого» в нём не бывает."""
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "Квесты акта (5):" in out
    assert "  1. Папка. " in out
    assert "  3. Первый запрос. " in out
    # Катсцена стоит до списка: две фразы о том, что делаем и зачем, дальше
    # квесты (language.md, «Размеры»). Кодов квестов на экране нет.
    assert out.index("знакомишься с Claude Code") < out.index("Квесты акта")
    assert "01-folder" not in out


def test_project_names_the_recipes_deploy_path_until_chosen(paths, capsys):
    """`recipe` печатал «Путь деплоя: managed», а `project` рядом — «не
    назван»: читалось как противоречие (живой прогон 2026-09-11). Пока путь
    не выбран, `project` называет, чего ждёт рецепт, и ручку."""
    assert run(["project", "type", "telegram-bot"], paths, capsys)[0] == 0
    code, out = run(["project"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if "Путь деплоя" in l)
    assert "не назван" in line and "managed" in line
    assert "project deploy managed" in line
    assert run(["project", "deploy", "vps"], paths, capsys)[0] == 0
    _, out = run(["project"], paths, capsys)
    line = next(l for l in out.splitlines() if "Путь деплоя" in l)
    assert line.strip() == "Путь деплоя: vps"


# --- Простой язык до первого ранга (#67, ADR-0014) ------------------------

# Слова, которым рано звучать до ранга Искатель: заменённые имена и то, что
# объясняется одним предложением после первого ранга (language.md). По
# границе слова, как в линтере: подстрока «бот» ловила бы «работа».
EARLY_FORBIDDEN = tuple(
    re.compile(pattern) for pattern in (
        r"\b[Кк]ниг\w*", r"\b[Пп]ривязк\w*", r"\b[Кк]луб\w*",
        r"\bcraftsman\b", r"\bfounder\b", r"\b[Тт][её]мн\w*\s+сторон\w*",
        r"\b[Аа]ртефакт\w*", r"\b[Сс]вит(?:ок|к[а-я]+)\b", r"\b[Бб]от\w*",
    )
)


def test_youngling_status_and_enter_have_no_late_words(paths, capsys):
    """Первый экран и вход в Акт 1 обходятся без Книги, привязки, клуба,
    внутренних имён треков и заменённых имён (live-прогон 2026-09-12)."""
    code, status = run(["status"], paths, capsys)
    assert code == 0
    code, entered = run(["enter", "1"], paths, capsys)
    assert code == 0
    for out in (status, entered):
        for word in EARLY_FORBIDDEN:
            assert not word.search(out), (word.pattern, out)


def test_youngling_map_does_not_ask_for_track(paths, capsys):
    """У Акта 1 «Знакомство» развилки нет: карта называет счёт, а вопрос
    «для кого продукт» новичку первого вечера не задаётся нигде."""
    code, out = run(["status"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if "Акт 1" in l)
    assert line == "  Акт 1. Знакомство — не начат, квестов закрыто: 0/5"
    assert "для себя" not in out and "для людей" not in out


def test_map_asks_for_track_in_plain_words_where_the_act_branches(
        paths, capsys, monkeypatch):
    """Вопрос остался у акта с развилкой по треку — сегодня это Акт 5, и он
    выключен; дверь открывается здесь, чтобы строка не сгнила."""
    monkeypatch.setattr(ranks, "MUTED_ACTS", ())
    code, out = run(["status"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if "Акт 5" in l)
    assert "для себя" in line and "для людей" in line


def test_muted_act_on_map_does_not_name_the_club(paths, capsys):
    code, out = run(["status"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if "не написан" in l)
    assert line == "  Акты 2–5 ещё не написаны" and "клуб" not in out


def test_status_names_penalties_and_moves(paths, capsys):
    data = _seeker_state()
    data["dark_side"] = 1
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Штрафы: 1" in out
    assert "Приёмы: /jedicoder:brainstorm" in out
    assert "Тёмная сторона" not in out and "Артефакт" not in out


def test_status_explains_the_streak_in_the_same_line(paths, capsys):
    data = st.default_state("local-test")
    data["streak"] = {"current": 2, "best": 3}
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if l.startswith("Серия сохранений:"))
    assert "2" in line and "3" in line
    assert "дней подряд" in line


def test_status_hides_zero_words_and_explains_nonzero(paths, capsys):
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "Открыто слов" not in out
    data = st.default_state("local-test")
    data["lexicon_unlocked"] = ["terminal", "pain"]
    st.save(data, paths["state_path"])
    code, out = run(["status"], paths, capsys)
    assert code == 0
    line = next(l for l in out.splitlines() if l.startswith("Открыто слов:"))
    assert "2" in line and "Новое слово" in line


def test_missing_project_folder_does_not_mention_the_streak(paths, capsys):
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert "серия" not in out.lower()
    assert "Папка проекта ещё не названа." in out


def test_enter_1_does_not_ask_about_the_book(paths, capsys):
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "book yes" not in out
    assert _book_line(out) is None
    assert st.load(paths["state_path"]).get("book_asked") is not True


def test_enter_at_seeker_says_the_book_sentence_and_asks_once(paths, capsys, monkeypatch):
    monkeypatch.setenv("JEDICODER_SITE_URL", "https://example.test")
    st.save(_seeker_state(), paths["state_path"])
    code, first = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "Книга" in first and "book yes" in first and "book no" in first
    assert _book_line(first) == "Книга — те же акты страницами в браузере: https://example.test/kniga"
    assert "link <ключ>" in first
    assert "потока" not in first
    assert st.load(paths["state_path"])["book_asked"] is True
    code, again = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "book yes" not in again


def test_enter_names_the_move_not_the_artifact(paths, capsys):
    code, out = run(["enter", "1"], paths, capsys)
    assert code == 0
    assert "Приём этого акта: /jedicoder:brainstorm" in out


def test_enter_without_track_asks_in_plain_words(paths, capsys, monkeypatch):
    """Отказ входа без трека — у акта с развилкой по треку. Сегодня это
    выключенный Акт 5: Акт 1 «Знакомство» трек не спрашивает вовсе."""
    monkeypatch.setattr(ranks, "MUTED_ACTS", ())
    _close_acts(paths, 4)
    code, out = run(["enter", "5"], paths, capsys)
    assert code == 1
    assert "для себя" in out and "для людей" in out
    assert "track craftsman" in out and "track founder" in out
    assert "5" not in st.load(paths["state_path"])["acts"]


def test_enter_muted_act_does_not_name_the_club(paths, capsys):
    code, out = run(["enter", "5"], paths, capsys)
    assert code == 1
    assert "клуб" not in out and "finale" not in out


def test_artifact_lock_speaks_of_moves(paths, capsys):
    code, out = run(["artifact", "brainstorm"], paths, capsys)
    assert code == 1
    assert "Приём" in out and "ртефакт" not in out
    code, out = run(["artifact", "nope"], paths, capsys)
    assert code == 1
    assert "приёма" in out.lower() and "ртефакт" not in out


# --- Прогон новичком 2026-09-13: слова, которые ушли на экран -------------

def test_track_speaks_human_words_not_internal_names(paths, capsys):
    """«Трек: craftsman» — внутреннее имя, которое модель не произносит, а CLI
    печатал его падавану. Теперь — «для себя» / «для людей»."""
    code, out = run(["track", "craftsman"], paths, capsys)
    assert code == 0
    assert "для себя" in out and "craftsman" not in out
    _, out = run(["track"], paths, capsys)
    assert "для себя" in out and "craftsman" not in out
    run(["track", "founder"], paths, capsys)
    _, out = run(["track"], paths, capsys)
    assert "для людей" in out and "founder" not in out


def test_status_explains_xp_in_the_same_line(paths, capsys):
    data = st.load(paths["state_path"])
    data["xp"] = 60
    st.save(data, paths["state_path"])
    _, out = run(["status"], paths, capsys)
    line = next(l for l in out.splitlines() if l.startswith("Очки:"))
    assert "ранг дают акты, а не очки" in line


# --- Первый экран говорит одно: что делать дальше (спека #75) --------------

def test_first_screen_ends_with_the_next_step_for_a_novice(paths, capsys):
    """Чистая установка: последнее, что читает новичок, — куда идти."""
    code, out = run(["status"], paths, capsys)
    assert code == 0
    assert out.rstrip().splitlines()[-2:] == [
        "Что дальше: начать Акт 1 «Знакомство» — квестов в нём 5.",
        "  Скажи Claude: «начинаем».",
    ]
    assert out.count("Что дальше") == 1


def test_next_step_names_the_open_quest_with_its_title(paths, capsys, project):
    proj = project(files=ACT1_FILES, **ACT1_PROJECT)
    assert run(["project", "path", str(proj)], paths, capsys)[0] == 0
    assert run(["enter", "1"], paths, capsys)[0] == 0
    _, out = run(["status"], paths, capsys)
    assert "Что дальше: квест «Папка» — Акт 1 «Знакомство»." in out
    assert "  Назови папку своего проекта." in out

    for quest_id in SCRIPTED:
        if quest_id == WORDS_FIRST:
            assert run(["seen", "1", quest_id], paths, capsys)[0] == 0
        assert run(["check", "1", quest_id], paths, capsys)[0] == 0
    _, out = run(["status"], paths, capsys)
    assert "Что дальше: квест «Стоп и отмена» — Акт 1 «Знакомство»." in out
    assert "  Останови Claude на ходу и верни всё назад." in out
    assert "ack" not in out and "check" not in out


def test_next_step_after_the_last_act_points_at_the_card_and_the_memo(
        paths, capsys, project):
    proj = project(files=ACT1_FILES, **ACT1_PROJECT)
    assert run(["project", "path", str(proj)], paths, capsys)[0] == 0
    close_act1(lambda *argv: run(list(argv), paths, capsys)[0])
    _, out = run(["status"], paths, capsys)
    assert "Что дальше: следующие акты ещё не написаны." in out
    assert "Памятку в папку проекта положит Claude" in out
    assert "scroll" not in out and "finale" not in out
    assert "enter 2" not in out


def test_next_step_is_silent_while_the_act_waits_for_a_choice(old_acts_open):
    """Состав акта ждёт выбора падавана — об этом уже спросила карта."""
    data = st.default_state("local-test")
    for act in (1, 2, 3):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    assert cli.render_next_step(data, {}) == []
    data["project"] = {"deploy_path": "managed"}
    assert cli.render_next_step(data, {})[0].startswith("Что дальше: начать Акт 4")


def test_next_step_survives_a_hand_edited_save():
    """Мусор в сохранении не роняет самую частую команду игры."""
    for broken in ({"acts": None}, {"acts": "строка"}, {"acts": {"1": "строка"}}):
        lines = cli.render_next_step(broken, {})
        assert lines and lines[0].startswith("Что дальше: начать Акт 1")


def test_next_step_works_without_titles(paths, capsys):
    """Контент испорчен — шаг назван идентификатором, экран не падает."""
    data = st.default_state("local-test")
    ranks.enter_act(data, 1)
    assert cli.render_next_step(data, {})[0] == (
        "Что дальше: квест 01-folder — Акт 1 «Знакомство»."
    )


# --- Выключенные акты: одна строка карты, финал только у конца реестра -----



def test_preparation_phrase_counts_the_range_from_the_registry():
    assert cli.preparing_phrase([5]) == "Акт 5 ещё не написан"
    assert cli.preparing_phrase([2, 3, 4, 5]) == "Акты 2–5 ещё не написаны"
    assert cli.preparing_phrase([2, 3]) == "Акты 2–3 ещё не написаны"
    assert cli.preparing_phrase([2, 4]) == "Акты 2, 4 ещё не написаны"


def _closed_everything(paths):
    data = st.default_state("local-test")
    data["passport"] = {"track": "craftsman"}
    data["project"] = {"deploy_path": "managed"}
    for act in sorted(ranks.ACTS):
        ranks.enter_act(data, act)
        if act != max(ranks.ACTS):
            ranks.close_act(data, act)
    last = max(ranks.ACTS)
    for quest_id in acts.quest_ids(last, acts.branch_of(data, last)):
        data["acts"][str(last)]["quests"][quest_id] = {"status": "done", "attempts": 1}
    st.save(data, paths["state_path"])
    return data, last


def test_closing_the_very_last_act_is_the_end_and_points_at_finale(
        paths, capsys, all_acts_open):
    """Выключенных актов впереди нет — поведение прежнее: это конец игры."""
    data, last = _closed_everything(paths)
    assert cli._maybe_close_act(data, last, paths["state_path"]) is True
    out = capsys.readouterr().out
    assert "Это конец игры." in out
    assert "карточку ранга" in out and "памятку" in out
    assert "finale" not in out and "scroll" not in out
    assert "не написан" not in out

    code, out = run(["finale"], paths, capsys)
    assert code == 0
    assert cli._finale_url() in out
    assert st.load(paths["state_path"])["finale_announced"] is True


def test_closing_the_last_playable_act_before_muted_ones_is_not_the_end(
        paths, capsys, old_acts_open):
    """Тот же случай, что сегодня с Актом 1, на прежней раскладке: закрыт
    четвёртый, пятый готовится — финала нет, зовут только за памяткой."""
    data = st.default_state("local-test")
    data["project"] = {"deploy_path": "managed"}
    for act in (1, 2, 3):
        ranks.enter_act(data, act)
        ranks.close_act(data, act)
    ranks.enter_act(data, 4)
    for quest_id in acts.quest_ids(4, "managed"):
        data["acts"]["4"]["quests"][quest_id] = {"status": "done", "attempts": 1}
    st.save(data, paths["state_path"])
    assert cli._maybe_close_act(data, 4, paths["state_path"]) is True
    out = capsys.readouterr().out
    assert "На этом игра пока кончается: следующие акты ещё не написаны." in out
    assert "Памятку в папку проекта положит Claude" in out
    assert "scroll" not in out and "finale" not in out

    code, out = run(["finale"], paths, capsys)
    assert code == 1
    assert "Игра ещё не кончилась: Акт 5 ещё не написан." in out
    assert cli._finale_url() not in out
    assert not st.load(paths["state_path"]).get("finale_announced")



def test_map_names_a_single_act_in_preparation(paths, capsys, old_acts_open):
    _, out = run(["status"], paths, capsys)
    assert "  Акт 5 ещё не написан" in out.splitlines()
    assert "Выход в свет" not in out



def test_map_has_no_preparation_line_when_nothing_is_muted(
        paths, capsys, all_acts_open):
    _, out = run(["status"], paths, capsys)
    assert "готов" not in out
    assert "Акт 5. Выход в свет" in out



def test_third_failed_attempt_outside_act1_keeps_the_loop_protocol(
        paths, capsys, project, old_acts_open):
    proj = project()
    assert run(["project", "path", str(proj)], paths, capsys)[0] == 0
    _start_act(paths, 2)
    for _ in range(3):
        code, out = run(["check", "2", "02-claude-md"], paths, capsys)
        assert code == 1
    assert "протокол «ИИ ходит по кругу»" in out
    assert "откатись на рабочий коммит" in out

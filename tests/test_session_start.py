"""SessionStart: папка проекта из окружения запуска доезжает до сохранения.

Голокрон запускает Claude Code в режиме без вопросов, а защитный хук
стережёт `.env` только внутри папки, записанной в сохранении. Папку человек
выбрал ещё в Подготовке приложения — она приходит переменной окружения, и
хук старта сессии записывает её раньше первой команды человека (#81).

Хук гоняется отдельным процессом, как его запускает Claude Code: дверь та
же, что у настоящей сессии. Окружение собирается с нуля — `HOME` и путь
сохранения ведут в песочницу теста, иначе хук писал бы в боевое.
"""
import json
import subprocess
from pathlib import Path

import pytest

from jedicoder import state as st

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
HOOKS = PLUGIN / "hooks"

VAR = "JEDICODER_GOLOKRON_PROJECT"
KEY_VAR = "JEDICODER_GOLOKRON_KEY"
# Ключ Голокрона по форме (golokronKey.ts в репозитории сайта, вектор его
# тестов): `GK-` и три группы по четыре знака без 0, 1, O и I.
GOLOKRON_KEY = "GK-3333-3333-333T"


@pytest.fixture
def sandbox(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {
        "home": home,
        "state": home / ".jedicoder" / "state.json",
        "marker": home / ".jedicoder" / "plugin_root",
    }


def _env(sandbox, folder=None, **extra):
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(sandbox["home"]),
        "JEDICODER_STATE_PATH": str(sandbox["state"]),
        "JEDICODER_PLUGIN_ROOT_FILE": str(sandbox["marker"]),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
    }
    if folder is not None:
        env[VAR] = str(folder)
    env.update(extra)
    return env


def _start_session(sandbox, folder=None, **extra):
    payload = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})
    return subprocess.run(
        ["python3", str(HOOKS / "session_start.py")],
        input=payload, capture_output=True, text=True,
        env=_env(sandbox, folder, **extra),
    )


def _run_guard(sandbox, cwd, command):
    payload = json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "tool_input": {"command": command}, "cwd": str(cwd),
    })
    return subprocess.run(
        ["python3", str(HOOKS / "bash_guard.py")],
        input=payload, capture_output=True, text=True, env=_env(sandbox),
    )


def _silent_success(result):
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def _recorded(sandbox):
    return (st.load(sandbox["state"]).get("project") or {}).get("path")


def test_folder_from_launch_reaches_the_save(sandbox, tmp_path):
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    assert not sandbox["state"].exists()

    _silent_success(_start_session(sandbox, folder))

    assert _recorded(sandbox) == str(folder)


def test_session_without_the_variable_creates_no_save(sandbox):
    # Терминал без Голокрона: игра ведёт себя как прежде, сохранение заводит
    # первая команда человека.
    _silent_success(_start_session(sandbox))
    assert not sandbox["state"].exists()


def test_recorded_folder_is_never_replaced(sandbox, tmp_path):
    mine = tmp_path / "moy-produkt"
    other = tmp_path / "drugaya"
    mine.mkdir()
    other.mkdir()
    data = st.default_state("padawan-1")
    data["project"] = {"path": str(mine), "has_db": True}
    data["xp"] = 40
    st.save(data, sandbox["state"])
    before = sandbox["state"].read_bytes()

    _silent_success(_start_session(sandbox, other))

    # До байта: записанное человеком хук не трогает — даже не пересохраняет.
    assert sandbox["state"].read_bytes() == before


def test_existing_progress_survives_when_folder_is_added(sandbox, tmp_path):
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    data = st.default_state("padawan-1")
    data["xp"] = 40
    data["lexicon_unlocked"] = ["commit"]
    st.save(data, sandbox["state"])

    _silent_success(_start_session(sandbox, folder))

    after = st.load(sandbox["state"])
    assert after["project"] == {"path": str(folder)}
    assert after["xp"] == 40
    assert after["lexicon_unlocked"] == ["commit"]
    assert after["padawan_id"] == "padawan-1"


def test_dead_recorded_folder_gives_way(sandbox, tmp_path):
    # Папку по записанному пути удалили: приложение спросило новую и
    # передало её. Со старой сторожу стеречь нечего.
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    data = st.default_state("padawan-1")
    data["project"] = {"path": str(tmp_path / "uzhe-net"), "has_db": True}
    st.save(data, sandbox["state"])

    _silent_success(_start_session(sandbox, folder))

    assert st.load(sandbox["state"])["project"] == {
        "path": str(folder), "has_db": True,
    }


@pytest.mark.parametrize("garbage", [None, "строка", [], 7])
def test_garbage_project_field_reads_as_absent(sandbox, tmp_path, garbage):
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    data = st.default_state("padawan-1")
    data["project"] = garbage
    st.save(data, sandbox["state"])

    _silent_success(_start_session(sandbox, folder))

    assert _recorded(sandbox) == str(folder)


def test_corrupt_save_is_recovered_not_blanked(sandbox, tmp_path):
    # Испорченный файл движок уносит в сторону и берёт копию. Хук обязан
    # дописать папку в восстановленное, а не завести пустое поверх.
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    data = st.default_state("padawan-1")
    data["xp"] = 40
    st.save(data, sandbox["state"])
    st.save(data, sandbox["state"])  # вторая запись кладёт копию рядом
    sandbox["state"].write_text("{не json", encoding="utf-8")

    _silent_success(_start_session(sandbox, folder))

    after = st.load(sandbox["state"])
    assert after["padawan_id"] == "padawan-1"
    assert after["xp"] == 40
    assert after["project"]["path"] == str(folder)


def test_folder_that_contains_home_is_not_a_product_folder(sandbox):
    # `/home` или `/mnt/c`: дом лежит внутри — «в проекте» значило бы «везде».
    _silent_success(_start_session(sandbox, sandbox["home"].parent))
    assert not sandbox["state"].exists()


def test_first_entry_mark_is_left_to_the_first_command(sandbox, tmp_path):
    # По пустому `padawan_id` приложение узнаёт, что человек ещё не набрал
    # первую команду игры: шаг «Первый запуск» обязан остаться на экране.
    # Отметку ставит CLI (`cli._load`), и хук её ставить не вправе.
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    _start_session(sandbox, folder)
    raw = json.loads(sandbox["state"].read_text(encoding="utf-8"))
    assert raw["padawan_id"] is None
    assert raw["pending_sync"] == []


def test_folder_is_recorded_resolved_like_project_path(sandbox, tmp_path):
    # Урок `project path` без resolve(): сторож сравнивает realpath, и папка,
    # записанная через ссылку, читалась бы как «вне проекта».
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    _start_session(sandbox, link)

    assert _recorded(sandbox) == str(real.resolve())


@pytest.mark.parametrize("value", [
    "/нет/такой/папки",
    "relative/dir",
    ".",
    "",
    "   ",
    "/",
    "~",
])
def test_garbage_in_the_variable_writes_nothing(sandbox, value):
    _silent_success(_start_session(sandbox, value))
    assert not sandbox["state"].exists()


def test_a_file_is_not_a_folder(sandbox, tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("x", encoding="utf-8")
    _silent_success(_start_session(sandbox, target))
    assert not sandbox["state"].exists()


def test_home_is_not_a_product_folder(sandbox):
    # Домашний каталог проектом не бывает: сторож не дал бы стереть его и
    # так, а «внутри проекта» означало бы «везде».
    _silent_success(_start_session(sandbox, sandbox["home"]))
    assert not sandbox["state"].exists()


def test_write_failure_is_silent(sandbox, tmp_path):
    # Закон хуков: сохранение не пишется (на его месте в пути стоит файл) —
    # сессия человека стартует как ни в чём не бывало.
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    result = _start_session(
        sandbox, folder, JEDICODER_STATE_PATH=str(blocker / "state.json")
    )
    _silent_success(result)
    # Маркер корня плагина при этом записан: одна беда не отменяет другое дело.
    assert sandbox["marker"].read_text(encoding="utf-8").strip() == str(PLUGIN)


def test_unreadable_plugin_does_not_block_the_session(sandbox, tmp_path):
    # Корень плагина указывает в пустоту — движок не импортируется, писать
    # нечем. Молчим.
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    result = _start_session(
        sandbox, folder, CLAUDE_PLUGIN_ROOT=str(tmp_path / "уехавший-плагин")
    )
    assert result.returncode == 0
    assert result.stderr == ""


def test_plugin_root_marker_is_still_written(sandbox, tmp_path):
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    _start_session(sandbox, folder)
    assert sandbox["marker"].read_text(encoding="utf-8").strip() == str(PLUGIN)


def test_env_is_guarded_before_any_quest(sandbox, project):
    """Критерий тикета: после старта сессии `git add .env` заблокирован,
    хотя человек не набрал ни одной команды игры."""
    folder = project(files={".env": "TOKEN=secret\n"}, git=True, commits=1)

    before = _run_guard(sandbox, folder, "git add .env")
    assert before.stdout == "", "без записанной папки сторож молчит — это и есть окно"

    _start_session(sandbox, folder)

    after = _run_guard(sandbox, folder, "git add .env")
    verdict = json.loads(after.stdout)["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"
    assert ".env" in verdict["permissionDecisionReason"]
    assert st.load(sandbox["state"])["dark_side"] == 2


# --- Ключ Голокрона из окружения запуска (#84) -------------------------
#
# Один ключ вместо двух кодов: человек ввёл Ключ Голокрона в приложении, оно
# передало его запуску, и хук записывает его как связь с ботом — если её ещё
# нет. Бот находит по ключу того, кому его выдал. Игра в терминале без
# приложения переменной не получает и не меняется.

def _link(sandbox):
    return st.load(sandbox["state"]).get("link_key")


def _queued(sandbox, event_type):
    return [
        event for event in st.load(sandbox["state"]).get("pending_sync", [])
        if event["type"] == event_type
    ]


def test_key_from_launch_becomes_the_link(sandbox):
    assert not sandbox["state"].exists()

    _silent_success(_start_session(sandbox, **{KEY_VAR: GOLOKRON_KEY}))

    assert _link(sandbox) == GOLOKRON_KEY


def test_key_from_launch_announces_itself_to_the_bot(sandbox):
    # Бот применяет события пути только после события привязки (проекция
    # в боте: «новее привязки»). Без него ключ записан, а путь не виден.
    data = st.default_state("padawan-1")
    data["xp"] = 40
    st.save(data, sandbox["state"])

    _start_session(sandbox, **{KEY_VAR: GOLOKRON_KEY})

    (linked,) = _queued(sandbox, "linked")
    assert linked["payload"]["xp"] == 40
    assert linked["payload"]["rank"] == "youngling"
    assert linked["payload"]["padawan_id"] == "padawan-1"


def test_key_and_folder_arrive_together(sandbox, tmp_path):
    folder = tmp_path / "moya-igra"
    folder.mkdir()

    _silent_success(_start_session(sandbox, folder, **{KEY_VAR: GOLOKRON_KEY}))

    after = st.load(sandbox["state"])
    assert after["link_key"] == GOLOKRON_KEY
    assert after["project"]["path"] == str(folder)


def test_existing_link_is_never_replaced(sandbox, tmp_path):
    # Человек связал игру с ботом сам — прежним кодом из восьми знаков. Его
    # слово старше: хук не трогает файл вовсе, даже не пересохраняет.
    folder = tmp_path / "moy-proekt"
    folder.mkdir()
    data = st.default_state("padawan-1")
    data["link_key"] = "abcd2345"
    data["project"] = {"path": str(folder)}
    st.save(data, sandbox["state"])
    before = sandbox["state"].read_bytes()

    _silent_success(_start_session(sandbox, folder, **{KEY_VAR: GOLOKRON_KEY}))

    assert sandbox["state"].read_bytes() == before


def test_second_session_with_the_same_key_writes_nothing(sandbox):
    _start_session(sandbox, **{KEY_VAR: GOLOKRON_KEY})
    before = sandbox["state"].read_bytes()

    _silent_success(_start_session(sandbox, **{KEY_VAR: GOLOKRON_KEY}))

    assert sandbox["state"].read_bytes() == before


def test_progress_survives_when_the_key_is_added(sandbox):
    data = st.default_state("padawan-1")
    data["xp"] = 40
    data["lexicon_unlocked"] = ["commit"]
    st.save(data, sandbox["state"])

    _start_session(sandbox, **{KEY_VAR: GOLOKRON_KEY})

    after = st.load(sandbox["state"])
    assert after["link_key"] == GOLOKRON_KEY
    assert after["xp"] == 40
    assert after["lexicon_unlocked"] == ["commit"]
    assert after["padawan_id"] == "padawan-1"


@pytest.mark.parametrize("value", [
    "",
    "   ",
    "abcd2345",               # прежний код от бота — его вводят командой link
    "GK-3333-3333",           # короткий
    "GK-3333-3333-333T-3333",  # длинный
    "GK-0000-1111-OOII",      # знаки, которых в ключе не бывает
    "gk-3333-3333-333t",      # приложение передаёт ключ в каноне
    "GK-3333-3333-333T; rm -rf ~",
    "GK-3333-3333-333T\nlink_key",
])
def test_garbage_in_the_key_variable_writes_nothing(sandbox, value):
    # Значение пришло из чужого процесса: годится только бесспорное.
    _silent_success(_start_session(sandbox, **{KEY_VAR: value}))
    assert not sandbox["state"].exists()


def test_garbage_key_does_not_cancel_the_folder(sandbox, tmp_path):
    folder = tmp_path / "moya-igra"
    folder.mkdir()

    _silent_success(_start_session(sandbox, folder, **{KEY_VAR: "мусор"}))

    assert _recorded(sandbox) == str(folder)
    assert _link(sandbox) is None
    assert _queued(sandbox, "linked") == []


def test_key_trouble_does_not_cancel_the_folder(sandbox, tmp_path):
    # Мусор в сохранении, на котором снимок для бота не собирается: связь с
    # ботом подождёт, а папка обязана записаться — по ней сторож стережёт
    # файл с паролями, и это важнее.
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    data = st.default_state("padawan-1")
    data["xp"] = "много"
    st.save(data, sandbox["state"])

    _silent_success(_start_session(sandbox, folder, **{KEY_VAR: GOLOKRON_KEY}))

    assert _recorded(sandbox) == str(folder)
    assert _link(sandbox) is None


def test_broken_queue_does_not_cancel_the_folder(sandbox, tmp_path):
    # Очередь событий в сохранении — не список: событие привязки положить
    # некуда. Папка всё равно записывается, ключ ждёт.
    folder = tmp_path / "moya-igra"
    folder.mkdir()
    raw = st.default_state("padawan-1")
    raw["pending_sync"] = "мусор"
    sandbox["state"].parent.mkdir(parents=True, exist_ok=True)
    sandbox["state"].write_text(json.dumps(raw), encoding="utf-8")

    _silent_success(_start_session(sandbox, folder, **{KEY_VAR: GOLOKRON_KEY}))

    assert _recorded(sandbox) == str(folder)
    assert _link(sandbox) is None


def test_first_entry_mark_survives_the_key(sandbox):
    # Как и с папкой: отметку первого входа ставит первая команда игры, и по
    # её отсутствию приложение держит шаг «Первый запуск» на экране.
    _start_session(sandbox, **{KEY_VAR: GOLOKRON_KEY})
    raw = json.loads(sandbox["state"].read_text(encoding="utf-8"))
    assert raw["padawan_id"] is None


def test_key_write_failure_is_silent(sandbox, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    result = _start_session(
        sandbox, JEDICODER_STATE_PATH=str(blocker / "state.json"),
        **{KEY_VAR: GOLOKRON_KEY}
    )
    _silent_success(result)


def test_session_start_never_touches_the_network(sandbox, tmp_path):
    # Старт сессии не ждёт сеть: событие ложится в очередь, отправит его
    # первая же команда игры. Адрес бота ведёт в никуда — и хук не замечает.
    result = _start_session(
        sandbox, JEDICODER_SYNC_URL="http://127.0.0.1:1/x",
        **{KEY_VAR: GOLOKRON_KEY}
    )
    _silent_success(result)
    assert len(_queued(sandbox, "linked")) == 1


# --- Шов с приложением: имя переменной и форма ключа -------------------
#
# Договор живёт в двух репозиториях: приложение ставит переменную
# (golokron/src/main/workbench/launch.ts), бот задаёт алфавит ключа
# (jedicoder_academy_bot/src/golokronKey.ts), хук читает и то и другое по
# своим копиям. Разойдутся — бот молча перестанет видеть путь. Чужой
# репозиторий лежит рядом только на машине автора: нет его — тест пропущен.

def _site_file(*parts):
    import os

    root = Path(os.environ.get(
        "JEDICODER_SITE_ROOT", str(Path.home() / "projects" / "jedicoder_Appstore")
    ))
    target = root.joinpath(*parts)
    if not target.is_file():
        pytest.skip("нет {} — репозиторий сайта не рядом".format(target))
    return target.read_text(encoding="utf-8")


def _hook_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "session_start_under_test", str(HOOKS / "session_start.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_app_sets_the_variable_the_hook_reads():
    source = _site_file("golokron", "src", "main", "workbench", "launch.ts")
    if "KEY_VAR" not in source:
        pytest.skip("приложение в этой копии репозитория ключ игре ещё не называет")
    hook = _hook_module()
    assert 'export const KEY_VAR = "{}"'.format(hook.GOLOKRON_KEY_VAR) in source
    assert hook.GOLOKRON_KEY_VAR == KEY_VAR


def test_the_hook_accepts_exactly_the_alphabet_of_the_bot():
    import re

    source = _site_file("jedicoder_academy_bot", "src", "golokronKey.ts")
    alphabet = re.search(r'GOLOKRON_KEY_ALPHABET = "([^"]+)"', source).group(1)
    hook = _hook_module()
    for char in alphabet:
        assert hook.GOLOKRON_KEY_RE.fullmatch("GK-{0}{0}{0}{0}-2222-2222".format(char)), char
    for char in "01OIa-_ ":
        assert not hook.GOLOKRON_KEY_RE.fullmatch("GK-{0}{0}{0}{0}-2222-2222".format(char)), char

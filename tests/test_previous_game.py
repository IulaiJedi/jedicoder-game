"""Сохранение прежней игры уходит в архив при первой встрече (#78).

Игра перестроена (спека #75): под номером 1 новый акт, прежние Акты 2–5
выключены. Сохранение того, кто играл в прежнюю игру, с новым порядком
несовместимо, и прогресс не переносится (решение оператора 7): файл уходит в
архив рядом тем же кодом, что `reset`, игра начинается с нуля, первый экран
один раз говорит об этом.

Три двери, через которые прежнее сохранение встречает новая версия: движок
(`state.load`, `state.update_state`), CLI и хуки. Исход обязан быть один.

Засев допустим по правилу CLAUDE.md: прежнее сохранение — не выдуманное
состояние, а артефакт предыдущей версии игры, и через CLI новой версии оно
недостижимо по определению. Каждый тест пишет в свою песочницу; ни один не
зовёт `st.save` без пути.
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from jedicoder import cli, content, state as st
from test_act1_walkthrough import ACK, SCRIPTED, STEPS, WORDS_FIRST

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin"
HOOKS = PLUGIN / "hooks"

LINK_KEY = "abcd1234efgh"


def previous_save(project_path="/home/padawan/moy-bot", link_key=LINK_KEY):
    """Файл ровно той формы, что писала прежняя игра (схема 3).

    Ключи верхнего уровня сняты с настоящего сохранения версии 0.8.0; акты —
    в форме `ranks.enter_act`/`quests.record_result` тех выпусков: закрыты
    прежние Акт 1 (ресерч, путь «для себя») и Акт 2 «Чертёж», ранг Падаван.
    """
    def done(*quest_ids):
        return {
            "status": "done",
            "started_at": "2026-09-01T10:00:00Z",
            "completed_at": "2026-09-02T10:00:00Z",
            "quests": {q: {"status": "done", "attempts": 1} for q in quest_ids},
        }

    return {
        "schema_version": 3,
        "padawan_id": "local-1a2b3c4d",
        "link_key": link_key,
        "cohort": "2026-09",
        "passport": {"track": "craftsman", "product_type": "telegram-bot"},
        "rank": "padawan",
        "xp": 260,
        "dark_side": 3,
        "dark_side_log": [
            {"type": "env_staged", "date": "2026-09-01"},
            {"type": "env_staged", "date": "2026-09-01"},
            {"type": "vague_prompt", "date": "2026-09-02"},
        ],
        "streak": {"current": 2, "best": 4, "last_commit_date": "2026-09-02"},
        "first_try": {"passed": 7, "attempted": 8},
        "current_act": 3,
        "acts": {
            "1": done("01-idea", "02-one-evening", "08-research-done"),
            "2": done("01-recipe", "02-claude-md", "03-db-schema",
                      "04-git-init", "05-env-guard", "06-pipeline"),
        },
        "artifacts": ["brainstorm", "plan"],
        "lexicon_unlocked": ["mvp", "commit", "stack"],
        "lexicon_queue": ["env"],
        "project": {"path": project_path, "db": False, "type": "telegram-bot"},
        "pending_sync": [
            {"client_id": "c1", "type": "rank_up", "act": 2, "quest": None,
             "at": "2026-09-02T10:00:00Z", "payload": {"rank": "padawan"}},
            {"client_id": "c2", "type": "dark_side", "act": None, "quest": None,
             "at": "2026-09-02T11:00:00Z", "payload": {"amount": 1, "total": 3}},
        ],
        "notices": [],
        "scroll": {"files": {"README.md": {"sha256": "ab" * 32,
                                           "date": "2026-09-02"}}},
        "debrief": {"text": "Разбор прежнего пути.", "facts": "cd" * 32},
        "book_open": False,
        "book_asked": True,
        "magistr_called": True,
        "root_login_warned": True,
        "commit_nag_left": 5,
    }


def put(path, data):
    """Положить файл так, как он лежит у игрока: без участия движка."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path.read_bytes()


def archives(path):
    """Архивы рядом с сохранением, без их резервных копий."""
    return sorted(
        item for item in path.parent.glob(path.name + ".arhiv-*")
        if not item.name.endswith(".bak")
    )


@pytest.fixture
def save_path(tmp_path):
    return tmp_path / "home" / ".jedicoder" / "state.json"


# --- движок: state.load ---------------------------------------------------

def test_previous_save_goes_to_the_archive_untouched(save_path):
    before = put(save_path, previous_save())

    st.load(save_path)

    (archive,) = archives(save_path)
    assert archive.read_bytes() == before, "архив — прежний файл до байта"
    assert json.loads(archive.read_text(encoding="utf-8"))["rank"] == "padawan"


def test_new_game_starts_from_scratch(save_path):
    put(save_path, previous_save())

    fresh = st.load(save_path)

    assert fresh["rank"] == "youngling"
    assert fresh["acts"] == {}
    assert fresh["current_act"] == 1
    assert fresh["xp"] == 0
    assert fresh["dark_side"] == 0
    assert fresh["dark_side_log"] == []
    assert fresh["artifacts"] == []
    assert fresh["lexicon_unlocked"] == []
    assert fresh["lexicon_queue"] == []
    assert fresh["streak"] == {"current": 0, "best": 0, "last_commit_date": None}
    assert fresh["first_try"] == {"passed": 0, "attempted": 0}
    assert fresh["passport"] == {}
    assert fresh["scroll"] == {"files": {}}
    assert fresh["debrief"] == {"text": "", "facts": ""}
    assert fresh["pending_sync"] == []
    for leftover in ("magistr_called", "root_login_warned", "commit_nag_left"):
        assert leftover not in fresh


def test_new_save_is_on_disk_with_the_version_mark(save_path):
    """Новое сохранение пишет сам load: команда, которая только читает,
    иначе оставила бы игрока без файла, а следующую — без переноса."""
    put(save_path, previous_save())

    st.load(save_path)

    on_disk = json.loads(save_path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 4
    assert on_disk["rank"] == "youngling"
    assert on_disk["acts"] == {}


def test_what_is_not_about_progress_is_carried_over(save_path):
    put(save_path, previous_save(project_path="/home/padawan/moy-bot"))

    fresh = st.load(save_path)

    assert fresh["padawan_id"] == "local-1a2b3c4d"
    assert fresh["link_key"] == LINK_KEY
    assert fresh["cohort"] == "2026-09"
    assert fresh["book_open"] is False
    assert fresh["book_asked"] is True
    # Из раздела проекта — только папка: тип продукта, база и остальное
    # отвечали на вопросы прежних актов.
    assert fresh["project"] == {"path": "/home/padawan/moy-bot"}


def test_archive_happens_exactly_once(save_path):
    put(save_path, previous_save())

    st.load(save_path)
    after_first = save_path.read_bytes()
    st.load(save_path)
    st.load(save_path)

    assert len(archives(save_path)) == 1
    assert save_path.read_bytes() == after_first


def test_new_save_remembers_where_the_archive_is(save_path):
    put(save_path, previous_save())

    fresh = st.load(save_path)

    (archive,) = archives(save_path)
    assert fresh["previous_save"] == str(archive)
    assert fresh["notices"] == [st.NOTICE_GAME_REBUILT]


def test_save_of_the_new_game_is_never_archived(save_path):
    data = st.default_state("local-new")
    data["xp"] = 100
    data["acts"] = {"1": {"status": "done", "quests": {
        quest_id: {"status": "done", "attempts": 1}
        for quest_id in SCRIPTED + (ACK,)
    }}}
    data["rank"] = "seeker"
    st.save(data, save_path)
    before = save_path.read_bytes()

    loaded = st.load(save_path)
    st.load(save_path)

    assert archives(save_path) == []
    assert save_path.read_bytes() == before
    assert loaded["xp"] == 100 and loaded["rank"] == "seeker"
    assert loaded["notices"] == []


def test_backup_of_the_previous_game_leaves_with_it(save_path):
    """Резервная копия прежней игры не остаётся рядом с новой: иначе
    восстановление испорченного файла подняло бы прежний путь."""
    put(save_path, previous_save())
    bak = put(st.backup_path(save_path), previous_save())

    st.load(save_path)

    (archive,) = archives(save_path)
    assert Path(str(archive) + ".bak").read_bytes() == bak
    assert not st.backup_path(save_path).exists()


def test_previous_game_does_not_come_back_through_the_backup(save_path):
    """Основной файл испорчен, а копия — прежней игры: восстановление не
    выдаёт прежний путь за новую игру."""
    save_path.parent.mkdir(parents=True)
    save_path.write_text("{обрыв", encoding="utf-8")
    bak = put(st.backup_path(save_path), previous_save())

    fresh = st.load(save_path)

    assert fresh["rank"] == "youngling" and fresh["acts"] == {}
    assert fresh["link_key"] == LINK_KEY
    assert not st.backup_path(save_path).exists()
    assert Path(fresh["previous_save"]).read_bytes() == bak
    assert json.loads(save_path.read_text(encoding="utf-8"))["schema_version"] == 4


def test_two_archives_in_one_minute_do_not_overwrite_each_other(save_path):
    """Вернул архив на место и запустил снова — первый архив цел."""
    first = put(save_path, previous_save())
    st.load(save_path)
    second = put(save_path, previous_save(link_key=None))
    st.load(save_path)
    third = put(save_path, previous_save(project_path="/x"))
    st.load(save_path)

    assert sorted(a.read_bytes() for a in archives(save_path)) == sorted(
        [first, second, third]
    )


def test_file_without_a_version_is_not_taken_for_the_previous_game(save_path):
    """Версии нет — файл собран руками, а не игрой: игра всегда писала её.
    Архив — только по прямому признаку."""
    put(save_path, {"xp": 10, "streak": {"current": 3}})

    loaded = st.load(save_path)

    assert archives(save_path) == []
    assert loaded["xp"] == 10
    assert loaded["streak"] == {"current": 3, "best": 0, "last_commit_date": None}
    assert loaded["schema_version"] == st.SCHEMA_VERSION


@pytest.mark.parametrize("garbage", [
    {"link_key": ["не", "строка"], "padawan_id": 7, "project": "мусор",
     "book_open": "да", "book_asked": 1, "cohort": {"x": 1}},
    {"project": {"path": ["/tmp"]}},
])
def test_garbage_in_carried_fields_is_not_carried(save_path, garbage):
    data = previous_save()
    data.update(garbage)
    put(save_path, data)

    fresh = st.load(save_path)

    assert fresh["project"] == {}
    if "link_key" in garbage:
        assert fresh["link_key"] is None
        assert fresh["padawan_id"] is None
        assert fresh["cohort"] is None
        assert fresh["book_open"] is None
        assert fresh["book_asked"] is False


def test_hand_edited_version_number_does_not_slip_past_the_archive(save_path):
    """`3.0` вместо `3` — та же прежняя игра: под видом новой не проходит."""
    data = previous_save()
    data["schema_version"] = 3.0
    put(save_path, data)

    fresh = st.load(save_path)

    assert len(archives(save_path)) == 1
    assert fresh["rank"] == "youngling" and fresh["acts"] == {}


def test_previous_save_with_nothing_in_it_is_archived_quietly(save_path):
    """Сохранение прежней версии завёл хук, человек в неё не играл: файл
    уходит в архив тем же порядком, а говорить ему не о чем."""
    data = previous_save()
    data.update(acts={}, xp=0, dark_side=0, dark_side_log=[], artifacts=[],
                lexicon_unlocked=[], rank="youngling", current_act=1)
    before = put(save_path, data)

    fresh = st.load(save_path)

    (archive,) = archives(save_path)
    assert archive.read_bytes() == before
    assert fresh["notices"] == []
    assert fresh["previous_save"] == str(archive)
    assert fresh["link_key"] == LINK_KEY


def test_reading_inside_a_write_window_does_not_hang(save_path):
    """Замок не повторно-входим: чтение из тела update_state на пустом месте
    встало бы в очередь за самим собой. В хуке это остановленная сессия."""
    save_path.parent.mkdir(parents=True)
    done = []

    def nested():
        with st.update_state(save_path) as state:
            state["xp"] = 7
            done.append(st.load(save_path)["xp"])
            done.append(st.archive(save_path))

    thread = threading.Thread(target=nested, daemon=True)
    thread.start()
    thread.join(timeout=10)

    assert not thread.is_alive(), "чтение под своим же замком повисло"
    assert done == [0, None]
    assert st.load(save_path)["xp"] == 7


def test_save_newer_than_the_plugin_is_still_refused(save_path):
    put(save_path, {"schema_version": st.SCHEMA_VERSION + 1})
    with pytest.raises(st.StateError, match="обнови плагин"):
        st.load(save_path)
    assert archives(save_path) == []


# --- движок: state.update_state — дверь хуков ----------------------------

def test_update_state_never_writes_into_the_previous_save(save_path):
    before = put(save_path, previous_save())

    with st.update_state(save_path) as state:
        assert state["xp"] == 0, "хук видит новую игру, а не прежнюю"
        state["xp"] = 5

    (archive,) = archives(save_path)
    assert archive.read_bytes() == before
    after = st.load(save_path)
    assert after["xp"] == 5
    assert after["link_key"] == LINK_KEY
    assert after["notices"] == [st.NOTICE_GAME_REBUILT]
    assert len(archives(save_path)) == 1


def test_command_and_hooks_meeting_it_at_once_start_one_game(save_path):
    """Команда читает (`load`), хуки пишут (`update_state`) — все разом и все
    первыми. Архив один, перенос не потерян, ни одна запись не пропала."""
    before = put(save_path, previous_save())
    seen = []

    def read():
        seen.append(st.load(save_path))

    def write():
        with st.update_state(save_path) as state:
            seen.append(dict(state))
            state["xp"] = int(state.get("xp", 0)) + 1

    threads = [threading.Thread(target=job) for job in (read, write) * 6]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    (archive,) = archives(save_path)
    assert archive.read_bytes() == before
    assert len(seen) == 12
    assert all(state["link_key"] == LINK_KEY for state in seen)
    assert all(state["rank"] == "youngling" for state in seen)
    after = st.load(save_path)
    assert after["xp"] == 6
    assert after["previous_save"] == str(archive)
    assert after["notices"] == [st.NOTICE_GAME_REBUILT]


# --- CLI: первый экран ----------------------------------------------------

@pytest.fixture
def jc(save_path, content_root, quests_root, capsys):
    def call(*argv):
        code = cli.main(
            list(argv), state_path=save_path, content_root=content_root,
            quests_root=quests_root,
        )
        return code, capsys.readouterr().out

    return call


def test_first_screen_says_where_the_previous_path_is(save_path, jc):
    put(save_path, previous_save())

    code, out = jc("status")

    assert code == 0
    (archive,) = archives(save_path)
    assert "порядок актов изменился" in out
    assert str(archive) in out, "где именно лежит прежний путь"
    assert out.splitlines()[0].startswith("Ранг: Юнлинг — так в игре зовут новичка")


def test_first_screen_offers_the_new_first_act(save_path, jc):
    """Баг-свидетель из #77: с закрытым прежним Актом 1 экран говорил
    «следующие акты готовятся» и нового акта не предлагал."""
    put(save_path, previous_save())

    _, out = jc("status")

    assert "  Акт 1. Знакомство — не начат" in out
    assert "Что дальше: начать Акт 1 «Знакомство»" in out
    assert "XP" not in out and "Штрафы" not in out


def test_first_screen_says_it_once(save_path, jc):
    put(save_path, previous_save())

    jc("status")
    code, out = jc("status")

    assert code == 0
    assert "порядок актов изменился" not in out
    assert "архив" not in out
    assert len(archives(save_path)) == 1
    # Строка снята, а путь к архиву в сохранении остался.
    saved = st.load(save_path)
    assert saved["notices"] == []
    assert saved["previous_save"] == str(archives(save_path)[0])


def test_the_line_waits_for_the_first_screen(save_path, jc):
    """Первой оказалась не `status`, а другая команда — строка не пропала."""
    put(save_path, previous_save())

    code, out = jc("book")
    assert code == 0
    assert "порядок актов изменился" not in out

    _, out = jc("status")
    assert "порядок актов изменился" in out


def test_the_line_speaks_about_the_bot_only_to_the_linked(save_path, jc):
    put(save_path, previous_save())
    _, linked = jc("status")
    assert "Код от бота вводить заново не нужно." in linked

    for old in archives(save_path):
        old.unlink()
    put(save_path, previous_save(link_key=None))
    _, unlinked = jc("status")
    assert "порядок актов изменился" in unlinked
    assert "бот" not in unlinked.lower()


def test_new_player_never_sees_the_line(save_path, jc):
    code, out = jc("status")
    assert code == 0
    assert "порядок актов изменился" not in out
    assert "архив" not in out
    assert archives(save_path) == []


def _notice(out):
    lines = out.splitlines()
    start = next(i for i, line in enumerate(lines) if "порядок актов" in line)
    return lines[start:]


def test_the_line_keeps_the_rules_of_plain_language(save_path, jc, content_root):
    """Фраза до 15 слов, ни одного слова из поздних актов, и до первого ранга
    не звучат «привязка» и её соседи (language.md)."""
    sys.path.insert(0, str(HOOKS))
    import lexicon_loot

    put(save_path, previous_save())
    _, out = jc("status")
    notice = _notice(out)
    # Строка с отступом — путь к архиву: в счёт слов он не идёт.
    text = " ".join(line for line in notice if not line.startswith("  "))

    phrases = [p.strip() for p in text.replace(":", ".").split(".") if p.strip()]
    assert len(phrases) >= 3
    for phrase in phrases:
        assert len(phrase.split()) <= 15, phrase
    for word in ("привяз", "Книг", "клуб", "артефакт", "Свиток", "Тёмн"):
        assert word not in text
    late = [
        (term.term, alias)
        for term in content.load_terms(content_root) if term.act >= 2
        for alias in term.aliases
        if lexicon_loot._alias_pattern(alias).search("\n".join(notice))
    ]
    assert late == []


def test_reset_still_archives_with_the_same_code(save_path, jc):
    """`reset` и прежняя игра уходят в архив одним кодом: то же имя, тот же
    хвост у резервной копии."""
    data = st.default_state("local-new")
    data["xp"] = 40
    st.save(data, save_path)
    st.save(data, save_path)  # второй раз — чтобы рядом легла резервная копия
    before = save_path.read_bytes()

    code, out = jc("reset", "confirm")

    assert code == 0
    (archive,) = archives(save_path)
    assert archive.read_bytes() == before
    assert Path(str(archive) + ".bak").exists()
    assert not save_path.exists() and not st.backup_path(save_path).exists()
    assert str(archive) in out


def test_reset_on_the_previous_save_does_not_bury_the_line(save_path, jc):
    """`reset` первой командой после обновления: прежняя игра уже в архиве,
    второй архив унёс бы пустое сохранение вместе со строкой о первом."""
    before = put(save_path, previous_save())

    for argv in (("reset",), ("reset", "confirm")):
        code, out = jc(*argv)
        assert code == 0
        (archive,) = archives(save_path)
        assert archive.read_bytes() == before
        assert str(archive) in out
        assert "ничего не меняется" not in out
        assert "mv " not in out

    _, out = jc("status")
    assert "порядок актов изменился" in out and str(archive) in out


def test_reset_of_a_broken_save_names_no_phantom_archive(save_path, jc):
    save_path.parent.mkdir(parents=True)
    save_path.write_text("{обрыв", encoding="utf-8")

    code, out = jc("reset", "confirm")

    assert code == 0
    assert "None" not in out
    assert "нечего" in out


def test_quiet_archive_adds_nothing_to_the_first_screen(save_path, jc):
    data = previous_save()
    data.update(acts={}, xp=0, dark_side=0, dark_side_log=[], artifacts=[],
                lexicon_unlocked=[], rank="youngling", current_act=1)
    put(save_path, data)

    code, out = jc("status")

    assert code == 0
    assert len(archives(save_path)) == 1
    assert "порядок актов изменился" not in out
    assert "архив" not in out


def test_previous_player_without_the_bot_walks_the_new_act(save_path, jc, tmp_path):
    """Игра проходима с пустым кодом от бота — и после архива тоже: игрок
    прежней игры проходит новый Акт 1 той же дверью, что новичок."""
    proj = tmp_path / "proj"
    proj.mkdir()
    put(save_path, previous_save(project_path=str(proj), link_key=None))

    code, out = jc("enter", "1")
    assert code == 0, out
    # Папка переехала из прежней игры, но в новой её ещё никто не называл:
    # квест «Папка» засчитывает слово человека, а не унаследованную запись.
    code, out = jc("check", "1", "01-folder")
    assert code == 1 and "Папку проекта назвал ты сам" in out
    assert jc("project", "path", str(proj))[0] == 0
    for quest_id in SCRIPTED:
        if quest_id in STEPS:
            STEPS[quest_id](proj)
        if quest_id == WORDS_FIRST:
            assert jc("seen", "1", quest_id)[0] == 0
        code, out = jc("check", "1", quest_id)
        assert code == 0, "квест {} не закрылся: {}".format(quest_id, out)
    code, out = jc("ack", "1", ACK)
    assert code == 0, out

    after = st.load(save_path)
    assert after["rank"] == "seeker"
    assert after["link_key"] is None
    assert len(archives(save_path)) == 1


def test_events_of_the_previous_game_are_not_sent_to_the_bot(save_path, jc, monkeypatch):
    """Очередь прежней игры остаётся в архиве: новая игра с тем же кодом от
    бота не шлёт ему события прежних актов."""
    from jedicoder import sync

    sent = []

    def fake_post(link_key, events, timeout=None):
        sent.extend(events)
        return 200, len(events), True

    monkeypatch.setattr(sync, "_post", fake_post)
    before = put(save_path, previous_save())

    jc("status")

    assert sent == []
    assert st.load(save_path)["pending_sync"] == []
    (archive,) = archives(save_path)
    assert archive.read_bytes() == before
    assert len(json.loads(archive.read_text(encoding="utf-8"))["pending_sync"]) == 2


# --- хуки: первым прежнее сохранение встречает не CLI ---------------------

def _hook_env(save_path, **extra):
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(save_path.parent.parent),
        "JEDICODER_STATE_PATH": str(save_path),
        "JEDICODER_PLUGIN_ROOT_FILE": str(save_path.parent / "plugin_root"),
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
    }
    env.update(extra)
    return env


def _hook(name, payload, env):
    return subprocess.run(
        ["python3", str(HOOKS / name)], input=json.dumps(payload),
        capture_output=True, text=True, env=env,
    )


SESSION_START = {"hook_event_name": "SessionStart", "source": "startup"}


def test_session_start_meets_the_previous_save_first(save_path, jc, tmp_path):
    """Приложение передало папку, сессия стартовала — хук раньше любой
    команды. Исход тот же, что у CLI: один архив, новая игра, строка ждёт
    первого экрана."""
    old_folder = tmp_path / "staryi-proekt"
    old_folder.mkdir()
    launch_folder = tmp_path / "novaya-zateya"
    launch_folder.mkdir()
    before = put(save_path, previous_save(project_path=str(old_folder)))

    result = _hook(
        "session_start.py", SESSION_START,
        _hook_env(save_path, JEDICODER_GOLOKRON_PROJECT=str(launch_folder)),
    )

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    (archive,) = archives(save_path)
    assert archive.read_bytes() == before
    on_disk = json.loads(save_path.read_text(encoding="utf-8"))
    assert on_disk["schema_version"] == 4 and on_disk["acts"] == {}
    assert on_disk["link_key"] == LINK_KEY
    # Папка прежней игры жива и перенесена — слово человека старше папки
    # запуска, как и до архива.
    assert on_disk["project"] == {"path": str(old_folder)}

    code, out = jc("status")
    assert code == 0
    assert "порядок актов изменился" in out and str(archive) in out
    _, out = jc("status")
    assert "порядок актов изменился" not in out
    assert len(archives(save_path)) == 1


def test_session_start_without_a_folder_leaves_the_previous_save_to_the_cli(save_path, jc):
    """Сессия без приложения: хук в сохранение не смотрит вовсе, прежний файл
    дожидается первой команды нетронутым."""
    before = put(save_path, previous_save())

    result = _hook("session_start.py", SESSION_START, _hook_env(save_path))

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert save_path.read_bytes() == before
    assert archives(save_path) == []
    _, out = jc("status")
    assert "порядок актов изменился" in out


def test_penalty_hook_writes_into_the_new_game(save_path, project):
    """Хук штрафов встретил прежнее сохранение первым: очко ложится в новую
    игру, прежний файл в архиве не тронут ни байтом.

    Сессию делает игровой Голокрон (#97): папке проекта из прежнего
    сохранения хук не верит, пока оно не перенесено, — как и Лицо.
    """
    folder = project(files={".env": "TOKEN=secret\n"}, git=True, commits=1)
    before = put(save_path, previous_save(project_path=str(folder)))

    result = _hook("bash_guard.py", {
        "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "tool_input": {"command": "git add .env"}, "cwd": str(folder),
    }, _hook_env(save_path, JEDICODER_GOLOKRON="1"))

    assert result.returncode == 0
    verdict = json.loads(result.stdout)["hookSpecificOutput"]
    assert ".env" in verdict["permissionDecisionReason"]
    (archive,) = archives(save_path)
    assert archive.read_bytes() == before
    after = st.load(save_path)
    assert after["dark_side"] == 2, "очки новой игры, а не 3 + 2 прежней"
    assert [entry["type"] for entry in after["dark_side_log"]] == ["env_staged"] * 2
    assert after["notices"] == [st.NOTICE_GAME_REBUILT]


def test_a_hook_without_a_game_sign_leaves_the_previous_save_alone(
        save_path, project):
    """Прежнее сохранение уносит в архив тот, кого позвал человек (#97).

    Раньше это делал первый же хук любой сессии на машине — в том числе в
    чужом проекте. Теперь хук без признака игровой сессии прежнее сохранение
    только видит: папке проекта из него он не верит, как и Лицо
    (`state.peek`), файл цел, архива нет. Катастрофа блокируется и тут.
    """
    folder = project(files={".env": "TOKEN=secret\n"}, git=True, commits=1)
    before = put(save_path, previous_save(project_path=str(folder)))

    for command, blocked in (("git add .env", False), ("rm -rf /", True)):
        result = _hook("bash_guard.py", {
            "hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": str(folder),
            "session_id": "S-terminal",
        }, _hook_env(save_path))
        assert result.returncode == 0
        assert bool(result.stdout.strip()) is blocked, command

    assert save_path.read_bytes() == before
    assert archives(save_path) == []


def test_the_game_command_carries_the_previous_save_over_and_the_guard_wakes(
        save_path, project):
    """Голый терминал, прежнее сохранение: человек зовёт игру — хук запроса
    уносит прежнее в архив той же дверью, что и команда, и с этой минуты
    сторож в папке проекта судит."""
    folder = project(files={".env": "TOKEN=secret\n"}, git=True, commits=1)
    before = put(save_path, previous_save(project_path=str(folder)))
    env = _hook_env(save_path)

    called = _hook("vague_prompt.py", {
        "hook_event_name": "UserPromptSubmit", "prompt": "/jedicoder:start",
        "session_id": "S-terminal", "cwd": str(folder),
    }, env)
    assert called.returncode == 0 and called.stdout == ""
    (archive,) = archives(save_path)
    assert archive.read_bytes() == before
    assert st.load(save_path)["notices"] == [st.NOTICE_GAME_REBUILT]

    result = _hook("bash_guard.py", {
        "hook_event_name": "PreToolUse", "tool_name": "Bash",
        "tool_input": {"command": "git add .env"}, "cwd": str(folder),
        "session_id": "S-terminal",
    }, env)
    verdict = json.loads(result.stdout)["hookSpecificOutput"]
    assert verdict["permissionDecision"] == "deny"
    assert st.load(save_path)["dark_side"] == 2
    assert archives(save_path) == [archive], "архив один"


def test_hook_stays_silent_when_the_archive_cannot_be_made(save_path, tmp_path):
    """Закон хуков: архив не удался (папка сохранения только для чтения) —
    сессия стартует молча, прежний файл цел."""
    if os.geteuid() == 0:
        pytest.skip("root пишет и в папку только для чтения")
    folder = tmp_path / "zateya"
    folder.mkdir()
    before = put(save_path, previous_save(project_path="/net/takoi"))
    save_path.parent.chmod(0o500)
    try:
        result = _hook(
            "session_start.py", SESSION_START,
            _hook_env(save_path, JEDICODER_GOLOKRON_PROJECT=str(folder),
                      JEDICODER_PLUGIN_ROOT_FILE=str(tmp_path / "plugin_root")),
        )
    finally:
        save_path.parent.chmod(0o700)

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert save_path.read_bytes() == before
    assert archives(save_path) == []

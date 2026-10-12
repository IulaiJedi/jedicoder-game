"""Общие фикстуры. Добавляет plugin/lib в sys.path, чтобы пакет jedicoder
импортировался без установки — плагин не пакуется в дистрибутив.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugin" / "lib"))

CONTENT_ROOT = ROOT / "plugin" / "content" / "ru"
QUESTS_ROOT = ROOT / "plugin" / "quests"


@pytest.fixture(autouse=True)
def isolated_state(tmp_path_factory, monkeypatch):
    """Каждый тест пишет сохранение в свою песочницу, а не в боевое.

    Умолчание `state.py` — `~/.jedicoder/state.json` того, кто запускает
    тесты. Тест, забывший передать путь, затирает живой прогресс: ровно это
    и случилось 2026-09-07 на красной фазе этой же задачи, и восстановить
    файл удалось только из ручной копии. Одна переменная закрывает дыру для
    всего суита сразу — теперь, когда движок её читает.

    Своя папка, а не `tmp_path` теста: тесты, проверяющие «ничего не легло
    на диск» (`test_scroll.py`), считают файлы в `tmp_path`, и подброшенное
    сохранение сделало бы их ложью.

    Тесту, которому нужно поведение «переменной нет», достаточно
    `monkeypatch.delenv("JEDICODER_STATE_PATH", raising=False)`.

    Чего фикстура НЕ закрывает: подпроцесс, запущенный с вычищенным
    окружением, переменной не увидит и уйдёт в настоящий `$HOME`. Такие
    тесты обязаны подменять `HOME` сами.
    """
    monkeypatch.setenv(
        "JEDICODER_STATE_PATH",
        str(tmp_path_factory.mktemp("isolated-state") / "state.json"),
    )
    # Суит, запущенный из Верстака Голокрона, унаследовал бы его метку — и
    # каждая сессия в тестах хуков стала бы игровой (#97). Тест, которому
    # нужен Голокрон, ставит метку сам.
    monkeypatch.delenv("JEDICODER_GOLOKRON", raising=False)


@pytest.fixture
def content_root():
    return CONTENT_ROOT


@pytest.fixture
def quests_root():
    return QUESTS_ROOT


@pytest.fixture
def old_acts_open(monkeypatch):
    """Акты 2–4 открыты, как до 2026-10-08: выключен один Акт 5.

    Игра сегодня кончается Актом 1 (`ranks.MUTED_ACTS`, спека #75), но
    механика поздних актов — порядок входа, развилка по пути деплоя, Книга на
    входе, хэш `CLAUDE.md` для босса — живёт в движке и вернётся с актами.
    Юнит-тесты этой механики открывают дверь сами, чтобы она не сгнила молча
    к тому дню, когда номер уйдёт из списка.

    Сквозных тестов это не касается: они ходят дверью падавана, а дверь
    закрыта — у них `skipif` по тому же списку.

    Вместе со списком подменяются обе производные: `FINAL_ACT` и
    `FINAL_RANK` посчитаны при импорте и сами за списком не пойдут.
    """
    from jedicoder import ranks

    monkeypatch.setattr(ranks, "MUTED_ACTS", (5,))
    monkeypatch.setattr(ranks, "FINAL_ACT", 4)
    monkeypatch.setattr(ranks, "FINAL_RANK", ranks.ACTS[4]["rank"])


@pytest.fixture
def all_acts_open(monkeypatch):
    """Ни один акт не выключен: игра идёт до последнего акта реестра.

    Так выглядит день, когда `ranks.MUTED_ACTS` опустеет. Финал — карточка,
    адрес страницы финала, событие боту — существует только в этом мире:
    пока после последнего играемого акта есть выключенные, игра не кончилась
    (решение оператора 2026-10-08). Тесты самого финала открывают дверь
    этой фикстурой, чтобы он не сгнил к тому дню.
    """
    from jedicoder import ranks

    last = max(ranks.ACTS)
    monkeypatch.setattr(ranks, "MUTED_ACTS", ())
    monkeypatch.setattr(ranks, "FINAL_ACT", last)
    monkeypatch.setattr(ranks, "FINAL_RANK", ranks.ACTS[last]["rank"])


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


@pytest.fixture
def project(tmp_path):
    """Фабрика проектов падавана.

    make(files={...}, gitignore="...", git=True, commits=2, commit_env=True)
    Файлы создаются ДО git init, поэтому попадают в первый же коммит.

    Каждый вызов возвращает свою независимую директорию: тесты вроде
    Акта 3 (нужны и «до» и «после» — 3 коммита и 5 коммитов) вызывают
    фабрику дважды за тест, и второй проект не должен видеть git-историю
    первого.
    """
    calls = []

    def make(files=None, gitignore=None, git=False, commits=0, commit_env=False,
             leak_token=False):
        d = tmp_path / "proj{}".format(len(calls) + 1)
        calls.append(d)
        d.mkdir(exist_ok=True)
        for name, text in (files or {}).items():
            target = d / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        if gitignore is not None:
            (d / ".gitignore").write_text(gitignore, encoding="utf-8")
        if git:
            _git(d, "init", "-q")
            _git(d, "config", "user.email", "padawan@example.test")
            _git(d, "config", "user.name", "Padawan")
            _git(d, "config", "commit.gpgsign", "false")
            for i in range(commits):
                (d / "step{}.txt".format(i)).write_text(str(i), encoding="utf-8")
                _git(d, "add", "-A")
                _git(d, "commit", "-q", "-m", "шаг {}".format(i))
            if commit_env:
                (d / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
                _git(d, "add", "-f", ".env")
                _git(d, "commit", "-q", "-m", "случайно закоммитил env")
            if leak_token:
                (d / "config.py").write_text(
                    'TOKEN = "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz123456"\n', encoding="utf-8"
                )
                _git(d, "add", "-A")
                _git(d, "commit", "-q", "-m", "конфиг")
        return d

    return make

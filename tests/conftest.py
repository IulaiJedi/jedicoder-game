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


@pytest.fixture
def content_root():
    return CONTENT_ROOT


@pytest.fixture
def quests_root():
    return QUESTS_ROOT


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

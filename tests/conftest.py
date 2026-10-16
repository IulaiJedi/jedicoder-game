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


SHELF_ACT4 = ROOT / "shelf" / "act4-shchit"

#: Полка в выгрузку не едет (`build_release.SHIP_TOP`): тесту, которому она
#: нужна, в выгрузке нечего проверять — пропуск, а не красный.
needs_shelf = pytest.mark.skipif(
    not (ROOT / "shelf").is_dir(), reason="полки нет: выгрузка без shelf/"
)


@pytest.fixture
def shield_on_act4(monkeypatch):
    """Прежний Акт 4 «Щит» — с полки на место Акта 4, как до 2026-10-14.

    Развилка по пути деплоя живёт в движке (`acts.ACT_AXIS`,
    `filter_by_deploy`, `project deploy`), но ни один играемый акт сегодня по
    ней не ветвится (спека #117). Юнит-тесты этой механики ставят «Щит» на его
    прежний номер сами: состав и ветки берутся из катсцены на полке, вид
    квеста — по тому, лежит ли там его проверка. Отдаёт корень квестов полки:
    проверки «Щита» лежат там.
    """
    from jedicoder import acts, content, quests, ranks

    if not SHELF_ACT4.is_dir():
        pytest.skip("полки нет: выгрузка без shelf/")
    scene = next(iter(content.load_acts(SHELF_ACT4 / "content")))
    root = SHELF_ACT4 / "quests"
    registry = tuple(
        (
            quest_id,
            quests.KIND_SCRIPT
            if (root / scene.slug / quest_id / "check.sh").is_file()
            else quests.KIND_ACK,
            branch,
        )
        for quest_id, branch in zip(scene.quests, scene.quest_branches)
    )
    monkeypatch.setitem(ranks.ACTS, 4, {
        "slug": scene.slug, "title": scene.title,
        "artifact": scene.artifact, "rank": scene.rank,
    })
    monkeypatch.setitem(acts.QUESTS_BY_ACT, 4, registry)
    monkeypatch.setattr(acts, "ACT_AXIS", {4: acts.AXIS_DEPLOY})
    return root


@pytest.fixture
def shield_content(tmp_path_factory):
    """Копия живого контента, где на месте катсцены Акта 4 — катсцена «Щита».

    Для тестов, которым на входе в «Щит» (`shield_on_act4`) нужны его
    названия квестов: живой контент описывает уже «Свой продукт».
    """
    import shutil

    if not SHELF_ACT4.is_dir():
        pytest.skip("полки нет: выгрузка без shelf/")
    root = tmp_path_factory.mktemp("shield-content") / "ru"
    shutil.copytree(str(CONTENT_ROOT), str(root))
    for scene in (root / "acts").glob("act4-*.md"):
        scene.unlink()
    shutil.copy(
        str(SHELF_ACT4 / "content" / "acts" / "act4-shchit.md"),
        str(root / "acts" / "act4-shchit.md"),
    )
    return root


@pytest.fixture
def old_acts_open(monkeypatch, shield_on_act4):
    """Акты 3–4 открыты, как до 2026-10-08: выключен один Акт 5, а на месте
    Акта 4 стоит прежний «Щит» с развилкой по пути деплоя (`shield_on_act4`).

    Игра сегодня кончается Актом 4 «Свой продукт» (`ranks.MUTED_ACTS`, спеки
    #75, #99, #108 и #117), но механика поздних актов — порядок входа,
    развилка по пути деплоя, Книга на входе, хэш `CLAUDE.md` для босса —
    живёт в движке и вернётся с актами.
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

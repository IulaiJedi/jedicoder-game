import hashlib
import re

import pytest

from conftest import _git
from jedicoder import quests

ACT = "act2-chertezh"

ARCH_GOOD = "# Архитектура\n\n## Стек\n\n" + ("Python и aiogram. " * 40)
CLAUDE_GOOD = "# Проект\n\n" + ("Бот присылает цитаты по команде. " * 20)
DB_GOOD = "# Схема\n\n## Таблица users\n\nid, tg_id, created_at\n"


def check(quests_root, quest, project_dir, env=None):
    return quests.run_check(quests_root, ACT, quest, project_dir, env_extra=env)


def test_recipe_requires_architecture(quests_root, project):
    assert check(quests_root, "01-recipe", project()).ok is False


def test_recipe_requires_stack_section(quests_root, project):
    proj = project(files={"ARCHITECTURE.md": "# Архитектура\n\n" + "текст " * 100})
    result = check(quests_root, "01-recipe", proj)
    assert result.ok is False
    assert "arch_has_stack" in [c["id"] for c in quests.failed_checks(result)]


def test_recipe_rejects_stub(quests_root, project):
    proj = project(files={"ARCHITECTURE.md": "# Архитектура\n\n## Стек\n\nпитон\n"})
    result = check(quests_root, "01-recipe", proj)
    assert result.ok is False
    assert "arch_substantial" in [c["id"] for c in quests.failed_checks(result)]


def test_recipe_passes_on_good_file(quests_root, project):
    proj = project(files={"ARCHITECTURE.md": ARCH_GOOD})
    assert check(quests_root, "01-recipe", proj).ok is True


def test_claude_md_missing_and_stub(quests_root, project):
    assert check(quests_root, "02-claude-md", project()).ok is False
    stub = project(files={"CLAUDE.md": "проект\n"})
    result = check(quests_root, "02-claude-md", stub)
    assert "claude_md_substantial" in [c["id"] for c in quests.failed_checks(result)]


def test_claude_md_passes(quests_root, project):
    assert check(quests_root, "02-claude-md", project(files={"CLAUDE.md": CLAUDE_GOOD})).ok is True


def test_db_schema_bails_when_unknown(quests_root, project):
    result = check(quests_root, "03-db-schema", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False


def test_db_schema_skipped_when_no_db(quests_root, project):
    result = check(quests_root, "03-db-schema", project(), env={"JEDICODER_HAS_DB": "no"})
    assert result.ok is True


def test_db_schema_required_when_has_db(quests_root, project):
    env = {"JEDICODER_HAS_DB": "yes"}
    assert check(quests_root, "03-db-schema", project(), env=env).ok is False
    proj = project(files={"DB-SCHEMA.md": DB_GOOD})
    assert check(quests_root, "03-db-schema", proj, env=env).ok is True


def test_git_init_without_repo(quests_root, project):
    result = check(quests_root, "04-git-init", project())
    assert result.ok is False
    assert "repo_exists" in [c["id"] for c in quests.failed_checks(result)]


def test_git_init_repo_without_commits(quests_root, project):
    result = check(quests_root, "04-git-init", project(git=True, commits=0))
    assert result.ok is False
    assert [c["id"] for c in quests.failed_checks(result)] == ["has_commit"]


def test_git_init_passes_with_commit(quests_root, project):
    assert check(quests_root, "04-git-init", project(git=True, commits=1)).ok is True


def test_env_guard_bails_outside_repo(quests_root, project):
    result = check(quests_root, "05-env-guard", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_env_guard_requires_gitignore_rule(quests_root, project):
    proj = project(gitignore="node_modules\n", git=True, commits=1)
    result = check(quests_root, "05-env-guard", proj)
    assert result.ok is False
    assert "env_ignored" in [c["id"] for c in quests.failed_checks(result)]


def test_env_guard_catches_tracked_env(quests_root, project):
    proj = project(gitignore=".env\n", git=True, commits=1, commit_env=True)
    result = check(quests_root, "05-env-guard", proj)
    failed = [c["id"] for c in quests.failed_checks(result)]
    assert "env_not_tracked" in failed


def test_env_guard_catches_token_in_history(quests_root, project):
    proj = project(gitignore=".env\n", git=True, commits=1, leak_token=True)
    result = check(quests_root, "05-env-guard", proj)
    assert "no_secrets_in_history" in [c["id"] for c in quests.failed_checks(result)]


def test_env_guard_catches_github_pat_in_history(quests_root, project):
    # Fine-grained-токены GitHub (github_pat_…) — второй живой формат
    # после ghp_; регексп обязан ловить оба.
    proj = project(gitignore=".env\n", git=True, commits=1)
    (proj / "conf.py").write_text(
        'TOKEN = "github_pat_11ABCDE2Y0hooeAETqYIsl_'
        'zXhCRT1jzGlGnkH8T9yWuGPnDCXi9NuIkKcXjIRFvR3EHXYIDGE"\n',
        encoding="utf-8",
    )
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "конфиг")
    result = check(quests_root, "05-env-guard", proj)
    assert result.ok is False
    ids = [c["id"] for c in result.checks if not c["ok"]]
    assert ids == ["no_secrets_in_history"]


def test_env_guard_catches_anthropic_key_in_history(quests_root, project):
    # sk-ant-… (Anthropic) — hyphenated-формат, ускользавший от старого
    # sk-[A-Za-z0-9]{16,}: дефисы после sk-ant- рвут алфанумерик-класс.
    proj = project(gitignore=".env\n", git=True, commits=1)
    (proj / "conf.py").write_text(
        'ANTHROPIC_API_KEY = "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWx-'
        '1234567890AbCdEfGh"\n',
        encoding="utf-8",
    )
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "конфиг")
    result = check(quests_root, "05-env-guard", proj)
    assert result.ok is False
    ids = [c["id"] for c in result.checks if not c["ok"]]
    assert ids == ["no_secrets_in_history"]


def test_env_guard_catches_openai_project_key_in_history(quests_root, project):
    # sk-proj-… (новый OpenAI) — тот же класс пропуска, что и sk-ant-.
    proj = project(gitignore=".env\n", git=True, commits=1)
    (proj / "conf.py").write_text(
        'OPENAI_API_KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz1234567890"\n',
        encoding="utf-8",
    )
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "-m", "конфиг")
    result = check(quests_root, "05-env-guard", proj)
    assert result.ok is False
    ids = [c["id"] for c in result.checks if not c["ok"]]
    assert ids == ["no_secrets_in_history"]


def test_env_guard_passes_when_clean(quests_root, project):
    proj = project(gitignore=".env\n.venv\n", git=True, commits=1)
    assert check(quests_root, "05-env-guard", proj).ok is True


def test_pipeline_quest_has_no_script(quests_root, project):
    result = check(quests_root, "06-pipeline", project())
    assert result.kind == quests.KIND_ACK


def test_size_labels_say_bytes_not_chars(quests_root):
    """wc -c считает байты; в кириллице это вдвое меньше символов, чем обещано."""
    for quest, label in (("01-recipe", "400"), ("02-claude-md", "300")):
        text = (quests_root / ACT / quest / "check.sh").read_text(encoding="utf-8")
        assert "{} байт".format(label) in text
        assert "{} символов".format(label) not in text


def test_db_schema_bails_on_garbage_answer(quests_root, project):
    """Не «yes» — не значит «БД есть»: мусор уходил в ветку с проверкой файла."""
    result = check(quests_root, "03-db-schema", project(), env={"JEDICODER_HAS_DB": "мaybe"})
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False
    assert "project db yes|no" in result.stderr


def test_check_stderr_reaches_caller(quests_root, project):
    """Диагностика команды не должна глотаться: иначе «нет git» неотличимо
    от невыполненного условия.
    """
    result = check(quests_root, "04-git-init", project(git=False))
    assert result.ok is False
    assert "git" in result.stderr.lower()


def _snapshot(root):
    """Слепок проекта: путь + хеш содержимого каждого файла.

    Сравнивать имена недостаточно: скрипт, дописавший в существующий файл,
    прошёл бы такую проверку незамеченным. Хеш ловит и это.
    """
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        snapshot[str(path.relative_to(root))] = digest
    return snapshot


def test_checks_do_not_mutate_project(quests_root, project):
    proj = project(files={"ARCHITECTURE.md": ARCH_GOOD, "CLAUDE.md": CLAUDE_GOOD},
                   gitignore=".env\n", git=True, commits=1)
    before = _snapshot(proj)
    for quest in ("01-recipe", "02-claude-md", "04-git-init", "05-env-guard"):
        check(quests_root, quest, proj)
    after = _snapshot(proj)
    assert before == after


def test_env_guard_rejects_env_example_as_protection(quests_root, project):
    """Регрессия: .env.example в .gitignore НЕ защищает .env."""
    proj = project(gitignore=".env.example\n", git=True, commits=1)
    result = check(quests_root, "05-env-guard", proj)
    assert result.ok is False
    assert "env_ignored" in [c["id"] for c in quests.failed_checks(result)]


def test_env_guard_accepts_wildcard_env_rule(quests_root, project):
    """И не даёт ложного отказа: .env* тоже реально защищает .env."""
    proj = project(gitignore=".env*\n", git=True, commits=1)
    result = check(quests_root, "05-env-guard", proj)
    assert "env_ignored" not in [c["id"] for c in quests.failed_checks(result)]


@pytest.mark.parametrize(
    "heading",
    ["## Стек", "## СТЕК", "## стек", "## СтЕк",
     "## Stack", "## STACK", "## stack", "### Стек", "# Стек"],
)
def test_recipe_finds_stack_heading_in_any_case(quests_root, heading, project):
    """Регистр складывается классами, а не `grep -i`.

    Классу нужно только многобайтовое сопоставление; `grep -i` требует ещё
    и многобайтового СЛОЖЕНИЯ регистра — ровно то, на чём спотыкается BSD
    grep из macOS, а macOS заявлена целевой платформой. Ставка тут не край,
    а основной путь: подсказка велит писать «## Стек» с заглавной.
    """
    proj = project(files={"ARCHITECTURE.md": ARCH_GOOD.replace("## Стек", heading, 1)})
    result = check(quests_root, "01-recipe", proj)
    assert "arch_has_stack" not in [c["id"] for c in quests.failed_checks(result)]


@pytest.mark.parametrize(
    "word",
    ["Таблица users", "ТАБЛИЦА USERS", "таблица users", "ТаБлИца users",
     "Table users", "TABLE users", "table users"],
)
def test_db_schema_finds_table_word_in_any_case(quests_root, word, project):
    """То же самое для «таблиц»/«table» в 03-db-schema."""
    proj = project(files={"DB-SCHEMA.md": DB_GOOD.replace("Таблица users", word, 1)})
    result = check(quests_root, "03-db-schema", proj, env={"JEDICODER_HAS_DB": "yes"})
    assert result.ok is True, quests.failed_checks(result)


def test_no_check_folds_case_with_grep_i(quests_root):
    """Ни одна проверка игры не складывает регистр через `grep -i`.

    Настоящий отказ отсюда не воспроизвести: у GNU grep на Linux `-i`
    кириллицу складывает. Ломается он на BSD grep из macOS, заявленной
    целевой платформой, — поэтому сторожит правило, а не симптом. Правило
    записано в CLAUDE.md: регистр задаётся классом. Тест заодно закрывает
    «новых таких не заводить» для будущих актов.
    """
    offenders = []
    for script in sorted(quests_root.rglob("check.sh")):
        for number, line in enumerate(
                script.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if re.search(r"grep\s+(-\w*\s+)*-\w*i", code):
                offenders.append("{}:{}".format(script.name, number))
    assert offenders == [], "регистр складывается классом, а не grep -i: {}".format(
        ", ".join(offenders)
    )


def test_recipe_still_rejects_unrelated_heading(quests_root, project):
    """Классы не должны заодно расширить, что считается разделом про стек."""
    proj = project(
        files={"ARCHITECTURE.md": ARCH_GOOD.replace("## Стек", "## Стены", 1)}
    )
    result = check(quests_root, "01-recipe", proj)
    assert "arch_has_stack" in [c["id"] for c in quests.failed_checks(result)]


def test_act2_checks_survive_hostile_locale(quests_root, project):
    """Проверки Акта 2 обязаны работать при LC_ALL=C.

    Локаль падавана — лотерея: у свежего WSL Ubuntu LANG нередко вообще не
    задан, а LC_ALL=C приезжает из чужих скриптов и CI. В C-локали кириллица
    режется на байты, и «## Стек» перестаёт находиться. Акт 1 это переживал
    сам (подбор UTF-8-локали жил в md.sh), а Акт 2 md.sh не сорсит и вставал
    намертво на двух квестах из шести. Подбор локали переехал в emit.sh —
    его сорсят все проверки всех актов.
    """
    proj = project(files={"ARCHITECTURE.md": ARCH_GOOD, "DB-SCHEMA.md": DB_GOOD})
    hostile = {"LC_ALL": "C"}
    recipe = check(quests_root, "01-recipe", proj, env=hostile)
    assert recipe.ok is True, quests.failed_checks(recipe)
    db = check(quests_root, "03-db-schema", proj,
               env=dict(hostile, JEDICODER_HAS_DB="yes"))
    assert db.ok is True, quests.failed_checks(db)


def test_env_guard_no_false_positive_on_hyphenated_words(quests_root, project):
    """Регрессия: 'task-management...' содержит 'sk-' и ловился как секрет."""
    proj = project(files={"notes.md": "task-management1234567890abcdef\n"},
                   gitignore=".env\n", git=True, commits=1)
    result = check(quests_root, "05-env-guard", proj)
    assert "no_secrets_in_history" not in [
        c["id"] for c in quests.failed_checks(result)
    ]

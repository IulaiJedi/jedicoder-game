"""Проверки квестов Акта 3. curl в тестах живой: сервер поднимается
по-настоящему, не мокается — той же дверью, что у падавана.
"""
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from conftest import _git
from jedicoder import quests

ACT = "act3-pervaya-krov"


def check(quests_root, quest, project_dir, env=None):
    return quests.run_check(quests_root, ACT, quest, project_dir, env_extra=env)


@pytest.fixture
def live_server(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        cwd=str(tmp_path),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while True:
        try:
            urllib.request.urlopen(
                "http://127.0.0.1:{}/".format(port), timeout=1
            ).close()
            break
        except OSError:
            if time.time() > deadline:
                proc.terminate()
                raise RuntimeError("тестовый сервер не поднялся")
            time.sleep(0.05)
    yield port
    proc.terminate()
    proc.wait(timeout=10)


HEALTH_ONLY_SERVER = """
import http.server, sys
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        code = 200 if self.path == "/health" else 404
        self.send_response(code); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a): pass
http.server.HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
"""


@pytest.fixture
def health_only_server(tmp_path):
    """Сервер, у которого корень отвечает 404, а /health — 200: так живёт
    бот со страницей «жив» по рецепту."""
    script = tmp_path / "health_only.py"
    script.write_text(HEALTH_ONLY_SERVER, encoding="utf-8")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, str(script), str(port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + 10
    while True:
        try:
            urllib.request.urlopen(
                "http://127.0.0.1:{}/health".format(port), timeout=1
            ).close()
            break
        except OSError:
            if time.time() > deadline:
                proc.terminate()
                raise RuntimeError("тестовый сервер не поднялся")
            time.sleep(0.05)
    yield port
    proc.terminate()
    proc.wait(timeout=10)


def free_dead_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_launch_bails_without_port(quests_root, project):
    result = check(quests_root, "01-launch", project())
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False


def test_launch_fails_when_nothing_listens(quests_root, project):
    env = {"JEDICODER_PORT": str(free_dead_port())}
    assert check(quests_root, "01-launch", project(), env=env).ok is False


def test_launch_passes_on_live_server(quests_root, project, live_server):
    env = {"JEDICODER_PORT": str(live_server)}
    assert check(quests_root, "01-launch", project(), env=env).ok is True


def test_launch_accepts_health_page_when_root_is_404(
        quests_root, project, health_only_server):
    """Рецепт велит странице «жив» жить на /health; проверка не вправе
    требовать корень (живой прогон 2026-09-11: попытка ушла на 404)."""
    env = {"JEDICODER_PORT": str(health_only_server)}
    assert check(quests_root, "01-launch", project(), env=env).ok is True


def test_feature_needs_five_commits(quests_root, project):
    assert check(quests_root, "02-feature", project(git=True, commits=3)).ok is False
    assert check(quests_root, "02-feature", project(git=True, commits=5)).ok is True


def commit_all(proj, message):
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "--allow-empty", "-m", message)


def test_break_requires_marker_commit(quests_root, project):
    proj = project(git=True, commits=1)
    assert check(quests_root, "03-break", proj).ok is False
    commit_all(proj, "слом: уронил парсер нарочно")
    assert check(quests_root, "03-break", proj).ok is True


def test_break_accepts_capital_marker(quests_root, project):
    proj = project(git=True, commits=1)
    commit_all(proj, "Слом: спрятал кавычку")
    assert check(quests_root, "03-break", proj).ok is True


def test_fix_bails_without_marker(quests_root, project, live_server):
    proj = project(git=True, commits=2)
    env = {"JEDICODER_PORT": str(live_server)}
    result = check(quests_root, "04-fix", proj, env=env)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK


def test_fix_needs_commit_after_marker(quests_root, project, live_server):
    proj = project(git=True, commits=1)
    commit_all(proj, "слом: сломал руками")
    env = {"JEDICODER_PORT": str(live_server)}
    result = check(quests_root, "04-fix", proj, env=env)
    assert result.ok is False
    assert "fix_committed" in [c["id"] for c in quests.failed_checks(result)]
    commit_all(proj, "починил: вернул кавычку")
    assert check(quests_root, "04-fix", proj, env=env).ok is True


def test_fix_needs_live_server(quests_root, project):
    proj = project(git=True, commits=1)
    commit_all(proj, "слом: сломал")
    commit_all(proj, "починил")
    env = {"JEDICODER_PORT": str(free_dead_port())}
    result = check(quests_root, "04-fix", proj, env=env)
    assert result.ok is False
    assert "server_alive" in [c["id"] for c in quests.failed_checks(result)]


def test_fix_bails_without_port(quests_root, project):
    proj = project(git=True, commits=1)
    commit_all(proj, "слом: сломал")
    result = check(quests_root, "04-fix", proj)
    assert result.exit_code == quests.EXIT_CANNOT_CHECK
    assert result.countable is False


def test_break_rejects_body_line_spoof(quests_root, project):
    # Метка должна быть в заголовке коммита, а не где-то в теле сообщения —
    # иначе обычный коммит с «слом:» в теле ложно закрывал бы квест.
    proj = project(git=True, commits=1)
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "--allow-empty", "-m", "обычный коммит",
         "-m", "слом: в теле, не маркер")
    assert check(quests_root, "03-break", proj).ok is False


def test_fix_ignores_body_line_marker_spoof(quests_root, project, live_server):
    # Более поздний коммит со «слом:» в теле не должен перехватывать роль
    # маркера у настоящего слома — иначе rev-list marker..HEAD обнулился бы
    # и правильно починивший падаван получил бы ложный провал.
    proj = project(git=True, commits=1)
    commit_all(proj, "слом: настоящий слом")
    commit_all(proj, "починил: вернул кавычку")
    _git(proj, "add", "-A")
    _git(proj, "commit", "-q", "--allow-empty", "-m", "обычный коммит",
         "-m", "слом: в теле, не маркер")
    env = {"JEDICODER_PORT": str(live_server)}
    assert check(quests_root, "04-fix", proj, env=env).ok is True


def test_fix_marker_matches_glued_colon(quests_root, project, live_server):
    # grep в 04-fix ищет «слом:» сразу после хэша и пробела ('^[0-9a-f]+
    # [Сс]лом:'); awk лишь берёт $1 (хэш) из найденной строки. Проверяем,
    # что маркер срабатывает и без пробела после «:» — «слом:текст» —
    # не только с ним.
    proj = project(git=True, commits=1)
    commit_all(proj, "слом:пропала_кавычка")
    commit_all(proj, "починил: вернул")
    env = {"JEDICODER_PORT": str(live_server)}
    assert check(quests_root, "04-fix", proj, env=env).ok is True


def test_marker_match_survives_mawk(quests_root, project):
    """mawk (дефолт WSL) матчит байтово: кириллический класс в awk-регэкспе
    молча не находит ничего, и суит зелёный на gawk этого не видит.
    Проверяем сами скрипты под подменённым awk."""
    if shutil.which("mawk") is None:
        pytest.skip("mawk недоступен")
    proj = project(git=True, commits=1)
    commit_all(proj, "слом: уронил")
    commit_all(proj, "починил")
    bin_dir = proj.parent / "mawkbin"
    bin_dir.mkdir(exist_ok=True)
    awk_stub = bin_dir / "awk"
    awk_stub.write_text('#!/bin/sh\nexec mawk "$@"\n', encoding="utf-8")
    awk_stub.chmod(0o755)
    env = {
        "PATH": "{}:{}".format(bin_dir, os.environ["PATH"]),
        "JEDICODER_PORT": str(free_dead_port()),
    }
    result = check(quests_root, "04-fix", proj, env=env)
    # маркер обязан найтись даже под mawk: bail (exit 2) значит «не нашёл слом»
    assert result.exit_code != quests.EXIT_CANNOT_CHECK


DECISIONS_ONE_DAY = (
    "# Решения\n\n"
    "## 2026-07-27 — SQLite вместо Postgres\n\nОдин файл, ноль настройки.\n\n"
    "## 2026-07-27 — бот без вебхуков\n\nПоллинг проще на старте.\n"
)
DECISIONS_TWO_DAYS = DECISIONS_ONE_DAY + (
    "\n## 2026-07-28 — вебхуки всё же нужны\n\nПоллинг ест лимиты.\n"
)


def test_decisions_missing_and_empty(quests_root, project):
    assert check(quests_root, "05-decisions", project()).ok is False
    proj = project(files={"DECISIONS.md": ""})
    assert check(quests_root, "05-decisions", proj).ok is False


def test_decisions_one_day_is_not_a_journal(quests_root, project):
    """Две записи одним днём и одним коммитом — не журнал: квест не закрыт,
    и это календарь (бейл), а не провал."""
    proj = project(files={"DECISIONS.md": DECISIONS_ONE_DAY}, git=True, commits=1)
    result = check(quests_root, "05-decisions", proj)
    assert result.ok is False
    assert result.countable is False


def commit_dated(proj, message, date):
    """Коммит с заданной датой автора и коммитера — «вчерашняя» запись."""
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(
        ["git", "add", "-A"], cwd=str(proj), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", message], cwd=str(proj), check=True,
        capture_output=True, env=env,
    )


def test_decisions_two_headings_in_one_commit_day_is_calendar_not_failure(
        quests_root, project):
    """Долг №17: дни считаются по коммитам, трогавшим DECISIONS.md, а не по
    датам в заголовках — вчерашнюю дату можно вписать руками, а вчерашний
    коммит нет. Найдено живым прогоном 2026-09-10: квест «вернись завтра»
    закрылся в тот же день. Журнал в порядке, коммитили один день — это
    календарь, а не провал: попытка не тратится, протокол «третья попытка —
    стоп» не печатается (прогон 2026-09-11)."""
    proj = project(files={"DECISIONS.md": DECISIONS_TWO_DAYS}, git=True, commits=1)
    result = check(quests_root, "05-decisions", proj)
    assert result.ok is False
    assert result.countable is False
    assert "завтра" in result.stderr


def test_decisions_uncommitted_journal_fails(quests_root, project):
    """Ни одного коммита с журналом — вина падавана, а не календаря: честный
    провал с подсказкой закоммитить."""
    proj = project(files={"DECISIONS.md": DECISIONS_TWO_DAYS}, git=True)
    result = check(quests_root, "05-decisions", proj)
    assert result.ok is False
    assert result.countable is True
    failed = {c["id"]: c for c in quests.failed_checks(result)}
    assert "коммит" in failed["decisions_dates"]["hint"]


def test_decisions_two_commit_days_pass(quests_root, project):
    proj = project(files={"DECISIONS.md": DECISIONS_ONE_DAY}, git=True)
    commit_dated(proj, "журнал: первое решение", "2026-07-27T12:00:00+0000")
    (proj / "DECISIONS.md").write_text(DECISIONS_TWO_DAYS, encoding="utf-8")
    commit_dated(proj, "журнал: второе решение", "2026-07-28T12:00:00+0000")
    assert check(quests_root, "05-decisions", proj).ok is True


def test_decisions_without_git_bails(quests_root, project):
    """Без репозитория дни посчитать нечем: «не смог проверить», а не провал."""
    proj = project(files={"DECISIONS.md": DECISIONS_TWO_DAYS})
    assert check(quests_root, "05-decisions", proj).countable is False


def fake_claude_path(tmp_path, exit_code):
    """PATH со stub-«claude»: тест не должен зависеть от машины."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "claude"
    stub.write_text("#!/bin/sh\nexit {}\n".format(exit_code), encoding="utf-8")
    stub.chmod(0o755)
    return "{}:{}".format(bin_dir, os.environ["PATH"])


def test_context7_fails_when_absent(quests_root, project, tmp_path):
    env = {"PATH": fake_claude_path(tmp_path, 1)}
    assert check(quests_root, "06-context7", project(), env=env).ok is False


def _label(result, check_id):
    return next(c["label"] for c in result.checks if c["id"] == check_id)


def test_context7_passes_via_mcp_json(quests_root, project, tmp_path):
    proj = project(files={".mcp.json": '{"mcpServers": {"context7": {}}}'})
    env = {"PATH": fake_claude_path(tmp_path, 1)}
    result = check(quests_root, "06-context7", proj, env=env)
    assert result.ok is True
    # Долг №18: где нашли — в строке проверки, а не в голом «подключён».
    assert ".mcp.json" in _label(result, "context7_connected")


def test_context7_passes_via_claude_cli(quests_root, project, tmp_path):
    env = {"PATH": fake_claude_path(tmp_path, 0)}
    result = check(quests_root, "06-context7", project(), env=env)
    assert result.ok is True
    assert "на этой машине" in _label(result, "context7_connected")


def test_git_safety_requires_revert_commit(quests_root, project):
    proj = project(git=True, commits=2)
    assert check(quests_root, "07-git-safety", proj).ok is False
    _git(proj, "revert", "--no-edit", "HEAD")
    assert check(quests_root, "07-git-safety", proj).ok is True


def test_git_safety_ignores_body_line_revert(quests_root, project):
    proj = project(git=True, commits=2)
    _git(proj, "commit", "-q", "--allow-empty",
         "-m", "обычный коммит",
         "-m", "Revert this decision if the metric regresses.")
    assert check(quests_root, "07-git-safety", proj).ok is False


def test_skill_requires_real_skill_md(quests_root, project):
    assert check(quests_root, "08-skill", project()).ok is False
    stub = project(files={".claude/skills/verify/SKILL.md": "проверь\n"})
    assert check(quests_root, "08-skill", stub).ok is False
    body = "# Проверка бота\n\n" + ("Открой чат, отправь /start, жди ответ. " * 10)
    good = project(files={".claude/skills/verify/SKILL.md": body})
    assert check(quests_root, "08-skill", good).ok is True


def git_sha_of(proj, name):
    done = subprocess.run(
        ["git", "hash-object", name], cwd=str(proj),
        capture_output=True, text=True, check=True,
    )
    return done.stdout.strip()


def test_boss_requires_claude_md(quests_root, project):
    assert check(quests_root, "10-boss", project()).ok is False


def test_boss_passes_when_no_baseline(quests_root, project):
    proj = project(files={"CLAUDE.md": "# Память\n"})
    assert check(quests_root, "10-boss", proj).ok is True


def test_boss_fails_on_untouched_claude_md(quests_root, project):
    proj = project(files={"CLAUDE.md": "# Память\n"})
    env = {"JEDICODER_PREV_CLAUDE_MD_SHA": git_sha_of(proj, "CLAUDE.md")}
    result = check(quests_root, "10-boss", proj, env=env)
    assert result.ok is False
    assert "claude_md_grew" in [c["id"] for c in quests.failed_checks(result)]


def test_boss_passes_on_changed_claude_md(quests_root, project):
    proj = project(files={"CLAUDE.md": "# Память\n"})
    env = {"JEDICODER_PREV_CLAUDE_MD_SHA": git_sha_of(proj, "CLAUDE.md")}
    (proj / "CLAUDE.md").write_text(
        "# Память\n\nЗапуск: python main.py, порт 8000.\n", encoding="utf-8"
    )
    assert check(quests_root, "10-boss", proj, env=env).ok is True

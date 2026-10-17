"""Стражи дымовой проверки лица (тикет #95).

Сама проверка поднимает живую сессию Claude Code и стоит хода модели —
в суите её нет и быть не может. Здесь то, что видно без Claude Code: скрипт
на месте, честно отвечает «не смог проверить», когда проверить нечем, и в
его тексте нет того, что задело бы боевую игру автора.

Последнее — не перестраховка. Сессия с плагином из папки под настоящей
домашней папкой переписывает указатель на плагин боевой игры, а команда
удаления папки целиком засчитывается сторожем игры штрафом в боевое
сохранение.
"""
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "face_smoke.sh"

BASH = shutil.which("bash") or "/bin/bash"


def code_lines():
    """Строки скрипта без комментариев — то, что исполняется."""
    lines = []
    for line in SCRIPT.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(line)
    return lines


def stub(folder, name):
    """Пустышка вместо программы: её зовут — тест падает по следу."""
    path = folder / name
    path.write_text(
        "#!{}\necho called >> \"{}\"\nexit 0\n".format(BASH, folder / "called.log"),
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def run(tmp_path, programs, home=None, args=()):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in programs:
        stub(bin_dir, name)
    home = home or (tmp_path / "home")
    home.mkdir(exist_ok=True)
    env = {"PATH": str(bin_dir), "HOME": str(home), "TMPDIR": str(tmp_path)}
    result = subprocess.run(
        [BASH, str(SCRIPT)] + list(args), env=env, cwd=str(tmp_path),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    called = (bin_dir / "called.log").exists()
    return result.returncode, result.stdout.decode("utf-8", "replace"), called


def test_script_exists_and_is_executable():
    assert SCRIPT.is_file()
    assert os.access(str(SCRIPT), os.X_OK), "скрипт не исполняемый"
    assert SCRIPT.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash\n")


def test_script_is_valid_bash():
    result = subprocess.run([BASH, "-n", str(SCRIPT)], stderr=subprocess.PIPE)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")


@pytest.mark.parametrize("programs, missing", [
    ((), "tmux"),
    (("tmux",), "claude"),
    (("tmux", "claude"), "python3"),
])
def test_missing_program_is_cannot_check_not_a_verdict(tmp_path, programs, missing):
    """Нет программы — код 2 и слово: лицо не осуждено и не оправдано."""
    code, output, called = run(tmp_path, programs)
    assert code == 2, output
    assert "НЕ СМОГ ПРОВЕРИТЬ" in output
    assert missing in output
    assert "ЛИЦО НА МЕСТЕ" not in output and "ЛИЦА НЕТ" not in output
    assert not called, "до проверки условий запущена программа"


def test_no_credentials_is_cannot_check(tmp_path):
    """Без входа в Claude Code сессия не поднимется — и это не вина лица."""
    code, output, called = run(tmp_path, ("tmux", "claude", "python3", "mktemp"))
    assert code == 2, output
    assert "НЕ СМОГ ПРОВЕРИТЬ" in output
    assert "учётных данных" in output
    assert not called, "Claude Code запущен без учётных данных"


def test_missing_plugin_folder_is_cannot_check(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text("{}", encoding="utf-8")
    (home / ".claude.json").write_text("{}", encoding="utf-8")
    code, output, called = run(
        tmp_path, ("tmux", "claude", "python3", "mktemp"), home=home,
        args=(str(tmp_path / "нет-такой-папки"),),
    )
    assert code == 2, output
    assert "в папке нет плагина" in output
    assert not called


def test_script_names_all_three_outcomes():
    text = SCRIPT.read_text(encoding="utf-8")
    for word in ("ЛИЦО НА МЕСТЕ", "ЛИЦА НЕТ: ", "НЕ СМОГ ПРОВЕРИТЬ: "):
        assert word in text, word
    assert re.search(r"^\s*exit 0$", text, re.M)
    assert re.search(r"^\s*exit 1$", text, re.M)
    assert re.search(r"^\s*exit 2$", text, re.M)


@pytest.mark.parametrize("banned", [
    "pkill", "killall", "rm -rf", "rm -fr", "rm -r", "rmtree",
    ".jedicoder", "git ",
])
def test_script_text_has_nothing_that_hurts_the_live_game(banned):
    """Ни в коде, ни в комментариях: текст скрипта читают и копируют."""
    assert banned not in SCRIPT.read_text(encoding="utf-8"), banned


def test_claude_code_never_runs_under_the_real_home():
    """Каждый запуск Claude Code подменяет домашнюю папку в той же строке."""
    launches = [
        line for line in code_lines()
        if re.search(r"(^|[\s\"'(])claude\s+(-|/)", line)
    ]
    assert len(launches) >= 2, "запуски Claude Code не найдены — страж ослеп"
    for line in launches:
        assert "HOME=" in line, line
        assert "-u CLAUDE_CODE_PLUGIN_DIRS" in line, line
        # Своя папка настроек увела бы Claude Code из песочницы.
        assert "-u CLAUDE_CONFIG_DIR" in line, line
    # Подмена — песочницей, а не чем попало: значения игровой сессии едут
    # отдельной строкой, и стеречь надо её, а не слово `HOME=`.
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'HOME="$SANDBOX_HOME" claude' in text
    assert 'SANDBOX="$(mktemp -d)"' in text
    assert 'SANDBOX_HOME="$SANDBOX/home"' in text
    assert (
        "HOME=%q JEDICODER_STATE_PATH=%q claude --plugin-dir %q "
        "--dangerously-skip-permissions --debug-file %q /jedicoder:start' \\\n"
        '    "$SANDBOX_HOME" "$SANDBOX/state.json" "$PLUGIN" "$DEBUG_LOG")"'
    ) in text
    # Указатель на плагин хук пишет по своей переменной мимо домашней папки.
    assert "-u JEDICODER_PLUGIN_ROOT_FILE" in text


def test_cleanup_is_armed_before_account_data_lands_in_the_sandbox():
    text = SCRIPT.read_text(encoding="utf-8")
    armed = text.index("trap cleanup EXIT")
    assert armed < text.index('ln -s "$CREDENTIALS"')
    assert armed < text.index('"$SANDBOX_HOME/.claude.json" <<')


def test_owner_tool_servers_do_not_start_in_the_sandbox():
    """Серверы инструментов хозяина машины — с их ключами — в сессию не едут."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'data.pop("mcpServers", None)' in text
    assert 'data.pop("projects", None)' in text


def test_only_its_own_tmux_server_is_touched():
    """Свой сервер — своё имя сокета; чужие сессии tmux не видны вовсе."""
    for line in code_lines():
        if re.search(r"(^|[\s|;(])tmux\s", line) and "for tool in" not in line:
            assert '-L "$SOCKET"' in line, line
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'SOCKET="jcface-smoke-$$"' in text
    assert text.count("kill-server") >= 2
    assert "trap cleanup EXIT" in text


def test_no_early_exit_grep_in_a_pipeline():
    """Правило репозитория: `grep -q` в конвейере не дочитывает писателя."""
    for line in code_lines():
        assert not re.search(r"\|\s*grep\s+-[a-zA-Z]*q", line), line


def test_credentials_are_linked_not_read():
    text = "\n".join(code_lines())
    assert 'ln -s "$CREDENTIALS"' in text
    for reader in ("cat", "head", "tail", "less", "cp", "grep"):
        assert not re.search(
            r"\b{}\b[^\n|]*\$CREDENTIALS".format(reader), text
        ), reader


def test_cleanup_takes_the_copies_of_the_account_settings_too(tmp_path):
    """Claude Code сам кладёт копии `.claude.json` в `.claude/backups/` —
    это те же данные учётной записи (#122). Уборка уносит их и папку, а
    остальную песочницу оставляет для разбора.

    Функция уборки берётся из текста скрипта и исполняется сама: сессии и
    tmux для неё не нужны."""
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("cleanup() {")
    function = text[start:text.index("\n}\n", start) + 3]
    home = tmp_path / "home"
    backups = home / ".claude" / "backups"
    backups.mkdir(parents=True)
    (backups / ".claude.json.backup.1792226609967").write_text("{}", encoding="utf-8")
    (home / ".claude.json").write_text("{}", encoding="utf-8")
    (home / "keep.txt").write_text("разбор", encoding="utf-8")
    script = (
        'SANDBOX_HOME="{home}"\nBACKUPS="$SANDBOX_HOME/.claude/backups"\n'
        "in_tmux() {{ :; }}\n{function}cleanup\n"
    ).format(home=home, function=function)
    result = subprocess.run([BASH, "-c", script], stderr=subprocess.PIPE)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert not backups.exists()
    assert not (home / ".claude.json").exists()
    assert (home / "keep.txt").is_file()
    assert 'BACKUPS="$SANDBOX_HOME/.claude/backups"' in text

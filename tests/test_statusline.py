"""Строка состояния Claude Code от игры: полоса в терминале и снимок для Голокрона.

Claude Code даёт строке состояния JSON — единственное место, где наружу
выходят заполнение контекста и остаток лимитов (`context_window`,
`rate_limits`). Плагин привезти строку не может (в его settings.json
разрешены только agent и subagentStatusLine), поэтому её ставит Голокрон
по кнопке или падаван руками по узлу Акта 0; скрипт же живёт здесь, в игре.

Два шва: `render` — что печатается в терминале, `snapshot` — что ложится в
`~/.jedicoder/statusline.json` для Сцены. Оба чистые.
"""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugin" / "lib" / "jedicoder" / "statusline.py"
sys.path.insert(0, str(ROOT / "plugin" / "lib"))

from jedicoder import statusline  # noqa: E402

# Пример из документации Claude Code (statusline), усечённый до нужного.
EXAMPLE = {
    "model": {"id": "claude-opus-5", "display_name": "Opus"},
    "effort": {"level": "high"},
    "context_window": {
        "context_window_size": 200000,
        "used_percentage": 8,
        "remaining_percentage": 92,
    },
    "rate_limits": {
        "five_hour": {"used_percentage": 23.5, "resets_at": 1738425600},
        "seven_day": {"used_percentage": 41.2, "resets_at": 1738857600},
    },
}


def test_render_names_model_effort_context_and_limits():
    line = statusline.render(EXAMPLE)
    assert "Opus" in line
    assert "high" in line
    assert "8%" in line
    assert "24%" in line or "23%" in line
    assert "41%" in line
    assert "\n" not in line


def test_render_context_bar_grows_with_usage():
    low = statusline.render({**EXAMPLE, "context_window": {"used_percentage": 10}})
    high = statusline.render({**EXAMPLE, "context_window": {"used_percentage": 90}})
    assert low.count(statusline.FULL) < high.count(statusline.FULL)


def test_render_without_limits_still_shows_context():
    """Лимитов в JSON нет (старый Claude Code, API-ключ) — строка не пустая."""
    data = {k: v for k, v in EXAMPLE.items() if k != "rate_limits"}
    line = statusline.render(data)
    assert "8%" in line
    assert "лимит" not in line.lower()


def test_render_handles_garbage_without_raising():
    assert statusline.render({}) == ""
    assert statusline.render({"context_window": "мусор"}) == ""


def test_snapshot_keeps_only_what_scene_needs():
    snap = statusline.snapshot(EXAMPLE, now=1738425000)
    assert snap["context"] == {"used": 8, "remaining": 92, "size": 200000}
    assert snap["limits"]["five_hour"] == {"used": 23.5, "resets_at": 1738425600}
    assert snap["limits"]["seven_day"] == {"used": 41.2, "resets_at": 1738857600}
    assert snap["model"] == {"id": "claude-opus-5", "name": "Opus"}
    assert snap["effort"] == "high"
    assert snap["written_at"] == 1738425000
    # Ни цены, ни git, ни кэша: Сцене это не нужно, а лишнее в файле —
    # лишнее обещание совместимости.
    assert "cost" not in snap and "prompt_cache" not in snap


def test_snapshot_without_limits_has_null_limits():
    data = {k: v for k, v in EXAMPLE.items() if k != "rate_limits"}
    assert statusline.snapshot(data, now=1)["limits"] is None


def test_script_prints_line_and_writes_snapshot(tmp_path):
    """Сквозной прогон, как его запускает Claude Code: JSON на stdin."""
    env = {**os.environ, "JEDICODER_STATE_PATH": str(tmp_path / "state.json")}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], input=json.dumps(EXAMPLE),
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert result.returncode == 0
    assert "Opus" in result.stdout
    written = json.loads((tmp_path / "statusline.json").read_text(encoding="utf-8"))
    assert written["context"]["used"] == 8


def test_script_swallows_bad_input(tmp_path):
    """Закон хуков: чужой мусор — молчаливый ноль, а не traceback в терминале."""
    env = {**os.environ, "JEDICODER_STATE_PATH": str(tmp_path / "state.json")}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], input="это не json",
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert not (tmp_path / "statusline.json").exists()


def test_script_does_not_touch_the_save(tmp_path):
    """Снимок — отдельный файл рядом с сохранением; само сохранение не трогается."""
    save = tmp_path / "state.json"
    save.write_text('{"rank": "youngling"}', encoding="utf-8")
    before = save.read_bytes()
    env = {**os.environ, "JEDICODER_STATE_PATH": str(save)}
    subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(EXAMPLE),
                   capture_output=True, text=True, env=env, timeout=10)
    assert save.read_bytes() == before


# --- --install: одна дверь для Голокрона и для узла Акта 0 ---

def _run_install(config_dir):
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir)}
    return subprocess.run([sys.executable, str(SCRIPT), "--install"],
                          capture_output=True, text=True, env=env, timeout=10)


def test_install_writes_statusline_into_empty_config(tmp_path):
    result = _run_install(tmp_path / "claude")
    assert result.returncode == 0
    written = json.loads((tmp_path / "claude" / "settings.json").read_text(encoding="utf-8"))
    assert written["statusLine"]["type"] == "command"
    assert "plugin_root" in written["statusLine"]["command"]
    assert "statusline.py" in written["statusLine"]["command"]
    assert "включена" in result.stdout


def test_install_keeps_other_settings(tmp_path):
    cfg = tmp_path / "claude"
    cfg.mkdir()
    (cfg / "settings.json").write_text('{"model": "opus", "permissions": {"allow": ["Bash"]}}', encoding="utf-8")
    assert _run_install(cfg).returncode == 0
    written = json.loads((cfg / "settings.json").read_text(encoding="utf-8"))
    assert written["model"] == "opus"
    assert written["permissions"] == {"allow": ["Bash"]}
    assert "statusLine" in written


def test_install_never_replaces_existing_statusline(tmp_path):
    """Чужая строка дороже нашей: у автора игры она своя, и стереть её молча
    — то же, что стереть чужой файл."""
    cfg = tmp_path / "claude"
    cfg.mkdir()
    own = '{"statusLine": {"type": "command", "command": "~/my-bar.sh"}}'
    (cfg / "settings.json").write_text(own, encoding="utf-8")
    result = _run_install(cfg)
    assert result.returncode == 0
    assert json.loads((cfg / "settings.json").read_text(encoding="utf-8"))["statusLine"]["command"] == "~/my-bar.sh"
    assert "уже настроена" in result.stdout


def test_install_refuses_broken_settings(tmp_path):
    cfg = tmp_path / "claude"
    cfg.mkdir()
    (cfg / "settings.json").write_text("{не json", encoding="utf-8")
    result = _run_install(cfg)
    assert result.returncode == 1
    assert (cfg / "settings.json").read_text(encoding="utf-8") == "{не json"

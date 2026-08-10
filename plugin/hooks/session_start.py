#!/usr/bin/env python3
"""SessionStart: записать корень плагина в ~/.jedicoder/plugin_root.

Зачем: скиллы и команды — это markdown, им нужен путь до cli.py, а он
заранее неизвестен. В хуках $CLAUDE_PLUGIN_ROOT гарантированно есть, в
markdown — не гарантированно. Поэтому корень фиксируется здесь один раз
за сессию, а скиллы читают его из файла.

Хук молчит и всегда завершается успешно: сломать старт сессии падавана
из-за нашей телеметрии недопустимо.
"""
import os
import sys
from pathlib import Path

DEFAULT_MARKER = Path.home() / ".jedicoder" / "plugin_root"

# Маркер осмысленен только если по этому пути действительно лежит CLI: скиллы
# запускают именно его. Иначе после обновления, переноса или переустановки
# плагина падаван получит «python3: can't open file ...» вместо игры.
CLI_RELATIVE = Path("lib") / "jedicoder" / "cli.py"


def main():
    try:
        sys.stdin.read()  # payload не нужен, но stdin надо вычитать
        root = os.environ.get("CLAUDE_PLUGIN_ROOT")
        if not root:
            return 0
        if not (Path(root) / CLI_RELATIVE).is_file():
            return 0
        marker = Path(os.environ.get("JEDICODER_PLUGIN_ROOT_FILE") or DEFAULT_MARKER)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(root + "\n", encoding="utf-8")
    except Exception:
        # Ловим широко и намеренно: это учётная запись для скиллов, а не
        # критичная операция, и никакая её ошибка (stdin не в UTF-8,
        # недоступный диск и т.п.) не должна долететь до падавана в виде
        # traceback'а. BaseException не трогаем — Ctrl+C и SystemExit
        # обязаны проходить насквозь.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

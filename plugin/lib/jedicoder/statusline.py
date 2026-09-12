#!/usr/bin/env python3
"""Строка состояния Claude Code от игры.

Claude Code зовёт этот скрипт после каждого ответа и даёт на stdin JSON —
единственное место, где наружу выходят заполнение контекстного окна и остаток
лимитов (`context_window`, `rate_limits`). Скрипт печатает одну строку для
терминала и кладёт снимок в `~/.jedicoder/statusline.json` — его читает Сцена
Голокрона и рисует те же полосы рядом с терминалом.

Плагин привезти строку состояния сам не может: в его settings.json разрешены
только agent и subagentStatusLine (документация Claude Code, plugins-reference).
Поэтому настройку ставит Голокрон по кнопке — и только если своей строки у
человека нет — или падаван руками по узлу Акта 0. Команда в настройке зовёт
скрипт через указатель `~/.jedicoder/plugin_root`, а не по пути с версией:
кэш плагина живёт в папке с номером версии, и прямой путь умер бы на первом
же обновлении.

Закон хуков действует и здесь: любой мусор на входе — тишина и код 0, а не
traceback в терминале падавана. Сохранение игры не трогается никогда: снимок —
отдельный файл рядом, без блокировки и без резервной копии, потому что он
перезаписывается после каждого ответа и ценности не имеет.

Ноль зависимостей: только stdlib.
"""
import json
import os
import sys
import tempfile
import time

try:
    from jedicoder import state as st
except ImportError:  # запуск файлом, не пакетом: sys.path без lib/
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from jedicoder import state as st

FULL = "█"
EMPTY = "░"
BAR_WIDTH = 10
SNAPSHOT_NAME = "statusline.json"


def _percent(value):
    """Число процентов или None: JSON приходит чужой, форму не обещает."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value:  # NaN
        return None
    return value


def _bar(percent):
    filled = int(round(percent / 100.0 * BAR_WIDTH))
    filled = max(0, min(BAR_WIDTH, filled))
    return FULL * filled + EMPTY * (BAR_WIDTH - filled)


def _context(data):
    window = data.get("context_window")
    if not isinstance(window, dict):
        return None
    used = _percent(window.get("used_percentage"))
    if used is None:
        return None
    remaining = _percent(window.get("remaining_percentage"))
    size = window.get("context_window_size")
    return {
        "used": used,
        "remaining": remaining if remaining is not None else max(0, 100 - used),
        "size": size if isinstance(size, int) and not isinstance(size, bool) else None,
    }


def _limit(entry):
    if not isinstance(entry, dict):
        return None
    used = _percent(entry.get("used_percentage"))
    if used is None:
        return None
    resets = entry.get("resets_at")
    return {
        "used": used,
        "resets_at": resets if isinstance(resets, (int, float)) and not isinstance(resets, bool) else None,
    }


def _limits(data):
    limits = data.get("rate_limits")
    if not isinstance(limits, dict):
        return None
    five = _limit(limits.get("five_hour"))
    week = _limit(limits.get("seven_day"))
    if five is None and week is None:
        return None
    return {"five_hour": five, "seven_day": week}


def _model(data):
    model = data.get("model")
    if not isinstance(model, dict):
        return None
    return {
        "id": model.get("id") if isinstance(model.get("id"), str) else None,
        "name": model.get("display_name") if isinstance(model.get("display_name"), str) else None,
    }


def _effort(data):
    effort = data.get("effort")
    if isinstance(effort, dict) and isinstance(effort.get("level"), str):
        return effort["level"]
    return None


def render(data):
    """Одна строка для терминала. Пустая — если показывать нечего.

    Слова здесь ранние и русские: строку видит падаван с первого вечера, до
    любого акта. «Контекст» и «лимит» — оба объясняются в игре, а сама полоса
    показывает раньше, чем объясняет: заполняющийся контекст видно глазами.
    """
    if not isinstance(data, dict):
        return ""
    context = _context(data)
    if context is None:
        return ""
    parts = []
    model = _model(data)
    effort = _effort(data)
    head = " · ".join(x for x in [(model or {}).get("name"), effort] if x)
    if head:
        parts.append("[{}]".format(head))
    parts.append("контекст {} {:.0f}%".format(_bar(context["used"]), context["used"]))
    limits = _limits(data)
    if limits:
        five, week = limits["five_hour"], limits["seven_day"]
        if five:
            parts.append("лимит 5ч {:.0f}%".format(five["used"]))
        if week:
            parts.append("неделя {:.0f}%".format(week["used"]))
    return " · ".join(parts)


def snapshot(data, now=None):
    """Что ложится в файл для Сцены. Только то, что она рисует, — ни цены, ни
    git, ни кэша: лишнее в файле — лишнее обещание совместимости."""
    return {
        "context": _context(data) if isinstance(data, dict) else None,
        "limits": _limits(data) if isinstance(data, dict) else None,
        "model": _model(data) if isinstance(data, dict) else None,
        "effort": _effort(data) if isinstance(data, dict) else None,
        "written_at": int(time.time()) if now is None else now,
    }


def snapshot_path():
    """Рядом с сохранением: тот же каталог, что и у state.json, — значит
    JEDICODER_STATE_PATH уводит и снимок, и тесты не трогают боевой."""
    return st.state_path().parent / SNAPSHOT_NAME


def write_snapshot(snap, path=None):
    """Атомарно, без резервной копии и без блокировки: файл перезаписывается
    после каждого ответа и ценности не имеет; полузаписанного Сцена не увидит."""
    path = snapshot_path() if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".statusline-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(snap, stream, ensure_ascii=False)
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# Команда для настроек Claude Code: скрипт ищется через указатель на корень
# плагина, а не по пути с версией — кэш плагина живёт в папке с номером
# версии, и прямой путь умер бы на первом обновлении.
INSTALL_COMMAND = 'python3 "$(cat ~/.jedicoder/plugin_root)/lib/jedicoder/statusline.py"'


def settings_path():
    """Файл настроек Claude Code. CLAUDE_CONFIG_DIR — его же переменная:
    так и тесты не трогают боевые настройки, и тот, кто держит конфиг не
    дома, получает строку туда же, куда смотрит Claude Code."""
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "settings.json")


def install(path=None):
    """Включить строку состояния: `--install`. Одна дверь для всех — этой же
    командой её ставит Голокрон по кнопке и падаван руками по узлу Акта 0.

    Чужую строку не трогает никогда: у того, кто настроил свою, она дороже
    нашей, и молча заменить её — то же, что стереть чужой файл. Ответ —
    словами и кодом 0: это не ошибка, это отказ по правилу.
    """
    path = settings_path() if path is None else path
    data = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
        except (ValueError, OSError):
            print("Не смог прочитать {}: файл повреждён, ничего не меняю.".format(path))
            return 1
        if not isinstance(data, dict):
            print("В {} не объект настроек, ничего не меняю.".format(path))
            return 1
    if data.get("statusLine"):
        print("Строка состояния у тебя уже настроена — не трогаю. Хочешь нашу, убери свою из {}.".format(path))
        return 0
    data["statusLine"] = {"type": "command", "command": INSTALL_COMMAND}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    print("Строка состояния включена. Появится после следующего ответа Claude Code.")
    return 0


def main():
    if "--install" in sys.argv[1:]:
        return install()
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    try:
        line = render(data)
        if not line:
            return 0
        sys.stdout.write(line)
        sys.stdout.flush()
        write_snapshot(snapshot(data))
    except Exception:  # закон хуков: чужая ошибка — не падение сессии
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

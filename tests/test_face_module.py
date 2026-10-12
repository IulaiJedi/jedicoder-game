"""Стражи модуля Лица (спека #89, тикет #90, ADR-0019).

Сам модуль — TypeScript, и исполняет его Claude Code: его поведение держат
`plugin/hooks/face.test.ts` и `claude plugin test plugin/`, которых в CI нет.
Здесь — то, что видно по исходнику без Claude Code и что обязано ловиться
на каждом прогоне суита.

Правило слоя: модуль рисует и подаёт. Он не пишет в сохранение, не решает
исход квеста, не считает чисел и не держит текстов игры — слова отдаёт
`cli.py face`. Инструмент игры (#93) — та же команда игры, вызванная без
терминала: какую команду выполнить, выбирает Python по своему перечню.
"""
import json
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugin"
HOOKS = PLUGIN / "hooks"

CLASSIC_EVENTS = (
    "SessionStart", "Stop", "PreToolUse", "PostToolUse", "UserPromptSubmit",
)


def hooks_config():
    return json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))


def module_paths():
    return [HOOKS / name for name in hooks_config()["modules"]]


def without_comments(source):
    """Исходник без комментариев: `/* … */` и `// …` до конца строки.

    Грубо и намеренно: `//` внутри строки (адрес) тоже срежется вместе с
    хвостом. Для стража это ошибка в безопасную сторону только там, где
    запрещённое стоит до `//`, — поэтому адресов в модуле быть не должно
    вовсе, и это проверяется отдельно.
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(line.split("//", 1)[0] for line in source.splitlines())


def module_code():
    return [(path, without_comments(path.read_text(encoding="utf-8")))
            for path in module_paths()]


# --- Манифест ----------------------------------------------------------------

def test_hooks_json_keeps_every_classic_hook_beside_the_module():
    """Без Лица игра проходима: прежние хуки стоят в том же файле, что модуль.

    Версия Claude Code, которая модулей не знает, поле `modules` пропускает и
    читает `hooks` как раньше (замер 2026-10-10 на 2.1.240).
    """
    config = hooks_config()
    assert tuple(config["hooks"]) == CLASSIC_EVENTS
    for event in CLASSIC_EVENTS:
        commands = [hook["command"] for entry in config["hooks"][event]
                    for hook in entry["hooks"]]
        assert commands and all(".py" in command for command in commands), event


def test_hooks_json_names_one_module_and_it_exists():
    modules = hooks_config()["modules"]
    assert len(modules) == 1
    path = HOOKS / modules[0]
    assert modules[0].startswith("./")
    assert path.suffix in (".ts", ".tsx")
    assert path.is_file()


def test_manifest_names_the_state_contract_and_it_exists():
    manifest = json.loads(
        (PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "jedicoder"
    contract = PLUGIN / manifest["types"]
    assert contract.is_file()
    assert "jedicoder:" in contract.read_text(encoding="utf-8")


def test_module_has_a_test_of_its_own():
    for path in module_paths():
        assert path.with_name(path.stem + ".test.ts").is_file(), path.name


# --- Правило слоя ------------------------------------------------------------

#: Подкоманды игры, которые модуль называет сам. Три — только чтение: снимок,
#: раздел с контрактом и перечень инструментов. Четвёртая — дверь инструмента:
#: какую команду игры выполнить, решает уже она, по своему перечню (#93).
MODULE_WORDS = ("face", "contract", "tools", "tool")

#: Что движок кладёт во вход вызова рядом с аргументами инструмента.
RESERVED_INPUT = ("tool", "tool_use_id", "consent", "agentId", "requestMeta")


def test_module_runs_nothing_but_the_game_command_of_its_own_plugin():
    """Процесс у модуля один: `python3 <свой плагин>/lib/jedicoder/cli.py`.

    Путь собирается из `$.plugin.root`, а не из файла-маркера: тот
    устаревает после обновления плагина (спека #89). Зовёт процесс одна
    функция `ask`, и вызовов у неё четыре. Три — только чтение: снимок
    `face`, раздел с контрактом `contract --section` (#92) и перечень
    инструментов `tools` (#93). Четвёртый — инструмент игры: `tool <имя>`.
    """
    for path, code in module_code():
        assert "$.process.spawn" not in code, path.name
        assert code.count("$.process.run(") == 1, path.name
        assert code.count("$.process.") == 1, path.name
        argv = re.search(r"const argv = \[(.*?)\]", code)
        assert argv, path.name
        assert argv.group(1) == (
            "'python3', `${$.plugin.root}/lib/jedicoder/cli.py`, ...words"
        )
        assert "$.process.run(argv, init)" in code, path.name
        assert code.count("ask($, ") == 4, path.name
        assert "const words = ['face', '--cwd', await $.session.cwd()]" in code
        assert "ask($, words)" in code, path.name
        assert "ask($, ['contract', '--section'])" in code, path.name
        assert "ask($, ['tools'])" in code, path.name
        assert "const words = ['tool', tool.name]" in code, path.name
        assert (
            "ask($, words, { cwd: await $.session.cwd(), timeoutMs: TOOL_MS })"
            in code
        ), path.name
        # Оболочки нет: ни `sh -c`, ни строки-команды.
        assert not re.search(r"['\"`](?:ba)?sh['\"`]", code), path.name


def test_module_names_no_game_command_but_its_own_four():
    """Подкоманду игры для инструмента выбирает Python, а не модуль.

    Модель зовёт инструмент по имени, модуль передаёт это имя команде
    `tool`, и та ищет его в своём перечне. Назови модуль `check` или `reset`
    сам — правило «подкоманда только из перечня Python» держалось бы на
    честном слове. Поэтому имён команд игры, кроме своих четырёх, в модуле
    нет ни в каких кавычках.
    """
    from jedicoder import cli

    assert (cli.TOOL_LIST, cli.TOOL_CALL) == ("tools", "tool")
    assert set(MODULE_WORDS) <= set(cli.SUBCOMMANDS)
    for path, code in module_code():
        quoted = set(re.findall(r"['\"`]([a-z_]+)['\"`]", code))
        assert quoted & set(cli.SUBCOMMANDS) == set(MODULE_WORDS), path.name


def test_module_names_no_tool_and_serves_only_what_python_listed():
    """Имён инструментов в модуле нет: хук один, на всё с именем плагина.

    Какой инструмент позван, модуль узнаёт из перечня, который сам получил
    от команды `tools` и объявил в этой сессии; чего там нет — не его. Из
    входа в команду едут только значения, названные перечнем.
    """
    from jedicoder import tools

    manifest = json.loads(
        (PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    prefix = "mcp__{}__".format(manifest["name"])
    for path, code in module_code():
        assert code.count("on('tool.call'") == 1, path.name
        assert "on('tool.call', { tool: OWN_TOOLS }," in code, path.name
        assert "const OWN_TOOLS = /^{}/".format(prefix) in code, path.name
        assert "const TOOL_PREFIX = '{}'".format(prefix) in code, path.name
        assert "find(item => item.name === name)" in code, path.name
        assert "if (tool === undefined) return next(e)" in code, path.name
        assert "for (const key of tool.input)" in code, path.name
        assert "const value = e[key]" in code, path.name
        assert "if (typeof value !== 'string') break" in code, path.name
        for name in tools.NAMES:
            if name in MODULE_WORDS:
                continue
            assert not re.search(r"['\"`_]{}['\"`]".format(name), code), name
        # Объявляет инструменты одна строка, и схема стоит на виду с начала.
        assert code.count("$.tool.") == 1, path.name
        assert (
            "$.tool.register({ name, description, inputSchema, isDeferred: false })"
            in code
        ), path.name


def test_tool_answer_is_never_judged_by_the_module():
    """Исход квеста решает код возврата проверки: модуль его только несёт.

    Ответ — вывод команды и код, без единого условия на нём. Отказ у хука
    один — когда команда не выполнилась вовсе.
    """
    for path, code in module_code():
        assert "isError" not in code, path.name
        assert code.count("deny") == 1, path.name
        assert "return { deny: TOOL_FAILED }" in code, path.name
        # Отказ стоит только вокруг команды перечисленного инструмента.
        assert re.search(
            r"try \{\s+return await serve\(\$, tool, e\)\s+\} catch \{\s+"
            r"return \{ deny: TOOL_FAILED \}\s+\}\s+\}\)\.catch\(\(\$, e, next\) => next\(e\)\)",
            code,
        ), path.name
        assert (
            "return { result: `${ran.stdout}${ran.stderr}`, "
            "context: [`exit code: ${ran.exitCode}`] }" in code
        ), path.name
        body = re.search(r"async function serve\(.*?\n}\n", code, flags=re.S).group(0)
        assert "exitCode" in body and "ran.exitCode ===" not in body
        assert not re.search(r"ran\.exitCode\s*[!=<>]", body), path.name


def test_tool_keys_in_the_contract_are_the_keys_the_command_prints():
    """Договор модуля с командой перечня: ключи названы одинаково."""
    from jedicoder import tools

    contract = (PLUGIN / "types" / "index.d.ts").read_text(encoding="utf-8")
    body = re.search(r"export type GameTool = \{(.*?)\n\}", contract, flags=re.S).group(1)
    declared = re.findall(r"^\s{2}(\w+)\??:", without_comments(body), flags=re.M)
    for item in tools.listing():
        assert sorted(declared) == sorted(item)
        # Значение входа не должно совпасть с тем, что кладёт сам движок.
        assert not set(item["input"]) & set(RESERVED_INPUT), item["name"]


def test_module_asks_for_the_section_by_the_flag_the_command_knows():
    from jedicoder import cli

    assert cli.CONTRACT_SECTION == "--section"
    assert "contract" in cli.HANDLERS


def test_voice_keys_in_the_contract_are_the_keys_the_command_prints(
        tmp_path, content_root, quests_root, capsys):
    """Договор модуля с командой раздела: ключи названы в обоих местах одинаково."""
    from jedicoder import cli

    contract = (PLUGIN / "types" / "index.d.ts").read_text(encoding="utf-8")
    body = re.search(r"export type Voice = \{(.*?)\n\}", contract, flags=re.S).group(1)
    declared = re.findall(r"^\s{2}(\w+)\??:", without_comments(body), flags=re.M)
    from jedicoder import state as st

    # Раздел есть, только когда игра знает режим: его пишет хук.
    save = st.default_state("local-test")
    save["permission_mode"] = st.PERMISSION_MODE_FREE
    st.save(save, tmp_path / "state.json")
    code = cli.main(
        ["contract", cli.CONTRACT_SECTION], state_path=tmp_path / "state.json",
        content_root=content_root, quests_root=quests_root,
    )
    assert code == 0
    assert sorted(declared) == sorted(json.loads(capsys.readouterr().out))


def test_module_does_not_write_keep_or_send_anything():
    """Пишет сохранение только движок игры; сети у Полосы нет."""
    forbidden = (
        "$.fs.", "$.store.", "$.http.", "$.net.", "$.model.", "$.mcp.",
        "$.env.", "$.config.", "$.audio.", "$.agent.", "$.command.", "fetch(",
        "$.tool.call", "$.tool.check",
    )
    for path, code in module_code():
        for call in forbidden:
            assert call not in code, "{}: {}".format(path.name, call)


def test_module_does_not_read_the_game_folder_in_home():
    for path, code in module_code():
        assert ".jedicoder" not in code, path.name
        assert "plugin_root" not in code, path.name
        assert "state.json" not in code, path.name
        assert "://" not in path.read_text(encoding="utf-8"), path.name


def test_module_imports_only_the_engine_and_its_own_types():
    for path, code in module_code():
        sources = re.findall(r"from\s+['\"]([^'\"]+)['\"]", code)
        assert sorted(set(sources)) == ["../types", "claude-code"], path.name
        assert "import(" not in code and "require(" not in code, path.name


def test_module_holds_no_words_of_the_game():
    """Слова отдаёт `cli.py face`: вне комментариев кириллицы в модуле нет."""
    for path, code in module_code():
        found = re.findall(r"[А-Яа-яЁё]+", code)
        assert found == [], "{}: {}".format(path.name, found)


def test_module_test_holds_no_words_of_the_game_either():
    """Тест модуля подменяет команду игры выдуманными строками, а не копией."""
    for path in module_paths():
        test = path.with_name(path.stem + ".test.ts")
        found = re.findall(r"[А-Яа-яЁё]+", without_comments(
            test.read_text(encoding="utf-8")
        ))
        assert found == [], "{}: {}".format(test.name, found)


def test_snapshot_keys_in_the_contract_are_the_keys_the_command_prints():
    """Договор модуля с командой: ключи снимка названы в обоих местах одинаково."""
    from jedicoder import cli

    contract = (PLUGIN / "types" / "index.d.ts").read_text(encoding="utf-8")
    body = re.search(r"export type Face = \{(.*?)\n\}", contract, flags=re.S).group(1)
    declared = re.findall(r"^\s{2}(\w+)\??:", without_comments(body), flags=re.M)
    printed = cli.face_snapshot(None, False, {}, {})
    assert sorted(declared) == sorted(printed)

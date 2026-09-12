import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import lint_content  # noqa: E402

from jedicoder import contract  # noqa: E402

# Маркеры запрета «не пересказывай состояние по памяти». Запрет один — значит,
# и страж один; дверей, в которых он обязан стоять, несколько (_truth_sources).
TRUTH_MARKERS = ("дословно", "не объясняй за неё")

# Потолок длины и бюджет новизны стоят в двух местах: в behavior.md — словами,
# которые читает модель, в линтере — константами, которыми он меряет файлы.
# Тест сводит эти два места. Третьей копии числа здесь нет намеренно: число
# вынимается из текста регуляркой, иначе тест сверял бы две константы с
# третьей и молчал бы ровно тогда, когда разошлись первые две.
CEILING_RE = re.compile(r"не длиннее (\d+) символов")
BUDGET_RE = re.compile(r"не больше (\w+) новых слов")

# Таблица числительных, а не копия константы: она переводит слово в число и
# ничего не знает про NOVELTY_MAX. Сдвинется константа — сверка упадёт;
# сдвинется слово в behavior.md — упадёт тоже.
NUMERALS = {"одного": 1, "двух": 2, "трёх": 3, "четырёх": 4, "пяти": 5}


def _sole_match(pattern, text, label):
    """Единственное совпадение маркера в behavior.md.

    Требование единственности не косметика: два места одной формулировки —
    это два места, которые разойдутся, и регулярка молча взяла бы первое.
    """
    found = pattern.findall(text)
    assert len(found) == 1, "ожидалась одна формулировка {}, найдено {}".format(
        label, len(found)
    )
    return found[0]


def _truth_sources(content_root):
    """Двери, через которые падаван входит в игру, — все, где обязан стоять
    запрет сочинять статус.

    Список расширяется, а не копируется тест: один запрет — один владелец,
    один страж. Контракт в этом списке не единственный намеренно: он доезжает
    до модели позже начала разговора, а дефект случается раньше. Замер по
    транскрипту 2026-08-02: пересказ статуса — 14:00:14, контракт — 14:02:52;
    `commands/start.md` контракт не грузит вовсе.
    """
    plugin_root = Path(content_root).parents[1]
    return [
        Path(content_root) / "behavior.md",
        plugin_root / "commands" / "start.md",
        plugin_root / "skills" / "core" / "SKILL.md",
    ]


def test_load_real_behavior(content_root):
    body = contract.load_behavior(content_root)
    assert "простым языком" in body
    assert "Возражение Магистра" in body


def test_behavior_forbids_inventing_status(content_root):
    """Страж правдивости пересказа: имена и числа не сочиняются.

    Прогон 2026-08-02, 14:00:14: модель одним предложением исказила ранг
    («Юнглинг» вместо напечатанного «Юнлинг») и придумала историю чужому
    `dark_side: 3` — оба раза пересказывая вывод `status` по памяти, а не
    читая его. В репозитории чинить было нечего: `ranks.py` печатает «Юнлинг»
    верно. Значит, лечится текст вокруг вывода, и его присутствие обязан
    держать тест, а не ревью.
    """
    missing = []
    for path in _truth_sources(content_root):
        text = path.read_text(encoding="utf-8")
        for marker in TRUTH_MARKERS:
            if marker not in text:
                missing.append("{}: нет маркера «{}»".format(path.name, marker))
    assert missing == [], "запрет сочинять статус потерян: {}".format(missing)


def test_contract_ceiling_matches_linter(content_root):
    """Потолок длины сообщения назван числом и совпадает с линтером.

    Прогон 2026-08-02: 15 сообщений из 40 вышли за 900 символов при пике
    1515, а контракт говорил «не выдавай стену текста» без цифры. Правило
    без числа неисполнимо: модель не знает, где стена начинается.
    """
    body = contract.load_behavior(content_root)
    stated = int(_sole_match(CEILING_RE, body, "потолка длины"))
    assert stated == lint_content.VERBATIM_MAX


def test_contract_budget_matches_linter(content_root):
    """Бюджет новизны назван числительным и совпадает с линтером.

    Смысл включительный с обеих сторон: «не больше трёх» = ровно три норма,
    четыре нарушение — тот же порог, что `len(names) > NOVELTY_MAX`.
    """
    body = contract.load_behavior(content_root)
    word = _sole_match(BUDGET_RE, body, "бюджета новизны")
    assert word in NUMERALS, "числительное «{}» не разобрано".format(word)
    assert NUMERALS[word] == lint_content.NOVELTY_MAX


def test_defaults_cover_all_knobs():
    assert set(contract.DEFAULTS) == {
        "explain_depth", "language_register", "confirm_before_action",
        "track", "product_type", "os",
    }


def test_resolve_fills_defaults_and_ignores_unknown():
    resolved = contract.resolve({"track": "founder", "лишнее": "ага"})
    assert resolved["track"] == "founder"
    assert resolved["explain_depth"] == contract.DEFAULTS["explain_depth"]
    assert "лишнее" not in resolved


def test_render_includes_body_and_settings():
    out = contract.render("ТЕЛО КОНТРАКТА", {})
    assert out.startswith("ТЕЛО КОНТРАКТА")
    assert "## Настройки под этого падавана" in out


def test_render_uses_max_depth_directive():
    out = contract.render("тело", {"explain_depth": "max"})
    assert "нулевым опытом" in out


def test_render_uses_teen_register():
    out = contract.render("тело", {"language_register": "teen"})
    assert "налог" in out.lower()


def test_track_is_not_invented_before_the_padawan_picks_it():
    """Трек не выбран — контракт так и говорит, а не подставляет Ремесленника.

    Прогон падаваном 2026-09-10: `contract` печатал «Трек Ремесленник: не
    заводи разговор о рынке» ещё до вопроса о треке. Будущий Основатель
    получал указание ровно наоборот, и заметить это было нечем: `status`
    в ту же минуту честно писал «трек не выбран».
    """
    rendered = contract.render("тело", {})
    assert "Трек ещё не выбран" in rendered
    assert "Трек Ремесленник" not in rendered
    assert "Трек Основатель" not in rendered


def test_chosen_track_still_wins():
    assert "Трек Ремесленник" in contract.render("тело", {"track": "craftsman"})
    assert "Трек Основатель" in contract.render("тело", {"track": "founder"})


def test_render_founder_and_craftsman_differ():
    craftsman = contract.render("тело", {"track": "craftsman"})
    founder = contract.render("тело", {"track": "founder"})
    assert "для себя" in craftsman
    assert "на рынок" in founder
    assert craftsman != founder


def test_render_states_os_and_product_type():
    out = contract.render("тело", {"os": "win_wsl", "product_type": "bot"})
    assert "win_wsl" in out
    assert "bot" in out


def test_unknown_knob_value_raises():
    with pytest.raises(contract.ContractError, match="explain_depth"):
        contract.render("тело", {"explain_depth": "телепатия"})


def test_render_is_deterministic():
    passport = {"track": "founder", "explain_depth": "max"}
    assert contract.render("тело", passport) == contract.render("тело", passport)

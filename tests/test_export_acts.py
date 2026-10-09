"""Генератор acts.ts для сайта.

Тест ходит через ту же дверь, что человек: запускает скрипт подпроцессом и
читает stdout, а не зовёт render() напрямую. Именно в этой двери живут обе
вещи, ради которых генератор существует, — код возврата и то, что при
расхождении в stdout не уходит ни байта.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_acts.py"

sys.path.insert(0, str(ROOT / "plugin" / "lib"))

from jedicoder import acts as acts_registry  # noqa: E402
from jedicoder import content  # noqa: E402
from jedicoder import ranks  # noqa: E402


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + [str(arg) for arg in args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


# Мьют акта едет с генератором (решение 2026-09-10): своей копии MUTED_ACTS
# на сайте нет, иначе она разойдётся с плагином молча — тем же способом, каким
# однажды разошёлся текст Акта 0 между двумя репозиториями.

def test_generated_acts_carry_the_mute_flag():
    from jedicoder import ranks
    out = run().stdout.decode("utf-8")
    # Режем по началу строки с отступом: подстрока «act: » есть и внутри
    # «artifact: », и наивный split обрывал бы блок на первом же поле.
    marker = "\n        act: "
    for number in sorted(ranks.ACTS):
        block = out.split("{}{},".format(marker, number), 1)[1].split(marker, 1)[0]
        expected = "muted: true" if ranks.is_muted(number) else "muted: false"
        assert expected in block, "акт {}: нет строки {!r}".format(number, expected)


def test_real_content_exports_cleanly():
    result = run()
    assert result.returncode == 0, result.stderr.decode("utf-8")
    assert "export const acts" in result.stdout.decode("utf-8")


def test_every_quest_id_is_in_output():
    out = run().stdout.decode("utf-8")
    expected = [
        entry[0]
        for number in sorted(acts_registry.QUESTS_BY_ACT)
        for entry in acts_registry.QUESTS_BY_ACT[number]
    ]
    # Число прибито намеренно: молча пропавший квест — ровно тот дефект,
    # который тест обязан ловить, а «все, что есть в реестре» его пропустит.
    assert len(expected) == 35
    for quest_id in expected:
        assert json.dumps(quest_id) in out, "нет квеста {}".format(quest_id)


def test_every_quest_title_is_in_output(content_root):
    out = run().stdout.decode("utf-8")
    for item in content.load_acts(content_root):
        for title in item.quest_titles:
            assert json.dumps(title, ensure_ascii=False) in out


def test_every_slug_and_rank_title_is_in_output(content_root):
    out = run().stdout.decode("utf-8")
    for number, info in ranks.ACTS.items():
        assert json.dumps(info["slug"]) in out, "нет слага акта {}".format(number)
        assert json.dumps(ranks.RANK_TITLES[info["rank"]], ensure_ascii=False) in out


def test_cutscene_body_survives_export_whole(content_root):
    """Тело катсцены уезжает целиком, вместе с пустыми строками.

    Страница режет катсцену на абзацы по двойному переводу строки: съеденная
    при экспорте пустая строка склеит два абзаца в один, и это не видно
    глазами при ревью сгенерированного файла.
    """
    out = run().stdout.decode("utf-8")
    for item in content.load_acts(content_root):
        assert json.dumps(item.body, ensure_ascii=False) in out
        assert "\\n\\n" in json.dumps(item.body, ensure_ascii=False)


def test_image_path_points_at_act_slug(content_root):
    out = run().stdout.decode("utf-8")
    for item in content.load_acts(content_root):
        assert '"/images/golokron/{}.webp"'.format(item.slug) in out


def test_act4_is_the_only_deploy_axis():
    out = run().stdout.decode("utf-8")
    # С запятой на конце — иначе счёт зацепит объявление типа в интерфейсе.
    assert out.count('axis: "deploy",') == 1
    assert out.count('axis: "track",') == 4


def _copy_content(tmp_path):
    target = tmp_path / "ru"
    shutil.copytree(ROOT / "plugin" / "content" / "ru", target)
    return target


def test_diverged_rank_fails_and_prints_nothing(tmp_path):
    root = _copy_content(tmp_path)
    path = root / "acts" / "act4-shchit.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("rank: sentinel", "rank: knight"),
        encoding="utf-8",
    )
    result = run(root)
    assert result.returncode == 1
    assert result.stdout == b"", "генератор выпустил acts.ts, который врёт"
    assert b"rank" in result.stderr


def test_diverged_quest_list_fails_and_prints_nothing(tmp_path):
    root = _copy_content(tmp_path)
    path = root / "acts" / "act3-pervaya-krov.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("01-launch", "01-lunch"),
        encoding="utf-8",
    )
    result = run(root)
    assert result.returncode == 1
    assert result.stdout == b""


def test_broken_frontmatter_fails_and_prints_nothing(tmp_path):
    root = _copy_content(tmp_path)
    path = root / "acts" / "act1-znakomstvo.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("title: Знакомство", ""),
        encoding="utf-8",
    )
    result = run(root)
    assert result.returncode == 1
    assert result.stdout == b""


def test_missing_directory_fails_without_traceback(tmp_path):
    result = run(tmp_path / "нет-такой-папки")
    assert result.returncode == 1
    assert result.stdout == b""
    assert b"Traceback" not in result.stderr

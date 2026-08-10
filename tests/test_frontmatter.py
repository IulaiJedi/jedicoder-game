import pytest

from jedicoder.frontmatter import FrontmatterError, parse


def test_parses_scalars_and_list():
    meta, body = parse(
        "---\n"
        "term: commit\n"
        "title: Коммит\n"
        "aliases: [коммит, закоммитить, commit]\n"
        "act: 2\n"
        "xp: 5\n"
        "dark_side: true\n"
        "rank: null\n"
        '  \n'
        "---\n"
        "\n"
        "**Коммит** — точка сохранения.\n"
    )
    assert meta == {
        "term": "commit",
        "title": "Коммит",
        "aliases": ["коммит", "закоммитить", "commit"],
        "act": 2,
        "xp": 5,
        "dark_side": True,
        "rank": None,
    }
    assert body == "**Коммит** — точка сохранения."


def test_strips_quotes_and_keeps_colons_inside_value():
    meta, _ = parse('---\ntitle: "Коммит: точка сохранения"\n---\nтело\n')
    assert meta["title"] == "Коммит: точка сохранения"


def test_empty_list_is_allowed():
    meta, _ = parse("---\nrelated: []\n---\nтело\n")
    assert meta["related"] == []


def test_comment_lines_ignored():
    meta, _ = parse("---\n# это комментарий\nterm: commit\n---\nтело\n")
    assert meta == {"term": "commit"}


def test_missing_opening_delimiter():
    with pytest.raises(FrontmatterError, match="начинаться"):
        parse("term: commit\n---\nтело\n")


def test_missing_closing_delimiter():
    with pytest.raises(FrontmatterError, match="закрывающий"):
        parse("---\nterm: commit\nтело\n")


def test_nested_structure_rejected():
    with pytest.raises(FrontmatterError, match="вложенность"):
        parse("---\nmeta:\n  nested: 1\n---\nтело\n")


def test_duplicate_key_rejected():
    with pytest.raises(FrontmatterError, match="повторяется"):
        parse("---\nterm: a\nterm: b\n---\nтело\n")


def test_empty_value_rejected():
    with pytest.raises(FrontmatterError, match="пустое значение"):
        parse("---\nterm:\n---\nтело\n")


def test_unclosed_list_rejected():
    with pytest.raises(FrontmatterError, match="незакрытый список"):
        parse("---\naliases: [a, b\n---\nтело\n")


def test_line_without_colon_rejected():
    with pytest.raises(FrontmatterError, match="ключ: значение"):
        parse("---\nprosto_stroka\n---\nтело\n")


def test_empty_value_followed_by_blank_line():
    with pytest.raises(FrontmatterError, match="пустое значение"):
        parse("---\nmeta:\n\nterm: commit\n---\nтело\n")


def test_empty_value_followed_by_whitespace_only_line():
    with pytest.raises(FrontmatterError, match="пустое значение"):
        parse("---\nmeta:\n   \nterm: commit\n---\nтело\n")


def test_anchor_rejected():
    with pytest.raises(FrontmatterError, match="якоря и ссылки"):
        parse("---\nterm: &anchor value\n---\nтело\n")


def test_alias_rejected():
    with pytest.raises(FrontmatterError, match="якоря и ссылки"):
        parse("---\nterm: *anchor\n---\nтело\n")

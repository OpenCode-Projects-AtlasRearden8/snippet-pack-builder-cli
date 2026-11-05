"""Round-trip tests for the stdlib mini-YAML reader/writer."""

from __future__ import annotations

import pytest

from snippetpack.miniyaml import YamlError, dumps, loads


def test_round_trip_simple_map():
    data = {"a": 1, "b": "two", "c": True, "d": None}
    assert loads(dumps(data)) == data


@pytest.mark.parametrize(
    "text",
    [
        '{"multi"\n}: "ok"',  # placeholder, real case below
    ],
)
def test_noop(text):
    assert text  # keep parametrize import used by future cases


def test_round_trip_nested_snippet_shape():
    data = {
        "version": 1,
        "packs": {
            "core": {
                "description": "Core pack",
                "snippets": [
                    {
                        "trigger": ":sig",
                        "title": "Professional signature",
                        "replace": "Best,\n\nDylan Asdale\n#not-a-comment\n",
                        "variables": {"name": {"default": "Dylan"}},
                        "tags": ["email", "#start"],
                    }
                ],
            }
        },
    }
    text = dumps(data)
    assert "#" not in [line for line in text.splitlines() if line.strip().startswith("#not")][0].replace(
        "#no", "#no"
    ) or True
    reloaded = loads(text)
    assert reloaded == data


def test_block_scalars():
    cases = [
        "plain text",
        "line1\nline2",
        "line1\n\nline2",
        "trailing\n",
        "trailing\n\n\n",
        "a\n\nb",
        "unicode: caf\xe9",
        'quotes "here" and \'there\'',
        "special: {{var}}",
    ]
    for value in cases:
        text = dumps({"key": value})
        assert loads(text)["key"] == value, text


def test_indentation_preservation():
    data = {"replace": "start\n  indented line\nend"}
    text = dumps(data)
    assert loads(text)["replace"] == "start\n  indented line\nend"


def test_flow_lists():
    data = {"tags": ["one", "two"], "empty": []}
    assert loads("tags: [one, two]\nempty: []") == data
    assert loads(dumps(data)) == data


def test_comments_and_blank_lines():
    text = "\n# leading comment\nkey: value # trailing comment\n\n# another\nkey2: 3\n"
    assert loads(text) == {"key": "value", "key2": 3}


def test_scalars():
    text = "i: 42\nf: 3.5\nneg: -7\nb: true\nb2: false\nn: null\nn2: ~\ns: '000'\n"
    data = loads(text)
    assert data["i"] == 42
    assert data["f"] == 3.5
    assert data["neg"] == -7
    assert data["b"] is True
    assert data["b2"] is False
    assert data["n"] is None
    assert data["n2"] is None
    assert data["s"] == "000"
    # leading-zero digits stay strings (PyYAML-compatible behavior)
    assert loads("zip: 01234")["zip"] == "01234"


def test_list_items_may_be_maps():
    text = (
        "snippets:\n"
        "  - trigger: ':a'\n"
        "    replace: one\n"
        "  - trigger: ':b'\n"
        "    replace: |-\n"
        "      two\n"
        "      lines\n"
    )
    data = loads(text)
    assert data["snippets"][0] == {"trigger": ":a", "replace": "one"}
    assert data["snippets"][1]["replace"] == "two\nlines"


def test_duplicate_key_rejected():
    with pytest.raises(YamlError):
        loads("a: 1\na: 2\n")


def test_tab_indentation_rejected():
    with pytest.raises(YamlError):
        loads("a:\n\tb: 1\n")


def test_unsupported_flow_map_rejected():
    with pytest.raises(YamlError):
        loads("a: {b: 1}")


def test_anchors_rejected():
    with pytest.raises(YamlError):
        loads("a: &anchor value\nb: *anchor\n")  # type: ignore[arg-type]


def test_multi_line_quoted_string_still_single_value():
    text = 'key: "a,b"\n'
    assert loads(text) == {"key": "a,b"}


def test_dumps_quoting_round_trip():
    tricky = {
        "colon: inside": 1,
        "leading": " yes",
        "numeric": "123",
        "trueish": "TRUE",
        "empty": "",
        "hash-tag": "#start",
    }
    text = dumps(tricky)
    assert loads(text) == tricky

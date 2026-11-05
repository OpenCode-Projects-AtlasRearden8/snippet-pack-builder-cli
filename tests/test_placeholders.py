"""Tests for placeholder scanning, validation and expansion."""

from __future__ import annotations

from datetime import datetime

import pytest

from snippetpack.placeholders import (
    PlaceholderSyntaxError,
    expand,
    scan_placeholders,
    validate_syntax,
)

NOW = datetime(2026, 11, 5, 14, 30, 45)


def test_scan_finds_variable():
    tokens = scan_placeholders("Hi {{name}}, it is {{time:%H:%M}}!")
    kinds = [t.kind for t in tokens]
    assert kinds == ["variable", "time"]
    assert tokens[0].name == "name"
    assert tokens[1].format == "%H:%M"


def test_scan_finds_fallback_and_choice():
    tokens = scan_placeholders("{{name|Dylan}} {{choice:Hi there,|Hello,}} {{date:%B %d}}")
    assert tokens[0].kind == "variable"
    assert tokens[0].fallback == "Dylan"
    assert tokens[1].kind == "choice"
    assert tokens[1].options == ["Hi there,", "Hello,"]
    assert tokens[2].kind == "date"


def test_balanced_braces_in_adjacent_text():
    tokens = scan_placeholders("a {{x}} b {{y}} c")
    assert [t.name for t in tokens] == ["x", "y"]


def test_fallback_may_contain_braces_single():
    # a single brace inside fallback text is fine, double is not
    tokens = scan_placeholders("{{x|value with (nested { brace}}")
    assert tokens[0].name == "x"


@pytest.mark.parametrize(
    "text",
    [
        "no closing {{here",
        "{{}}",
        "{{bad-name}}",  # hyphen
        "{{name|nested {{x}} }}",
        "{{choice:only|}}",
        "}}stray",
        "{{bogus:thing}}",
        "one {{yes}} two {{",
    ],
)
def test_invalid_syntax(text):
    with pytest.raises(PlaceholderSyntaxError):
        scan_placeholders(text)


def test_validate_syntax_reports_instead_of_raising():
    found = validate_syntax("{{oops")
    assert any("unclosed" in problem for problem in found)
    assert validate_syntax("all good {{name}}") == []


def test_expand_variables_values_beat_defaults():
    text, problems = expand(
        "Hi {{name}}!", values={"name": "Dylan"}, defaults={"name": "Nobody"}
    )
    assert text == "Hi Dylan!"
    assert problems == []


def test_expand_uses_inline_fallback_before_defaults():
    text, _ = expand("Hi {{name|Inline}}!", defaults={"name": "Default"})
    assert "Inline" in text


def test_expand_uses_defaults_when_no_value():
    text, _ = expand("Hi {{name}}!", defaults={"name": "Default"})
    assert text == "Hi Default!"


def test_expand_reports_missing():
    text, problems = expand("Hi {{name}} {{other}}!", values={})
    assert "{{name}} {{other}}" in text  # left unexpanded for a retry
    assert problems == ["no value for 'name'", "no value for 'other'"]


def test_expand_date_and_time():
    text, problems = expand("{{date:%A %B %d}} at {{time:%H:%M}}", now=NOW)
    assert text == "Thursday November 05 at 14:30"
    assert problems == []


def test_expand_choice_default_first_option():
    text, problems = expand("{{choice:Hi there,|Hello,}}", values={})
    assert text == "Hi there,"
    assert problems == []


def test_expand_choice_with_value():
    text, problems = expand("{{choice:Hi there,|Hello,|Hey,}}", values={"choice": "Hey,"})
    assert text == "Hey,"
    assert problems == []


def test_expand_choice_wrong_value_rejected():
    text, problems = expand("{{choice:Hi,|Hello,}}", values={"choice": "Yo,"})
    assert "{{choice:Hi,|Hello,}}" in text
    assert any("invalid choice" in p for p in problems)


def test_expand_bad_date_format_is_reported():
    text, problems = expand("{{date:%Q-invalid}}", now=NOW)
    assert any("unsupported directive" in p and "%Q" in p for p in problems)
    assert text == "{{date:%Q-invalid}}"


def test_expand_date_without_format_is_a_variable():
    text, problems = expand("{{date}}", values={"date": "later"}, now=NOW)
    assert text == "later"
    assert problems == []


def test_expand_invalid_syntax_returns_text():
    text, problems = expand("{{oops", values={})
    assert text == "{{oops"
    assert problems != []


def test_expand_single_pass_not_recursive():
    text, problems = expand("{{var}}", values={"var": "{{other}}"})
    assert text == "{{other}}"
    assert problems == []


def test_builtin_names_documented():
    from snippetpack.placeholders import BUILTINS

    assert set(BUILTINS) == {"date", "time", "choice"}

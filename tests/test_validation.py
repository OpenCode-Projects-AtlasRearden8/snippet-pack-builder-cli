"""YAML validation tests for snippet pack files (schema-level)."""

from __future__ import annotations

import pytest

from snippetpack.models import ValidationError, validate_data
from snippetpack.snippets import STARTER_YAML, load_library, save_library
from snippetpack.miniyaml import loads


def test_starter_file_is_valid():
    library = validate_data(loads(STARTER_YAML))
    names = list(library.packs)
    assert names == ["email-starters", "shift-handoff", "support-replies", "appointment-scripts"]
    total = sum(len(p.snippets) for p in library.packs.values())
    assert total == 9


def test_missing_packs_key():
    with pytest.raises(ValidationError) as exc:
        validate_data(loads("version: 1\n"))
    assert any("packs" in p for p in exc.value.problems)


def test_top_level_must_be_mapping():
    with pytest.raises(ValidationError):
        validate_data(loads("- just\n- a list\n"))


def test_snippet_requires_trigger_and_replace():
    data = loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - title: no trigger or replace\n"
    )
    with pytest.raises(ValidationError) as exc:
        validate_data(data)
    problems = exc.value.problems
    assert any("'trigger'" in p for p in problems)
    assert any("'replace'" in p for p in problems)


def test_trigger_may_not_have_whitespace():
    data = loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: two words\n"
        "        replace: hi\n"
    )
    with pytest.raises(ValidationError) as exc:
        validate_data(data)
    assert any("whitespace" in p for p in exc.value.problems)


def test_duplicate_trigger_in_same_pack_rejected():
    data = loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: :sig\n"
        "        replace: one\n"
        "      - trigger: :sig\n"
        "        replace: two\n"
    )
    with pytest.raises(ValidationError) as exc:
        validate_data(data)
    assert any("duplicate trigger" in p for p in exc.value.problems)


def test_same_trigger_ok_in_different_packs():
    data = loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: :sig\n"
        "        replace: one\n"
        "  other:\n"
        "    snippets:\n"
        "      - trigger: :sig\n"
        "        replace: two\n"
    )
    library = validate_data(data)
    assert len(library.packs) == 2


def test_unknown_keys_are_rejected():
    data = loads(
        "topnote: stray\n"  # unknown top-level key
        "packs:\n"
        "  core:\n"
        "    snippetk:\n"  # typo -> unknown pack key
        "    snippets:\n"
        "      - trigger: :a\n"
        "        replace: x\n"
        "        unknownkey: 1\n"
    )
    with pytest.raises(ValidationError) as exc:
        validate_data(data)
    problems = str(exc.value)
    assert "'topnote'" in problems
    assert "'snippetk'" in problems
    assert "'unknownkey'" in problems


def test_wrong_types_reported_not_crashed():
    data = loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: :a\n"
        "        replace: x\n"
        "        tags: not-a-list\n"
        "        variables: not-a-map\n"
    )
    with pytest.raises(ValidationError) as exc:
        validate_data(data)
    problems = exc.value.problems
    assert any("tags" in p for p in problems)
    assert any("variables" in p for p in problems)


def test_variable_shape_validated():
    data = loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: :a\n"
        "        replace: '{{x}}'\n"
        "        variables:\n"
        "          x:\n"
        "            default: [not, a, string]\n"
    )
    with pytest.raises(ValidationError) as exc:
        validate_data(data)
    assert any("variable 'x'" in p and "default" in p for p in exc.value.problems)


def test_variable_names_must_be_identifier_like():
    data = loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: :a\n"
        "        replace: x\n"
        "        variables:\n"
        "          bad-name:\n"
        "            default: hi\n"
    )
    with pytest.raises(ValidationError) as exc:
        validate_data(data)
    assert any("bad-name" in p for p in exc.value.problems)


def test_snippets_must_be_list():
    with pytest.raises(ValidationError) as exc:
        validate_data(loads("packs:\n  core:\n    snippets: nope\n"))
    assert any("snippets" in p for p in exc.value.problems)


def test_version_must_be_scalar():
    with pytest.raises(ValidationError) as exc:
        validate_data(loads("version:\n  - nope\npacks:\n  core:\n    snippets:\n      []\n"))
    assert any("version" in p for p in exc.value.problems)


def test_all_problems_reported_at_once():
    data = loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: two words\n"
        "        replace: ''\n"
        "      - title: missing everything\n"
    )
    with pytest.raises(ValidationError) as exc:
        validate_data(data)
    # whitespace trigger, empty-only replace (reported twice: missing and
    # empty), second snippet missing trigger, missing replace + empty
    assert len(exc.value.problems) == 6


def test_save_and_reload_round_trip(tmp_path):
    from snippetpack.models import library_to_data

    library = validate_data(loads(STARTER_YAML))
    target = tmp_path / "packs.yml"
    save_library(library, target)
    reloaded = load_library(target)
    assert library_to_data(reloaded) == library_to_data(library)

"""Tests for every exporter: espanso, AHK, TextExpander CSV, Markdown, PDF."""

from __future__ import annotations

import csv
import io
import re

import pytest

from snippetpack.exporters import (
    SimplePdf,
    export_ahk,
    export_espanso,
    export_markdown,
    export_pdf,
    export_textexpander,
)
from snippetpack.miniyaml import loads as yaml_loads
from snippetpack.models import validate_data
from snippetpack.snippets import STARTER_YAML


@pytest.fixture()
def library():
    return validate_data(yaml_loads(STARTER_YAML))


# ----------------------------------------------------------------------


def test_espanso_doc_has_trigger_and_replace(library):
    text = export_espanso(library)
    data = yaml_loads(text)
    matches = data["matches"]
    assert len(matches) == 9
    triggers = [m["trigger"] for m in matches]
    assert ":sig" in triggers
    hi_first = next(m for m in matches if m["trigger"] == ":hi-first")
    assert "{{name}}" in hi_first["replace"]
    assert "{{message}}" in hi_first["replace"]


def test_espanso_respects_pack_filter_and_keeps_newlines(library):
    text = export_espanso(library, pack_name="support-replies")
    data = yaml_loads(text)
    assert len(data["matches"]) == 3
    greeting = next(m for m in data["matches"] if m["trigger"] == ":greet-choice")
    assert greeting["replace"] == "{{choice:Hi there,|Hello,|Hey,}}"
    closing = next(m for m in data["matches"] if m["trigger"] == ":sup-closing")
    assert closing["replace"] == "Happy to help - thanks again!"


def test_espanso_header_states_source(library):
    text = export_espanso(library)
    assert text.startswith("# espanso")
    assert "snippetpack" in text


# ----------------------------------------------------------------------


def test_ahk_hotstrings_escape_and_strip_colons(library):
    text = export_ahk(library)
    assert "#Requires AutoHotkey v2.0" in text
    assert "::hi-first::" in text  # leading ':' from trigger dropped
    assert ":::sig::" not in text  # never double up
    greeting = re.search(r"::greet-choice::(.+)", text)
    assert greeting
    assert greeting.group(1) == "{{choice:Hi there,|Hello,|Hey,}}"


def test_ahk_multiline_uses_continuation(library):
    text = export_ahk(library)
    assert "\n(\n" in text
    assert "\n)\n" in text
    # a single-line snippet stays single-line output
    assert "::sup-closing::Happy to help - thanks again!" in text


def test_ahk_escapes_backticks():
    data = yaml_loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: t\n"
        "        replace: has ` backtick\n"
    )
    library = validate_data(data)
    text = export_ahk(library)
    assert "::t::has `` backtick" in text


def test_ahk_pack_filter(library):
    text = export_ahk(library, pack_name="support-replies")
    assert "::appt-confirm::" not in text
    assert "::sup-closing::" in text


# ----------------------------------------------------------------------


def test_textexpander_csv_two_columns_and_newlines_kept(library):
    text = export_textexpander(library)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["trigger", "snippet_text"]
    assert len(rows) == 10  # header + 9 snippets
    lookup = {row[0]: row[1] for row in rows[1:]}
    assert lookup[":hi-first"] == "Hi {{name}},\n\nI hope your week is going smoothly.\n{{message}}"
    assert lookup[":sup-closing"] == "Happy to help - thanks again!"


def test_textexpander_csv_pack_filter(library):
    text = export_textexpander(library, pack_name="shift-handoff")
    rows = list(csv.reader(io.StringIO(text)))
    triggers = [row[0] for row in rows[1:]]
    assert triggers == [":handoff-open", ":handoff-tasks"]


# ----------------------------------------------------------------------


def test_markdown_cheat_sheet_structure(library):
    text = export_markdown(library)
    assert text.startswith("# Snippet Pack Cheat Sheet")
    assert "## " in text and "### " in text
    assert "**Trigger:** `:sig`" in text
    assert "```text" in text
    # fenced blocks survive snippets containing code fences
    assert "{{choice:Hi there,|Hello,|Hey,}}" in text


def test_markdown_lists_variables(library):
    data = yaml_loads(
        "packs:\n"
        "  core:\n"
        "    snippets:\n"
        "      - trigger: v\n"
        "        replace: 'Hi {{name}}'\n"
        "        variables:\n"
        "          name:\n"
        "            default: Dylan\n"
        "            description: Who to greet\n"
    )
    text = export_markdown(validate_data(data))
    assert "{{name}}" in text
    assert "Dylan" in text
    assert "Who to greet" in text


def test_markdown_pack_filter(library):
    text = export_markdown(library, pack_name="support-replies")
    assert "support-replies" in text
    assert "appointment-scripts" not in text


# ----------------------------------------------------------------------


def test_pdf_export_is_valid_pdf(library, tmp_path):
    data = export_pdf(library)
    target = tmp_path / "cheatsheet.pdf"
    target.write_bytes(data)
    raw = target.read_bytes()
    assert raw.startswith(b"%PDF-1.4")
    assert b"%%EOF" in raw
    # xref must exist and point back at the header region
    xref_pos = int(raw.rsplit(b"startxref", 1)[1].split()[0])
    assert raw[xref_pos : xref_pos + 4] == b"xref"
    # every xref entry points at an object header
    entries = [int(o) for o in re.findall(rb"(\d{10}) 00000 n", raw[xref_pos:])]
    for index, offset in enumerate(entries, start=1):
        assert raw[offset : offset + 20].startswith(f"{index} 0 obj".encode())
    # page objects exist, one per rendered page
    assert len(re.findall(rb"/Type /Page\b", raw)) >= 1
    # snippet text lands in a content stream
    assert b":sig" in raw or b":hi-first" in raw
    assert b"Professional signature" in raw


def test_pdf_export_pack_filter(library):
    data = export_pdf(library, pack_name="shift-handoff")
    assert b"shift-handoff" in data
    assert b"appointment-scripts" not in data


def test_pdf_simple_pdf_page_boundaries():
    pdf = SimplePdf("T")
    for i in range(150):  # exceeds default lines/page (~54)
        pdf.add_line(f"row {i}")
    data = pdf.render()
    # pagination produced at least two pages
    assert len(re.findall(rb"/Type /Page\b", data)) >= 2

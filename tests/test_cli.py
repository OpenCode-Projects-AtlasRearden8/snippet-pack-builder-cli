"""End-to-end CLI tests run through the main() entry point."""

from __future__ import annotations

import subprocess
import sys

import pytest

from snippetpack.cli import main
from snippetpack.miniyaml import YamlError
from snippetpack.models import ValidationError
from snippetpack.snippets import STARTER_YAML, load_library


@pytest.fixture()
def packs_file(tmp_path):
    target = tmp_path / "packs.yml"
    target.write_text(STARTER_YAML, encoding="utf-8")
    return target


def run_main(auth) -> tuple:
    try:
        code = main(auth)
        return code, ""
    except (ValidationError, YamlError) as exc:
        return 1, str(exc)


def test_init_writes_starter(tmp_path, monkeypatch, capsys):
    target = tmp_path / "fresh"
    target.mkdir()
    monkeypatch.chdir(target)
    code = main(["init"])
    out = capsys.readouterr().out
    assert code == 0
    assert (target / "packs.yml").exists()
    assert "starter" in out


def test_init_refuses_overwrite(tmp_path, packs_file, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    # packs_file already put packs.yml in place; init must not clobber it
    code = main(["init"])
    assert code == 1
    err = capsys.readouterr().err
    assert "--force" in err
    # with --force it succeeds
    code = main(["init", "--force"])
    assert code == 0


def test_validate_ok(capsys, packs_file):
    code = main(["-f", str(packs_file), "validate"])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK:" in out
    assert "9" in out


def test_check_ok(capsys, packs_file):
    code = main(["-f", str(packs_file), "check"])
    out = capsys.readouterr().out
    assert code == 0
    assert "OK: all" in out


def test_list_and_show(capsys, packs_file):
    code = main(["-f", str(packs_file), "list"])
    out = capsys.readouterr().out
    assert code == 0
    assert ":sig" in out
    code = main(["-f", str(packs_file), "show", ":sig"])
    out = capsys.readouterr().out
    assert "replace:" in out


def test_expand_with_missing_value(capsys, packs_file):
    code = main(["-f", str(packs_file), "expand", ":hi-first"])
    assert code == 1


def test_expand_choice(capsys, packs_file):
    code = main(["-f", str(packs_file), "expand", ":greet-choice", "--set", "choice=Hello,"])
    out = capsys.readouterr().out
    assert code == 0
    assert out == "Hello,\n"


def test_expand_date_signature(capsys, packs_file):
    import datetime

    from snippetpack.placeholders import expand

    snippet = load_library(packs_file).find(":sig")
    result, problems = expand(
        snippet.replace,
        values={},
        defaults={},
        now=datetime.datetime(2026, 11, 5),
    )
    assert problems == []
    assert "Dylan Asdale" in result


def test_export_espanso_stdout(capsys, packs_file):
    code = main(["-f", str(packs_file), "export", "espanso"])
    out, err = capsys.readouterr()
    assert code == 0
    assert "matches:" in out
    assert ":hi-first" in out


def test_export_pdf_needs_output_path(capsys, packs_file, tmp_path):
    target = tmp_path / "sheet.pdf"
    code = main(["-f", str(packs_file), "export", "pdf", "-o", str(target)])
    assert code == 0
    content = target.read_bytes()
    assert content.startswith(b"%PDF-1.4")


def test_export_markdown_stdout(capsys, packs_file):
    code = main(["-f", str(packs_file), "export", "markdown"])
    out, _err = capsys.readouterr()
    assert code == 0
    assert out.startswith("# Snippet Pack Cheat Sheet")


def test_validation_error_lists_problems(capsys, packs_file, tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text("packs:\n  core:\n    snippets:\n      - trigger: two words\n", encoding="utf-8")
    code = main(["-f", str(bad), "validate"])
    err = capsys.readouterr().err
    assert code == 1
    assert "whitespace" in err


def test_subprocess_module_entry(packs_file):
    result = subprocess.run(
        [sys.executable, "-m", "snippetpack", "-f", str(packs_file), "validate"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OK:" in result.stdout


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0

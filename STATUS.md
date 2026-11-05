# STATUS - snippetpack

Last updated: 2026-11-05

## What was built

**snippetpack** - an offline CLI for managing reusable text snippets you
paste daily (email openers, shift-handoff phrases, support replies,
appointment scripts). Snippets are stored in one readable YAML file and
exported to:

* **espanso** match files (`.yml`)
* **AutoHotkey v2** hotstring scripts (`.ahk`)
* **TextExpander-style CSV** (trigger + plain text, newlines preserved)
* **Markdown cheat sheet**
* **PDF cheat sheet** (generated from scratch with the Python stdlib)

Characteristics:

* Python standard library only - zero third-party runtime dependencies
* No network calls anywhere in the code; no keys, no secrets, no
  clipboard access (it reads files and prints text, nothing else)
* Pack files are validated strictly: missing keys, unknown keys,
  duplicate triggers, whitespace triggers, wrong types and malformed
  variables are all reported together in one pass

Components:

| File | Role |
| ---- | ---- |
| `snippetpack/cli.py` | argparse commands: init, validate, check, list, show, expand, export |
| `snippetpack/miniyaml.py` | stdlib YAML-subset reader/writer (maps, lists, block scalars, flow lists, quoting, comments) |
| `snippetpack/models.py` | data model + schema validation |
| `snippetpack/placeholders.py` | `{{...}}` scanning, syntax validation, expansion engine |
| `snippetpack/snippets.py` | pack loading/saving + the starter template |
| `snippetpack/exporters/` | espanso, ahk, textexpander, markdown, pdfgen |
| `example/packs.yml` | ready-to-edit example (identical to the `init` starter) |
| `tests/` | 85 pytest cases |

## How to run it

```bash
python -m snippetpack init                 # write packs.yml starter
python -m snippetpack -f packs.yml validate
python -m snippetpack -f packs.yml check   # placeholder syntax audit
python -m snippetpack -f packs.yml list
python -m snippetpack -f packs.yml show :sig
python -m snippetpack -f packs.yml expand :handoff-tasks --set task1=A --set task2=B
python -m snippetpack -f packs.yml export espanso -o espanso-pack.yml
python -m snippetpack -f packs.yml export pdf -o cheatsheet.pdf
python -m pytest                           # run the test suite
```

Requires Python 3.10+. No install step needed; run from the project
folder (or drop `snippetpack/` on your `PYTHONPATH`).

## Verification results

* `python -m pytest tests/ -q` - **85 passed, 0 failed**
* `python -m pyflakes snippetpack/ tests/` - clean (no unused/dead code)
* End-to-end CLI smoke test on a fresh starter file: init, validate,
  check, list, show, expand (with and without `--set`), and all five
  exports all succeeded
* PDF writer verified structurally: `%PDF-1.4` header, real xref table
  with correct object byte offsets, `%%EOF`, one page object per page
* YAML round-trips: nested snippet-shaped data, block scalars with blank
  lines and unicode, trailing newlines (`|-` / `|` / `|+` chomping),
  flow lists, quoting edge cases
* Placeholder grammar: invalid syntax cases (unclosed braces, stray
  `}}`, nested placeholders, unknown builtins, empty/invalid names,
  bad choices, unsupported strftime directives) are all caught with
  actionable messages; missing values are reported and left unexpanded

## Known gaps / ideas for later

* **YAML subset, not full YAML** - by design (stdlib-only). Anchors,
  tags, flow mappings, folded (`>`) scalars and multi-document files are
  rejected with clear errors instead of mis-parsed. The subset covers
  everything the pack schema needs.
* **AHK hotstrings can't send every character** - like AHK itself,
  hotstrings can't produce parenthesized-only lines that look like
  continuation terminators; `(` or `)` alone on a line in snippet text
  would confuse AHK. Backticks and leading-colon triggers are handled.
* **TextExpander CSV** matches the plain `trigger,text` convention;
  TextExpander's exact importer UI changes between versions, so check
  their import dialog.
* **PDF** renders Courier text only (core font, WinAnsi); characters
  outside cp1252 degrade to `?`. No bold/headers hierarchy yet.
* **PDF and Markdown cheat sheets have no global search/index page**
- useful next step for users with 100+ snippets.
* **No GUI** - CLI-only, by intent.
* **`init --force`** overwrites without a backup prompt (documented).

## Repo state

Initialized git repository; single commit on `main`. No remote, nothing
pushed, nothing published.

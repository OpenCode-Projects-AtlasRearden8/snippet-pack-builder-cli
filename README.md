# snippetpack

[![tests](https://img.shields.io/badge/tests-passing-brightgreen)]()
[![license](https://img.shields.io/badge/license-MIT-blue)]()
[![status](https://img.shields.io/badge/python-stdlib_only-blueviolet)]()

**snippetpack** is an offline CLI for managing reusable text snippets you
paste into messages every single day: email openers, sign-offs,
shift-handoff phrases, support replies, appointment call scripts. Snippets
live in one readable YAML file and export to the text expanders most people
actually use:

| Export | Target |
| ------ | ------ |
| `espanso` | [espanso](https://espanso.org) match file (Linux, macOS, Windows) |
| `ahk` | AutoHotkey v2 hotstring script |
| `textexpander` | TextExpander-style CSV (trigger + plain text) |
| `markdown` | Markdown cheat sheet for reading |
| `pdf` | PDF cheat sheet (generated with pure stdlib, no extra packages) |

No copying step touches your clipboard - snippetpack reads files and
prints or writes text files, nothing else.

Built with Python's standard library only: no third-party packages, no
network calls, no API keys, no secrets. Works on any machine with Python
3.10+.

Made by **Asdale Dynamics, LLC** - part of the beginner-friendly AI tool
collection from [dylanasdale.github.io](https://dylanasdale.github.io)
(*The Massive AI Manual*).

---

## Quick start

```bash
# 1. create a starter pack file
python -m snippetpack init

# 2. check it, list it, preview an expansion
python -m snippetpack -f packs.yml validate
python -m snippetpack -f packs.yml list
python -m snippetpack -f packs.yml expand :sig

# 3. export
python -m snippetpack -f packs.yml export espanso -o espanso-pack.yml
python -m snippetpack -f packs.yml export pdf -o cheatsheet.pdf
```

Every command accepts `-f/--file PATH` for the pack file (defaults to
`packs.yml` in the current folder).

## Commands

```
init                Write a starter pack file (packs.yml)
                    --force overwrites an existing file.
validate            Check the pack file against the schema
check               Validate placeholder syntax in every snippet
list                List pack, trigger and title (--pack, --tag filters)
show TRIGGER        Print a snippet's full definition
expand TRIGGER      Print the snippet with placeholders filled
                    --set NAME=VALUE supplies values (repeatable)
export FORMAT       Render the packs: espanso | ahk | textexpander | markdown | pdf
                    --pack NAME  export only one pack
                    -o/--output  write to a file instead of stdout
```

## The pack file

```yaml
version: 1
packs:
  email-starters:
    description: Openers and sign-offs you paste into email every day
    snippets:
      - trigger: ":hi-first"
        title: First-touch email opener
        replace: |-
          Hi {{name}},

          I hope your week is going smoothly.
          {{message}}
        variables:
          name:
            default: Alex            # used when expanded without --set
            description: Who is being greeted
        tags: [email, greetings]
```

A starter file ships with the tool (`init`) and also as
`example/packs.yml`.

* `trigger` - unique per pack, no whitespace. App users conventionally
  start triggers with `:`; the AutoHotkey export drops leading colons
  automatically because AHK cannot use them.
* `replace` - the text the expander inserts. Placeholders live here.
* `title`, `notes`, `tags` - optional metadata; `notes` are highlighted
  on the cheat sheets and `tags` power the `list --tag` filter.
* `variables` - optional declared defaults. Even without declarations,
  any `{{name}}` expands from an inline fallback or `--set`.

Validation is strict on purpose: unknown keys, duplicate triggers,
wrong types and malformed snippets are all reported together, at once,
with the pack and snippet named so you can fix them in one pass.

## Placeholder syntax

```
{{ name }}                    plain variable
{{ name | fallback text }}    variable with an inline fallback
{{ date: %B %d, %Y }}         today's date (strftime format required)
{{ time: %H:%M }}             right now (strftime format required)
{{ choice: Hi there, | Hello, | Hey, }}   pick at expansion time
```

Rules the `check` and `expand` commands enforce:

* Names are `[A-Za-z_][A-Za-z0-9_]*`.
* Braces are not nestable; no `{{` inside a fallback.
* Expansion order: `--set` value **>** inline `| fallback` **>**
  declared `variables:` default **>** reported-and-left-unexpanded
  (missing values never silently vanish).
* `choice` without a supplied value expands to its first option; a bad
  supplied value is an error.
* Strftime directives are checked against a portable allow-list, so the
  same file expands identically on Linux, macOS and Windows.
* Unknown builtins (like a hypothetical `{{clip:...}}`) are syntax
  errors - snippetpack deliberately has no clipboard placeholder.

## Export targets

```bash
python -m snippetpack export espanso -o espanso-pack.yml    # into espanso match dir
python -m snippetpack export ahk     -o snippets.ahk        # run with AutoHotkey v2
python -m snippetpack export textexpander -o snippets.csv   # import into TextExpander
python -m snippetpack export markdown -o cheatsheet.md      # readable cheat sheet
python -m snippetpack export pdf #-o cheatsheet.pdf        # printed reference
```

* **espanso** - every snippet becomes a `matches:` entry with
  `trigger`/`replace` (and `comment` from the title).
* **AutoHotkey** - v2 hotstrings; multi-line replacements use the
  parenthesized continuation form; backticks are escaped; leading `:`
  triggers are trimmed.
* **TextExpander-style CSV** - `trigger,snippet_text` header plus one
  quoted row per snippet; embedded newlines are preserved.
* **Markdown / PDF** - human-readable cheat sheets grouped by pack,
  with triggers, tags, variables and the full replacement text.

## Design notes

* **Stdlib-only YAML** - the pack file is real (subset) YAML, parsed and
  written by `snippetpack/miniyaml.py`. The subset covers packed files
  completely: nested maps/lists, block scalars (`|`, `|-`, `+`), flow
  sequences, quoting, comments - and rejects anchors, tags and flow
  maps with clear errors rather than mis-parsing them.
* **Offline first** - no network code paths exist. Secret-free: no keys,
  no credentials; it is your own local text.
* **PDF from scratch** - `exporters/pdfgen.py` writes a minimal PDF
  (catalog/pages/font/text streams, real xref) using the Courier core font,
  core fonts, so no reportlab needed.

## Running the tests

```bash
python -m pytest
```

85 tests cover YAML round-trips and errors, schema validation
(survives every failure mode without crashing), placeholder grammar and
expansion, all four text exporters, the PDF writer (including xref
offsets), and the CLI end to end.

## Project layout

```
snippetpack/
  cli.py        argparse wiring + commands
  miniyaml.py   stdlib YAML subset reader/writer
  models.py     data model + validation
  placeholders.py {{...}} scanning, validation, expansion
  snippets.py   pack file load/save + starter template
  exporters/    espanso, ahk, textexpander, markdown, pdfgen
example/packs.yml
tests/
```

## License

MIT - Copyright (c) 2026 **Asdale Dynamics, LLC**. See `LICENSE`.

Healthcare notes in the starter pack are workflow phrasing examples only
and contain no patient data; snippetpack is a text utility, not medical
software, and is not medical advice.

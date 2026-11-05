"""Command line interface for snippetpack.

Run it with ``python -m snippetpack``. Every command reads the pack
file given by ``-f/--file``; output goes to stdout (or a file with
``export -o``). The tool reads files and prints text only - it never
touches the clipboard or the network.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__
from .miniyaml import YamlError
from .models import ValidationError
from .placeholders import expand, validate_syntax
from .snippets import STARTER_YAML, StarterError, load_library

__all__ = ["main", "build_parser"]

FORMATS = ("espanso", "ahk", "textexpander", "markdown", "pdf")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="snippetpack",
        description=(
            "Build and export reusable text snippet packs from one readable "
            "YAML file. Prints to stdout; use export -o/--output to save."
        ),
    )
    parser.add_argument("--version", action="version", version=f"snippetpack {__version__}")
    parser.add_argument(
        "-f",
        "--file",
        default="packs.yml",
        help="path to the snippet pack YAML file (default: %(default)s)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    init = subparsers.add_parser("init", help="write a starter pack file")
    init.add_argument("--force", action="store_true", help="overwrite an existing pack file")

    subparsers.add_parser("validate", help="check the pack file against the schema")

    subparsers.add_parser("check", help="validate placeholder syntax in every snippet")

    list_pack = subparsers.add_parser("list", help="list triggers and titles")
    list_pack.add_argument("--pack", help="only this pack")
    list_pack.add_argument("--tag", help="only snippets carrying this tag")

    show = subparsers.add_parser("show", help="print one snippet's full definition")
    show.add_argument("trigger")

    expand_cmd = subparsers.add_parser(
        "expand", help="expand a snippet's placeholders and print the result"
    )
    expand_cmd.add_argument("trigger")
    expand_cmd.add_argument(
        "--set",
        dest="sets",
        action="append",
        metavar="NAME=VALUE",
        help="supply a variable value (repeatable; choice uses --set choice=...)",
    )

    export = subparsers.add_parser("export", help="export the packs")
    export.add_argument("format", choices=FORMATS)
    export.add_argument("--pack", help="only export this pack")
    export.add_argument("-o", "--output", help="write to this file instead of stdout")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    try:
        return _dispatch(ns, parser)
    except ValidationError as exc:
        print(f"validation error in {ns.file}:", file=sys.stderr)
        for problem in exc.problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "Tip: 'python -m snippetpack init --force' writes a known-good starter file.",
            file=sys.stderr,
        )
        return 1
    except YamlError as exc:
        print(f"YAML problem in {ns.file}: {exc}", file=sys.stderr)
        print(
            "Tip: 'python -m snippetpack init --force' writes a known-good starter file.",
            file=sys.stderr,
        )
        return 1
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Create a starter file with: python -m snippetpack init", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"error: no snippet with trigger {exc.args[0]!r}", file=sys.stderr)
        return 1
    except StarterError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(ns: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    command = ns.command

    if command == "init":
        target = Path(ns.file)
        if target.exists() and not ns.force:
            raise StarterError(f"{target} already exists (use --force to overwrite)")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(STARTER_YAML, encoding="utf-8")
        print(f"wrote starter pack file: {target}")
        return 0

    library = load_library(ns.file)

    if command == "validate":
        total = sum(len(p.snippets) for p in library.packs.values())
        print(f"OK: {ns.file} is a valid snippet pack file")
        print(f"packs: {', '.join(library.packs)} ({len(library.packs)})")
        print(f"snippets: {total}")
        return 0

    if command == "check":
        problems: List[str] = []
        for pack in library.packs.values():
            for snippet in pack.snippets:
                for problem in validate_syntax(snippet.replace):
                    problems.append(f"pack {pack.name!r} snippet {snippet.trigger!r}: {problem}")
        if problems:
            print(f"found {len(problems)} placeholder problem(s):")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        total = sum(len(p.snippets) for p in library.packs.values())
        print(f"OK: all {total} snippets use valid placeholder syntax")
        return 0

    if command == "list":
        rows: List[tuple] = []
        for pack in library.packs.values():
            if ns.pack and pack.name != ns.pack:
                continue
            for snippet in pack.snippets:
                if ns.tag and ns.tag not in snippet.tags:
                    continue
                rows.append((pack.name, snippet.trigger, snippet.title))
        if not rows:
            print("no snippets matched", file=sys.stderr)
            return 1
        pad_pack = max(len(r[0]) for r in rows)
        pad_trigger = max(len(r[1]) for r in rows)
        for pack_name, trigger, title in rows:
            print(f"{pack_name.ljust(pad_pack)}  {trigger.ljust(pad_trigger)}  {title}")
        return 0

    if command == "show":
        snippet = library.find(ns.trigger)
        print(f"trigger:   {snippet.trigger}")
        print(f"title:     {snippet.title}")
        if snippet.tags:
            print(f"tags:      {', '.join(snippet.tags)}")
        if snippet.notes:
            print(f"notes:     {snippet.notes}")
        if snippet.variables:
            print("variables:")
            for var in snippet.variables.values():
                default = f" default={var.default!r}" if var.default else ""
                description = f" ({var.description})" if var.description else ""
                print(f"  {{{{{var.name}}}}}{default}{description}")
        print("replace:")
        for line in snippet.replace.splitlines():
            print(f"  | {line}")
        return 0

    if command == "expand":
        snippet = library.find(ns.trigger)
        values: Dict[str, str] = {}
        for pair in ns.sets or []:
            name, sep, value = pair.partition("=")
            if sep != "=":
                print(f"error: --set expects NAME=VALUE, got {pair!r}", file=sys.stderr)
                return 2
            values[name.strip()] = value
        defaults = {var.name: var.default for var in snippet.variables.values()}
        result, problems = expand(snippet.replace, values=values, defaults=defaults)
        fatal = [p for p in problems if p.startswith("no value") or p.startswith("invalid")]
        if problems:
            for problem in problems:
                print(f"warning: {problem}", file=sys.stderr)
        if fatal:
            return 1
        sys.stdout.write(result)
        if not result.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    if command == "export":
        from .exporters import (
            export_ahk,
            export_espanso,
            export_markdown,
            export_pdf,
            export_textexpander,
        )

        exporters = {
            "espanso": export_espanso,
            "ahk": export_ahk,
            "textexpander": export_textexpander,
            "markdown": export_markdown,
            "pdf": export_pdf,
        }
        if ns.format == "pdf":
            content_bytes = export_pdf(library, pack_name=ns.pack)
        else:
            content_bytes = exporters[ns.format](library, pack_name=ns.pack).encode("utf-8")
        if ns.output:
            out = Path(ns.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(content_bytes)
            print(f"wrote {ns.format} export: {out}")
            return 0
        sys.stdout.buffer.write(content_bytes)
        return 0

    parser.error(f"unknown command: {command}")
    return 2

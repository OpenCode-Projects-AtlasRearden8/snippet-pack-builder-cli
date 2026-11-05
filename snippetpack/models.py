"""Data model and validation rules for snippet pack files.

A pack file is a single YAML document:

.. code-block:: yaml

    version: 1
    packs:
      professional:
        description: Everyday placeholders
        snippets:
          - trigger: ":sig"
            title: Professional signature
            replace: |-
              Best,
              {{name}}
            variables:
              name:
                default: Dylan Asdale
                description: The name signed with
            tags: [email]      # quoted strings only
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List

__all__ = [
    "ValidationError",
    "Variable",
    "Snippet",
    "Pack",
    "Library",
    "validate_data",
    "library_to_data",
]

_TRIGGER_RE = re.compile(r"^[^\s]+$")

_SNIPPET_KEYS = {"trigger", "title", "replace", "variables", "tags", "notes"}
_PACK_KEYS = {"description", "snippets"}
_VARIABLE_KEYS = {"default", "description"}
_TOP_KEYS = {"version", "packs"}
_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ValidationError(ValueError):
    """Raised when a pack file violates the documented schema."""

    def __init__(self, problems: List[str]) -> None:
        self.problems = list(problems)
        count = len(self.problems)
        super().__init__(
            f"{count} validation problem{'' if count == 1 else 's'}:\n- "
            + "\n- ".join(self.problems)
        )


def _type_name(value: Any) -> str:
    if value is None:
        return "null/empty"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return type(value).__name__


@dataclass
class Variable:
    name: str
    default: str = ""
    description: str = ""


@dataclass
class Snippet:
    trigger: str
    replace: str
    title: str = ""
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    variables: Dict[str, Variable] = field(default_factory=dict)

    def variable_names(self) -> List[str]:
        return list(self.variables)


@dataclass
class Pack:
    name: str
    description: str = ""
    snippets: List[Snippet] = field(default_factory=list)


@dataclass
class Library:
    version: str = "1"
    packs: Dict[str, Pack] = field(default_factory=dict)

    def all_snippets(self) -> List[Snippet]:
        out = []
        for pack in self.packs.values():
            out.extend(pack.snippets)
        return out

    def find(self, trigger: str) -> Snippet:
        matches = [s for s in self.all_snippets() if s.trigger == trigger]
        if not matches:
            raise KeyError(trigger)
        return matches[0]


def validate_data(data: Any) -> Library:
    """Validate raw YAML data and return a :class:`Library`.

    Raises :class:`ValidationError` listing every problem found.
    """
    problems: List[str] = []
    library = Library()

    if not isinstance(data, dict):
        raise ValidationError(["the file must contain a top-level mapping with a 'packs:' key"])

    for key in data:
        if key not in _TOP_KEYS:
            problems.append(f"top-level: unknown key {key!r}")

    version = data.get("version", "1")
    if not isinstance(version, (str, int)) or isinstance(version, bool):
        problems.append(f"version: expected a string or integer, got {_type_name(version)}")
    else:
        library.version = str(version)

    packs = data.get("packs")
    if packs is None:
        problems.append("missing required top-level key 'packs:'")
        packs = {}
    if not isinstance(packs, dict):
        problems.append(f"packs: expected a mapping, got {_type_name(packs)}")
        packs = {}
    for pack_name, pack_data in packs.items():
        library.packs[pack_name] = _validate_pack(pack_name, pack_data, problems)

    if problems:
        raise ValidationError(problems)
    return library


def _validate_pack(pack_name: Any, pack_data: Any, problems: List[str]) -> Pack:
    pack_label = f"pack {pack_name!r}" if isinstance(pack_name, str) else "pack <invalid name>"
    if not isinstance(pack_name, str) or not pack_name.strip():
        problems.append("packs: every pack needs a non-empty name (the mapping key)")
    if isinstance(pack_name, str) and "\\" in pack_name:
        problems.append(f"packs: pack name {pack_name!r} should not contain backslashes")
    if ":" in str(pack_name) or "#" in str(pack_name) or "\n" in str(pack_name):
        problems.append(f"packs: pack name {str(pack_name)!r} may not contain ':', '#' or newlines")
    pack = Pack(name=pack_name if isinstance(pack_name, str) else str(pack_name))

    if not isinstance(pack_data, dict):
        problems.append(f"{pack_label}: expected a mapping, got {_type_name(pack_data)}")
        return pack

    for key in pack_data:
        if key not in _PACK_KEYS:
            problems.append(f"{pack_label}: unknown key {key!r} (allowed: {sorted(_PACK_KEYS)})")

    description = pack_data.get("description", "")
    if not isinstance(description, str):
        problems.append(f"{pack_label}: description must be a string, got {_type_name(description)}")
    else:
        pack.description = description

    snippets = pack_data.get("snippets")
    if snippets is None:
        problems.append(f"{pack_label}: missing required key 'snippets:'")
        snippets = []
    if not isinstance(snippets, list):
        problems.append(f"{pack_label}: snippets must be a list, got {_type_name(snippets)}")
        snippets = []
    seen: Dict[str, int] = {}
    for index, snip_data in enumerate(snippets):
        snippet = _validate_snippet(snip_data, problems, f"{pack_label} snippet #{index + 1}")
        if snippet.trigger in seen:
            problems.append(
                f"{pack_label}: duplicate trigger {snippet.trigger!r} "
                f"(already defined by snippet #{seen[snippet.trigger]})"
            )
        else:
            seen[snippet.trigger] = index + 1
        pack.snippets.append(snippet)

    return pack


def _validate_snippet(snip_data: Any, problems: List[str], label: str) -> Snippet:
    if not isinstance(snip_data, dict):
        problems.append(f"{label}: expected a mapping, got {_type_name(snip_data)}")
        return Snippet(trigger="", replace="")

    for key in snip_data:
        if key not in _SNIPPET_KEYS:
            problems.append(f"{label}: unknown key {key!r} (allowed: {sorted(_SNIPPET_KEYS)})")

    trigger = snip_data.get("trigger")
    if trigger is None:
        problems.append(f"{label}: missing required key 'trigger'")
        trigger = ""
    if not isinstance(trigger, str):
        problems.append(f"{label}: trigger must be a string, got {_type_name(trigger)}")
        trigger = str(trigger)
    elif not trigger:
        problems.append(f"{label}: trigger may not be empty")
    elif not _TRIGGER_RE.match(trigger):
        problems.append(f"{label}: trigger {trigger!r} may not contain whitespace")
    elif trigger == "-" or trigger.startswith("-"):
        problems.append(f"{label}: trigger {trigger!r} may not start with '-'")

    replace = snip_data.get("replace")
    if replace is None:
        problems.append(f"{label}: missing required key 'replace'")
        replace = ""
    if not isinstance(replace, str):
        problems.append(f"{label}: replace must be a string, got {_type_name(replace)}")
        replace = str(replace)
    elif not replace:
        problems.append(f"{label}: replace may not be empty")

    snippet = Snippet(trigger=trigger if isinstance(trigger, str) else "", replace=replace)

    title = snip_data.get("title", "")
    if not isinstance(title, str):
        problems.append(f"{label}: title must be a string, got {_type_name(title)}")
    else:
        snippet.title = title

    notes = snip_data.get("notes", "")
    if not isinstance(notes, str):
        problems.append(f"{label}: notes must be a string, got {_type_name(notes)}")
    else:
        snippet.notes = notes

    tags = snip_data.get("tags", [])
    if not isinstance(tags, list):
        problems.append(f"{label}: tags must be a list of strings, got {_type_name(tags)}")
    else:
        bad = [t for t in tags if not isinstance(t, str)]
        if bad:
            problems.append(
                f"{label}: tags must be plain strings (bad values: {_short(bad)})"
            )
        else:
            snippet.tags = list(tags)

    variables = snip_data.get("variables", {})
    if not isinstance(variables, dict):
        problems.append(f"{label}: variables must be a mapping, got {_type_name(variables)}")
    else:
        for var_name, var_data in variables.items():
            snippet.variables.update(
                _validate_variable(var_name, var_data, problems, label)
            )

    return snippet


def _validate_variable(
    var_name: Any, var_data: Any, problems: List[str], label: str
) -> Dict[str, Variable]:
    var_label = f"{label} variable {var_name!r}"
    if not isinstance(var_name, str) or not _VAR_NAME_RE.match(var_name):
        problems.append(
            f"{var_label}: variable names must match {_VAR_NAME_RE.pattern!r} "
            f"(got {var_name!r})"
        )
        var_name = str(var_name)

    if var_data is None:
        var_data = {}
    if not isinstance(var_data, dict):
        problems.append(
            f"{var_label}: expected a mapping with 'default'/'description', "
            f"got {_type_name(var_data)}"
        )
        return {var_name: Variable(name=var_name)}

    for key in var_data:
        if key not in _VARIABLE_KEYS:
            problems.append(
                f"{var_label}: unknown key {key!r} (allowed: {sorted(_VARIABLE_KEYS)})"
            )
    default = var_data.get("default", "")
    description = var_data.get("description", "")
    if not isinstance(default, str):
        problems.append(f"{var_label}: default must be a string, got {_type_name(default)}")
        default = str(default)
    if not isinstance(description, str):
        problems.append(
            f"{var_label}: description must be a string, got {_type_name(description)}"
        )
        description = str(description)
    return {var_name: Variable(name=var_name, default=default, description=description)}


def _short(values: Any) -> str:
    shown = values[:3]
    return str(shown) + (" ..." if len(values) > 3 else "")


def library_to_data(library: Library) -> dict:
    """Convert a :class:`Library` back to plain YAML-ready data."""
    packs: dict = {}
    for pack_name, pack in library.packs.items():
        pack_dict: dict = {}
        if pack.description:
            pack_dict["description"] = pack.description
        pack_dict["snippets"] = [
            {
                "trigger": s.trigger,
                "title": s.title,
                "replace": s.replace,
                "variables": {
                    v.name: {
                        **({"default": v.default} if v.default else {}),
                        **({"description": v.description} if v.description else {}),
                    }
                    for v in s.variables.values()
                }
                if s.variables
                else {},
                **({"tags": list(s.tags)} if s.tags else {}),
                "notes": s.notes,
            }
            for s in pack.snippets
        ]
        packs[pack_name] = pack_dict
    data: dict = {"version": library.version, "packs": packs}
    return data

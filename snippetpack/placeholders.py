"""Placeholder syntax: scanning, validation and expansion.

Placeholders live inside a snippet's ``replace`` text and are written as
double curly braces. The grammar is intentionally tiny:

.. code-block:: text

    {{ name }}                      plain variable, or a named builtin
    {{ name | fallback text }}      variable with an inline fallback
    {{ date: strftime format }}     today's date, e.g. {{date:%B %d, %Y}}
    {{ time: strftime format }}     right now,          e.g. {{time:%H:%M}}
    {{ choice: option a | option b | option c }}

Rules:

* A variable name is ``[A-Za-z_][A-Za-z0-9_]*``.
* ``date`` and ``time`` must be written with a ``:strftime format``
  (for example ``{{date:%B %d, %Y}}``); plain ``{{date}}`` is treated as
  an ordinary (undeclared) variable named "date". Directives are checked
  against a portable allow-list so behavior is the same on every OS.
* ``choice`` must be followed by ``:`` and at least one option; the
  expansion call either receives a value via ``--set choice=...`` or uses
  the first option. If a value is supplied it must be one of the options.
* Braces are not nestable; a default may not itself contain ``{{``.

Expanding a variable goes through (in order): an explicitly supplied
value (``--set``), the placeholder's inline ``| fallback``, the
snippet's ``variables:`` ``default:``, and finally a missing-value
report. Unresolved placeholders are left literally in the output so
expansion can safely be retried.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

__all__ = [
    "PlaceholderSyntaxError",
    "Placeholder",
    "BUILTINS",
    "scan_placeholders",
    "validate_syntax",
    "expand",
]

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# strftime directives snippetpack accepts (kept portable, not glibc-random)
_STRFTIME_OK = set("AaBbCcdeEFgGHIjklMmnNpPrRsSTtUuVwWxXyYzZ%")

BUILTINS = ("date", "time", "choice")


class PlaceholderSyntaxError(ValueError):
    """Raised when a snippet contains malformed placeholder syntax."""


@dataclass
class Placeholder:
    raw: str
    kind: str = "variable"  # "variable", "date", "time", "choice"
    name: str = ""
    fallback: str = ""
    format: str = ""
    options: List[str] = field(default_factory=list)


def scan_placeholders(text: str) -> List[Placeholder]:
    """Return the parsed placeholders in ``text``.

    Raises :class:`PlaceholderSyntaxError` for unbalanced braces, stray
    closing braces, empties, unknown builtins or nested ``{{``.
    """
    tokens: List[Placeholder] = []
    i = 0
    depth = 0
    start = -1
    n = len(text)
    while i < n:
        if text.startswith("{{", i):
            if depth == 0:
                start = i
            depth += 1
            if depth > 1:
                raise PlaceholderSyntaxError(
                    message(i, "nested '{{' is not allowed inside a placeholder")
                )
            i += 2
            continue
        if text.startswith("}}", i):
            if depth == 0:
                raise PlaceholderSyntaxError(message(i, "stray '}}' without a matching '{{'"))
            depth -= 1
            if depth == 0:
                tokens.append(_parse_token(text[start : i + 2]))
            i += 2
            continue
        i += 1
    if depth != 0:
        raise PlaceholderSyntaxError(
            message(start, "unclosed '{{' (missing matching '}}')")
        )
    return tokens


def message(index: int, text: str) -> str:
    return f"position {index}: {text}"


def _parse_token(raw: str) -> Placeholder:
    inner = raw[2:-2].strip()
    if not inner:
        raise PlaceholderSyntaxError("empty placeholder {{}}")
    if ":" in inner:
        prefix, _, rest = inner.partition(":")
        prefix = prefix.strip()
        if prefix in ("date", "time"):
            ph = Placeholder(raw=raw, kind=prefix, format=rest.strip())
            return ph
        if prefix == "choice":
            options = [opt.strip() for opt in rest.split("|")]
            if not options or all(opt == "" for opt in options):
                raise PlaceholderSyntaxError(
                    f"placeholder {raw!r}: 'choice' needs at least one option"
                )
            if any(opt == "" for opt in options):
                raise PlaceholderSyntaxError(f"placeholder {raw!r}: options may not be empty")
            if "{{" in rest:
                raise PlaceholderSyntaxError(
                    f"placeholder {raw!r}: placeholders cannot be nested inside options"
                )
            return Placeholder(raw=raw, kind="choice", options=options)
        raise PlaceholderSyntaxError(
            f"placeholder {raw!r}: unknown builtin {prefix + ':'!r} "
            f"(expected one of: {', '.join(BUILTINS)})"
        )
    if "|" in inner:
        name, _, fallback = inner.partition("|")
        name = name.strip()
        fallback = fallback.strip()
    else:
        name, fallback = inner.strip(), ""
    if not NAME_RE.match(name):
        raise PlaceholderSyntaxError(
            f"placeholder {raw!r}: names must match {NAME_RE.pattern!r} (got {name!r})"
        )
    if "{{" in fallback:
        raise PlaceholderSyntaxError(
            f"placeholder {raw!r}: placeholders cannot be nested inside fallback text"
        )
    return Placeholder(raw=raw, kind="variable", name=name, fallback=fallback)


def validate_syntax(text: str) -> List[str]:
    """Return a list of human-readable syntax problems (empty if valid)."""
    try:
        scan_placeholders(text)
    except PlaceholderSyntaxError as exc:
        return [str(exc)]
    return []


def _strftime_problems(fmt: str) -> Optional[str]:
    """Return a problem string for unsupported strftime directives."""
    i = 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == "%":
            if i + 1 >= len(fmt):
                return f"strftime format {fmt!r} ends with a bare '%'"
            nxt = fmt[i + 1]
            if nxt == "-":
                if i + 2 >= len(fmt):
                    return f"strftime format {fmt!r} has a bare '%-'"
                nxt = fmt[i + 2]
                if nxt not in _STRFTIME_OK:
                    return f"strftime format {fmt!r} has unsupported directive '%-{nxt}'"
                i += 3
                continue
            if nxt not in _STRFTIME_OK:
                return f"strftime format {fmt!r} has unsupported directive '%{nxt}'"
            i += 2
            continue
        i += 1
    return None


def expand(
    text: str,
    values: Optional[Dict[str, str]] = None,
    defaults: Optional[Dict[str, str]] = None,
    now: Optional[datetime] = None,
) -> Tuple[str, List[str]]:
    """Expand all placeholders in ``text``.

    Returns ``(result, problems)``. Missing variable names are reported
    in ``problems`` and left unexpanded in ``result``. ``values`` beat
    ``defaults``; the placeholder's inline ``|fallback`` sits between
    them.
    """
    values = dict(values or {})
    defaults = dict(defaults or {})
    now = now or datetime.now()
    try:
        tokens = scan_placeholders(text)
    except PlaceholderSyntaxError as exc:
        return text, [str(exc)]

    problems: List[str] = []
    out = text
    for token in tokens:
        if token.kind == "variable":
            if token.name in values:
                out = out.replace(token.raw, str(values[token.name]), 1)
            elif token.fallback:
                out = out.replace(token.raw, token.fallback, 1)
            elif token.name in defaults:
                out = out.replace(token.raw, str(defaults[token.name]), 1)
            else:
                problems.append(f"no value for {token.name!r}")
        elif token.kind in ("date", "time"):
            target = now.date() if token.kind == "date" else now
            text_problem = _strftime_problems(token.format)
            if text_problem:
                problems.append(text_problem)
            else:
                try:
                    rendered = target.strftime(token.format)
                except (ValueError, TypeError) as exc:
                    problems.append(f"invalid {token.kind} format {token.format!r}: {exc}")
                else:
                    out = out.replace(token.raw, rendered, 1)
        elif token.kind == "choice":
            picked = values.get("choice", "")
            if picked == "":
                out = out.replace(token.raw, token.options[0], 1)
            elif picked in token.options:
                out = out.replace(token.raw, picked, 1)
            else:
                problems.append(
                    f"invalid choice {picked!r}: expected one of {token.options}"
                )
    return out, problems

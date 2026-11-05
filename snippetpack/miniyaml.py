"""A small, safe YAML subset parser/writer that ships with snippetpack.

snippetpack is stdlib-only, so it cannot depend on PyYAML. This module
implements the YAML subset that snippet files actually need, and no more:

* mappings and lists, arbitrarily nested
* ``key: value`` inline scalars
* ``- value`` and ``- key: value`` list items
* literal block scalars ``|``, ``|-`` and ``|+`` (multi-line text,
  including blank lines inside the text)
* plain strings, double/single-quoted strings, integers, floats,
  booleans (true/false) and null (``null``/``~``/empty)
* simple flow sequences like ``[one, two]`` (scalars only)
* ``#`` comments on their own line or trailing a value
  (never inside block scalars, where ``#`` is text)

Anything else (anchors, tags, flow collections other than empty
``{}``/``[]``, folded scalars, multi-document files) is not supported
and raises :class:`YamlError`.
"""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional, Tuple

__all__ = ["YamlError", "loads", "dumps"]


class YamlError(ValueError):
    """Raised when a file uses YAML outside the supported subset."""


class _Node:
    __slots__ = ("indent", "content", "line")

    def __init__(self, indent: int, content: str, line: int) -> None:
        self.indent = indent
        self.content = content
        self.line = line


_INT_RE = re.compile(r"^[+-]?(?:0|[1-9]\d*)$")
_FLOAT_RE = re.compile(r"^[+-]?(?:0|[1-9]\d*)?\.\d+(?:[eE][+-]?\d+)?$")

_PLAIN_WORDS = {"true": True, "false": False, "null": None, "~": None}


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _strip_comment(text: str) -> str:
    """Remove a trailing ``#...`` comment while respecting quotes."""
    quote: Optional[str] = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i].rstrip()
        i += 1
    return text


def _split_entry(content: str) -> Tuple[str, str]:
    """Split ``key: value`` at the first unquoted ``key:`` separator.

    Raises ``ValueError`` when the text has no top-level ``key:`` colon
    (the caller decides what that means for its own node type).
    """
    quote: Optional[str] = None
    i = 0
    while i < len(content):
        ch = content[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == ":":
            after = content[i + 1 : i + 2]
            if after in ("", " "):
                return content[:i], content[i + 1 :]
        i += 1
    raise ValueError("no top-level 'key:' colon")


def _has_entry_colon(text: str) -> bool:
    try:
        _split_entry(text)
    except ValueError:
        return False
    return True


def _parse_flow_list(text: str) -> Optional[List[Any]]:
    """Parse ``[a, b, ...]`` when text is a simple flow sequence."""
    s = text.strip()
    if not (s.startswith("[") and s.endswith("]")):
        return None
    body = s[1:-1].strip()
    if body == "":
        return []
    # split at top-level commas, respecting quotes
    items: List[str] = []
    buf = []
    quote: Optional[str] = None
    i = 0
    depth = 0
    while i < len(body):
        ch = body[i]
        if quote:
            buf.append(ch)
            if quote == '"' and ch == "\\":
                if i + 1 < len(body):
                    buf.append(body[i + 1])
                    i += 2
                    continue
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == "[":
            depth += 1
            buf.append(ch)
        elif ch == "]":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    if depth != 0:
        raise YamlError(f"unbalanced brackets in flow list: {text!r}")
    if quote is not None:
        raise YamlError(f"unterminated quoted item in flow list: {text!r}")
    items.append("".join(buf).strip())
    return [_parse_scalar(item) for item in items if item != ""]


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text.startswith('"') or text.startswith("'"):
        quote = text[0]
        if quote == '"':
            try:
                decoder = json.JSONDecoder()
                value, end = decoder.raw_decode(text)
            except json.JSONDecodeError as exc:
                raise YamlError(f"broken double-quoted string: {exc}") from exc
            if text[end:].strip():
                raise YamlError(f"unexpected trailing text after quoted scalar: {text[end:]!r}")
            return value
        value, rest = _split_single(text[1:])
        if rest.strip():
            raise YamlError(f"unexpected trailing text after quoted scalar: {rest!r}")
        return value
    if text == "":
        return None
    if text == "{}":
        return {}
    if text == "[]":
        return []
    if text.startswith("{"):
        raise YamlError(
            f"flow mappings are not supported ({text[:20]!r}...); "
            "use 'key: value' lines or '{}'"
        )
    if text.startswith("[") and text.endswith("]"):
        flow = _parse_flow_list(text)
        if flow is not None:
            return flow
    lowered = text.lower()
    if lowered in _PLAIN_WORDS:
        return _PLAIN_WORDS[lowered]
    if text[0] in "&*!":
        raise YamlError(
            f"anchors, tags and aliases are not supported (bad scalar {text[:20]!r})"
        )
    if _INT_RE.match(text):
        return int(text)
    if _FLOAT_RE.match(text):
        return float(text)
    return text


def _split_single(body: str) -> Tuple[str, str]:
    """Parse a single-quoted scalar; ``body`` excludes the opening quote.

    Returns ``(value, rest-after-closing-quote)``. A doubled ``''`` is an
    escaped single quote.
    """
    buf: List[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "'":
            if body[i + 1 : i + 2] == "'":
                buf.append("'")
                i += 2
                continue
            return "".join(buf), body[i + 1 :]
        buf.append(ch)
        i += 1
    raise YamlError("unterminated single-quoted string")


def _tokenize(text: str) -> List[_Node]:
    nodes: List[_Node] = []
    for line_no, raw in enumerate(text.splitlines(), start=1):
        leading = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in leading:
            raise YamlError(f"line {line_no}: tab characters are not allowed for indentation")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        content = _strip_comment(raw).strip()
        if not content:
            # value made only of a trailing comment - treat as empty
            continue
        nodes.append(_Node(len(leading), content, line_no))
    return nodes


class _Parser:
    def __init__(self, text: str) -> None:
        self.nodes = _tokenize(text)
        self.raw_lines = text.splitlines()
        self.pos = 0

    def _error(self, node: _Node, message: str) -> YamlError:
        return YamlError(f"line {node.line}: {message}")

    def _is_list_item(self, node: _Node) -> bool:
        return node.content == "-" or node.content.startswith("- ")

    # -- public ------------------------------------------------------
    def parse(self) -> Any:
        if not self.nodes:
            return {}
        value = self._block(0)
        if self.pos != len(self.nodes):
            raise self._error(self.nodes[self.pos], "unexpected content (check indentation)")
        return value

    # -- block dispatch ----------------------------------------------
    def _block(self, min_indent: int) -> Any:
        node = self.nodes[self.pos]
        if node.indent < min_indent:
            raise self._error(node, "unexpected indentation")
        if self._is_list_item(node):
            return self._list(node.indent)
        return self._map(node.indent)

    def _list(self, indent: int) -> List[Any]:
        items: List[Any] = []
        while self.pos < len(self.nodes):
            node = self.nodes[self.pos]
            if node.indent < indent:
                break
            if node.indent > indent:
                raise self._error(node, "unexpected indentation in list")
            if not self._is_list_item(node):
                break  # let the caller (parent map) take over
            if node.content == "-":
                # empty marker: the value is the following deeper block
                self.pos += 1
                if (
                    self.pos < len(self.nodes)
                    and self.nodes[self.pos].indent > indent
                ):
                    items.append(self._list(self.nodes[self.pos].indent))
                else:
                    items.append(None)
                continue
            rest = node.content[1:].lstrip()
            if _has_entry_colon(rest):
                # "- key: value ..." starts an inline mapping whose keys
                # are indented two past the "-" marker.
                self.nodes[self.pos] = _Node(indent + 2, rest, node.line)
                items.append(self._map(indent + 2))
                continue
            if rest.startswith("|"):
                value = self._block_scalar(rest, node, indent)
                items.append(value)
                continue
            items.append(_parse_scalar(rest))
            self.pos += 1
        return items

    def _map(self, indent: int) -> dict:
        result: dict = {}
        while self.pos < len(self.nodes):
            node = self.nodes[self.pos]
            if node.indent < indent or self._is_list_item(node):
                break
            if node.indent > indent:
                raise self._error(node, "unexpected indentation in mapping")
            try:
                key_text, value_text = _split_entry(node.content)
            except ValueError:
                raise self._error(node, "expected 'key: value' or a list item") from None
            key = _parse_scalar(key_text)
            if not isinstance(key, str):
                key = node.content[: len(key_text)]
            if key in result:
                raise self._error(node, f"duplicate key {key!r}")
            if value_text == "":
                deeper = (
                    self.pos + 1 < len(self.nodes)
                    and self.nodes[self.pos + 1].indent > indent
                )
                if deeper:
                    nxt = self.nodes[self.pos + 1]
                    if nxt.content in ("{}", "[]") and (
                        self.pos + 2 >= len(self.nodes)
                        or self.nodes[self.pos + 2].indent <= indent
                    ):
                        result[key] = {} if nxt.content == "{}" else []
                        self.pos += 2
                        continue
                    if not self._is_list_item(nxt):
                        self.pos += 1
                        result[key] = self._block(indent + 1)
                        continue
                    self.pos += 1
                    result[key] = self._list(nxt.indent)
                    continue
                result[key] = None
                self.pos += 1
                continue
            if value_text.lstrip().startswith("|"):
                result[key] = self._block_scalar(value_text.lstrip(), node, indent)
                continue
            result[key] = _parse_scalar(value_text)
            self.pos += 1
        return result

    def _block_scalar(self, header: str, node: _Node, parent_indent: int) -> str:
        """Consume the raw lines after ``node`` as a literal block scalar."""
        if header.startswith("|-"):
            chomp = "strip"
        elif header.startswith("|+"):
            chomp = "keep"
        elif header == "|":
            chomp = "clip"
        else:
            raise self._error(node, f"unsupported block scalar style: {header!r}")
        if header.strip() not in ("|", "|-", "|+"):
            raise self._error(node, f"unsupported block scalar header: {header!r}")

        header_index = node.line - 1  # 0-based index into raw_lines
        i = header_index + 1
        collected: List[str] = []
        block_indent: Optional[int] = None
        while i < len(self.raw_lines):
            raw = self.raw_lines[i]
            if raw.strip() == "":
                collected.append("")
                i += 1
                continue
            indent = len(raw) - len(raw.lstrip(" "))
            if block_indent is None:
                if indent <= parent_indent:
                    break
                block_indent = indent
            if indent < block_indent:
                break
            # dots/asterisks etc. are text; comments are NOT stripped here
            collected.append(raw[block_indent:].rstrip("\n"))
            i += 1

        # blank lines at the end may belong to the *next* structure when
        # chomping (clip/strip) is requested; with "keep" they belong here
        keep_blanks = 0
        if chomp != "keep":
            while collected and collected[-1] == "":
                collected.pop()
        else:
            while collected and collected[-1] == "":
                collected.pop()
                keep_blanks += 1

        # advance the node cursor past everything consumed
        while self.pos < len(self.nodes) and self.nodes[self.pos].line <= i:
            self.pos += 1

        if not collected:
            return ""
        if chomp == "strip":
            return "\n".join(collected)
        if chomp == "clip":
            return "\n".join(collected) + "\n"
        return "\n".join(collected) + "\n" + "\n" * keep_blanks


def loads(text: str) -> Any:
    """Parse the supported YAML subset into plain Python data."""
    return _Parser(text).parse()


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _needs_quoting(s: str) -> bool:
    if s == "" or s != s.strip():
        return True
    if _INT_RE.match(s) or _FLOAT_RE.match(s):
        return True
    if s.lower() in ("true", "false", "null", "~", "yes", "no", "on", "off"):
        return True
    if any(ch in s for ch in ":{}[],\'\"\\\n\r\t#"):
        return True
    if s[0] in "-?:[]{}#&*!|>'\"%@`":
        return s[1:2] in ("", " ") or s != s.strip()
    return False


def _quote(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


def _scalar_repr(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    if _needs_quoting(s):
        return _quote(s)
    return s


def dumps(data: Any) -> str:
    """Serialize plain data back into the supported YAML subset."""
    out: List[str] = []
    _emit_body(data, "", out)
    return "\n".join(out) + ("\n" if out else "")


def _emit_body(value: Any, pad: str, out: List[str]) -> None:
    """Write the block body of ``value`` so its first lines start at ``pad``."""
    if isinstance(value, dict):
        if not value:
            out.append(pad + "{}")
            return
        for key, item in value.items():
            key_text = _key_repr(key)
            if isinstance(item, dict) and not item:
                out.append(f"{pad}{key_text}: {{}}")
            elif isinstance(item, list) and not item:
                out.append(f"{pad}{key_text}: []")
            elif isinstance(item, (dict, list)):
                out.append(f"{pad}{key_text}:")
                _emit_body(item, pad + "  ", out)
            else:
                _emit_scalar(out, f"{pad}{key_text}: ", item, pad + "  ")
    elif isinstance(value, list):
        if not value:
            out.append(pad + "[]")
            return
        for item in value:
            if isinstance(item, dict) and item:
                child_pad = pad + "  "
                first = True
                for key, sub in item.items():
                    key_text = _key_repr(key)
                    if first:
                        first = False
                        if isinstance(sub, dict) and not sub:
                            out.append(f"{pad}- {key_text}: {{}}")
                        elif isinstance(sub, list) and not sub:
                            out.append(f"{pad}- {key_text}: []")
                        elif isinstance(sub, (dict, list)):
                            out.append(f"{pad}- {key_text}:")
                            _emit_body(sub, child_pad + "  ", out)
                        else:
                            _emit_scalar(out, f"{pad}- {key_text}: ", sub, child_pad + "  ")
                    else:
                        if isinstance(sub, dict) and not sub:
                            out.append(f"{child_pad}{key_text}: {{}}")
                        elif isinstance(sub, list) and not sub:
                            out.append(f"{child_pad}{key_text}: []")
                        elif isinstance(sub, (dict, list)):
                            out.append(f"{child_pad}{key_text}:")
                            _emit_body(sub, child_pad + "  ", out)
                        else:
                            _emit_scalar(out, f"{child_pad}{key_text}: ", sub, child_pad + "  ")
            elif isinstance(item, list) and item:
                out.append(pad + "-")
                _emit_body(item, pad + "    ", out)
            elif isinstance(item, (dict, list)):
                out.append(pad + ("- {}" if isinstance(item, dict) else "- []"))
            else:
                _emit_scalar(out, pad + "- ", item, pad + "    ")
    else:
        _emit_scalar(out, pad, value, pad + "  ")


def _emit_scalar(out: List[str], prefix: str, value: Any, body_pad: str) -> None:
    if isinstance(value, (dict, list)):
        raise TypeError("nested containers cannot be written as a scalar")
    if isinstance(value, str) and "\n" in value:
        _emit_block_scalar(out, prefix, value, body_pad)
    else:
        out.append(prefix + _scalar_repr(value))


def _emit_block_scalar(out: List[str], prefix: str, value: str, body_pad: str) -> None:
    trailing_nl = len(value) - len(value.rstrip("\n"))
    content = value.rstrip("\n")
    if trailing_nl == 0:
        header = "|-"
    elif trailing_nl == 1:
        header = "|"
    else:
        header = "|+"
    out.append(prefix + header)
    for line in content.split("\n"):
        if line == "":
            out.append("")
        else:
            out.append(body_pad + line)
    if header == "|+":
        for _ in range(trailing_nl - 1):
            out.append("")


def _key_repr(key: Any) -> str:
    s = str(key)
    if _needs_quoting(s):
        return _quote(s)
    return s

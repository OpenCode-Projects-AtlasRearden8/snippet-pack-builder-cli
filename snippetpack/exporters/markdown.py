"""Export a pack library to a Markdown cheat sheet."""

from __future__ import annotations

import datetime
from ..models import Library

__all__ = ["export_markdown"]


def _code_fence(text: str) -> str:
    if "````" in text or "```" in text:
        return "````text"
    return "```text"


def _heading_anchor(name: str) -> str:
    # only used for local links within our own document
    return "pack-" + name


def export_markdown(library: Library, pack_name: str | None = None) -> str:
    out: list[str] = []
    out.append("# Snippet Pack Cheat Sheet")
    out.append("")
    out.append(
        "Generated from a snippetpack YAML library by snippetpack "
        f"on {datetime.date.today().isoformat()}."
    )
    out.append("")
    selected = [
        p
        for p in library.packs.values()
        if not pack_name or p.name == pack_name
    ]
    if not selected:
        return "\n".join(out).rstrip("\n") + "\n"

    out.append("| Pack | Snippets |")
    out.append("| ---- | -------- |")
    for pack in selected:
        out.append(f"| `[{pack.name}](#{_heading_anchor(pack.name)})` | {len(pack.snippets)} |")
    out.append("")

    for pack in selected:
        out.append(f"## <a id=\"pack-{pack.name}\"></a>{pack.name}")
        out.append("")
        if pack.description:
            out.append(pack.description)
            out.append("")
        for snippet in pack.snippets:
            heading = snippet.title or snippet.trigger
            out.append(f"### {heading}")
            out.append("")
            out.append(f"**Trigger:** `{snippet.trigger}`")
            if pack.description and False:
                pass
            tags = ", ".join(f"`{t}`" for t in snippet.tags)
            if tags:
                out.append(f"**Tags:** {tags}")
            if snippet.variables:
                out.append("**Variables:**")
                for var in snippet.variables.values():
                    desc = f" - {var.description}" if var.description else ""
                    default = f" (default: `{var.default}`)" if var.default else ""
                    out.append(f"- `{{{{{var.name}}}}}`{default}{desc}")
            if snippet.notes:
                out.append("")
                out.append(f"*{snippet.notes}*")
            out.append("")
            out.append(f"{_code_fence(snippet.replace)}")
            out.append(snippet.replace)
            out.append("```")
            out.append("")
    return "\n".join(out).rstrip("\n") + "\n"

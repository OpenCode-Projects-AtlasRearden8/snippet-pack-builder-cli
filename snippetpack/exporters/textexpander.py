"""Export a pack library to TextExpander-style CSV.

The CSV has two columns, ``trigger`` and ``snippet_text``; multi-line
snippet text stays inside the second column. Import tools that do not
like the header row usually ignore the first line.
"""

from __future__ import annotations

import csv
import io
from ..models import Library

__all__ = ["export_textexpander"]


def export_textexpander(library: Library, pack_name: str | None = None) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(["trigger", "snippet_text"])
    for pack in library.packs.values():
        if pack_name and pack.name != pack_name:
            continue
        for snippet in pack.snippets:
            writer.writerow([snippet.trigger, snippet.replace])
    return out.getvalue()

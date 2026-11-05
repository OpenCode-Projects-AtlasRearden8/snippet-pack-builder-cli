"""A tiny, dependency-free PDF writer for cheat sheets.

It supports only what the cheat sheet needs: multiple pages of
monospaced text lines on Letter-size pages, one embedded core font
reference, plain text drawing with ``Tj`` and ``T*``. Output is raw
bytes starting with ``%PDF-1.4``. Non-WinAnsi characters are replaced
with ``?`` because core fonts ship no Unicode glyph table.
"""

from __future__ import annotations

import textwrap
from typing import List

__all__ = ["SimplePdf", "PAGE_WIDTH", "PAGE_HEIGHT"]

PAGE_WIDTH = 612.0  # US Letter, points (1/72 inch)
PAGE_HEIGHT = 792.0
MARGIN_LEFT = 54.0
MARGIN_WIDTH = PAGE_WIDTH - 2 * 54.0        # usable width
MARGIN_TOP = 54.0
MARGIN_BOTTOM = 54.0
FONT_SIZE = 9.5
LEADING = 12.5
FONT_NAME = "Courier"  # core font: 0.6 em advance, no embedding needed

CHARS_PER_LINE = int(MARGIN_WIDTH // (0.6 * FONT_SIZE))
LINES_PER_PAGE = int((PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM) // LEADING)


def _pdf_escape(text: str) -> str:
    """Escape a string for a PDF text string literal."""
    out = []
    for ch in text:
        if ch in "()\\":
            out.append("\\" + ch)
        else:
            try:
                ch.encode("cp1252")
                out.append(ch)
            except UnicodeEncodeError:
                out.append("?")
    return "".join(out)


def _content_stream(lines: List[str], title: str) -> bytes:
    parts = [
        "BT\n/F1 %.1f Tf\n%.1f TL\n%.1f %.1f Td\n"
        % (FONT_SIZE, LEADING, MARGIN_LEFT, PAGE_HEIGHT - MARGIN_TOP - FONT_SIZE)
    ]
    if title:
        parts.append("(%s) Tj\nT*\n" % _pdf_escape(title))
        parts.append("([]) Tj\nT*\n")  # a blank-ish separator line
    for index, line in enumerate(lines):
        if index > 0:
            parts.append("T*\n")
        parts.append("(%s) Tj\n" % _pdf_escape(line))
    parts.append("ET\n")
    return "".join(parts).encode("latin-1", "replace")


class SimplePdf:
    """Accumulate pages of text lines, then render complete PDF bytes."""

    def __init__(self, title: str = "") -> None:
        self.title = title or "Snippet Pack Cheat Sheet"
        self._pages: List[List[str]] = []
        self._current: List[str] = []

    def add_line(self, line: str) -> None:
        """Add one logical line; wraps long lines and paginates."""
        wrapped = textwrap.wrap(line, CHARS_PER_LINE) if line else [""]
        for piece in wrapped:
            self._push(piece)

    def _push(self, line: str) -> None:
        self._current.append(line)
        if len(self._current) >= LINES_PER_PAGE:
            self.new_page()

    def new_page(self) -> None:
        self._pages.append(self._current)
        self._current = []

    def render(self) -> bytes:
        if self._current:
            self.new_page()
        page_lines: List[List[str]] = [p if p else [""] for p in self._pages]
        if not page_lines:
            page_lines = [[""]]

        contents = [_content_stream(p if index else _with_title(p, self.title), self.title if index == 0 else "")
                    for index, p in enumerate(page_lines)]

        # object layout: 1 catalog, 2 pages, 3 font, then two per page
        object_bodies: List[bytes] = [
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
            b"3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /"
            + FONT_NAME.encode("latin-1")
            + b" /Encoding /WinAnsiEncoding >>\nendobj\n",
        ]
        page_ids: List[int] = []
        stream_ids: List[int] = []
        next_id = 4
        for content in contents:
            stream_ids.append(next_id)
            page_ids.append(next_id + 1)
            next_id += 2
            object_bodies.append(
                (
                    "%d 0 obj\n<< /Length %d >>\nstream\n" % (stream_ids[-1], len(content))
                ).encode("latin-1")
                + content
                + b"endstream\nendobj\n"
            )
            object_bodies.append(
                (
                    "%d 0 obj\n<< /Type /Page /Parent 2 0 R "
                    "/MediaBox [0 0 %s %s] "
                    "/Resources << /Font << /F1 3 0 R >> >> "
                    "/Contents %d 0 R >>\nendobj\n"
                    % (page_ids[-1], _fmt(PAGE_WIDTH), _fmt(PAGE_HEIGHT), stream_ids[-1])
                ).encode("latin-1")
            )
        kids_line = " ".join("%d 0 R" % pid for pid in page_ids)
        # pages object sits at id 2; font at 3; so rebuild bodies in id order
        pages_body = (
            "2 0 obj\n<< /Type /Pages /Kids [%s] /Count %d >>\nendobj\n"
            % (kids_line, len(page_ids))
        ).encode("latin-1")
        font_body = object_bodies.pop(1)  # font currently third; becomes object 3
        ordered: List[bytes] = [
            object_bodies[0],  # catalog -> id 1
            pages_body,        # id 2
            font_body,         # id 3
            *object_bodies[1:],  # page objects -> id 4...
        ]

        pdf = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        offsets: List[int] = []
        for body in ordered:
            offsets.append(len(pdf))
            pdf += body
        xref_pos = len(pdf)
        total = len(ordered) + 1
        xref = ["xref", "0 %d" % total, "0000000000 65535 f "]
        xref += ["%010d 00000 n " % off for off in offsets]
        escaped_title = _pdf_escape(self.title[:96])
        trailer = (
            "trailer\n<< /Size %d /Root 1 0 R /Info << "
            "/Producer (snippetpack, Python stdlib) /Title (%s) >> >>\n"
            "startxref\n%d\n%%%%EOF\n" % (total, escaped_title, xref_pos)
        )
        return pdf + "\n".join(xref).encode("latin-1") + b"\n" + trailer.encode("latin-1")


def _with_title(lines: List[str], title: str) -> List[str]:
    return lines


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else "%.2f" % value

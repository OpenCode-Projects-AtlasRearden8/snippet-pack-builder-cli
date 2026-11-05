"""All exporters in one place."""

from .ahk import export_ahk
from .espanso import export_espanso
from .markdown import export_markdown
from .pdfgen import SimplePdf
from .textexpander import export_textexpander

__all__ = [
    "export_espanso",
    "export_ahk",
    "export_textexpander",
    "export_markdown",
    "export_pdf",
    "SimplePdf",
]


def export_pdf(library, pack_name=None, title=None):
    """Render the library (or one pack) to a plain-text PDF cheat sheet."""
    from .markdown import export_markdown

    pdf = SimplePdf(title=title or "Snippet Pack Cheat Sheet")
    for line in export_markdown(library, pack_name).splitlines():
        pdf.add_line(line)
    pdf.new_page()
    return pdf.render()

"""
PDF Exporter

Converts a Markdown document (+ metadata) to a print-ready, text-selectable PDF
using `xhtml2pdf` (pure Python, no native deps — deploys cleanly on Render).

Flow:
    Markdown ──► HTML (via python-markdown with table + fenced-code extensions)
            ──► Wrapped in a styled template (amber theme matching the UI preview)
            ──► xhtml2pdf.pisa.CreatePDF ──► bytes

Call `render_document_pdf(...)` and you get PDF bytes ready to stream back.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Optional

import markdown as md_lib
from xhtml2pdf import pisa

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Styled HTML template
# xhtml2pdf supports a limited CSS subset, so keep styles simple and class-based.
# ──────────────────────────────────────────────
_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>{title}</title>
<style>
    @page {{
        size: A4;
        margin: 20mm 18mm 22mm 18mm;
        @frame footer_frame {{
            -pdf-frame-content: footer_content;
            left: 18mm; right: 18mm;
            top: 280mm; height: 10mm;
        }}
    }}
    body {{
        font-family: Helvetica, Arial, sans-serif;
        font-size: 11pt;
        color: #1f2937;
        line-height: 1.55;
    }}
    h1 {{
        font-size: 18pt;
        color: #0f172a;
        margin: 14pt 0 8pt 0;
    }}
    h2 {{
        font-size: 14pt;
        color: #c2410c;
        margin: 16pt 0 6pt 0;
        padding-bottom: 3pt;
        border-bottom: 0.5pt solid #fcd34d;
    }}
    h3 {{
        font-size: 12pt;
        color: #b45309;
        margin: 12pt 0 4pt 0;
    }}
    h4 {{
        font-size: 11pt;
        color: #78350f;
        margin: 10pt 0 3pt 0;
    }}
    p {{
        margin: 6pt 0;
    }}
    strong {{ color: #0f172a; }}
    em {{ color: #334155; }}
    code {{
        background: #fef3c7;
        color: #8a4a00;
        padding: 1pt 3pt;
        font-family: "Courier New", monospace;
        font-size: 10pt;
    }}
    pre {{
        background: #f8fafc;
        border: 0.5pt solid #e2e8f0;
        padding: 8pt;
        font-family: "Courier New", monospace;
        font-size: 9.5pt;
        white-space: pre-wrap;
    }}
    ul, ol {{
        margin: 6pt 0 6pt 16pt;
    }}
    li {{
        margin: 2pt 0;
    }}
    hr {{
        border: none;
        border-top: 0.5pt solid #cbd5e1;
        margin: 12pt 0;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 8pt 0;
        font-size: 10pt;
    }}
    thead {{
        background-color: #fef3c7;
    }}
    th {{
        color: #92400e;
        font-weight: bold;
        text-align: left;
        padding: 6pt 8pt;
        border: 0.5pt solid #e5e7eb;
    }}
    td {{
        padding: 5pt 8pt;
        border: 0.5pt solid #e5e7eb;
        color: #1f2937;
    }}
    blockquote {{
        border-left: 2pt solid #fcd34d;
        padding-left: 10pt;
        color: #4b5563;
        margin: 8pt 0;
        font-style: italic;
    }}
    #footer_content {{
        font-size: 8pt;
        color: #94a3b8;
        text-align: right;
    }}
</style>
</head>
<body>
    {body}

    <div id="footer_content">
        Exported {exported_on}
    </div>
</body>
</html>"""


def _markdown_to_html(content: str) -> str:
    """Convert markdown → HTML with GitHub-style extensions."""
    return md_lib.markdown(
        content or '',
        extensions=[
            'tables',
            'fenced_code',
            'sane_lists',
            'nl2br',
        ],
        output_format='html',
    )


def render_document_pdf(
    *,
    title: str,
    content_markdown: str,
    template_label: Optional[str] = None,
    tone_label: Optional[str] = None,
    version: Optional[int] = None,
    word_count: Optional[int] = None,
) -> bytes:
    """Render a document to PDF bytes.

    Raises:
        RuntimeError: if xhtml2pdf fails to generate the PDF.
    """
    safe_title = (title or 'Document').strip() or 'Document'
    body_html = _markdown_to_html(content_markdown)

    html = _TEMPLATE.format(
        title=safe_title,
        body=body_html,
        exported_on=datetime.now().strftime('%B %d, %Y'),
    )

    buffer = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer, encoding='utf-8')
    if result.err:
        logger.error('xhtml2pdf failed to render PDF. Errors: %s', result.err)
        raise RuntimeError(f'PDF generation failed ({result.err} errors)')

    return buffer.getvalue()

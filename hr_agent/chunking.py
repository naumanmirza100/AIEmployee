"""Section-aware chunking for HR documents.

The naive chunker splits at fixed character offsets, which:
  * splits sentences mid-word
  * splits sections across chunks (one chunk = part of two policies)
  * scores worse on QA — the LLM has to stitch fragments back together

This module detects natural boundaries (Markdown ``#``/``##`` headings,
ALL-CAPS section titles common in PDFs, numbered article markers like
``Article 4`` / ``Section 4.2`` / ``4.2 ``) and splits on them. Within a
section, if the section is longer than ``max_chunk_size``, we sub-split on
paragraph boundaries with ``overlap`` characters of context.

Public entry point: :func:`chunk_with_headings(text, *, max_chunk_size,
overlap)` returning a list of ``(chunk_text, section_heading)`` tuples.
Falls back to fixed-size chunking when no headings are detected, so it's
safe to use for any text (heading will be ``""`` for unheaded chunks).
"""
from __future__ import annotations

import re
from typing import List, Tuple


# A line is a heading if it matches any of these patterns (whole-line).
# Order matters — Markdown is most reliable, ALL-CAPS most generic.
_HEADING_PATTERNS = [
    re.compile(r'^\s*#{1,6}\s+\S.*$'),                       # `# Heading` / `## Sub`
    re.compile(r'^\s*(?:Article|ARTICLE)\s+\d+(?:\.\d+)*\b.*$'),  # `Article 4 ...`
    re.compile(r'^\s*(?:Section|SECTION)\s+\d+(?:\.\d+)*\b.*$'),  # `Section 4.2 ...`
    re.compile(r'^\s*\d+(?:\.\d+){0,3}\s+[A-Z][A-Za-z].*$'),  # `4.2 Paid time off`
    re.compile(r'^\s*[A-Z][A-Z0-9 \-,&/]{3,80}$'),            # ALL-CAPS lines
]


def _is_heading(line: str) -> bool:
    line = line.rstrip()
    if not line.strip():
        return False
    for pat in _HEADING_PATTERNS:
        if pat.match(line):
            return True
    return False


def _split_into_sections(text: str) -> List[Tuple[str, str]]:
    """Split ``text`` into ``(heading, section_text)`` pairs.

    The heading line itself is kept at the top of ``section_text`` so the
    full chunk is self-contained for embedding, while ``heading`` is stored
    separately on the chunk row for citation display.

    If no headings are detected, returns a single ``("", text)`` pair.
    """
    if not text:
        return []
    lines = text.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    current_heading: str = ''
    current_lines: List[str] = []
    for line in lines:
        if _is_heading(line):
            if current_lines and any(s.strip() for s in current_lines):
                sections.append((current_heading, current_lines))
            current_heading = line.strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines and any(s.strip() for s in current_lines):
        sections.append((current_heading, current_lines))
    if not sections:
        return [('', text)]
    return [(h, '\n'.join(ls).strip()) for h, ls in sections]


def _split_long_section(section: str, max_size: int, overlap: int) -> List[str]:
    """If a section is shorter than ``max_size``, return it as-is.
    Otherwise, sub-split on blank-line paragraph boundaries, packing
    paragraphs into ≤ ``max_size`` chunks. Falls back to character slicing
    when even a single paragraph is too long.
    """
    if len(section) <= max_size:
        return [section]

    # Try paragraph packing first
    paragraphs = re.split(r'\n\s*\n', section)
    chunks: List[str] = []
    buf = ''
    for p in paragraphs:
        p = p.rstrip()
        if not p:
            continue
        if not buf:
            buf = p
        elif len(buf) + 2 + len(p) <= max_size:
            buf = buf + '\n\n' + p
        else:
            chunks.append(buf)
            # carry overlap from end of previous chunk
            tail = buf[-overlap:] if overlap and len(buf) > overlap else ''
            buf = (tail + '\n\n' + p) if tail else p
    if buf:
        chunks.append(buf)

    # If any single chunk is still over budget, fall back to fixed-size.
    out: List[str] = []
    step = max(1, max_size - overlap)
    for c in chunks:
        if len(c) <= max_size:
            out.append(c)
            continue
        i = 0
        while i < len(c):
            out.append(c[i:i + max_size])
            i += step
    return out


def chunk_with_headings(text: str, *, max_chunk_size: int = 4000,
                        overlap: int = 200) -> List[Tuple[str, str]]:
    """Top-level chunker. Detects sections, then sub-splits long ones.

    Returns a flat list of ``(chunk_text, section_heading)`` tuples where
    ``section_heading`` is the detected heading that opened the section
    (empty string for preamble text or non-section-aware doc types).
    Each chunk text is ≤ ``max_chunk_size`` characters.
    """
    if not text:
        return []
    sections = _split_into_sections(text)
    out: List[Tuple[str, str]] = []
    for heading, section_text in sections:
        for chunk in _split_long_section(section_text, max_chunk_size, overlap):
            chunk = chunk.strip()
            if chunk:
                out.append((chunk, heading))
    return out


# Document types that benefit most from heading-aware chunking. Other types
# (offer_letter, payslip, contract) tend to be single-section so the naive
# chunker is fine.
SECTION_AWARE_TYPES = frozenset({'handbook', 'policy', 'procedure', 'training', 'compliance', 'benefits'})

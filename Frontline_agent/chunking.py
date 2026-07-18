"""Chunk-quality helpers for the Frontline knowledge pipeline.

Currently a single public helper — :func:`looks_like_toc_or_index` — used by
both the chunker (`Frontline_agent.tasks.process_document`) and the retriever
(`core.Frontline_agent.services._search_documents`) to drop table-of-contents,
index, and cover-page fragments that would otherwise pollute retrieval with
high-scoring-but-useless matches (dot-leaders, bare page numbers, etc.).

Mirrors the shape of `hr_agent.chunking._looks_like_toc_or_index` so the two
agents stay behaviourally aligned.
"""
from __future__ import annotations

import re


_DOT_LEADER_RE = re.compile(r'\.{3,}|(?:\.\s){3,}')
_PAGE_NUM_ONLY_RE = re.compile(r'^\s*(?:page\s*)?\d{1,4}\s*$', re.IGNORECASE)
_WORD_RE = re.compile(r'[A-Za-z]{2,}')


def looks_like_toc_or_index(text: str) -> bool:
    """Return True when the chunk is table-of-contents / index / cover page
    with no substantive content. Three heuristics:

    * A large fraction of lines contain dot-leaders (``. . . . 58``).
    * Most non-empty lines are just page numbers.
    * After stripping punctuation / digits / whitespace, fewer than 40 letters
      of actual text remain.
    """
    if not text:
        return True
    stripped = text.strip()
    if not stripped:
        return True

    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if not lines:
        return True

    dot_leader_lines = sum(1 for ln in lines if _DOT_LEADER_RE.search(ln))
    page_num_lines = sum(1 for ln in lines if _PAGE_NUM_ONLY_RE.match(ln))
    junk_ratio = (dot_leader_lines + page_num_lines) / max(len(lines), 1)
    if junk_ratio >= 0.5 and len(lines) >= 3:
        return True

    letters = sum(len(m.group(0)) for m in _WORD_RE.finditer(stripped))
    if letters < 40:
        return True

    return False

"""Character-level diff between two prompts, for `GET /prompts/diff`.

Uses the standard library's `difflib.SequenceMatcher` operated directly on
the two strings (character-level, matching the same granularity as the Diff
panel's client-side `diffChars`), rather than shipping full prompt content to
the browser and diffing there - lets the server fetch each event's full
content itself instead of the caller needing to fetch both first.

`diff_html` is built from `html.escape()`d segments only, wrapped in `<span
class="add"|"del"|"same">` - no other markup, attributes, or user-controlled
tag names ever reach the output, so a prompt containing `<script>` or an
`onclick=` attribute can't execute when the frontend renders it.
"""

from __future__ import annotations

import difflib
import html
from typing import TypedDict


class PromptDiffResult(TypedDict):
    additions: int
    deletions: int
    unchanged: int
    diff_html: str


def _span(css_class: str, text: str) -> str:
    return f'<span class="{css_class}">{html.escape(text)}</span>'


def compute_prompt_diff(text_a: str, text_b: str) -> PromptDiffResult:
    matcher = difflib.SequenceMatcher(None, text_a, text_b)
    additions = 0
    deletions = 0
    unchanged = 0
    html_parts: list[str] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segment = text_a[i1:i2]
            unchanged += len(segment)
            html_parts.append(_span("same", segment))
        elif tag == "delete":
            segment = text_a[i1:i2]
            deletions += len(segment)
            html_parts.append(_span("del", segment))
        elif tag == "insert":
            segment = text_b[j1:j2]
            additions += len(segment)
            html_parts.append(_span("add", segment))
        elif tag == "replace":
            deleted = text_a[i1:i2]
            inserted = text_b[j1:j2]
            deletions += len(deleted)
            additions += len(inserted)
            html_parts.append(_span("del", deleted))
            html_parts.append(_span("add", inserted))

    return {
        "additions": additions,
        "deletions": deletions,
        "unchanged": unchanged,
        "diff_html": "".join(html_parts),
    }

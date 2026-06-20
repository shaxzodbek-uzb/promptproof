"""Dependency-free token estimation.

We deliberately avoid ``tiktoken`` (and any network/model): the whole value of
promptproof is that it runs instantly with zero install friction. The estimate below
lands within roughly 15% of cl100k/o200k token counts for typical English prose and
markdown, which is more than enough for "is this asset 3x over budget?" checks.
"""

from __future__ import annotations

import re

_WORD = re.compile(r"\S+")


def estimate_tokens(text: str) -> int:
    """Heuristic token count for ``text``. Deterministic; 0 for empty/whitespace.

    Method: ``round(max(words * 1.3, chars / 4.0))``. The word term captures the fact
    that most whitespace-delimited tokens are 1-2 BPE tokens; the char term keeps the
    estimate sane for dense, punctuation-heavy, or non-spaced text. The result is never
    below the word count for non-empty text.
    """
    if not text or not text.strip():
        return 0
    n_words = len(_WORD.findall(text))
    n_chars = len(text)
    est = round(max(n_words * 1.3, n_chars / 4.0))
    return max(est, n_words)

"""Shared test helpers."""

from __future__ import annotations

from promptproof import DocKind, lint_text


def ids(text: str, *, kind: DocKind | None = None, path: str = "<text>") -> set[str]:
    """Rule ids fired when linting ``text`` (optionally forcing a kind)."""
    return {f.rule for f in lint_text(text, path=path, kind=kind)}

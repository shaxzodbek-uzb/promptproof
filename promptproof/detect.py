"""Classify a file into a :class:`~promptproof.document.DocKind`.

Detection is path- and content-based and deliberately conservative: when in doubt a
markdown/text file is a generic ``PROMPT`` (the universal rules still apply), so we never
mislabel a plain prompt as a skill and spray structure errors at it.
"""

from __future__ import annotations

import json
import os

from .document import DocKind


def _norm(path: str) -> str:
    return path.replace("\\", "/").lower()


def detect_kind(path: str, text: str, frontmatter: dict | None) -> DocKind:
    p = _norm(path)
    base = os.path.basename(p)
    ext = os.path.splitext(base)[1]

    if base == "skill.md":
        return DocKind.SKILL
    if "/.claude/agents/" in p:
        return DocKind.SUBAGENT
    if "/.claude/commands/" in p:
        return DocKind.COMMAND

    if ext == ".json":
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            obj = None
        if isinstance(obj, dict) and "name" in obj and (
            "inputSchema" in obj or "input_schema" in obj or "parameters" in obj
        ):
            return DocKind.MCP_TOOL

    if frontmatter and "name" in frontmatter and "description" in frontmatter:
        if "tools" in frontmatter or "model" in frontmatter:
            return DocKind.SUBAGENT
        return DocKind.SKILL

    if ext in (".md", ".markdown", ".txt", ".prompt"):
        return DocKind.PROMPT

    return DocKind.UNKNOWN

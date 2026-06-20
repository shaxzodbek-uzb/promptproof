"""The :class:`Document` model — a parsed prompt asset that rules inspect.

A Document carries the raw text, its detected kind, parsed frontmatter (if any), and the
body region (everything after the frontmatter). Rules read ``doc.lines`` for file-absolute
line numbers and ``doc.body_lines()`` to skip the frontmatter fence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .parsers import parse_frontmatter


class DocKind(str, Enum):
    SKILL = "skill"
    SUBAGENT = "subagent"
    COMMAND = "command"
    MCP_TOOL = "mcp-tool"
    PROMPT = "prompt"
    UNKNOWN = "unknown"


@dataclass
class Document:
    path: str
    text: str
    kind: DocKind
    frontmatter: dict | None
    frontmatter_span: tuple[int, int] | None
    body: str
    body_start_line: int
    lines: list[str] = field(default_factory=list)
    frontmatter_error: str | None = None
    _fenced_lines: frozenset[int] | None = field(default=None, compare=False, repr=False)

    @classmethod
    def from_text(
        cls, text: str, *, path: str = "<text>", kind: DocKind | None = None
    ) -> Document:
        fm, span, err = parse_frontmatter(text)
        lines = text.splitlines()
        if span is not None:
            body_start_line = span[1] + 1
            body = "\n".join(lines[span[1] :])
        else:
            body_start_line = 1
            body = text
        if kind is None:
            from . import detect

            kind = detect.detect_kind(path, text, fm)
        return cls(
            path=path,
            text=text,
            kind=kind,
            frontmatter=fm,
            frontmatter_span=span,
            body=body,
            body_start_line=body_start_line,
            lines=lines,
            frontmatter_error=err,
        )

    @classmethod
    def from_path(cls, path: str, *, kind: DocKind | None = None) -> Document:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        return cls.from_text(text, path=path, kind=kind)

    def body_lines(self) -> list[tuple[int, str]]:
        """(file_line_number_1based, line_text) for the body region only."""
        return [
            (i, line)
            for i, line in enumerate(self.lines, start=1)
            if i >= self.body_start_line
        ]

    def fenced_lines(self) -> frozenset[int]:
        """1-based file line numbers that sit inside a ``` fenced code block.

        Computed once and cached so rules can test membership in O(1) instead of
        rescanning the whole file per line (which is O(n^2) across a document).
        """
        if self._fenced_lines is None:
            inside: set[int] = set()
            fence = False
            for i, ln in enumerate(self.lines, start=1):
                if ln.lstrip().startswith("```"):
                    fence = not fence
                    if fence:  # the opening fence line counts as inside; closing does not
                        inside.add(i)
                    continue
                if fence:
                    inside.add(i)
            self._fenced_lines = frozenset(inside)
        return self._fenced_lines

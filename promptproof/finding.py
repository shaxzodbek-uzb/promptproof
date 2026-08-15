"""Core result types: severities, source locations, and findings.

These are the only objects a rule produces and the only objects a reporter consumes.
Everything is frozen and hashable so findings can be de-duplicated and sorted cheaply.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

_RANK = {"info": 1, "warning": 2, "error": 3}


class Severity(str, Enum):
    """Finding severity, ordered ``INFO < WARNING < ERROR`` via :attr:`rank`."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        return _RANK[self.value]

    @classmethod
    def parse(cls, value: str) -> Severity:
        return cls(value.strip().lower())


@dataclass(frozen=True)
class Location:
    """A 1-based source location. ``line``/``col`` of 0 mean whole-file / unknown."""

    path: str
    line: int = 0
    col: int = 0
    end_line: int | None = None


@dataclass(frozen=True)
class Edit:
    """A mechanical repair: replace lines ``[start_line, end_line]`` with ``replacement``.

    Line numbers are 1-based and inclusive, matching :class:`Location`. An empty
    ``replacement`` deletes the range. A rule attaches one to a finding only when the
    repair is **unambiguous** — anything requiring judgement about what the author meant
    stays a hint for a human to act on.
    """

    start_line: int
    end_line: int
    replacement: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    """A single lint result."""

    rule: str
    name: str
    severity: Severity
    message: str
    location: Location
    hint: str | None = None
    #: Set when this finding can be repaired mechanically (``--fix``).
    fix: Edit | None = None

    @property
    def fixable(self) -> bool:
        return self.fix is not None

    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.location.path, self.location.line, self.location.col, self.rule)

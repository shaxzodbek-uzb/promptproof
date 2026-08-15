"""Rule infrastructure: metadata, the ``Rule`` base class, the registry, and the small
set of shared text helpers every rule may reuse.

A rule module defines one or more ``Rule`` subclasses, each decorated with ``@register``
and (optionally) paired with a ``register_explain(id, text)`` call so ``promptproof
explain <id>`` has something to print. The ``rules`` package auto-imports every
``ppNNN_*.py`` module, which runs those decorators at import time.
"""

from __future__ import annotations

import abc
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..document import DocKind, Document
from ..finding import Edit, Finding, Location, Severity

if TYPE_CHECKING:
    from ..config import Config


@dataclass(frozen=True)
class RuleMeta:
    id: str
    name: str
    category: str
    summary: str
    default_severity: Severity
    kinds: tuple[DocKind, ...] = ()  # () means: applies to ALL kinds


@dataclass
class Context:
    config: Config

    def estimate_tokens(self, text: str) -> int:
        from ..tokens import estimate_tokens

        return estimate_tokens(text)

    def threshold(self, key: str, default):
        return self.config.thresholds.get(key, default)


class Rule(abc.ABC):
    meta: RuleMeta

    @abc.abstractmethod
    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        ...

    def finding(
        self,
        doc: Document,
        message: str,
        *,
        line: int = 0,
        col: int = 0,
        end_line: int | None = None,
        hint: str | None = None,
        severity: Severity | None = None,
        fix: Edit | None = None,
    ) -> Finding:
        return Finding(
            rule=self.meta.id,
            name=self.meta.name,
            severity=severity or self.meta.default_severity,
            message=message,
            location=Location(doc.path, line, col, end_line),
            hint=hint,
            fix=fix,
        )


# --------------------------------------------------------------------------- registry

_REGISTRY: dict[str, Rule] = {}
_EXPLAIN: dict[str, str] = {}


def register(cls: type[Rule]) -> type[Rule]:
    """Class decorator: instantiate the rule and register it under ``meta.id``."""
    meta = getattr(cls, "meta", None)
    if meta is None:
        raise TypeError(f"{cls.__name__} has no `meta` RuleMeta")
    if meta.id in _REGISTRY:
        raise ValueError(f"duplicate rule id {meta.id} ({cls.__name__})")
    _REGISTRY[meta.id] = cls()
    return cls


def register_explain(rule_id: str, text: str) -> None:
    _EXPLAIN[rule_id] = text.strip()


def explain_for(rule_id: str) -> str | None:
    return _EXPLAIN.get(rule_id)


def all_rules() -> list[Rule]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def get_rule(rule_id: str) -> Rule | None:
    return _REGISTRY.get(rule_id)


def rules_for_kind(kind: DocKind) -> list[Rule]:
    out = []
    for rule in all_rules():
        kinds = rule.meta.kinds
        if not kinds or kind in kinds:
            out.append(rule)
    return out


# ----------------------------------------------------------------------- text helpers

_IMPERATIVE_CUE = re.compile(
    r"^\s*(?:[-*]\s+|\d+[.)]\s+)?"
    r"(?:you\s+(?:must|should|need to|have to|will|are)\b"
    r"|always\b|never\b|do not\b|don't\b|do\b|please\b|ensure\b|make sure\b"
    r"|avoid\b|use\b|return\b|respond\b|output\b|write\b|include\b|prefer\b"
    r"|generate\b|create\b|format\b|keep\b|be\s+\w+)",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def is_imperative(line: str) -> bool:
    """Heuristic: does this line read as an instruction/directive?"""
    return bool(_IMPERATIVE_CUE.match(line))


def imperative_lines(doc: Document) -> list[tuple[int, str]]:
    """Body lines that look like instructions, as (file_line_1based, text)."""
    return [(n, ln) for n, ln in doc.body_lines() if ln.strip() and is_imperative(ln)]


def sentences(text: str) -> list[str]:
    """Naive sentence split on sentence punctuation and newlines."""
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def col_of(line: str, match: re.Match | str) -> int:
    """1-based column of a match (or substring) within ``line``; 0 if not found."""
    if isinstance(match, re.Match):
        return match.start() + 1
    idx = line.lower().find(match.lower())
    return idx + 1 if idx >= 0 else 0


def in_code_fence(lines: list[str], target_line: int) -> bool:
    """True if file line ``target_line`` (1-based) sits inside a ``` fenced block."""
    fence = False
    for i, ln in enumerate(lines, start=1):
        if ln.lstrip().startswith("```"):
            fence = not fence
        if i == target_line:
            return fence
    return False

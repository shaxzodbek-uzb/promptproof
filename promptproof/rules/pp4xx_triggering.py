"""Triggering rules (PP4xx) — the heart of promptproof.

The #1 reason a skill or sub-agent "doesn't work" is that its ``description`` never makes
the model decide to load it. These rules check that the description exists, is the right
length, and actually states *when* to use the asset rather than merely summarizing it.

This module is also the reference implementation other rule groups follow: a ``Rule``
subclass per check, ``@register``-decorated, with ``register_explain`` for ``explain``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from ..document import DocKind, Document
from ..finding import Finding, Severity
from .base import Context, Rule, RuleMeta, col_of, register, register_explain

_FRONTMATTER_KINDS = (DocKind.SKILL, DocKind.SUBAGENT, DocKind.COMMAND)

_TRIGGER_CUE = re.compile(
    r"\b(use\s+(this\s+)?(skill|tool|agent|command)?\s*when"
    r"|when\s+(the\s+)?(user|you)\b"
    r"|when\s+(asked|invoked|you\s+need)"
    r"|for\s+\w+ing\b"
    r"|trigger(s|ed)?\s+(when|on)"
    r"|invoke\s+(this\s+)?when"
    r"|if\s+(the\s+user|you)\b"
    r"|whenever\b)",
    re.IGNORECASE,
)
_SUMMARY_FRAME = re.compile(
    r"^\s*(a\s|an\s|this\s+(skill|tool|agent|command)\b|tool\s+to\s+|helps\s+you\b"
    r"|used\s+to\s+|allows\s+you\s+to\b|enables\b|provides\b)",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\bI\s+(will|can|am|help|provide|use|handle)\b")


def _mapping(doc: Document) -> dict | None:
    if doc.kind is DocKind.MCP_TOOL:
        try:
            obj = json.loads(doc.text)
        except (ValueError, TypeError):
            return None
        return obj if isinstance(obj, dict) else None
    return doc.frontmatter


def _field_location(doc: Document, key: str) -> tuple[int, int]:
    """Best-effort (line, col) of a frontmatter/json field by name."""
    if doc.kind is DocKind.MCP_TOOL:
        needle = f'"{key}"'
    else:
        needle = f"{key}:"
    span = doc.frontmatter_span
    lo = span[0] if span else 1
    hi = span[1] if span else len(doc.lines)
    for i in range(lo - 1, min(hi, len(doc.lines))):
        col = col_of(doc.lines[i], needle)
        if col:
            return i + 1, col
    return 0, 0


def _description(doc: Document) -> str | None:
    m = _mapping(doc)
    if not m:
        return None
    desc = m.get("description")
    if desc is None:
        return None
    return desc if isinstance(desc, str) else str(desc)


@register
class DescriptionMissing(Rule):
    meta = RuleMeta(
        id="PP401",
        name="description-missing",
        category="triggering",
        summary="asset has no description, so the agent can never decide to load it",
        default_severity=Severity.ERROR,
        kinds=(DocKind.SKILL, DocKind.SUBAGENT, DocKind.COMMAND, DocKind.MCP_TOOL),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        m = _mapping(doc)
        if m is None:  # no frontmatter / unparseable json -> covered by structure rules
            return
        desc = m.get("description")
        if desc is None or (isinstance(desc, str) and not desc.strip()):
            line, col = _field_location(doc, "name")
            yield self.finding(
                doc,
                "missing description — the agent has no trigger to load this asset",
                line=line,
                col=col,
                hint='add: description: "Use when <condition> — e.g. <example>"',
            )


@register
class DescriptionTooShort(Rule):
    meta = RuleMeta(
        id="PP402",
        name="description-too-short",
        category="triggering",
        summary="description is too thin to trigger reliably",
        default_severity=Severity.WARNING,
        kinds=(DocKind.SKILL, DocKind.SUBAGENT, DocKind.COMMAND, DocKind.MCP_TOOL),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        desc = _description(doc)
        if desc is None or not desc.strip():
            return
        min_chars = ctx.threshold("description_min_chars", 40)
        if len(desc.strip()) < min_chars:
            line, col = _field_location(doc, "description")
            yield self.finding(
                doc,
                f"description too short: {len(desc.strip())} chars "
                f"(aim for ≥ {min_chars}) — add the trigger condition",
                line=line,
                col=col,
            )


@register
class DescriptionTooLong(Rule):
    meta = RuleMeta(
        id="PP403",
        name="description-too-long",
        category="triggering",
        summary="description exceeds the SKILL.md length limit",
        default_severity=Severity.WARNING,
        kinds=(DocKind.SKILL,),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        desc = _description(doc)
        if desc is None:
            return
        max_chars = ctx.threshold("description_max_chars", 1024)
        n = len(desc.strip())
        if n > max_chars:
            line, col = _field_location(doc, "description")
            sev = Severity.ERROR if n > 2 * max_chars else Severity.WARNING
            yield self.finding(
                doc,
                f"description too long: {n} chars (limit {max_chars})",
                line=line,
                col=col,
                severity=sev,
                hint="move detail into the body; keep the description a tight trigger",
            )


@register
class WeakTrigger(Rule):
    meta = RuleMeta(
        id="PP404",
        name="weak-trigger",
        category="triggering",
        summary="description summarizes the asset instead of stating WHEN to use it",
        default_severity=Severity.WARNING,
        kinds=(DocKind.SKILL, DocKind.SUBAGENT, DocKind.MCP_TOOL),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        desc = _description(doc)
        if desc is None or not desc.strip():
            return
        has_cue = bool(_TRIGGER_CUE.search(desc))
        summary_frame = bool(_SUMMARY_FRAME.match(desc))
        if has_cue and not summary_frame:
            return
        line, col = _field_location(doc, "description")
        if summary_frame and not has_cue:
            msg = "weak trigger: description summarizes instead of stating when to use it"
        elif summary_frame:
            msg = "weak trigger: description opens by summarizing — lead with the trigger"
        else:
            msg = "weak trigger: description states no trigger condition (no \"use when …\")"
        yield self.finding(
            doc,
            msg,
            line=line,
            col=col,
            hint='rewrite as "Use when <condition> — e.g. <trigger example>"',
        )


@register
class FirstPersonDescription(Rule):
    meta = RuleMeta(
        id="PP405",
        name="first-person-description",
        category="triggering",
        summary="description is first-person instead of third-person trigger framing",
        default_severity=Severity.INFO,
        kinds=(DocKind.SKILL, DocKind.SUBAGENT, DocKind.MCP_TOOL),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        desc = _description(doc)
        if desc is None:
            return
        if _FIRST_PERSON.search(desc):
            line, col = _field_location(doc, "description")
            yield self.finding(
                doc,
                'first-person description ("I ...") — agents match on conditions, not voice',
                line=line,
                col=col,
                hint="rephrase as a third-person trigger: \"Use when …\"",
            )


@register
class ToolParamUndocumented(Rule):
    meta = RuleMeta(
        id="PP406",
        name="tool-param-undocumented",
        category="triggering",
        summary="an MCP tool input parameter has no description",
        default_severity=Severity.WARNING,
        kinds=(DocKind.MCP_TOOL,),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        m = _mapping(doc)
        if not m:
            return
        schema = m.get("inputSchema") or m.get("input_schema") or m.get("parameters")
        if not isinstance(schema, dict):
            return
        props = schema.get("properties")
        if not isinstance(props, dict):
            return
        for pname, pdef in props.items():
            if not isinstance(pdef, dict) or not str(pdef.get("description", "")).strip():
                line, col = _field_location(doc, str(pname))
                yield self.finding(
                    doc,
                    f"tool parameter '{pname}' has no description — the model will guess it",
                    line=line,
                    col=col,
                    hint=f"add a description to the '{pname}' property",
                )


register_explain(
    "PP404",
    """A description must tell the agent WHEN to reach for the asset, not WHAT it is.

BAD  (summarizes — the agent can't tell when it applies):
    description: A skill for working with PDF files.

GOOD (states the trigger condition + examples):
    description: >-
      Use when the user wants to read, merge, split, or extract text from PDF
      files, or mentions a .pdf by name.
""",
)
register_explain(
    "PP401",
    "Every skill / sub-agent / MCP tool needs a `description`. With none, the model has "
    "no signal to load it, so the asset is dead weight. Add a one-line trigger condition.",
)

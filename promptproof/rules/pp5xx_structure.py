"""Structure rules (PP5xx) — frontmatter wellformedness and naming hygiene.

These rules check the *shape* of an asset rather than its prose: that a skill /
sub-agent / command actually has a parseable frontmatter block, that it carries the
required ``name`` field in the canonical kebab-case form, that a ``SKILL.md`` lives in a
directory named after it, that a procedural skill tells the agent how to verify its work,
and that no stray (unknown) frontmatter keys sneak in.

Most checks are ERROR-level structural facts (missing / invalid / nameless frontmatter)
with no false-positive surface. The softer, heuristic checks (missing verify guidance,
unknown keys) are INFO so legitimate-but-unusual frontmatter is never punished hard.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

from ..document import DocKind, Document
from ..finding import Finding, Severity
from .base import Context, Rule, RuleMeta, col_of, register, register_explain

_FRONTMATTER_KINDS = (DocKind.SKILL, DocKind.SUBAGENT, DocKind.COMMAND)

_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# A body that mentions how to verify / check / confirm the work was done correctly.
_VERIFY_RE = re.compile(
    r"verif|how to (check|confirm)|to confirm|validate|make sure it works",
    re.IGNORECASE,
)

# Known frontmatter keys per kind (SPEC §6 "structure"). Keys outside the set => PP507.
_KNOWN_KEYS = {
    DocKind.SKILL: {"name", "description", "version", "license", "allowed-tools", "metadata"},
    DocKind.SUBAGENT: {"name", "description", "tools", "model", "color"},
    DocKind.COMMAND: {"name", "description", "argument-hint", "model", "allowed-tools"},
}

_SYNTHETIC_PATHS = ("<text>", "<stdin>")


def _key_location(doc: Document, key: str) -> tuple[int, int]:
    """Best-effort 1-based (line, col) of a ``key:`` inside the frontmatter span."""
    span = doc.frontmatter_span
    lo = span[0] if span else 1
    hi = span[1] if span else len(doc.lines)
    needle = f"{key}:"
    for i in range(lo - 1, min(hi, len(doc.lines))):
        # Anchor on a line that *starts* with the key (after optional indent) so we don't
        # match the key name appearing inside some other value.
        stripped = doc.lines[i].lstrip()
        if stripped.startswith(needle):
            return i + 1, col_of(doc.lines[i], needle)
    return 0, 0


@register
class FrontmatterMissing(Rule):
    meta = RuleMeta(
        id="PP501",
        name="frontmatter-missing",
        category="structure",
        summary="skill / sub-agent / command has no frontmatter block at all",
        default_severity=Severity.ERROR,
        kinds=_FRONTMATTER_KINDS,
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        # Only fire when there is genuinely no ``---`` block. If a block existed but failed
        # to parse, that is PP502's job (frontmatter is None but span is set).
        if doc.frontmatter is None and doc.frontmatter_span is None:
            yield self.finding(
                doc,
                "missing frontmatter — add a `---` block with at least `name` and "
                "`description`",
                line=1,
                hint='start the file with:\n---\nname: my-skill\ndescription: "Use when …"\n---',
            )


@register
class FrontmatterInvalid(Rule):
    meta = RuleMeta(
        id="PP502",
        name="frontmatter-invalid",
        category="structure",
        summary="a `---` frontmatter block exists but could not be parsed",
        default_severity=Severity.ERROR,
        kinds=_FRONTMATTER_KINDS,
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        if doc.frontmatter_error is None:
            return
        span = doc.frontmatter_span
        line = span[0] if span else 1
        yield self.finding(
            doc,
            f"invalid frontmatter: {doc.frontmatter_error}",
            line=line,
            hint="fix the YAML so it parses to a `key: value` mapping",
        )


@register
class NameMissing(Rule):
    meta = RuleMeta(
        id="PP503",
        name="name-missing",
        category="structure",
        summary="frontmatter is present but has no `name` field",
        default_severity=Severity.ERROR,
        kinds=_FRONTMATTER_KINDS,
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        # Don't fire when frontmatter is entirely absent — PP501 owns that case.
        if doc.frontmatter is None:
            return
        if "name" not in doc.frontmatter:
            span = doc.frontmatter_span
            line = span[0] if span else 1
            yield self.finding(
                doc,
                "missing `name` in frontmatter",
                line=line,
                hint="add `name: <kebab-case-id>` (match the directory name for skills)",
            )


@register
class NameNotKebab(Rule):
    meta = RuleMeta(
        id="PP504",
        name="name-not-kebab",
        category="structure",
        summary="`name` is not lowercase kebab-case",
        default_severity=Severity.WARNING,
        kinds=_FRONTMATTER_KINDS,
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        if doc.frontmatter is None:
            return
        name = doc.frontmatter.get("name")
        if not isinstance(name, str) or not name.strip():
            return
        value = name.strip()
        if not _KEBAB_RE.match(value):
            line, col = _key_location(doc, "name")
            yield self.finding(
                doc,
                f"name not kebab-case: {value!r}",
                line=line,
                col=col,
                hint="use lowercase letters, digits, and single hyphens, e.g. `pdf-tools`",
            )


@register
class NameDirMismatch(Rule):
    meta = RuleMeta(
        id="PP505",
        name="name-dir-mismatch",
        category="structure",
        summary="a SKILL.md `name` does not match its parent directory",
        default_severity=Severity.WARNING,
        kinds=(DocKind.SKILL,),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        if doc.frontmatter is None:
            return
        # Synthetic/in-memory documents have no real directory to compare against.
        if doc.path in _SYNTHETIC_PATHS:
            return
        # Only meaningful for the conventional ``<skill-name>/SKILL.md`` layout.
        if os.path.basename(doc.path) != "SKILL.md":
            return
        name = doc.frontmatter.get("name")
        if not isinstance(name, str) or not name.strip():
            return
        parent = os.path.basename(os.path.dirname(os.path.abspath(doc.path)))
        if not parent:
            return
        if name.strip() != parent:
            line, col = _key_location(doc, "name")
            yield self.finding(
                doc,
                f"name {name.strip()!r} does not match directory {parent!r}",
                line=line,
                col=col,
                hint=f"rename `name` to {parent!r} or move the file into a `{name.strip()}/` dir",
            )


@register
class MissingVerifyGuidance(Rule):
    meta = RuleMeta(
        id="PP506",
        name="missing-verify-guidance",
        category="structure",
        summary="a procedural skill body never says how to verify the work",
        default_severity=Severity.INFO,
        kinds=(DocKind.SKILL,),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        # Only meaningful for skills with an actual procedural body.
        if not doc.body.strip():
            return
        for _, line in doc.body_lines():
            if _VERIFY_RE.search(line):
                return
        severity = (
            Severity.WARNING
            if ctx.threshold("structure.require_verify", False)
            else Severity.INFO
        )
        yield self.finding(
            doc,
            "no verify / check step — the agent can't confirm it succeeded",
            line=0,
            severity=severity,
            hint='add a "Verify" section, e.g. how to confirm the change worked',
        )


@register
class UnknownFrontmatterKey(Rule):
    meta = RuleMeta(
        id="PP507",
        name="unknown-frontmatter-key",
        category="structure",
        summary="a frontmatter key outside the known set for this asset kind",
        default_severity=Severity.INFO,
        kinds=_FRONTMATTER_KINDS,
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        if doc.frontmatter is None:
            return
        known = _KNOWN_KEYS.get(doc.kind)
        if known is None:
            return
        for key in doc.frontmatter:
            if not isinstance(key, str) or key in known:
                continue
            line, col = _key_location(doc, key)
            yield self.finding(
                doc,
                f"unknown frontmatter key: {key!r}",
                line=line,
                col=col,
                hint=f"known keys for {doc.kind.value}: {', '.join(sorted(known))}",
            )


register_explain(
    "PP501",
    """A skill / sub-agent / command is defined by its frontmatter — without it the asset
has no name and no description, so the agent can never load it.

BAD  (no frontmatter — file is just a body):
    # PDF Tools
    Steps to merge PDFs ...

GOOD (a `---` block declares name + description):
    ---
    name: pdf-tools
    description: Use when the user wants to merge, split, or read PDF files.
    ---
    # PDF Tools
    Steps to merge PDFs ...
""",
)
register_explain(
    "PP504",
    """The `name` field is an identifier, not prose: keep it lowercase kebab-case so it is
stable across tools, URLs, and directory layouts.

BAD  (spaces / capitals break tooling):
    name: PDF Tools

GOOD:
    name: pdf-tools
""",
)
register_explain(
    "PP505",
    """A `SKILL.md` is discovered by its directory; if the frontmatter `name` and the parent
directory disagree, tools and the agent can reference the skill under two different names.

BAD  (dir `pdf-tools/` but name says otherwise):
    pdf-tools/SKILL.md  ->  name: pdf-utilities

GOOD (they match):
    pdf-tools/SKILL.md  ->  name: pdf-tools
""",
)

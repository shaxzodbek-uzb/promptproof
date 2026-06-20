"""Clarity rules (PP1xx) — instructions a model can't act on deterministically.

These rules flag prose that *reads* fine to a human but leaves a model guessing: a
directive qualified by a vague adverb ("handle it appropriately"), a countable asked for
without a number ("give some examples"), a sentence that opens on an unresolved pronoun,
acceptance phrased as a feeling ("make it nice"), or a firm step softened into a maybe
("try to validate the input"). All are prose-level and run on the body only; every match
is skipped inside fenced code blocks. Most are INFO — clarity is advisory, and a false
positive on legitimate prose is worse than a miss — with PP101 the one WARNING because a
qualifier inside an imperative line is a concrete, locatable defect.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..document import Document
from ..finding import Finding, Severity
from .base import (
    Context,
    Rule,
    RuleMeta,
    col_of,
    is_imperative,
    register,
    register_explain,
    sentences,
)

# --- PP101 ambiguous-directive ------------------------------------------------------
# Vague qualifiers that carry no concrete criterion. Only meaningful inside a directive.
_AMBIGUOUS = re.compile(
    r"\b(?:appropriately|properly|correctly"
    r"|as\s+needed|as\s+appropriate"
    r"|handle\s+it"
    r"|and\s+so\s+on|and\s+so\s+forth)\b"
    r"|\betc\.",  # trailing "." has no \b after it, so match it explicitly
    re.IGNORECASE,
)

# --- PP102 vague-quantifier ---------------------------------------------------------
# A vague quantifier immediately modifying a countable the model must produce, e.g.
# "give some examples". Require a PLURAL noun within ~3 tokens to stay precise.
_QUANTIFIER = re.compile(
    r"\b(?:some|several|a\s+few|many|most|a\s+lot\s+of|a\s+couple(?:\s+of)?)\b",
    re.IGNORECASE,
)
# A plural-ish noun: ends in a letter+s but not a typical -ss word; allow a couple of
# intervening words (adjectives) between quantifier and noun.
_PLURAL_AFTER = re.compile(
    r"^\s+(?:\w+\s+){0,2}([A-Za-z]+(?<![Ss])s)\b",
)

# --- PP103 unresolved-pronoun -------------------------------------------------------
# A sentence STARTING with a bare demonstrative/pronoun + a verb, with no noun before it
# in that same sentence (the sentence opener has nothing for the pronoun to refer to).
_PRONOUN_OPENER = re.compile(
    r"^(It|This|That|These|Those|They)\s+(\w+)",
)
# Common verbs / auxiliaries that signal "pronoun + verb" rather than "This <noun>".
_VERB_WORDS = (
    "is are was were be been being "
    "will would can could should may might must shall do does did has have had "
    "lets let makes make ensures ensure means mean allows allow requires require "
    "helps help shows show returns return causes cause gives give "
    "needs need uses use works work runs run handles handle prevents prevent"
)
_VERBS = set(_VERB_WORDS.split())

# --- PP104 subjective-criterion -----------------------------------------------------
# Acceptance worded only as a value judgement, with no measurable criterion nearby.
_SUBJECTIVE = re.compile(
    r"\b(?:good|nice|high[-\s]quality|better|best|appropriate|reasonable)\b",
    re.IGNORECASE,
)
# A measurable criterion somewhere on the same line defuses the finding: a number, a
# unit/limit word, or comparison/threshold vocabulary.
_MEASURABLE = re.compile(
    r"\b\d|\b(?:at\s+(?:least|most)|no\s+(?:more|less)|under|over|within|exactly"
    r"|chars?|characters?|words?|tokens?|lines?|bytes?|seconds?|ms|%|percent"
    r"|json|schema|regex|matches?|must\s+(?:equal|contain|match))\b",
    re.IGNORECASE,
)

# --- PP105 weak-modal ---------------------------------------------------------------
# A directive softened into an optional suggestion where a firm instruction is expected.
_WEAK_MODAL = re.compile(
    r"\b(?:try\s+to|maybe|perhaps|if\s+possible|ideally|when\s+convenient)\b",
    re.IGNORECASE,
)


def _body_prose_lines(doc: Document) -> list[tuple[int, str]]:
    """Body lines that are not inside a fenced code block, as (file_line, text)."""
    fenced = doc.fenced_lines()
    out = []
    for n, ln in doc.body_lines():
        if not ln.strip():
            continue
        if n in fenced:
            continue
        out.append((n, ln))
    return out


@register
class AmbiguousDirective(Rule):
    meta = RuleMeta(
        id="PP101",
        name="ambiguous-directive",
        category="clarity",
        summary="a directive relies on a vague qualifier with no concrete criterion",
        default_severity=Severity.WARNING,
        kinds=(),  # all kinds
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        for n, ln in _body_prose_lines(doc):
            if not is_imperative(ln):
                continue
            m = _AMBIGUOUS.search(ln)
            if not m:
                continue
            word = m.group(0)
            yield self.finding(
                doc,
                f'ambiguous directive: "{word}" gives the model no concrete criterion',
                line=n,
                col=col_of(ln, m),
                hint="name the concrete condition (what counts as done / correct)",
            )


@register
class VagueQuantifier(Rule):
    meta = RuleMeta(
        id="PP102",
        name="vague-quantifier",
        category="clarity",
        summary="a vague quantifier modifies a countable the model must produce",
        default_severity=Severity.INFO,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        for n, ln in _body_prose_lines(doc):
            for m in _QUANTIFIER.finditer(ln):
                tail = ln[m.end() :]
                noun = _PLURAL_AFTER.match(tail)
                if not noun:
                    continue
                phrase = m.group(0)
                yield self.finding(
                    doc,
                    f'vague quantifier: "{phrase} {noun.group(1)}" — state a number',
                    line=n,
                    col=col_of(ln, m),
                    hint=f"replace with an exact count, e.g. \"3 {noun.group(1)}\"",
                )
                break  # one finding per line is enough


@register
class UnresolvedPronoun(Rule):
    meta = RuleMeta(
        id="PP103",
        name="unresolved-pronoun",
        category="clarity",
        summary="a sentence opens on a pronoun with no antecedent in that sentence",
        default_severity=Severity.INFO,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        for n, ln in _body_prose_lines(doc):
            # Each sentence on the line is a candidate. A sentence that opens (after an
            # optional bullet/number prefix) on a bare pronoun + verb has nothing in it
            # for the pronoun to refer back to.
            for sent in sentences(ln):
                stripped = sent.lstrip("-*0123456789.) \t")
                m = _PRONOUN_OPENER.match(stripped)
                if not m:
                    continue
                if m.group(2).lower() not in _VERBS:
                    continue  # "This rule ..." (a noun follows) is fine
                pron = m.group(1)
                yield self.finding(
                    doc,
                    f'unresolved pronoun: "{pron}" opens the sentence with no antecedent',
                    line=n,
                    col=col_of(ln, pron),
                    hint="name the noun it refers to instead of the bare pronoun",
                )
                break  # one finding per line is enough


@register
class SubjectiveCriterion(Rule):
    meta = RuleMeta(
        id="PP104",
        name="subjective-criterion",
        category="clarity",
        summary="acceptance is worded as a value judgement with no measurable criterion",
        default_severity=Severity.INFO,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        for n, ln in _body_prose_lines(doc):
            m = _SUBJECTIVE.search(ln)
            if not m:
                continue
            if _MEASURABLE.search(ln):
                continue  # a concrete criterion is present on the line
            word = m.group(0)
            yield self.finding(
                doc,
                f'subjective criterion: "{word}" with no measurable bar',
                line=n,
                col=col_of(ln, m),
                hint="state a measurable criterion (a number, format, or check)",
            )


@register
class WeakModal(Rule):
    meta = RuleMeta(
        id="PP105",
        name="weak-modal",
        category="clarity",
        summary="an instruction is softened by a weak modal where a firm directive fits",
        default_severity=Severity.INFO,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        for n, ln in _body_prose_lines(doc):
            m = _WEAK_MODAL.search(ln)
            if not m:
                continue
            phrase = m.group(0)
            yield self.finding(
                doc,
                f'weak modal: "{phrase}" softens the instruction',
                line=n,
                col=col_of(ln, m),
                hint="use a firm directive (drop the hedge) if the step is required",
            )


register_explain(
    "PP101",
    """A directive qualified by a vague adverb tells the model to act but not how to know
it succeeded. The qualifier reads as guidance to a human and as noise to a model.

BAD  (no concrete criterion — what is "appropriately"?):
    Handle errors appropriately and format the output correctly.

GOOD (the condition is explicit and checkable):
    On a 4xx response, return {"error": <message>}; on 5xx, retry once then fail.
""",
)
register_explain(
    "PP102",
    """A vague quantifier in front of a countable the model must produce leaves the size of
the output undefined — you may get one item or twenty.

BAD  (how many is "some"?):
    Give some examples of valid inputs.

GOOD (state the number):
    Give exactly 3 examples of valid inputs.
""",
)
register_explain(
    "PP105",
    """A required step phrased as "try to" or "if possible" tells the model the step is
optional. If it is required, say so; if it is genuinely best-effort, keep the hedge.

BAD  (sounds optional):
    Try to validate the input before processing.

GOOD (firm directive):
    Validate the input before processing; reject it if validation fails.
""",
)

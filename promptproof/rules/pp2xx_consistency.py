"""Consistency rules (PP2xx) — internal contradictions in a single prompt asset.

A prompt that tells the model to "always cite sources" and later "never cite sources",
or to answer in both JSON and prose, sends mixed signals that surface as flaky agent
behavior. These rules look for *co-occurring* directives that pull in opposite
directions: contradictory always/never pairs (PP201), conflicting output formats
(PP202), conflicting length demands (PP203), and conflicting persona/tone (PP204).

Precision is paramount here — PP201 in particular is an ERROR, so it only fires when a
positive and a negative directive share a clear content word. The rest are scoped to
explicit format/length/persona vocabulary so they cannot trip on ordinary prose.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ..document import Document
from ..finding import Finding, Severity
from .base import Context, Rule, RuleMeta, col_of, register, register_explain

# --------------------------------------------------------------------------- PP201

# Positive (do-this) vs negative (don't-do-this) directive openers. We match the cue at
# a directive-ish position (line start, after a bullet, or after "you ").
_POS_CUE = re.compile(
    r"\b(always|must(?!\s+not)|require[ds]?|ensure[ds]?|make sure|do\b)",
    re.IGNORECASE,
)
_NEG_CUE = re.compile(
    r"\b(never|must not|must n't|mustn't|do not|don't|do n't|avoid)",
    re.IGNORECASE,
)

# Words that carry no object meaning — never count as the shared "target".
_STOPWORDS = frozenset(
    """
    the a an and or but for nor yet so to of in on at by with from into onto over under
    this that these those your you our their its it them they we us my his her
    always never must require requires required ensure ensures ensured avoid only also
    make sure ensure should shall will would could can may might please kindly
    when while where which what whom whose how why then than else such each every any all
    some most more less very much many few both either neither out off up down here there
    about above below after before during through between against without within along
    being been have has had does did done doing using used use uses user users
    response responses answer answers reply replies output outputs result results
    """.split()
)

# A directive line must look like an instruction, not narration; require the cue to sit
# near the front of the line (allowing a leading bullet / number / "you ").
_LINE_LEAD = re.compile(r"^\s*(?:[-*]\s+|\d+[.)]\s+)?(?:you\s+(?:must|should|will|are)?\s*)?", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _singular(word: str) -> str:
    """Crude singularization so "files"/"file" and "policies"/"policy" line up."""
    base = word.strip("'-")
    if base.endswith("ies") and len(base) > 4:
        return base[:-3] + "y"
    if base.endswith("ses") and len(base) > 4:
        return base[:-2]
    if base.endswith("s") and not base.endswith("ss") and len(base) > 4:
        return base[:-1]
    return base


# Function words that never count as the directive's head verb.
_NOT_VERB = frozenset(
    """
    you your the a an to that it is are be been being this these those they them we our us
    always never not must should will would do does make sure ensure please also only and
    or but for of in on at by with from when if then than as
    """.split()
)


def _directive_parts(line: str, cue: re.Pattern[str]) -> tuple[str, set[str]] | None:
    """(head_verb, object_tokens) for the directive at ``cue``, or None.

    The head verb is the first real word after the cue; object tokens are the salient
    content words after it. Two directives only contradict when they share BOTH the same
    action verb AND an object — sharing a noun alone (include the file / modify the file)
    is not a contradiction.
    """
    m = cue.search(line)
    if not m:
        return None
    verb: str | None = None
    obj: set[str] = set()
    for w in _WORD.findall(line[m.end() :].lower()):
        if verb is None:
            if len(w) >= 3 and w not in _NOT_VERB:
                verb = _singular(w)
            continue
        base = _singular(w)
        if len(base) > 3 and base not in _STOPWORDS:
            obj.add(base)
    return (verb, obj) if verb else None


def _directive_lines(doc: Document, cue: re.Pattern[str]) -> list[tuple[int, str]]:
    """Body lines whose directive head matches ``cue`` (positive or negative)."""
    hits: list[tuple[int, str]] = []
    for n, ln in doc.body_lines():
        if not ln.strip():
            continue
        if n in doc.fenced_lines():
            continue
        # only consider the cue when it appears in the instruction head region
        head_end = _LINE_LEAD.match(ln)
        # search the whole line, but the cue must be reasonably early to be a directive
        m = cue.search(ln)
        if m and m.start() <= (head_end.end() if head_end else 0) + 24:
            hits.append((n, ln))
    return hits


@register
class ContradictoryDirective(Rule):
    meta = RuleMeta(
        id="PP201",
        name="contradictory-directive",
        category="consistency",
        summary="a positive (always/must) and a negative (never/don't) directive target one thing",
        default_severity=Severity.ERROR,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        neg = _directive_lines(doc, _NEG_CUE)
        if not neg:
            return
        neg_lines = {n for n, _ in neg}
        # A "do not" line also matches the positive `do` cue — negatives win, so a line is
        # only "positive" when it does not also carry a negative cue.
        pos = [(n, ln) for n, ln in _directive_lines(doc, _POS_CUE) if n not in neg_lines]
        if not pos:
            return
        pos_parts = [(n, ln, _directive_parts(ln, _POS_CUE)) for n, ln in pos]
        neg_parts = [(n, ln, _directive_parts(ln, _NEG_CUE)) for n, ln in neg]
        for pn, pln, pp in pos_parts:
            if pp is None:
                continue
            pverb, pobj = pp
            for nn, nln, npart in neg_parts:
                if npart is None or pn == nn:
                    continue
                nverb, nobj = npart
                shared = pobj & nobj
                if pverb == nverb and shared:
                    word = sorted(shared)[0]
                    lo, hi = sorted((pn, nn))
                    col = col_of(pln, pverb) if pn == lo else col_of(nln, nverb)
                    yield self.finding(
                        doc,
                        f"contradictory directive: '{pverb} ... {word}' is both required "
                        f"and forbidden (lines {lo} and {hi})",
                        line=lo,
                        col=col or 1,
                        hint="reconcile the two instructions — keep one, qualify or drop the other",
                    )
                    return  # one finding per doc; this is ERROR, don't pile on


# --------------------------------------------------------------------------- PP202

# Output-context cue: a format demand is only meaningful near an output verb.
_OUTPUT_CUE = re.compile(
    r"\b(respond|responses?|output|return|format(?:ted)?|reply|repl(?:y|ies)|answer"
    r"|print|write)\b",
    re.IGNORECASE,
)

# An input/ingest context: a format named near these words describes data the model
# RECEIVES, not what it must produce — so it is never a conflicting *output* demand.
_INPUT_GUARD = re.compile(
    r"\b(input|accepts?|accepting|incoming|receiv\w*|ingest\w*|upload\w*|parse[ds]?"
    r"|parsing|given|provided\s+(?:by|as)|the\s+user\s+(?:provides|sends|gives|supplies))\b",
    re.IGNORECASE,
)

# Each format -> the regex that detects it. Order matters only for message stability.
_FORMAT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("json", re.compile(r"\bjson\b", re.I)),
    ("yaml", re.compile(r"\bya?ml\b", re.I)),
    ("xml", re.compile(r"\bxml\b", re.I)),
    ("csv", re.compile(r"\bcsv\b", re.I)),
    ("markdown table", re.compile(r"\bmarkdown\s+table\b|\btable\s+in\s+markdown\b", re.I)),
    ("bullet list", re.compile(r"\bbullet(?:ed)?\s+(?:list|points?)\b|\bbullet\s*points?\b", re.I)),
    ("plain text", re.compile(r"\bplain\s+text\b|\bplaintext\b", re.I)),
    ("prose", re.compile(r"\b(?:prose|paragraphs?|full\s+sentences?)\b", re.I)),
)

# Formats that genuinely conflict if demanded together. Markdown table / bullet list /
# prose can coexist with each other in many prompts, so we only flag *structured data*
# formats against each other and against prose/plain-text.
_STRUCTURED = frozenset({"json", "yaml", "xml", "csv"})
_FREEFORM = frozenset({"plain text", "prose"})


def _format_demands(doc: Document) -> dict[str, tuple[int, int]]:
    """Map each demanded format -> (line, col) of its first mention near an output verb."""
    found: dict[str, tuple[int, int]] = {}
    for n, ln in doc.body_lines():
        if not ln.strip() or n in doc.fenced_lines():
            continue
        if not _OUTPUT_CUE.search(ln) or _INPUT_GUARD.search(ln):
            continue
        for label, pat in _FORMAT_PATTERNS:
            m = pat.search(ln)
            if m and label not in found:
                found[label] = (n, m.start() + 1)
    return found


def _formats_conflict(labels: set[str]) -> bool:
    structured = labels & _STRUCTURED
    freeform = labels & _FREEFORM
    # two different structured serializations is a conflict (json AND yaml)
    if len(structured) >= 2:
        return True
    # a structured serialization plus a freeform demand is a conflict (json AND prose)
    if structured and freeform:
        return True
    # two distinct freeform demands (plain text AND prose) — mild but still conflicting
    if len(freeform) >= 2:
        return True
    return False


@register
class ConflictingFormat(Rule):
    meta = RuleMeta(
        id="PP202",
        name="conflicting-format",
        category="consistency",
        summary="two incompatible output-format demands (e.g. JSON and prose)",
        default_severity=Severity.WARNING,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        demands = _format_demands(doc)
        labels = set(demands)
        if len(labels) < 2 or not _formats_conflict(labels):
            return
        # report at the earliest-mentioned conflicting format
        ordered = sorted(demands.items(), key=lambda kv: (kv[1][0], kv[1][1]))
        names = ", ".join(label for label, _ in ordered)
        line, col = ordered[0][1]
        yield self.finding(
            doc,
            f"conflicting output formats demanded: {names}",
            line=line,
            col=col,
            hint="pick a single output format; move alternates to separate modes/examples",
        )


# --------------------------------------------------------------------------- PP203

_BREVITY_CUE = re.compile(
    r"\b(brief|briefly|concise|concisely|short|shorter|terse|succinct|tl;?dr"
    r"|one\s+sentence|single\s+sentence|keep\s+it\s+short|in\s+a\s+few\s+words)\b",
    re.IGNORECASE,
)
_VERBOSITY_CUE = re.compile(
    r"\b(detailed|in\s+detail|thorough(?:ly)?|comprehensive(?:ly)?|exhaustive(?:ly)?"
    r"|in[-\s]depth|step[-\s]by[-\s]step|elaborate|as\s+much\s+detail|very\s+detailed"
    r"|extensive(?:ly)?|at\s+length)\b",
    re.IGNORECASE,
)


def _first_cue(doc: Document, pat: re.Pattern[str]) -> tuple[int, int, str] | None:
    for n, ln in doc.body_lines():
        if not ln.strip() or n in doc.fenced_lines():
            continue
        m = pat.search(ln)
        if m:
            return n, m.start() + 1, m.group(0)
    return None


def _all_cues(doc: Document, pat: re.Pattern[str]) -> list[tuple[int, int, str]]:
    fenced = doc.fenced_lines()
    hits: list[tuple[int, int, str]] = []
    for n, ln in doc.body_lines():
        if not ln.strip() or n in fenced:
            continue
        for m in pat.finditer(ln):
            hits.append((n, m.start() + 1, m.group(0)))
    return hits


@register
class ConflictingLength(Rule):
    meta = RuleMeta(
        id="PP203",
        name="conflicting-length",
        category="consistency",
        summary="a brevity cue and a verbosity cue both appear in the same asset",
        default_severity=Severity.WARNING,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        brevity = _all_cues(doc, _BREVITY_CUE)
        verbosity = _all_cues(doc, _VERBOSITY_CUE)
        if not brevity or not verbosity:
            return
        # Only a conflict when the two demands are CLOSE — a "be brief" in one section and a
        # "be thorough" in another (about different artifacts) is not a contradiction.
        prox = ctx.threshold("conflict_proximity_lines", 4)
        best: tuple[int, int, int, str, int, str, int] | None = None
        for bn, bc, bword in brevity:
            for vn, vc, vword in verbosity:
                if (bn, bc) == (vn, vc) or abs(bn - vn) > prox:
                    continue
                lo_line, lo_col = (bn, bc) if (bn, bc) <= (vn, vc) else (vn, vc)
                cand = (abs(bn - vn), lo_line, lo_col, bword, bn, vword, vn)
                if best is None or cand < best:
                    best = cand
        if best is None:
            return
        _, lo_line, lo_col, bword, bn, vword, vn = best
        yield self.finding(
            doc,
            f"conflicting length demands: '{bword}' (line {bn}) vs '{vword}' (line {vn})",
            line=lo_line,
            col=lo_col,
            hint="choose one length target; brevity and exhaustive detail pull apart",
        )


# --------------------------------------------------------------------------- PP204

_ROLE_DECL = re.compile(
    r"\byou\s+are\s+(?:an?\s+)?([a-z][a-z /-]{2,40}?)"
    r"(?=[.,;:\n]|\s+(?:that|who|which|and|with|specialized|specializing|expert\b)|$)",
    re.IGNORECASE,
)
_FORMAL_CUE = re.compile(r"\b(formal|professional|polished|business-?like)\b", re.IGNORECASE)
_CASUAL_CUE = re.compile(
    r"\b(casual|playful|fun|informal|chatty|relaxed|laid-?back|breezy)\b", re.IGNORECASE
)

# Words that, as a captured "role", are too generic to count as a distinct persona on
# their own (so a single "you are a helpful assistant" never pairs with itself, and
# common filler doesn't masquerade as a second role).
_ROLE_FILLER = frozenset(
    {"helpful", "an", "a", "the", "very", "highly", "here", "able", "going", "now"}
)


def _normalize_role(raw: str) -> str:
    words = [w for w in re.split(r"[\s/-]+", raw.strip().lower()) if w]
    # drop leading generic adjectives ("helpful", "friendly") to compare the head noun
    while words and words[0] in _ROLE_FILLER:
        words.pop(0)
    return " ".join(words)


@register
class ConflictingPersona(Rule):
    meta = RuleMeta(
        id="PP204",
        name="conflicting-persona",
        category="consistency",
        summary="two different role declarations, or a formal-vs-casual tone clash",
        default_severity=Severity.INFO,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        # 1) distinct "You are a/an <role>" declarations
        roles: list[tuple[int, int, str, str]] = []  # (line, col, normalized, raw)
        for n, ln in doc.body_lines():
            if not ln.strip() or n in doc.fenced_lines():
                continue
            for m in _ROLE_DECL.finditer(ln):
                raw = m.group(1).strip(" .,/-")
                norm = _normalize_role(raw)
                if norm and norm not in _ROLE_FILLER:
                    roles.append((n, m.start(1) + 1, norm, raw))
        distinct = {norm for _, _, norm, _ in roles}
        if len(distinct) >= 2:
            (l1, c1, n1, r1), (_, _, _, r2) = self._two_distinct(roles)
            yield self.finding(
                doc,
                f"conflicting persona: declared as both '{r1}' and '{r2}'",
                line=l1,
                col=c1,
                hint="declare a single role; pick the persona that best fits the task",
            )
            return

        # 2) formal vs casual tone clash
        formal = _first_cue(doc, _FORMAL_CUE)
        casual = _first_cue(doc, _CASUAL_CUE)
        if formal and casual:
            fn, fc, fword = formal
            cn, cc, cword = casual
            lo_line, lo_col = (fn, fc) if (fn, fc) <= (cn, cc) else (cn, cc)
            yield self.finding(
                doc,
                f"conflicting tone: '{fword}' and '{cword}' both requested",
                line=lo_line,
                col=lo_col,
                hint="pick one register — formal or casual — to keep the voice consistent",
            )

    @staticmethod
    def _two_distinct(
        roles: list[tuple[int, int, str, str]],
    ) -> tuple[tuple[int, int, str, str], tuple[int, int, str, str]]:
        first = roles[0]
        for r in roles[1:]:
            if r[2] != first[2]:
                return first, r
        return first, first  # unreachable when len(distinct) >= 2


register_explain(
    "PP201",
    """Contradictory always/never directives about the same object make agent behavior
non-deterministic — the model can satisfy either reading and you cannot predict which.

BAD  (the same object is both required and forbidden):
    Always include the file path in your output.
    Never include the file path; keep it implicit.

GOOD (one consistent rule):
    Always include the file path in your output.
""",
)
register_explain(
    "PP202",
    """Demanding two incompatible output formats forces the model to guess, and the guess
varies run to run.

BAD:
    Respond in JSON. Also answer in plain prose so it's readable.

GOOD:
    Respond in JSON. (If you need prose, put it in a "summary" string field.)
""",
)
register_explain(
    "PP203",
    """"Be concise" and "be exhaustive" can't both be the target. Pick one; if you mean
"short but complete", say "cover every case in <= N sentences".

BAD:
    Keep your answer brief. Provide a thorough, step-by-step explanation.

GOOD:
    Give a concise answer: the decision plus one supporting sentence.
""",
)

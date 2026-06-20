"""Economy rules (PP3xx) — make the prompt cheaper without losing meaning.

Tokens are budget. Courtesy padding, wordy connectives, restated sentences, walls of
text, oversized bodies, and decorative ASCII/emoji banners all cost context for no signal.
Every rule here is deterministic and string/structural only — no model, no network.

These checks operate on ``doc.body`` (frontmatter is graded by the structure rules) and
favour precision: heuristics that could plausibly fire on legitimate prose are kept narrow,
emitted at most once per line, or gated behind a config threshold.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable

from ..document import DocKind, Document
from ..finding import Finding, Severity
from .base import (
    Context,
    Rule,
    RuleMeta,
    col_of,
    register,
    register_explain,
    sentences,
)

# --------------------------------------------------------------------------- patterns

# PP301: courtesy filler aimed at the model.
_POLITENESS = re.compile(
    r"\b("
    r"please"
    r"|kindly"
    r"|thank you"
    r"|thanks"
    r"|if you (?:would|could|don't mind)"
    r"|I would like you to"
    r"|I want you to"
    r"|could you(?: please)?"
    r")\b",
    re.IGNORECASE,
)

# PP302: wordy phrase -> shorter form. Order longest-first so the broad
# "due to the fact that" / "it is important to note that" win over substrings.
_FILLER_REWRITES: tuple[tuple[str, str], ...] = (
    ("it is important to note that", 'drop it, or just say "note:"'),
    ("at the end of the day", "drop it — it adds no instruction"),
    ("as a matter of fact", "drop it — it adds no instruction"),
    ("due to the fact that", 'replace with "because"'),
    ("please note that", 'drop it, or just say "note:"'),
    ("needless to say", "drop it — if needless, omit it"),
    ("in order to", 'replace with "to"'),
)
_FILLER = re.compile(
    "|".join(rf"\b{re.escape(phrase)}\b" for phrase, _ in _FILLER_REWRITES),
    re.IGNORECASE,
)
_REWRITE_BY_PHRASE = {phrase: rewrite for phrase, rewrite in _FILLER_REWRITES}

# PP306: decorative banners.
# A run of pure box-art / rule characters (no letters or digits at all).
_BANNER_CHARS = re.compile(r"^[\s#=*_~.\-–—•·░▒▓█|]+$")
# A markdown table separator row, e.g. |---|:--:|---| or --- | --- .
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")
# Emoji codepoint ranges (stdlib only; covers the common pictographic blocks).
_EMOJI = re.compile(
    "["
    "\U0001f300-\U0001faff"  # symbols, pictographs, supplemental, extended-A
    "\U00002600-\U000027bf"  # misc symbols + dingbats
    "\U0001f000-\U0001f0ff"  # mahjong/dominoes/cards
    "\U00002b00-\U00002bff"  # arrows/stars (e.g. ⭐ ✨ via 2700 block too)
    "\U0001f1e6-\U0001f1ff"  # regional indicators (flags)
    "\U0000fe00-\U0000fe0f"  # variation selectors
    "\U00002190-\U000021ff"  # arrows
    "]"
)

# Quoted spans: courtesy words inside quotes/backticks are usually UX copy the model must
# emit verbatim, not an instruction to the model — PP301 skips matches inside them.
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'|`[^`]*`")


def _within_quotes(text: str, idx: int) -> bool:
    return any(s <= idx < e for s, e in (m.span() for m in _QUOTED.finditer(text)))


# ----------------------------------------------------------------------- PP301

@register
class PolitenessPadding(Rule):
    meta = RuleMeta(
        id="PP301",
        name="politeness-padding",
        category="economy",
        summary="courtesy filler ('please', 'thank you') that models don't need",
        default_severity=Severity.WARNING,
        kinds=(),  # all kinds
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        if ctx.threshold("economy.allow_politeness", False):
            return
        for lineno, text in doc.body_lines():
            if not text.strip() or text.lstrip().startswith(">"):
                continue  # blockquotes are usually quoted copy, not directives
            m = _POLITENESS.search(text)
            if not m:
                continue
            if _within_quotes(text, m.start()):
                continue  # courtesy word sits inside quoted UX copy the model emits
            snippet = m.group(0)
            yield self.finding(
                doc,
                f"politeness padding: \"{snippet}\" — models don't need courtesy",
                line=lineno,
                col=col_of(text, m),
                hint="drop it; imperatives are clearer to models",
            )


# ----------------------------------------------------------------------- PP302

@register
class FillerPhrase(Rule):
    meta = RuleMeta(
        id="PP302",
        name="filler-phrase",
        category="economy",
        summary="wordy connective with a shorter equivalent",
        default_severity=Severity.WARNING,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        for lineno, text in doc.body_lines():
            if not text.strip():
                continue
            m = _FILLER.search(text)
            if not m:
                continue
            phrase = m.group(0).lower()
            rewrite = _REWRITE_BY_PHRASE.get(phrase)
            if rewrite is None:
                # regex matched on a phrase whose lowercase key differs only by
                # interior whitespace; fall back to the first phrase contained.
                for key, val in _REWRITE_BY_PHRASE.items():
                    if key in phrase:
                        rewrite = val
                        break
            yield self.finding(
                doc,
                f"filler phrase: \"{m.group(0)}\"",
                line=lineno,
                col=col_of(text, m),
                hint=rewrite or "shorten or drop it",
            )


# ----------------------------------------------------------------------- PP303

@register
class RedundantRestatement(Rule):
    meta = RuleMeta(
        id="PP303",
        name="redundant-restatement",
        category="economy",
        summary="a body sentence nearly duplicates an earlier one",
        default_severity=Severity.WARNING,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        threshold = ctx.threshold("redundant_similarity", 0.92)
        # Compare only reasonably long sentences, and only against a bounded window of
        # recent ones — redundant restatements sit near each other, and an all-pairs scan
        # is O(n^2) (a CI linter must terminate quickly on large files).
        window = 30
        # Bound the work: fuzzy sentence comparison is inherently superlinear, so cap how
        # many sentences this minor economy rule scans. A prompt with >800 long sentences
        # is far past any sane budget; PP305/PP304 already flag oversized bodies.
        max_sents = ctx.threshold("redundant_max_sentences", 800)
        candidates = [s for s in sentences(doc.body) if len(s) >= 25][:max_sents]
        seen: list[tuple[str, str]] = []  # (original, normalized)
        for sent in candidates:
            norm = _normalize(sent)
            dup = False
            for _, prev_norm in seen[-window:]:
                sm = difflib.SequenceMatcher(None, prev_norm, norm)
                # cheap O(1)/O(n) upper bounds prune mismatches before the O(n^2) ratio()
                if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
                    continue
                if sm.ratio() < threshold:
                    continue
                # Parallel templates that differ ONLY by numbers ("on 400 retry" / "on 500
                # fail") are intentional, not redundant — but exact repeats still count.
                if norm != prev_norm and _strip_digits(prev_norm) == _strip_digits(norm):
                    continue
                dup = True
                break
            if dup:
                line, col = _locate(doc, sent)
                yield self.finding(
                    doc,
                    "redundant restatement: sentence nearly duplicates an earlier one",
                    line=line,
                    col=col,
                    hint="remove the duplicate",
                )
            else:
                seen.append((sent, norm))


# ----------------------------------------------------------------------- PP304

@register
class WallOfText(Rule):
    meta = RuleMeta(
        id="PP304",
        name="wall-of-text",
        category="economy",
        summary="a single paragraph is too long to skim",
        default_severity=Severity.INFO,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        limit = ctx.threshold("wall_of_text_chars", 1200)
        para_start: int | None = None
        para_len = 0
        for lineno, text in doc.body_lines():
            if text.strip():
                if para_start is None:
                    para_start = lineno
                    para_len = 0
                para_len += len(text)
            else:
                if para_start is not None and para_len > limit:
                    yield self.finding(
                        doc,
                        f"wall of text: paragraph is {para_len:,} chars (limit {limit:,})",
                        line=para_start,
                        hint="break into bullets/sections",
                    )
                para_start = None
                para_len = 0
        if para_start is not None and para_len > limit:
            yield self.finding(
                doc,
                f"wall of text: paragraph is {para_len:,} chars (limit {limit:,})",
                line=para_start,
                hint="break into bullets/sections",
            )


# ----------------------------------------------------------------------- PP305

@register
class TokenBudget(Rule):
    meta = RuleMeta(
        id="PP305",
        name="token-budget",
        category="economy",
        summary="body token estimate exceeds the configured budget",
        default_severity=Severity.WARNING,
        kinds=(DocKind.SKILL, DocKind.SUBAGENT, DocKind.PROMPT),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        budget = ctx.threshold(f"token_budget.{doc.kind.value}", 0)
        if not isinstance(budget, int) or budget <= 0:
            return
        est = ctx.estimate_tokens(doc.body)
        if est <= budget:
            return
        pct = round((est - budget) / budget * 100)
        yield self.finding(
            doc,
            f"token budget: body ~{est:,} tokens, {pct}% over budget ({budget:,})",
            line=0,
            hint="trim the body or raise token_budget in config",
        )


# ----------------------------------------------------------------------- PP306

@register
class DecorativeBanner(Rule):
    meta = RuleMeta(
        id="PP306",
        name="decorative-banner",
        category="economy",
        summary="an ASCII/box-art or emoji banner line that only wastes tokens",
        default_severity=Severity.WARNING,
        kinds=(),
    )

    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]:
        fenced = doc.fenced_lines()
        for lineno, text in doc.body_lines():
            stripped = text.strip()
            if not stripped:
                continue
            if lineno in fenced:
                continue
            if _TABLE_SEP.match(text):
                continue
            if not self._is_banner(stripped):
                continue
            yield self.finding(
                doc,
                "decorative banner wastes tokens",
                line=lineno,
                col=col_of(text, stripped),
                hint="remove decorative banners; they waste tokens",
            )

    @staticmethod
    def _is_banner(stripped: str) -> bool:
        # 0) a pure run of markdown structural chars is valid markdown, not decoration:
        # thematic break (---/***/___), setext heading underline (===/---), emphasis,
        # or an alternate ~~~ code fence. Never flag these.
        non_space = [c for c in stripped if not c.isspace()]
        if non_space and set(non_space) <= {"-", "=", "*", "_", "~"}:
            return False
        # 1) pure box-art / rule characters, reasonably long.
        if len(stripped) >= 12 and _BANNER_CHARS.match(stripped):
            return True
        # 2) a line that is >=80% a single repeated punctuation char.
        if len(stripped) >= 12:
            non_space = [c for c in stripped if not c.isspace()]
            if non_space:
                top = max(non_space, key=non_space.count)
                if (
                    not top.isalnum()
                    and non_space.count(top) / len(non_space) >= 0.80
                ):
                    return True
        # 3) an all-emoji line with >= 6 emoji glyphs.
        emojis = _EMOJI.findall(stripped)
        if len(emojis) >= 6:
            # ensure the line is essentially just emoji (allow whitespace/sep).
            residue = _EMOJI.sub("", stripped)
            if not re.search(r"[A-Za-z0-9]", residue):
                return True
        return False


# --------------------------------------------------------------------------- helpers

_WS = re.compile(r"\s+")
_DIGITS = re.compile(r"\d+")


def _normalize(sentence: str) -> str:
    """Lowercase + collapse whitespace, for stable near-duplicate comparison."""
    return _WS.sub(" ", sentence.strip().lower())


def _strip_digits(sentence: str) -> str:
    return _DIGITS.sub("", sentence)


def _locate(doc: Document, sentence: str) -> tuple[int, int]:
    """Best-effort (line, col) for a body sentence's first words."""
    needle = sentence.split("\n", 1)[0][:30].strip()
    if not needle:
        return 0, 0
    for lineno, text in doc.body_lines():
        col = col_of(text, needle)
        if col:
            return lineno, col
    return 0, 0


# --------------------------------------------------------------------------- explain

register_explain(
    "PP301",
    """Models don't need politeness; courtesy words add tokens and dilute the directive.

BAD:
    Please could you carefully summarize the document, thank you.

GOOD:
    Summarize the document.
""",
)
register_explain(
    "PP302",
    """Wordy connectives have shorter equivalents that say exactly the same thing.

BAD:
    Due to the fact that the file is large, in order to save memory, stream it.

GOOD:
    Because the file is large, stream it to save memory.
""",
)
register_explain(
    "PP306",
    """ASCII/box-art and emoji banners are pure decoration: they cost tokens and carry no
instruction. agentskills.io discourages them.

BAD:
    ============================================
    ##############  SECTION 2  ##################
    ============================================

GOOD:
    ## Section 2
""",
)

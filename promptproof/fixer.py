"""Apply the mechanical repairs attached to findings.

The conservative half of ``--fix``. A rule attaches an :class:`~promptproof.finding.Edit`
only when the repair is unambiguous — deleting a decorative banner, dropping a courtesy
word, replacing "in order to" with "to". Anything that requires knowing what the author
*meant* stays a hint for a human.

Two properties make this safe to run over someone's prompt library:

* **No overlaps.** Edits are applied bottom-up and any edit touching a line an earlier
  edit already claimed is skipped, so two rules can never interleave on one line.
* **Convergence.** Several rules report at most one match per line, so removing one filler
  phrase can reveal another. :func:`fix_text` re-lints and re-applies until nothing
  changes, bounded by :data:`MAX_PASSES` so a pathological rule pair can't spin forever.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .document import DocKind, Document
from .engine import lint_document
from .finding import Finding

#: Upper bound on fix/re-lint rounds. Reaching it means a rule pair is oscillating.
MAX_PASSES = 5


@dataclass(frozen=True)
class FixResult:
    """What one file's fix run did."""

    text: str
    #: Findings whose edits were applied, oldest pass first.
    applied: tuple[Finding, ...]
    #: Findings still present after fixing (what the reporter should show).
    remaining: tuple[Finding, ...]
    passes: int

    @property
    def changed(self) -> bool:
        return bool(self.applied)


def apply_edits(lines: list[str], findings: list[Finding]) -> tuple[list[str], list[Finding]]:
    """Apply every non-overlapping edit to ``lines``; return the new lines and what applied.

    Edits are applied from the bottom of the file upward so earlier line numbers stay
    valid as the text shifts. Findings without a fix are ignored.
    """
    fixable = [f for f in findings if f.fix is not None]
    if not fixable:
        return lines, []

    # Bottom-up. Ties break on rule id so the choice between two edits on the same line
    # is deterministic rather than dependent on rule registration order.
    fixable.sort(key=lambda f: (-f.fix.start_line, f.rule))  # type: ignore[union-attr]

    out = list(lines)
    applied: list[Finding] = []
    claimed: set[int] = set()
    for finding in fixable:
        edit = finding.fix
        assert edit is not None
        if edit.start_line < 1 or edit.end_line > len(lines) or edit.end_line < edit.start_line:
            continue  # a rule computed a span that doesn't exist; refuse rather than guess
        span = range(edit.start_line, edit.end_line + 1)
        if any(line in claimed for line in span):
            continue  # another rule already rewrote these lines this pass
        claimed.update(span)
        out[edit.start_line - 1 : edit.end_line] = list(edit.replacement)
        applied.append(finding)
    return out, applied


def fix_text(
    text: str,
    *,
    path: str = "<text>",
    kind: DocKind | None = None,
    config: Config | None = None,
) -> FixResult:
    """Repeatedly lint and apply fixes until the text stops changing."""
    current = text
    applied: list[Finding] = []
    passes = 0
    findings = lint_document(Document.from_text(current, path=path, kind=kind), config)

    for _ in range(MAX_PASSES):
        doc = Document.from_text(current, path=path, kind=kind)
        findings = lint_document(doc, config)
        new_lines, just_applied = apply_edits(list(doc.lines), findings)
        if not just_applied:
            break
        passes += 1
        applied.extend(just_applied)
        # Preserve whether the original ended with a newline; joining alone would drop it.
        current = "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")
        findings = lint_document(Document.from_text(current, path=path, kind=kind), config)

    return FixResult(
        text=current,
        applied=tuple(applied),
        remaining=tuple(findings),
        passes=passes,
    )


def fix_file(
    path: str, *, kind: DocKind | None = None, config: Config | None = None, write: bool = True
) -> FixResult:
    """Fix one file in place. With ``write=False`` nothing is written (the ``--diff`` path)."""
    with open(path, encoding="utf-8") as fh:
        original = fh.read()
    result = fix_text(original, path=path, kind=kind, config=config)
    if write and result.text != original:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(result.text)
    return result


__all__ = ["FixResult", "MAX_PASSES", "apply_edits", "fix_text", "fix_file"]

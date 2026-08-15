"""A baseline file: accept today's findings, fail only on new ones.

Adopting a linter on an existing prompt library means a first run with hundreds of
findings and no way to gate CI until they're all fixed. A baseline records what is
already there so the build goes green immediately and stays honest about anything added
afterwards.

The design constraint is **stability under edits**. Keying a baseline entry on a line
number makes it useless the moment anyone inserts a paragraph: every finding below the
insertion looks new. Entries are therefore keyed on the *content* that triggered them —
path, rule, and a hash of the offending line — so a finding survives being moved and a
genuinely new one does not match.

Counts are kept per key, so three identical findings can be baselined and a fourth still
surfaces.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Iterable

from .finding import Finding

#: Bumped when the entry format changes so a stale file is rejected, not misread.
FORMAT_VERSION = 1

DEFAULT_BASELINE_PATH = ".promptproof-baseline.json"


class BaselineError(Exception):
    """The baseline file is missing, malformed, or from an incompatible version."""


def _source_line(finding: Finding, lines: list[str] | None) -> str:
    """The text that triggered the finding, or the message for whole-file findings."""
    line = finding.location.line
    if lines and 1 <= line <= len(lines):
        return " ".join(lines[line - 1].split())
    # Whole-file findings (line 0) have no source text; the message is the next most
    # stable thing about them, and it does not move when the file is edited.
    return finding.message


def fingerprint(finding: Finding, lines: list[str] | None = None) -> str:
    """A stable key for one finding: path + rule + the content that triggered it.

    Deliberately excludes the line and column. A finding that moves down the file is the
    same finding; one whose triggering text changed is a different one.
    """
    payload = "\x1f".join(
        [
            finding.location.path.replace("\\", "/"),
            finding.rule,
            _source_line(finding, lines),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _file_lines(path: str, cache: dict[str, list[str] | None]) -> list[str] | None:
    if path not in cache:
        try:
            with open(path, encoding="utf-8") as fh:
                cache[path] = fh.read().splitlines()
        except OSError:
            cache[path] = None
    return cache[path]


def fingerprints(findings: Iterable[Finding]) -> Counter[str]:
    """Count fingerprints for ``findings``, reading each file at most once."""
    cache: dict[str, list[str] | None] = {}
    return Counter(
        fingerprint(f, _file_lines(f.location.path, cache)) for f in findings
    )


class Baseline:
    """A recorded set of accepted findings."""

    def __init__(self, counts: Counter[str] | None = None) -> None:
        self.counts: Counter[str] = Counter(counts or {})

    def __len__(self) -> int:
        return sum(self.counts.values())

    @classmethod
    def from_findings(cls, findings: Iterable[Finding]) -> Baseline:
        return cls(fingerprints(findings))

    @classmethod
    def load(cls, path: str) -> Baseline:
        """Read a baseline file. Raises :class:`BaselineError` on anything unusable.

        A silently-empty baseline would turn a gate green for the wrong reason, so every
        failure here is loud.
        """
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError as exc:
            raise BaselineError(
                f"no baseline at {path}; create one with --write-baseline"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise BaselineError(f"could not read baseline {path}: {exc}") from exc

        if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
            found = data.get("version") if isinstance(data, dict) else "?"
            raise BaselineError(
                f"baseline {path} has version {found}, expected {FORMAT_VERSION}; "
                "regenerate it with --write-baseline"
            )
        entries = data.get("findings")
        if not isinstance(entries, dict):
            raise BaselineError(f"baseline {path} has no 'findings' object")
        counts: Counter[str] = Counter()
        for key, count in entries.items():
            if isinstance(key, str) and isinstance(count, int) and count > 0:
                counts[key] = count
        return cls(counts)

    def save(self, path: str, findings: Iterable[Finding]) -> int:
        """Write ``findings`` as the new baseline; returns how many were recorded."""
        counts = fingerprints(findings)
        payload = {
            "version": FORMAT_VERSION,
            "note": (
                "Generated by `promptproof --write-baseline`. Entries are keyed on file "
                "content, not line numbers, so they survive edits elsewhere in the file. "
                "Commit this file; regenerate it after fixing findings."
            ),
            "findings": dict(sorted(counts.items())),
        }
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=False)
            fh.write("\n")
        self.counts = counts
        return sum(counts.values())

    def filter(self, findings: list[Finding]) -> tuple[list[Finding], int]:
        """Drop baselined findings; return ``(new_findings, suppressed_count)``.

        With three identical findings baselined and four present, one is returned — the
        baseline accepts a known quantity of a problem, not the problem forever.
        """
        cache: dict[str, list[str] | None] = {}
        budget = Counter(self.counts)
        fresh: list[Finding] = []
        suppressed = 0
        for finding in findings:
            key = fingerprint(finding, _file_lines(finding.location.path, cache))
            if budget[key] > 0:
                budget[key] -= 1
                suppressed += 1
            else:
                fresh.append(finding)
        return fresh, suppressed


__all__ = [
    "Baseline",
    "BaselineError",
    "DEFAULT_BASELINE_PATH",
    "FORMAT_VERSION",
    "fingerprint",
    "fingerprints",
]

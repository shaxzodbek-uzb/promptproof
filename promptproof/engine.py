"""The lint engine: turn paths/text into a sorted list of findings.

Responsibilities: file discovery, building Documents, selecting applicable rules,
running them defensively (a buggy rule can never crash a run), applying severity
overrides and inline suppressions, and sorting the result.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from dataclasses import replace

from .config import Config
from .document import DocKind, Document
from .finding import Finding, Location, Severity
from .rules import base

_LINTABLE_EXT = (".md", ".markdown", ".txt", ".prompt")
_SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "dist", "build",
    "__pycache__", "vendor", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".tox", ".eggs", "site-packages",
}
_SUPPRESS = re.compile(r"promptproof:\s*ignore\s+([A-Za-z0-9, ]+)", re.IGNORECASE)


def is_enabled(meta: base.RuleMeta, config: Config) -> bool:
    if config.select is not None:
        if meta.id not in config.select and meta.category not in config.select:
            return False
    if meta.id in config.ignore or meta.category in config.ignore:
        return False
    return True


def _looks_like_tool_json(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    if not p.endswith(".json"):
        return False
    base_name = os.path.basename(p)
    return (
        "/tools/" in p
        or "/mcp/" in p
        or "tool" in base_name
        or "mcp" in base_name
    )


def discover(paths: Iterable[str]) -> list[str]:
    """Expand files and directories into a sorted list of lintable file paths."""
    found: list[str] = []
    seen: set[str] = set()

    def add(fp: str) -> None:
        ap = os.path.abspath(fp)
        if ap not in seen:
            seen.add(ap)
            found.append(fp)

    for raw in paths:
        if os.path.isfile(raw):
            add(raw)
            continue
        if not os.path.isdir(raw):
            continue
        for root, dirs, files in os.walk(raw):
            dirs[:] = [
                d
                for d in dirs
                if d not in _SKIP_DIRS and not (d.startswith(".") and d != ".claude")
            ]
            for fn in sorted(files):
                ext = os.path.splitext(fn)[1].lower()
                fp = os.path.join(root, fn)
                if ext in _LINTABLE_EXT or _looks_like_tool_json(fp):
                    add(fp)
    return found


def _suppressed_ids(line: str) -> set[str]:
    m = _SUPPRESS.search(line)
    if not m:
        return set()
    return {tok.strip().upper() for tok in m.group(1).split(",") if tok.strip()}


def _apply_suppressions(findings: list[Finding], doc: Document) -> list[Finding]:
    lines = doc.lines
    kept = []
    for f in findings:
        ln = f.location.line
        suppressed = False
        if ln and 1 <= ln <= len(lines):
            ids = _suppressed_ids(lines[ln - 1])
            if ln >= 2:
                ids |= _suppressed_ids(lines[ln - 2])
            if f.rule in ids:
                suppressed = True
        if not suppressed:
            kept.append(f)
    return kept


def lint_document(doc: Document, config: Config | None = None) -> list[Finding]:
    config = config or Config()
    ctx = base.Context(config)
    findings: list[Finding] = []
    for rule in base.rules_for_kind(doc.kind):
        if not is_enabled(rule.meta, config):
            continue
        try:
            findings.extend(rule.check(doc, ctx))
        except Exception as exc:  # a buggy rule must never crash the run
            findings.append(
                Finding(
                    rule="PP901",
                    name="internal-error",
                    severity=Severity.INFO,
                    message=f"rule {rule.meta.id} raised: {type(exc).__name__}",
                    location=Location(doc.path),
                )
            )
    # severity overrides
    if config.severity:
        findings = [
            f if f.rule not in config.severity
            # dataclasses.replace, so a field added later can't be silently dropped here
            # the way `fix` would have been by a positional rebuild.
            else replace(f, severity=config.severity[f.rule])
            for f in findings
        ]
    findings = _apply_suppressions(findings, doc)
    findings.sort(key=Finding.sort_key)
    return findings


def lint_text(
    text: str,
    *,
    path: str = "<text>",
    kind: DocKind | None = None,
    config: Config | None = None,
) -> list[Finding]:
    return lint_document(Document.from_text(text, path=path, kind=kind), config)


def lint_file(
    path: str, *, kind: DocKind | None = None, config: Config | None = None
) -> list[Finding]:
    try:
        doc = Document.from_path(path, kind=kind)
    except OSError as exc:
        return [
            Finding(
                rule="PP902",
                name="io-error",
                severity=Severity.WARNING,
                message=f"could not read file: {exc.strerror or exc}",
                location=Location(path),
            )
        ]
    return lint_document(doc, config)


def lint_paths(paths: Iterable[str], *, config: Config | None = None) -> list[Finding]:
    out: list[Finding] = []
    for fp in discover(paths):
        out.extend(lint_file(fp, config=config))
    out.sort(key=Finding.sort_key)
    return out


def exit_code(findings: list[Finding], fail_level: Severity) -> int:
    """1 if any finding is at/above ``fail_level``, else 0."""
    return 1 if any(f.severity.rank >= fail_level.rank for f in findings) else 0

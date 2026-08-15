"""The ``promptproof`` command-line interface (argparse only — zero dependencies).

Usage:
    promptproof [PATHS ...] [options]     # lint (default)
    promptproof [PATHS ...] --fix         # apply the mechanical repairs
    promptproof [PATHS ...] --diff        # preview them without writing
    promptproof --write-baseline          # accept today's findings
    promptproof --baseline                # fail only on findings added since
    promptproof rules [--category C] [--json]
    promptproof explain PPID
    promptproof version
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import time

from . import __version__
from .baseline import DEFAULT_BASELINE_PATH, Baseline, BaselineError
from .config import load_config
from .document import DocKind
from .engine import discover, exit_code, lint_file, lint_paths, lint_text
from .finding import Severity
from .fixer import fix_file
from .reporters import render
from .rules import all_rules, explain_for, get_rule

_FORMATS = ("text", "json", "github", "sarif")


def _split_csv(values: list[str] | None) -> set[str]:
    out: set[str] = set()
    for v in values or []:
        out.update(tok.strip() for tok in v.split(",") if tok.strip())
    return out


def _cmd_lint(argv: list[str]) -> int:
    import os

    parser = argparse.ArgumentParser(prog="promptproof", add_help=True)
    parser.add_argument("paths", nargs="*", default=["."], help="files or dirs (default: .)")
    parser.add_argument("--format", choices=_FORMATS, default=None)
    parser.add_argument("--select", action="append", help="rule ids/categories to run")
    parser.add_argument("--ignore", action="append", help="rule ids/categories to skip")
    parser.add_argument("--kind", choices=[k.value for k in DocKind], default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--fail-level", choices=[s.value for s in Severity], default=None)
    parser.add_argument("--exit-zero", action="store_true")
    parser.add_argument("--no-summary", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--color", dest="color", action="store_true", default=None)
    parser.add_argument("--no-color", dest="color", action="store_false")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="apply the mechanical repairs and rewrite the files in place",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="print the unified diff --fix would apply, without writing anything",
    )
    parser.add_argument(
        "--baseline",
        nargs="?",
        const=DEFAULT_BASELINE_PATH,
        default=None,
        metavar="PATH",
        help=f"suppress findings recorded in a baseline file (default: {DEFAULT_BASELINE_PATH})",
    )
    parser.add_argument(
        "--write-baseline",
        nargs="?",
        const=DEFAULT_BASELINE_PATH,
        default=None,
        metavar="PATH",
        help="record the current findings as the accepted baseline and exit 0",
    )
    args = parser.parse_args(argv)

    paths = args.paths or ["."]
    try:
        config = load_config(
            paths[0] if paths else ".", explicit=args.config
        )
    except Exception as exc:  # noqa: BLE001 - surface config errors as exit 2
        print(f"promptproof: error: {exc}", file=sys.stderr)
        return 2

    select = _split_csv(args.select)
    ignore = _split_csv(args.ignore)
    if select:
        config.select = frozenset(select if config.select is None else set(config.select) | select)
    if ignore:
        config.ignore = config.ignore | frozenset(ignore)
    if args.fail_level:
        config.fail_level = Severity(args.fail_level)

    fmt = args.format
    if fmt is None:
        fmt = "github" if os.environ.get("GITHUB_ACTIONS") == "true" else "text"

    kind = DocKind(args.kind) if args.kind else None

    reading_stdin = len(paths) == 1 and paths[0] == "-"
    if (args.fix or args.diff) and reading_stdin:
        print("promptproof: error: --fix/--diff need real files, not stdin", file=sys.stderr)
        return 2

    start = time.perf_counter()
    fixed_count = 0
    if reading_stdin:
        text = sys.stdin.read()
        findings = lint_text(text, path="<stdin>", kind=kind, config=config)
        files = 1
    elif args.fix or args.diff:
        findings, fixed_count, diff_text = _run_fixes(
            paths, kind=kind, config=config, write=args.fix
        )
        files = len(discover(paths))
        if diff_text:
            print(diff_text, end="")
    else:
        findings = lint_paths(paths, config=config)
        files = len({f.location.path for f in findings})
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    if args.write_baseline:
        written = Baseline().save(args.write_baseline, findings)
        print(f"wrote {written} finding(s) to {args.write_baseline}")
        return 0

    suppressed = 0
    if args.baseline:
        try:
            findings, suppressed = Baseline.load(args.baseline).filter(findings)
        except BaselineError as exc:
            print(f"promptproof: error: {exc}", file=sys.stderr)
            return 2

    if args.quiet:
        findings = [f for f in findings if f.severity is not Severity.INFO]

    out = render(
        findings,
        fmt,
        summary=not args.no_summary,
        color=args.color,
        elapsed_ms=elapsed_ms,
        files=files,
    )
    if out:
        print(out)

    notes = []
    if fixed_count:
        notes.append(f"fixed {fixed_count} finding(s)" if args.fix else f"{fixed_count} fixable")
    if suppressed:
        notes.append(f"{suppressed} baselined")
    if notes and not args.no_summary:
        print("  ·  ".join(notes))

    if args.exit_zero:
        return 0
    return exit_code(findings, config.fail_level)


def _run_fixes(
    paths: list[str], *, kind: DocKind | None, config, write: bool
) -> tuple[list, int, str]:
    """Fix (or preview fixing) every discovered file. Returns findings, count, diff text."""
    remaining: list = []
    fixed = 0
    diff_parts: list[str] = []
    for path in discover(paths):
        try:
            with open(path, encoding="utf-8") as fh:
                before = fh.read()
        except OSError:
            remaining.extend(lint_file(path, kind=kind, config=config))
            continue
        result = fix_file(path, kind=kind, config=config, write=write)
        remaining.extend(result.remaining)
        fixed += len(result.applied)
        if not write and result.text != before:
            diff_parts.extend(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    result.text.splitlines(keepends=True),
                    fromfile=path,
                    tofile=path,
                )
            )
    remaining.sort(key=lambda f: f.sort_key())
    return remaining, fixed, "".join(diff_parts)


def _cmd_rules(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="promptproof rules")
    parser.add_argument("--category", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rules = [r for r in all_rules() if not args.category or r.meta.category == args.category]
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": r.meta.id,
                        "name": r.meta.name,
                        "category": r.meta.category,
                        "severity": r.meta.default_severity.value,
                        "summary": r.meta.summary,
                    }
                    for r in rules
                ],
                indent=2,
            )
        )
        return 0
    for r in rules:
        print(f"{r.meta.id}  {r.meta.default_severity.value:<7}  {r.meta.category:<12}  "
              f"{r.meta.name:<24}  {r.meta.summary}")
    return 0


def _cmd_explain(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="promptproof explain")
    parser.add_argument("rule_id")
    args = parser.parse_args(argv)
    rid = args.rule_id.strip().upper()
    rule = get_rule(rid)
    if rule is None:
        print(f"promptproof: error: unknown rule {rid}", file=sys.stderr)
        return 2
    m = rule.meta
    print(f"{m.id}  {m.name}  [{m.category}, {m.default_severity.value}]")
    print()
    print(m.summary)
    text = explain_for(rid)
    if text:
        print()
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "rules":
        return _cmd_rules(argv[1:])
    if argv and argv[0] == "explain":
        return _cmd_explain(argv[1:])
    if argv and argv[0] in ("version", "--version", "-V"):
        print(f"promptproof {__version__}")
        return 0
    return _cmd_lint(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

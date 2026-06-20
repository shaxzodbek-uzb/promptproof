"""The ``promptproof`` command-line interface (argparse only — zero dependencies).

Usage:
    promptproof [PATHS ...] [options]     # lint (default)
    promptproof rules [--category C] [--json]
    promptproof explain PPID
    promptproof version
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import __version__
from .config import load_config
from .document import DocKind
from .engine import exit_code, lint_paths, lint_text
from .finding import Severity
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

    start = time.perf_counter()
    if paths == ["-"] or (len(paths) == 1 and paths[0] == "-"):
        text = sys.stdin.read()
        findings = lint_text(text, path="<stdin>", kind=kind, config=config)
        files = 1
    else:
        findings = lint_paths(paths, config=config)
        files = len({f.location.path for f in findings})
    elapsed_ms = (time.perf_counter() - start) * 1000.0

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

    if args.exit_zero:
        return 0
    return exit_code(findings, config.fail_level)


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

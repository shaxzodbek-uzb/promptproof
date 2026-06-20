"""Render findings in human and machine formats: text, json, github, sarif."""

from __future__ import annotations

import json
import os
import sys

from .finding import Finding, Severity

_COLORS = {Severity.ERROR: "31", Severity.WARNING: "33", Severity.INFO: "34"}
_RESET = "\033[0m"


def _use_color(color: bool | None) -> bool:
    if color is not None:
        return color
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _pos(n: int) -> str:
    return str(n) if n else "-"


def _counts(findings: list[Finding]) -> tuple[int, int, int]:
    e = sum(1 for f in findings if f.severity is Severity.ERROR)
    w = sum(1 for f in findings if f.severity is Severity.WARNING)
    i = sum(1 for f in findings if f.severity is Severity.INFO)
    return e, w, i


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _render_text(findings: list[Finding], summary: bool, color: bool, elapsed_ms) -> str:
    use_color = color
    lines: list[str] = []
    by_path: dict[str, list[Finding]] = {}
    for f in findings:
        by_path.setdefault(f.location.path, []).append(f)

    for path in by_path:
        lines.append(f"{path}:")
        for f in by_path[path]:
            rid = f.rule
            if use_color:
                rid = f"\033[{_COLORS[f.severity]}m{f.rule}{_RESET}"
            loc = f"{_pos(f.location.line)}:{_pos(f.location.col)}"
            lines.append(f"  {loc}: {rid} {f.message}")
            if f.hint:
                lines.append(f"        → {f.hint}")
        lines.append("")

    if summary:
        ms = f"{elapsed_ms:.0f}ms" if elapsed_ms is not None else "0ms"
        if findings:
            e, w, i = _counts(findings)
            lines.append(
                f"{_plural(e, 'error')}, {_plural(w, 'warning')}, {i} info"
                f"  ·  0 API calls  ·  {ms}"
            )
        else:
            lines.append(f"All prompts proofed ✓  ·  0 API calls  ·  {ms}")
    return "\n".join(lines).rstrip("\n") + ("\n" if findings or summary else "")


def _render_json(findings: list[Finding], paths_count: int) -> str:
    e, w, i = _counts(findings)
    payload = {
        "findings": [
            {
                "rule": f.rule,
                "name": f.name,
                "severity": f.severity.value,
                "message": f.message,
                "path": f.location.path,
                "line": f.location.line,
                "col": f.location.col,
                "end_line": f.location.end_line,
                "hint": f.hint,
            }
            for f in findings
        ],
        "summary": {"error": e, "warning": w, "info": i, "files": paths_count},
    }
    return json.dumps(payload, indent=2)


def _render_github(findings: list[Finding]) -> str:
    out = []
    for f in findings:
        level = "error" if f.severity is Severity.ERROR else "warning"
        params = [f"file={f.location.path}"]
        if f.location.line:
            params.append(f"line={f.location.line}")
            if f.location.col:
                params.append(f"col={f.location.col}")
        params.append(f"title={f.rule} {f.name}")
        out.append(f"::{level} {','.join(params)}::{f.message}")
    return "\n".join(out)


def _render_sarif(findings: list[Finding]) -> str:
    level_map = {Severity.ERROR: "error", Severity.WARNING: "warning", Severity.INFO: "note"}
    rule_ids = sorted({f.rule for f in findings})
    results = []
    for f in findings:
        region = {}
        if f.location.line:
            region["startLine"] = f.location.line
            if f.location.col:
                region["startColumn"] = f.location.col
        results.append(
            {
                "ruleId": f.rule,
                "level": level_map[f.severity],
                "message": {"text": f.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.location.path},
                            **({"region": region} if region else {}),
                        }
                    }
                ],
            }
        )
    log = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "promptproof",
                        "informationUri": "https://github.com/shaxzodbek-uzb/promptproof",
                        "rules": [{"id": rid} for rid in rule_ids],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(log, indent=2)


def render(
    findings: list[Finding],
    fmt: str = "text",
    *,
    summary: bool = True,
    color: bool | None = None,
    elapsed_ms: float | None = None,
    files: int = 0,
) -> str:
    if fmt == "text":
        return _render_text(findings, summary, _use_color(color), elapsed_ms)
    if fmt == "json":
        return _render_json(findings, files)
    if fmt == "github":
        return _render_github(findings)
    if fmt == "sarif":
        return _render_sarif(findings)
    raise ValueError(f"unknown format: {fmt}")

"""Reporters: text / json / github / sarif render correctly and round-trip."""

from __future__ import annotations

import json

from promptproof.finding import Finding, Location, Severity
from promptproof.reporters import render

FINDINGS = [
    Finding(
        rule="PP404",
        name="weak-trigger",
        severity=Severity.WARNING,
        message="weak trigger: description summarizes instead of stating when to use it",
        location=Location("a/SKILL.md", 2, 14),
        hint='rewrite as "Use when <condition>"',
    ),
    Finding(
        rule="PP601",
        name="secret-in-prompt",
        severity=Severity.ERROR,
        message="hardcoded secret detected (sk-a...)",
        location=Location("a/SKILL.md", 5, 1),
    ),
    Finding(
        rule="PP305",
        name="token-budget",
        severity=Severity.INFO,
        message="body ~7,200 tokens",
        location=Location("a/SKILL.md", 0, 0),
    ),
]


# --------------------------------------------------------------------------------- text


def test_text_renders_findings_and_footer():
    out = render(FINDINGS, "text", color=False, elapsed_ms=6)
    assert "a/SKILL.md:" in out
    assert "PP404" in out
    assert "0 API calls" in out
    assert "1 error, 1 warning, 1 info" in out


def test_text_renders_hint_arrow():
    out = render(FINDINGS, "text", color=False)
    assert "→ rewrite as" in out


def test_text_whole_file_location_renders_dash():
    out = render([FINDINGS[2]], "text", color=False)
    assert "-:-:" in out


def test_text_clean_footer_when_empty():
    out = render([], "text", color=False, elapsed_ms=3)
    assert "All prompts proofed" in out
    assert "0 API calls" in out


def test_text_color_emits_ansi():
    out = render(FINDINGS, "text", color=True)
    assert "\033[" in out


# --------------------------------------------------------------------------------- json


def test_json_round_trips():
    out = render(FINDINGS, "json", files=1)
    data = json.loads(out)
    assert "findings" in data
    assert "summary" in data
    assert data["summary"] == {"error": 1, "warning": 1, "info": 1, "files": 1}
    first = data["findings"][0]
    assert first["rule"] == "PP404"
    assert first["path"] == "a/SKILL.md"
    assert first["line"] == 2
    assert first["col"] == 14


def test_json_empty_is_valid():
    data = json.loads(render([], "json"))
    assert data["findings"] == []
    assert data["summary"]["error"] == 0


# ------------------------------------------------------------------------------- github


def test_github_emits_warning_and_error_lines():
    out = render(FINDINGS, "github")
    assert "::warning file=a/SKILL.md,line=2,col=14,title=PP404 weak-trigger::" in out
    assert "::error file=a/SKILL.md,line=5,col=1,title=PP601 secret-in-prompt::" in out


def test_github_info_uses_warning_level():
    out = render([FINDINGS[2]], "github")
    assert out.startswith("::warning ")


def test_github_omits_line_when_zero():
    out = render([FINDINGS[2]], "github")
    assert "line=" not in out


# -------------------------------------------------------------------------------- sarif


def test_sarif_shape():
    out = render(FINDINGS, "sarif")
    data = json.loads(out)
    assert data["version"] == "2.1.0"
    assert data["runs"][0]["tool"]["driver"]["name"] == "promptproof"
    assert len(data["runs"][0]["results"]) == 3


def test_sarif_maps_info_to_note():
    data = json.loads(render([FINDINGS[2]], "sarif"))
    assert data["runs"][0]["results"][0]["level"] == "note"


def test_unknown_format_raises():
    try:
        render(FINDINGS, "xml")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for unknown format")

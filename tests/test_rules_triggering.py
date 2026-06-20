"""Triggering rules (PP4xx). Every rule has a firing case AND a known-good case."""

from __future__ import annotations

from promptproof import DocKind, lint_text
from tests.conftest import ids

GOOD = (
    "---\n"
    "name: pdf-tools\n"
    "description: Use when the user wants to read or merge PDF files, or mentions a .pdf.\n"
    "---\n\n# PDF tools\n\nDo the thing.\n"
)


def test_good_skill_has_no_triggering_findings():
    assert not {i for i in ids(GOOD, kind=DocKind.SKILL) if i.startswith("PP4")}


def test_pp401_description_missing():
    text = "---\nname: my-skill\n---\n\nbody\n"
    assert "PP401" in ids(text, kind=DocKind.SKILL)


def test_pp402_description_too_short():
    text = "---\nname: x\ndescription: Reads files.\n---\n\nbody\n"
    assert "PP402" in ids(text, kind=DocKind.SKILL)


def test_pp403_description_too_long():
    long = "Use when " + "x" * 1100
    text = f"---\nname: x\ndescription: {long}\n---\n\nbody\n"
    assert "PP403" in ids(text, kind=DocKind.SKILL)


def test_pp404_weak_trigger_fires_on_summary():
    desc = "A skill for working with PDF files and documents."
    text = f"---\nname: x\ndescription: {desc}\n---\n\nb\n"
    assert "PP404" in ids(text, kind=DocKind.SKILL)


def test_pp404_does_not_fire_on_good_trigger():
    assert "PP404" not in ids(GOOD, kind=DocKind.SKILL)


def test_pp405_first_person():
    text = (
        "---\nname: x\n"
        "description: I will help you when you need to work with PDF files and documents.\n"
        "---\n\nb\n"
    )
    assert "PP405" in ids(text, kind=DocKind.SKILL)


def test_pp406_tool_param_undocumented():
    tool = (
        '{"name": "search", "description": "Use when the user wants to search the web.",'
        ' "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}}'
    )
    found = {f.rule for f in lint_text(tool, path="tool.json", kind=DocKind.MCP_TOOL)}
    assert "PP406" in found


def test_pp406_documented_param_is_clean():
    tool = (
        '{"name": "search", "description": "Use when the user wants to search the web.",'
        ' "inputSchema": {"type": "object", "properties":'
        ' {"query": {"type": "string", "description": "the search query"}}}}'
    )
    found = {f.rule for f in lint_text(tool, path="tool.json", kind=DocKind.MCP_TOOL)}
    assert "PP406" not in found

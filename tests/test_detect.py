"""detect_kind: path-, extension-, and frontmatter-based classification."""

from __future__ import annotations

from promptproof import DocKind
from promptproof.detect import detect_kind


def test_skill_md_basename():
    assert detect_kind("foo/SKILL.md", "x", None) is DocKind.SKILL
    assert detect_kind("skill.md", "x", None) is DocKind.SKILL


def test_subagent_by_path():
    p = "repo/.claude/agents/reviewer.md"
    assert detect_kind(p, "x", None) is DocKind.SUBAGENT


def test_command_by_path():
    p = "repo/.claude/commands/deploy.md"
    assert detect_kind(p, "x", None) is DocKind.COMMAND


def test_windows_style_claude_path():
    p = r"repo\.claude\agents\reviewer.md"
    assert detect_kind(p, "x", None) is DocKind.SUBAGENT


def test_mcp_tool_json_with_input_schema():
    text = '{"name": "search", "inputSchema": {"type": "object"}}'
    assert detect_kind("search.json", text, None) is DocKind.MCP_TOOL


def test_mcp_tool_json_with_parameters():
    text = '{"name": "search", "parameters": {"type": "object"}}'
    assert detect_kind("search.json", text, None) is DocKind.MCP_TOOL


def test_plain_json_without_schema_is_not_tool():
    text = '{"name": "search"}'  # missing inputSchema/parameters
    assert detect_kind("search.json", text, None) is DocKind.UNKNOWN


def test_frontmatter_name_description_is_skill():
    fm = {"name": "x", "description": "y"}
    assert detect_kind("doc.md", "x", fm) is DocKind.SKILL


def test_frontmatter_with_tools_is_subagent():
    fm = {"name": "x", "description": "y", "tools": ["Read"]}
    assert detect_kind("doc.md", "x", fm) is DocKind.SUBAGENT


def test_frontmatter_with_model_is_subagent():
    fm = {"name": "x", "description": "y", "model": "sonnet"}
    assert detect_kind("doc.md", "x", fm) is DocKind.SUBAGENT


def test_plain_md_and_txt_are_prompt():
    assert detect_kind("notes.md", "hi", None) is DocKind.PROMPT
    assert detect_kind("notes.txt", "hi", None) is DocKind.PROMPT
    assert detect_kind("notes.prompt", "hi", None) is DocKind.PROMPT


def test_unknown_extension():
    assert detect_kind("data.csv", "a,b", None) is DocKind.UNKNOWN

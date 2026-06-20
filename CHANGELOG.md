# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial release of `promptproof` — a fast, deterministic, **zero-API** linter for AI
  agent prompt assets: `SKILL.md`, Claude Code sub-agents, MCP tool descriptions,
  slash-command frontmatter, and plain system/user prompts.
- 31 rules across six categories: clarity (PP1xx), consistency (PP2xx), economy (PP3xx),
  triggering (PP4xx), structure (PP5xx), and safety (PP6xx).
- Document auto-detection (`SKILL.md`, `.claude/agents`, `.claude/commands`, MCP tool
  JSON, generic prompts) with per-kind rule selection.
- Output formats: `text` (default), `json`, `github` (Actions annotations), and `sarif`.
- Dependency-free core; optional extras for PyYAML frontmatter (`[yaml]`) and an
  MCP-native server wrapper (`[mcp]`).
- Inline suppression (`# promptproof: ignore PP404`), config via `[tool.promptproof]` in
  `pyproject.toml` or `.promptproof.toml`.
- Composite GitHub Action (`action.yml`) and `pre-commit` hook.

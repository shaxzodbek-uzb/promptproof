# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-08-16

### Added

- **`--fix`** — apply the fixes promptproof already knows how to make, in place.
  A finding now carries an optional `Edit`, and the fixer applies them
  bottom-up so line numbers stay valid, skipping any pair that overlaps.
  Re-linting runs up to `MAX_PASSES` (5) times, so a fix that exposes another
  finding still converges instead of spinning.
- **`--diff`** — print the unified diff instead of writing, to see exactly what
  `--fix` would change.
- **`--baseline` / `--write-baseline`** — record today's findings and report only
  what is new, so promptproof can be adopted on a large existing prompt tree
  without a thousand-line first run. Fingerprints are keyed on the *content* of
  the offending line rather than its number, so moving a block around the file
  does not resurface every finding in it; counts are tracked per key, so
  duplicating an already-baselined line is still reported.

### Fixed

- **PP301 and PP302 rewrote text inside fenced code blocks.** A prompt containing
  a fenced example of bad wording had the example itself edited, corrupting the
  block. Both rules now skip fenced lines.
- Removing courtesy filler could strand leading punctuation — "Needless to say,
  run the tests." became ", run the tests." The fixer now cleans up the seam.

### Changed

- Severity overrides rebuild findings via `dataclasses.replace`, so a `Finding`
  keeps its `fix` when its severity is overridden in config.

## [0.1.0] - 2026-06-20

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

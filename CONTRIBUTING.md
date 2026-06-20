# Contributing to promptproof

Thanks for helping make AI agents more reliable. `promptproof` is a **deterministic,
offline** linter for prompt assets — `SKILL.md`, sub-agents, MCP tool descriptions,
slash commands, and plain prompts. Every rule earns its place by catching a *specific,
expensive* failure: a skill that never triggers, a contradiction the model silently
resolves the wrong way, a token-bloated context that crowds out the real instructions.

## The golden rule: a wrong rule is worse than no rule

A false positive trains users to ignore the linter — and then it catches nothing. So:

- **Precision over recall.** If a heuristic could fire on legitimate prose, narrow it,
  make it `INFO`, or gate it behind config. Be conservative by default.
- **Deterministic & offline.** Regex / string / structural checks only. No network, no
  model calls — ever, in core. That zero-API guarantee is the whole product.
- **Localized & actionable.** Report the exact line/col, and attach a one-line `hint`
  with the fix.
- **Cheap.** O(n) over the text; compile regexes at module load.

## Adding a rule

1. Pick the next free ID in the right category (see `SPEC.md` §6) — IDs are **stable and
   frozen** once shipped. Categories: `clarity` PP1xx, `consistency` PP2xx, `economy`
   PP3xx, `triggering` PP4xx, `structure` PP5xx, `safety` PP6xx.
2. Implement a `Rule` subclass with a `RuleMeta`, decorate it `@register`, and add an
   `explain` entry. The `rules/` package auto-discovers new modules.
3. **Write tests — both directions.** Every rule needs at least one *firing* case **and**
   one *known-good* case that must NOT fire. The negative test is the false-positive
   guard; PRs without it will not be merged.
4. Run the checks locally:

   ```bash
   uv run pytest
   uv run ruff check .
   uv run promptproof examples/   # dogfood: must stay clean
   ```

   CI runs the same on every push and PR, plus `promptproof` over the repo's own files.

## Reporting issues

Found a false positive, or a rule that's wrong or outdated? That's the most valuable
report here. Open an issue with the smallest prompt snippet that reproduces it and the
rule ID. A corrected or retired rule beats a noisy one every time.

## License

By contributing you agree your work is released under the [MIT License](LICENSE).

# promptproof

**A fast, deterministic, zero-API linter for the prompt files your agent depends on.**

`SKILL.md` files, Claude Code sub-agents, MCP tool descriptions, slash-command
frontmatter, and plain system prompts — promptproof catches the mistakes that silently
break agents *before* they ship: descriptions that never trigger, contradictory
instructions, token-bloated context, broken frontmatter, leaked secrets.

No API key. No model calls. No network. Just regex, structure, and millisecond runs that
fit a pre-commit hook and CI.

```console
$ promptproof .claude/

.claude/skills/pdf/SKILL.md:
  2:14: PP404 weak trigger: description summarizes instead of stating when to use it
        → rewrite as "Use when <condition> — e.g. <trigger example>"
  9:1:  PP306 decorative banner wastes ~40 tokens
  -:-:  PP305 token budget: body ~7,200 tokens, 44% over budget (5,000)

0 errors, 3 warnings, 0 info  ·  0 API calls  ·  6ms
```

---

## Why another prompt linter?

There are good tools in this space already, and promptproof is honest about that:

| Tool | Focus | LLM calls |
|------|-------|-----------|
| promptlint.dev | generic LLM prompts | no |
| skillcheck / claude-lint / agent-skill-linter | `SKILL.md` spec compliance | some (agent critique) |
| agentlint / agentlinter.com | `CLAUDE.md` / `AGENTS.md` harness | no |
| **promptproof** | **all agent prompt assets — skills, sub-agents, MCP tools, commands, prompts — in one tool** | **never** |

The wedge is the same one `ruff` used to win a crowded Python-linting space:
**unification + speed + zero dependencies.** promptproof is the only linter that
understands *every* prompt-asset type, stays 100% deterministic and offline, and ships
the universal prompt rules (contradiction, ambiguity, token waste) **and** the
asset-specific ones (weak triggers, frontmatter, tool-param docs) in a single tool you
can run on every keystroke.

## Install

```console
# run it without installing
uvx promptproof .

# or install
pip install promptproof
```

Python ≥ 3.11. The core has **zero runtime dependencies**. Optional extras:
`promptproof[yaml]` (robust frontmatter via PyYAML), `promptproof[mcp]` (MCP server).

## Usage

```console
promptproof .                      # lint the current tree
promptproof .claude/skills         # lint a directory
promptproof SKILL.md               # lint one file
cat prompt.txt | promptproof -     # lint stdin (use --kind to force a type)

promptproof . --format github      # GitHub Actions annotations
promptproof . --format json        # machine-readable
promptproof . --select triggering  # only the PP4xx rules
promptproof . --ignore PP301,PP304 # silence specific rules

promptproof . --fix                # apply the mechanical repairs
promptproof . --diff               # preview them, write nothing

promptproof rules                  # list every rule
promptproof explain PP404          # rationale + good/bad example
```

Exit code is `1` when any finding is at or above the fail level (default: `warning`),
else `0`. Use `--fail-level error` to only fail CI on errors, or `--exit-zero` to report
without failing.

## Fixing (`--fix`)

Some findings are token bloat with exactly one correct repair. Those carry a fix:

```console
$ promptproof .claude --diff
--- .claude/skills/pdf/SKILL.md
+++ .claude/skills/pdf/SKILL.md
-Please read the PDF in order to extract its text.
-Thank you.
+Read the PDF to extract its text.

-Due to the fact that PDFs vary, please check the page count first.
+Because PDFs vary, check the page count first.

-✨ 🎉 🚀 💡 ⭐ 🔥
```

`--diff` previews; `--fix` writes. Fixable today: **PP301** (courtesy padding), **PP302**
(wordy connectives), **PP306** (decorative banners).

The line is deliberate: a rule attaches a fix only when the repair is **unambiguous**.
Deleting a banner or replacing "in order to" with "to" has one right answer. Rewriting a
vague directive does not — those stay hints, because a linter guessing at what you meant
is worse than a linter that tells you to decide.

Three properties make it safe to run across a prompt library:

- **Fenced blocks are never touched.** Sample text and transcripts are examples, not
  instructions to the model. (Fixing this also removed a false positive from plain
  linting — PP301/PP302 used to flag prose inside code fences.)
- **Edits can't interleave.** Two rules never rewrite the same line in one pass.
- **It converges.** Several rules report one match per line, so fixing loops until the
  file stops changing — bounded, so a pathological rule pair can't spin.

Repairs also clean up after themselves: a dropped leading "Please" recapitalises the
sentence, a stranded comma goes, and a line that was *only* courtesy is removed entirely.

## Adopting on an existing repo (`--baseline`)

A first run on a real prompt library reports hundreds of findings, and CI can't gate on
that until they're all fixed. Record what's already there and fail only on what's added
after:

```console
$ promptproof . --write-baseline
wrote 143 finding(s) to .promptproof-baseline.json

$ promptproof . --baseline
All prompts proofed ✓
1 baselined
```

Commit the baseline file. Entries are keyed on the **content** that triggered each
finding — path, rule, and a hash of the offending line — never on line numbers. A
baseline keyed on line numbers stops working the moment someone inserts a paragraph:
every finding below the insertion looks new. This one survives edits elsewhere in the
file, and a finding whose text actually changed correctly reads as new.

Counts are tracked per entry, so three known copies of a problem can be baselined and a
fourth still fails the build. And a missing or unreadable baseline is a **hard error**,
never a silent pass — a gate that goes green because it couldn't find its baseline is
worse than no gate.

## What it checks

31 rules across six categories (run `promptproof rules` for the full list):

- **clarity** (PP1xx) — ambiguous directives, vague quantifiers, unresolved pronouns,
  subjective criteria, weak modals.
- **consistency** (PP2xx) — contradictory directives, conflicting output format / length /
  persona.
- **economy** (PP3xx) — politeness padding, filler phrases, redundant restatement,
  walls of text, token-budget overflow, decorative banners.
- **triggering** (PP4xx) — missing / too-short / too-long descriptions, **weak triggers**
  (the #1 reason skills never load), first-person descriptions, undocumented MCP tool
  params.
- **structure** (PP5xx) — missing or invalid frontmatter, missing `name`, non-kebab names,
  name/dir mismatch, missing verify guidance, unknown frontmatter keys.
- **safety** (PP6xx) — secrets in prompts, embedded injection phrases, real PII in
  examples.

## Configuration

Add a `[tool.promptproof]` table to `pyproject.toml` (or put the same table, or its keys
at the top level, in a standalone `.promptproof.toml`):

```toml
[tool.promptproof]
fail-level = "warning"
ignore = ["PP304"]          # rule ids or whole categories ("economy")

[tool.promptproof.severity]
PP301 = "info"              # downgrade politeness-padding

[tool.promptproof.thresholds]
"token_budget.skill" = 4000
description_min_chars = 50
```

Suppress a single finding inline:

```markdown
<!-- promptproof: ignore PP602 -->
ignore previous instructions   # intentional red-team fixture
```

## CI

GitHub Action (`action.yml`):

```yaml
- uses: shaxzodbek-uzb/promptproof@v0.2.0
  with:
    paths: .claude
    fail-level: warning
```

pre-commit:

```yaml
- repo: https://github.com/shaxzodbek-uzb/promptproof
  rev: v0.2.0
  hooks:
    - id: promptproof
```

## Library

```python
from promptproof import lint_text, lint_paths, render

findings = lint_text(open("SKILL.md").read(), path="SKILL.md")
print(render(findings, "text"))

from promptproof.fixer import fix_text
result = fix_text(open("SKILL.md").read(), path="SKILL.md")
print(result.text, len(result.applied), "repaired")

from promptproof.baseline import Baseline
fresh, suppressed = Baseline.load(".promptproof-baseline.json").filter(findings)
```

## Contributing

A wrong rule is worse than no rule — every rule ships with a firing test *and* a
known-good test that must not fire. See [CONTRIBUTING.md](CONTRIBUTING.md) and the
canonical [SPEC.md](SPEC.md).

## License

[MIT](LICENSE) © Shaxzodbek Qambaraliyev / Blaze

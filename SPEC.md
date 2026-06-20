# promptproof — Canonical Build Spec (single source of truth)

> Every builder reads THIS file and implements exactly the signatures, names, IDs, and
> behaviors below. Do **not** invent extra public API. Match names, rule IDs, and
> messages character-for-character. When in doubt, prefer fewer moving parts and the
> Python standard library over dependencies. The **core has zero runtime dependencies.**

---

## 1. What it is (positioning)

`promptproof` is a **fast, deterministic, zero-API linter for AI agent prompt assets.**

Think `ruff`, but for the prompt files that make agents work: `SKILL.md` files,
sub-agent definitions, MCP tool descriptions, slash-command frontmatter, and plain
system / user prompts. It catches the mistakes that silently break agents —
descriptions that never trigger, contradictory instructions, token-bloated context,
weak frontmatter — **before** they ship.

**Why it exists alongside other tools (be honest in the README):** the space has
generic prompt linters (promptlint.dev), `SKILL.md` spec validators (skillcheck,
claude-lint, agent-skill-linter), and harness linters (agentlint, agentlinter.com).
`promptproof` is the only one that is **all three at once in one tool** and stays
**100% deterministic and offline** — no LLM calls, no API key, millisecond runs, so it
fits a pre-commit hook and CI. Like `ruff`, the wedge is **unification + speed +
zero-dependency**, not a single novel rule.

Tagline: *"Proof-check every prompt your agent depends on. Zero API calls, zero latency."*

### Non-goals (v0.1)
- No LLM-as-judge / semantic model calls. **Ever** in core. (An optional future
  `[ai]` extra may add opt-in deep checks; not in v0.1.)
- Not a full YAML engine. Frontmatter parsing covers the documented SKILL.md subset.
- Not an autofixer in v0.1 (rules emit a `hint`; `--fix` is roadmap).

---

## 2. Package layout

```
promptproof/
  __init__.py            # public exports (see §9)
  finding.py             # Severity, Location, Finding
  document.py            # DocKind, Document (+ from_path / from_text)
  parsers.py             # parse_frontmatter() — dependency-free YAML subset
  detect.py              # detect_kind() — classify a file into a DocKind
  tokens.py              # estimate_tokens() — heuristic, no tiktoken needed
  config.py              # Config, load_config(), DEFAULTS
  engine.py              # lint_text / lint_file / lint_paths / discover
  reporters.py           # render(findings, fmt, ...) -> str   (text|json|github|sarif)
  cli.py                 # argparse CLI; `promptproof` entry point
  rules/
    __init__.py          # auto-discovers & imports every ppNNN_*.py (pkgutil)
    base.py              # RuleMeta, Rule (ABC), Context, register(), registry API
    pp1xx_clarity.py     # PP101..PP105   (may be split one-file-per-rule; see §6)
    pp2xx_consistency.py # PP201..PP204
    pp3xx_economy.py     # PP301..PP306
    pp4xx_triggering.py  # PP401..PP406
    pp5xx_structure.py   # PP501..PP507
    pp6xx_safety.py      # PP601..PP603
  integrations/
    __init__.py
    mcp.py               # build_mcp_server() — optional MCP-native wrapper ([mcp] extra)
tests/                   # pytest; pure-logic, NO network. One test module per rule group.
examples/                # good/bad SKILL.md, mcp tool spec, .promptproof.toml
action.yml               # composite GitHub Action
.pre-commit-hooks.yaml   # pre-commit integration
.github/workflows/ci.yml # ruff + pytest matrix + self-lint (dogfood)
```

Distribution name `promptproof`; import package `promptproof`. **Python >= 3.11**
(stdlib `tomllib`). License MIT (holder: "Shaxzodbek Qambaraliyev / Blaze"). **Core deps:
none.** Optional extras: `mcp` (MCP server), `yaml` (PyYAML for robust frontmatter),
`dev` (pytest, ruff).

---

## 3. Core types & exact signatures

### 3.1 `finding.py`

```python
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:        # ERROR=3, WARNING=2, INFO=1  (for fail-level compare)
        return {"info": 1, "warning": 2, "error": 3}[self.value]

@dataclass(frozen=True)
class Location:
    path: str                     # file path, or "<text>" / "<stdin>"
    line: int = 0                 # 1-based; 0 == whole-file / unknown
    col: int = 0                  # 1-based; 0 == unknown
    end_line: int | None = None

@dataclass(frozen=True)
class Finding:
    rule: str                     # rule id, e.g. "PP404"
    name: str                     # rule name, e.g. "weak-trigger"
    severity: Severity
    message: str                  # ONE line, concrete, lowercase start, no trailing period
    location: Location
    hint: str | None = None       # suggested fix / rewrite; one line

    def sort_key(self) -> tuple:  # (path, line, col, rule)
        return (self.location.path, self.location.line, self.location.col, self.rule)
```

`message` style: terse, specific, includes the offending snippet when useful, e.g.
`weak trigger: description summarizes ("this skill ...") instead of stating WHEN to use it`.
No trailing period. Lowercase first letter (ruff style).

### 3.2 `document.py`

```python
class DocKind(str, Enum):
    SKILL = "skill"          # SKILL.md (agentskills.io / Anthropic agent-skills)
    SUBAGENT = "subagent"    # Claude Code sub-agent definition (.claude/agents/*.md)
    COMMAND = "command"      # slash command (.claude/commands/*.md)
    MCP_TOOL = "mcp-tool"    # an MCP tool spec (JSON) or --kind mcp-tool
    PROMPT = "prompt"        # generic system/user prompt (*.md, *.txt)
    UNKNOWN = "unknown"

@dataclass
class Document:
    path: str
    text: str
    kind: DocKind
    frontmatter: dict | None            # parsed mapping, or None if no/!frontmatter
    frontmatter_span: tuple[int, int] | None  # (start_line, end_line) 1-based incl. fences
    body: str                            # text after the frontmatter block
    body_start_line: int                 # 1-based file line where body begins (1 if no fm)
    lines: list[str]                     # text.splitlines() (no line endings)

    @classmethod
    def from_text(cls, text: str, *, path: str = "<text>",
                  kind: DocKind | None = None) -> "Document": ...
    @classmethod
    def from_path(cls, path: str, *, kind: DocKind | None = None) -> "Document": ...

    def body_lines(self) -> list[tuple[int, str]]:
        """(file_line_number_1based, line_text) for body region only (skips frontmatter)."""
```

`from_text`: if `kind` is None, call `detect.detect_kind(path, text, frontmatter)`.
Parsing frontmatter must never raise; on malformed frontmatter set `frontmatter=None`
and record nothing here (rule **PP502** reports it by re-checking, see §6).
To let PP502 fire, `Document` also exposes `frontmatter_error: str | None` (set when a
`---` block was present but could not be parsed).

### 3.3 `rules/base.py`

```python
@dataclass(frozen=True)
class RuleMeta:
    id: str                       # "PP404"
    name: str                     # "weak-trigger"  (kebab-case, unique)
    category: str                 # "triggering"  (one of the §6 category slugs)
    summary: str                  # one line for `promptproof rules`
    default_severity: Severity
    kinds: tuple[DocKind, ...]    # applicable kinds; () means ALL kinds

@dataclass
class Context:
    config: "Config"
    def estimate_tokens(self, text: str) -> int: ...   # delegates to tokens.estimate_tokens
    def threshold(self, key: str, default):  ...        # config threshold lookup w/ default

class Rule(abc.ABC):
    meta: RuleMeta                # class attribute
    @abc.abstractmethod
    def check(self, doc: Document, ctx: Context) -> Iterable[Finding]: ...

# Registry (module-level, ordered by insertion / then by id when listed)
_REGISTRY: dict[str, Rule]
def register(cls: type[Rule]) -> type[Rule]:   # decorator: instantiate + register by meta.id
def all_rules() -> list[Rule]:                  # sorted by id
def get_rule(rule_id: str) -> Rule | None:
def rules_for_kind(kind: DocKind) -> list[Rule]:
```

Each rule:
- subclasses `Rule`, sets `meta = RuleMeta(...)`, implements `check`, decorated `@register`.
- `check` yields `Finding`s. It must be **pure & side-effect free** and must not raise on
  weird input (guard your regexes). The engine wraps each call defensively anyway.
- A rule that does not apply to `doc.kind` is skipped by the engine (don't re-check kind
  inside `check`, except where a rule needs sub-conditions).
- To build a `Finding`, use the helper `self.finding(doc, message, *, line=0, col=0,
  end_line=None, hint=None, severity=None)` provided on `Rule` (fills rule/name/severity
  from meta unless overridden). Builders MUST use this helper so messages stay consistent.

### 3.4 `tokens.py`

```python
def estimate_tokens(text: str) -> int:
    """Heuristic token estimate (no tiktoken). Tuned to land within ~15% of cl100k/o200k
    for typical English prose+markdown. Deterministic. Document the method in the docstring."""
```
Method (implement exactly): tokens ≈ `round( max(n_words * 1.3, n_chars / 4.0) )` where
`n_words = len(re.findall(r"\S+", text))` and `n_chars = len(text)`. Never returns < the
word count for non-empty text. Empty/whitespace → 0.

### 3.5 `parsers.py`

```python
def parse_frontmatter(text: str) -> tuple[dict | None, tuple[int,int] | None, str | None]:
    """Returns (mapping, (start_line,end_line) 1-based incl. fences, error).
    - No leading '---' fence  -> (None, None, None)
    - Fenced block parsed OK  -> (mapping, span, None)
    - Fenced block but bad    -> (None, span, "reason")   # lets PP502 fire
    Dependency-free subset: top-level `key: value` scalars (str/int/float/bool/null),
    quoted strings, and block lists (`key:` then `- item` lines). Nested maps beyond depth
    1 are tolerated as raw strings, not errored. If the optional `yaml` extra is installed,
    prefer PyYAML safe_load for the block and only fall back to the subset parser."""
```

### 3.6 `detect.py`

```python
def detect_kind(path: str, text: str, frontmatter: dict | None) -> DocKind:
```
Rules, in order:
1. basename lower == `skill.md` → `SKILL`.
2. path contains `/.claude/agents/` (or `\.claude\agents\`) → `SUBAGENT`.
3. path contains `/.claude/commands/` → `COMMAND`.
4. extension `.json` and text parses to an object with `name` + (`inputSchema` or
   `input_schema` or `parameters`) → `MCP_TOOL`.
5. frontmatter present with both `name` and `description` keys → `SUBAGENT` if it also has
   `tools`/`model`, else `SKILL`.
6. extension in `.md`/`.markdown`/`.txt`/`.prompt` → `PROMPT`.
7. else → `UNKNOWN`.
An explicit `kind` passed by the caller/CLI always wins over detection.

### 3.7 `config.py`

```python
@dataclass
class Config:
    select: frozenset[str] | None = None      # ids/categories to run; None => all default-on
    ignore: frozenset[str] = frozenset()      # ids/categories to skip
    severity: dict[str, Severity] = field(default_factory=dict)   # id -> override
    thresholds: dict[str, object] = field(default_factory=dict)   # see DEFAULTS
    fail_level: Severity = Severity.WARNING   # exit 1 if any finding >= this rank

DEFAULTS: dict[str, object] = {
    "description_min_chars": 40,
    "description_max_chars": 1024,            # SKILL.md spec limit
    "token_budget.skill": 5000,               # body token budget for a SKILL.md
    "token_budget.subagent": 3000,
    "token_budget.prompt": 0,                 # 0 == disabled by default for generic prompts
    "wall_of_text_chars": 1200,               # single paragraph w/o blank line
    "redundant_similarity": 0.92,             # near-duplicate sentence ratio (difflib)
}

def load_config(start: str = ".") -> Config:
    """Search upward from `start` for `.promptproof.toml`, else `pyproject.toml`
    [tool.promptproof]. Uses stdlib tomllib. Missing file => Config() with DEFAULTS."""
```
Config file keys mirror CLI: `select`, `ignore`, `severity` (table id->level),
`fail-level`, plus any DEFAULTS threshold key. `thresholds` start as a copy of DEFAULTS
merged with file overrides.

### 3.8 `engine.py`

```python
def lint_text(text: str, *, path: str = "<text>", kind: DocKind | None = None,
              config: Config | None = None) -> list[Finding]:
def lint_file(path: str, *, kind: DocKind | None = None,
              config: Config | None = None) -> list[Finding]:
def lint_paths(paths: Iterable[str], *, config: Config | None = None) -> list[Finding]:
def discover(paths: Iterable[str]) -> list[str]:
    """Expand dirs to lintable files. Include: *.md, *.markdown, *.txt, *.prompt, and
    *.json only when basename suggests a tool spec OR under a `tools/`/`mcp` dir. Skip:
    hidden dirs except `.claude`; skip node_modules, .git, .venv, venv, dist, build,
    __pycache__, vendor. Honor a simple .promptproofignore (gitignore-lite) if present."""
```
Engine algorithm (`lint_text`):
1. Build `Document.from_text(text, path=path, kind=kind)`.
2. Resolve config (arg or `Config()` defaults).
3. `ctx = Context(config)`.
4. For each rule in `rules_for_kind(doc.kind)`: if rule enabled under config
   (select/ignore by id OR category), call `rule.check(doc, ctx)` inside try/except.
   On exception, append a synthetic `Finding(rule="PP901", name="internal-error",
   severity=INFO, ...)` and continue (never crash the run).
5. Apply per-id severity overrides.
6. Sort by `Finding.sort_key()`; return.

`lint_paths` runs `discover`, then `lint_file` each, concatenes, returns sorted.

Rule enablement logic (shared helper `is_enabled(meta, config)`):
- if `config.select` is not None: enabled iff `meta.id in select` or `meta.category in
  select`. else: enabled by default (all rules default-on in v0.1).
- then: disabled if `meta.id in ignore` or `meta.category in ignore`.

### 3.9 `reporters.py`

```python
def render(findings: list[Finding], fmt: str = "text", *, summary: bool = True,
           color: bool | None = None, elapsed_ms: float | None = None) -> str:
```
- `text` (default): group by path; one line per finding:
  `  {path}:{line}:{col}: {PPID} {message}` with severity-colored `PPID` (red error,
  yellow warning, blue info) when color on. `hint` on an indented `→ {hint}` line.
  Footer: `{E} error(s), {W} warning(s), {I} info  ·  0 API calls  ·  {ms}ms`. When zero
  findings: `All prompts proofed ✓  ·  0 API calls  ·  {ms}ms`.
  Color auto: on only if `color is True`, or (`color is None` and stdout isatty and not
  `NO_COLOR` env). Line/col of 0 render as `-`.
- `json`: `{"findings": [ {rule,name,severity,message,path,line,col,end_line,hint} ... ],
  "summary": {"error":E,"warning":W,"info":I,"files": n}}`. Stable key order. `json.dumps(indent=2)`.
- `github`: one workflow command per finding:
  `::{level} file={path},line={line},col={col},title={PPID} {name}::{message}` where
  level is `error` for ERROR else `warning` (info also `warning`). Lines with line==0 omit
  line/col params.
- `sarif`: minimal SARIF 2.1.0 log (tool driver name `promptproof`, rules + results with
  `level` mapped error->error, warning->warning, info->note). One object, `json.dumps`.

---

## 4. CLI (`promptproof`)

argparse only (no Typer/Click). `prog="promptproof"`.

```
promptproof [PATHS ...] [options]      # default: lint
promptproof rules [--category C] [--json]
promptproof explain PPID
promptproof version
```
Default-command options:
- positional `PATHS` (files or dirs; default `.`). `-` reads one document from stdin.
- `--format {text,json,github,sarif}` default `text`. If unset and env `GITHUB_ACTIONS`
  == "true", auto-switch to `github`.
- `--select RULES` comma-separated ids/categories (repeatable / comma list).
- `--ignore RULES` comma-separated ids/categories.
- `--kind {skill,subagent,command,mcp-tool,prompt}` force kind (esp. for stdin/single file).
- `--config PATH` explicit config file.
- `--fail-level {error,warning,info}` override exit threshold (default from config: warning).
- `--exit-zero` always exit 0 (report only).
- `--no-summary`, `--quiet` (errors only, suppress info), `--no-color` / `--color`.

Exit codes:
- `0`: no findings at/above fail-level (or `--exit-zero`).
- `1`: at least one finding at/above fail-level.
- `2`: usage / config / IO error (print `promptproof: error: ...` to stderr).

`rules`: print a table (id, severity, category, name — summary). `--json` emits the list.
`explain PPID`: print id/name/category/severity, the rationale, and a BAD vs GOOD snippet.
Each rule module must provide `explain` text via `RuleMeta`? No — keep `RuleMeta` lean;
put explain text in a module-level dict `EXPLAIN: dict[str,str]` per rules file, and
`cli` aggregates them via a `rules.base.explain_for(id)` helper that rule modules feed with
`register_explain(id, text)`. Builders: call `register_explain("PP404", "...bad...good...")`
at import time next to each rule.

---

## 5. Rule design contract (READ BEFORE WRITING ANY RULE)

A good rule here mirrors the repo's `CONTRIBUTING` ethos: **a wrong rule is worse than no
rule.** Therefore:
- **Precision over recall.** If a heuristic would fire on legitimate prose, make it
  `INFO`, narrow the trigger, or gate it behind config. Default severities below are
  chosen with this in mind.
- **Deterministic & offline.** Regex / string / structural only. No network, no model.
- **Localized.** Report the exact line/col of the offending token when possible (find the
  match span). Whole-file findings use line 0.
- **Actionable `hint`.** Every WARNING/ERROR finding should suggest the fix.
- **Cheap.** O(n) over the text; compile regexes at module load.
- **Self-tested.** Ship `tests/test_<group>.py` with at least one positive (fires) and one
  negative (must-NOT-fire / known-good) case per rule. Negative cases are mandatory — they
  are the false-positive guard.

Imperative-target detection helper (shared, put in `rules/base.py` as functions):
- `imperative_lines(doc)` → body lines that look like instructions (start with a verb /
  bullet / "you must|should|always|never|do not").
- `sentences(text)` → naive sentence split on `[.!?\n]`.
Builders reuse these instead of re-implementing.

---

## 6. Rule catalog (IDs, names, severities are FROZEN — implement exactly)

Category slugs: `clarity`, `consistency`, `economy`, `triggering`, `structure`, `safety`,
`internal`. Severity letters: E=error, W=warning, I=info. "Kinds" = applicable DocKinds
(`*` = all).

### clarity — PP1xx (kinds: *)
- **PP101 ambiguous-directive** (W): directive relies on a vague qualifier with no concrete
  criterion — `appropriately`, `properly`, `correctly`, `as needed`, `as appropriate`,
  `handle it`, `etc.`, `and so on`, `and so forth`. Fire only inside an imperative/instruction
  line. hint: name the concrete condition.
- **PP102 vague-quantifier** (I): `some|several|a few|many|most|a lot of|a couple` modifying a
  countable the model must produce (e.g. "give some examples"). hint: state a number.
- **PP103 unresolved-pronoun** (I): a sentence in the body starts with `It|This|That|These|
  Those|They` + verb, with no noun in the **same** sentence. Heuristic, INFO only.
- **PP104 subjective-criterion** (I): acceptance worded only as `good|nice|high[- ]quality|
  better|best|appropriate|reasonable` with no measurable criterion.
- **PP105 weak-modal** (I): instruction softened by `try to|maybe|perhaps|if possible|ideally|
  when convenient` where a firm directive is expected.

### consistency — PP2xx (kinds: *)
- **PP201 contradictory-directive** (E): an `always|must|require|ensure` directive about target
  X co-occurs with a `never|must not|do not|don't|avoid` directive about the same target X.
  Match by extracting the directive's object noun-phrase and pairing positive/negative. Be
  conservative (precision): only fire when the same salient token/lemma appears on both sides.
- **PP202 conflicting-format** (W): two incompatible output-format demands, e.g. `json` and
  `plain (text|prose)` / `markdown table` / `yaml`. Detect format keywords near
  "respond|output|return|format|reply".
- **PP203 conflicting-length** (W): a brevity word (`brief|concise|short|terse|succinct|one
  sentence`) co-occurs with a verbosity word (`detailed|thorough|comprehensive|exhaustive|
  in depth|step by step|elaborate`).
- **PP204 conflicting-persona** (I): two distinct `You are a/an <role>` declarations with
  different roles, or a formal vs casual tone pair (`formal|professional` with
  `casual|playful|fun|informal`).

### economy — PP3xx (kinds: * unless noted)
- **PP301 politeness-padding** (W): system-prompt courtesy filler — `please|kindly|thank you|
  thanks|if you (would|could|don't mind)|I would like you to|I want you to|could you( please)?`.
  hint: drop it; imperatives are clearer to models. (config: `economy.allow_politeness`
  disables.)
- **PP302 filler-phrase** (W): wordy connectives with a shorter form — `in order to`→`to`,
  `it is important to note that`/`please note that`/`needless to say`/`as a matter of fact`/
  `at the end of the day`/`due to the fact that`→`because`. Provide the rewrite in hint.
- **PP303 redundant-restatement** (W): two body sentences with `difflib.SequenceMatcher` ratio
  ≥ `redundant_similarity` (default 0.92). Report the second; hint: remove the duplicate.
- **PP304 wall-of-text** (I): a single paragraph (run of non-blank lines) whose char length
  exceeds `wall_of_text_chars` (default 1200). hint: break into bullets/sections.
- **PP305 token-budget** (W; kinds: skill, subagent, prompt): body `estimate_tokens` exceeds
  `token_budget.<kind>` (0 disables). Message states estimate vs budget and overage %.
- **PP306 decorative-banner** (W): lines that are pure ASCII/box-art or emoji banners
  (`^[\s#=*\-_~░▒▓█•·—]+$` length ≥ 12, or a line that is ≥ 80% a single repeated punctuation
  char, or an all-emoji line ≥ 6 glyphs). Wastes tokens; agentskills.io discourages. Skip
  fenced code blocks and markdown table separators (`|---|`).

### triggering — PP4xx (kinds: skill, subagent, mcp-tool unless noted)
- **PP401 description-missing** (E): no `description` (frontmatter for skill/subagent/command;
  the `description` field for an MCP tool spec).
- **PP402 description-too-short** (W): description length < `description_min_chars` (default 40).
- **PP403 description-too-long** (W; skill kinds only): description length >
  `description_max_chars` (default 1024). (E if > 2× the limit.)
- **PP404 weak-trigger** (W): the flagship rule. Description reads as a *summary* not a
  *trigger*. Fire when description does NOT contain any trigger cue
  (`use (this )?when|when the user|when you need|for <gerund>|trigger|invoke when|if (the
  user|you)`) AND/OR it opens with a summary frame (`^(a |an |this (skill|tool|agent|command)
  |tool to |helps you |used to )`). hint: rewrite as "Use when <condition> — e.g. <example>".
- **PP405 first-person-description** (I): description written in first person (`I (will|can|
  help|am)`) instead of third-person trigger framing.
- **PP406 tool-param-undocumented** (W; kinds: mcp-tool): a property in the tool's
  input schema has no `description`. One finding per undocumented param.

### structure — PP5xx (kinds: skill, subagent, command unless noted)
- **PP501 frontmatter-missing** (E): a skill/subagent/command file with no `---` frontmatter
  block at all.
- **PP502 frontmatter-invalid** (E): a `---` block exists but failed to parse
  (`Document.frontmatter_error` set).
- **PP503 name-missing** (E): required `name` field absent from frontmatter.
- **PP504 name-not-kebab** (W): `name` is not `^[a-z0-9]+(-[a-z0-9]+)*$`.
- **PP505 name-dir-mismatch** (W; kinds: skill): `name` != parent directory basename (only
  when the file is literally `SKILL.md` in a named dir).
- **PP506 missing-verify-guidance** (I; kinds: skill): a procedural skill body has no
  verify/check guidance (no line matching `verif|how to (check|confirm)|to confirm|validate`).
  INFO; gated by config `structure.require_verify` to escalate.
- **PP507 unknown-frontmatter-key** (I): a frontmatter key outside the known set for that kind
  (skill: name, description, version, license, allowed-tools, metadata; subagent: name,
  description, tools, model, color; command: name, description, argument-hint, model,
  allowed-tools). INFO.

### safety — PP6xx (kinds: *)
- **PP601 secret-in-prompt** (E): a hardcoded credential pattern — OpenAI `sk-[A-Za-z0-9]{20,}`,
  Anthropic `sk-ant-[A-Za-z0-9-]{20,}`, AWS `AKIA[0-9A-Z]{16}`, GitHub `gh[pousr]_[A-Za-z0-9]{36}`,
  Slack `xox[baprs]-...`, a JWT `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`, or
  `Bearer <token>`. Report location; **never echo the full secret** in the message (mask all
  but first 4 chars).
- **PP602 injection-phrase** (W): literal override phrases embedded in a prompt asset —
  `ignore (all )?(the )?previous instructions|disregard (the )?(above|previous)|forget
  everything (above|before)`. Often unintended in a system prompt. hint: if intentional
  (red-team fixture), add `# promptproof: ignore PP602`.
- **PP603 pii-example** (I): a real-looking email, US phone, SSN, or credit-card number in the
  body (not a placeholder like `user@example.com`, `xxx`, `<email>`, `555-`). hint: use a
  placeholder.

### internal — PP9xx
- **PP901 internal-error** (I): a rule raised; engine-synthesized. Not user-authored.

**Inline suppression:** a finding is dropped if the offending line (or the line above) ends
with `# promptproof: ignore <PPID>[,<PPID>...]` or `<!-- promptproof: ignore PP602 -->`.
Implement in the engine after collecting findings (shared, not per-rule).

Total authored rules: **31** (PP101-105, PP201-204, PP301-306, PP401-406, PP501-507,
PP601-603).

---

## 7. Output examples (golden — match shape)

`promptproof examples/bad-skill/SKILL.md`:
```
examples/bad-skill/SKILL.md:
  2:14: PP404 weak trigger: description summarizes instead of stating when to use it
        → rewrite as "Use when <condition> — e.g. <trigger example>"
  2:14: PP403 description too long: 1180 chars (limit 1024)
  9:1:  PP306 decorative banner wastes ~40 tokens
  -:-:  PP305 token budget: body ~7,200 tokens, 44% over budget (5,000)

0 errors, 4 warnings, 0 info  ·  0 API calls  ·  6ms
```

`promptproof --format github` emits `::warning file=...,line=2,col=14,title=PP404 weak-trigger::...`.

---

## 8. Tests (pytest, no network)

- `tests/test_engine.py` — detect/kind routing, discover() filtering, exception isolation
  (a deliberately throwing dummy rule yields PP901, run survives), inline suppression,
  fail-level/exit math (test a helper `exit_code(findings, fail_level)`).
- `tests/test_parsers.py`, `tests/test_tokens.py`, `tests/test_detect.py`,
  `tests/test_config.py`, `tests/test_reporters.py` (each format renders & round-trips).
- `tests/test_rules_<group>.py` — per rule: ≥1 firing case + ≥1 non-firing (known-good) case.
- `tests/test_cli.py` — `main([...])` returns expected exit codes; `rules`/`explain`/`version`.
- Provide `main(argv: list[str] | None = None) -> int` in `cli.py` for testability.
- Add a dogfood test: linting `examples/good-skill/SKILL.md` yields **zero** findings at
  WARNING+.

Target: clean `ruff check` (config in pyproject, line-length 100, select E,F,I,UP,B) and a
green `pytest` on 3.11-3.13.

---

## 9. Public API (`promptproof/__init__.py` exports)

```python
__all__ = [
    "Severity", "Location", "Finding", "DocKind", "Document",
    "Config", "load_config",
    "lint_text", "lint_file", "lint_paths", "discover",
    "render", "all_rules", "get_rule", "estimate_tokens", "__version__",
]
__version__ = "0.1.0"
```

---

## 10. Distribution / meta

- `pyproject.toml`: hatchling; `requires-python = ">=3.11"`; `[project.scripts]
  promptproof = "promptproof.cli:main"`; extras `mcp`, `yaml`, `dev`; ruff + pytest config;
  keywords (mcp, claude, skills, prompt, linter, agent, ci, prompt-engineering); URLs to
  `github.com/shaxzodbek-uzb/promptproof`.
- `action.yml`: composite action — `uses: actions/setup-python`, `pip install promptproof`,
  run `promptproof --format github ${{ inputs.paths }}`. Inputs: `paths` (default `.`),
  `fail-level`, `select`, `ignore`.
- `.pre-commit-hooks.yaml`: id `promptproof`, entry `promptproof`, language `python`,
  types `[markdown]` + files for `SKILL.md`.
- README: lead with the honest positioning (§1), a 15-second quickstart
  (`uvx promptproof .`), an asciinema-style output block, the rule table, config example,
  CI + pre-commit snippets, and a "how it compares" section naming the alternatives fairly.
- LICENSE MIT; CHANGELOG (Keep a Changelog); CONTRIBUTING (mirror laravel-guardrails ethos:
  a wrong rule is worse than no rule; every rule needs a negative test).

Dogfood: CI runs `promptproof examples/` and `promptproof` over the repo's own `.md`.
```
```
```
```

> Builders: when something here is ambiguous, choose the **lower-false-positive** option and
> note it in a code comment. Do not add public API beyond §9. Do not add runtime deps to core.

"""promptproof — fast, deterministic, zero-API linter for AI agent prompt assets.

Public API is intentionally small and stable; see ``SPEC.md`` §9.
"""

from __future__ import annotations

from .baseline import Baseline, BaselineError
from .config import Config, load_config
from .document import DocKind, Document
from .engine import discover, exit_code, lint_file, lint_paths, lint_text
from .finding import Edit, Finding, Location, Severity
from .fixer import FixResult, fix_file, fix_text
from .reporters import render
from .rules import all_rules, get_rule
from .tokens import estimate_tokens

__version__ = "0.2.0"

__all__ = [
    "Severity",
    "Location",
    "Finding",
    "Edit",
    "DocKind",
    "Document",
    "Config",
    "load_config",
    "lint_text",
    "lint_file",
    "lint_paths",
    "discover",
    "exit_code",
    "fix_text",
    "fix_file",
    "FixResult",
    "Baseline",
    "BaselineError",
    "render",
    "all_rules",
    "get_rule",
    "estimate_tokens",
    "__version__",
]

"""promptproof — fast, deterministic, zero-API linter for AI agent prompt assets.

Public API is intentionally small and stable; see ``SPEC.md`` §9.
"""

from __future__ import annotations

from .config import Config, load_config
from .document import DocKind, Document
from .engine import discover, exit_code, lint_file, lint_paths, lint_text
from .finding import Finding, Location, Severity
from .reporters import render
from .rules import all_rules, get_rule
from .tokens import estimate_tokens

__version__ = "0.1.0"

__all__ = [
    "Severity",
    "Location",
    "Finding",
    "DocKind",
    "Document",
    "Config",
    "load_config",
    "lint_text",
    "lint_file",
    "lint_paths",
    "discover",
    "exit_code",
    "render",
    "all_rules",
    "get_rule",
    "estimate_tokens",
    "__version__",
]

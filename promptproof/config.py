"""Configuration: defaults, the :class:`Config` object, and file discovery.

Config is resolved from (in order) ``.promptproof.toml`` or a ``[tool.promptproof]``
table in ``pyproject.toml``, found by walking up from the start directory. Everything is
optional — with no config file at all you get sensible, low-false-positive defaults.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field

from .finding import Severity

DEFAULTS: dict[str, object] = {
    "description_min_chars": 40,
    "description_max_chars": 1024,
    "token_budget.skill": 5000,
    "token_budget.subagent": 3000,
    "token_budget.prompt": 0,  # 0 disables the budget check for generic prompts
    "wall_of_text_chars": 1200,
    "redundant_similarity": 0.92,
    "redundant_max_sentences": 800,
    "conflict_proximity_lines": 4,
}

_CONFIG_FILENAMES = (".promptproof.toml", "pyproject.toml")


@dataclass
class Config:
    select: frozenset[str] | None = None
    ignore: frozenset[str] = frozenset()
    severity: dict[str, Severity] = field(default_factory=dict)
    thresholds: dict[str, object] = field(default_factory=lambda: dict(DEFAULTS))
    fail_level: Severity = Severity.WARNING

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        select = data.get("select")
        ignore = data.get("ignore", [])
        severity = {
            k: Severity.parse(v) for k, v in (data.get("severity") or {}).items()
        }
        thresholds = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in data:
                thresholds[key] = data[key]
        # also accept a nested [tool.promptproof.thresholds] table
        for key, val in (data.get("thresholds") or {}).items():
            thresholds[key] = val
        fail_level = Severity.parse(data.get("fail-level", data.get("fail_level", "warning")))
        return cls(
            select=frozenset(select) if select is not None else None,
            ignore=frozenset(ignore),
            severity=severity,
            thresholds=thresholds,
            fail_level=fail_level,
        )


def _read_toml_config(path: str) -> dict | None:
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if os.path.basename(path) == "pyproject.toml":
        return data.get("tool", {}).get("promptproof")
    # .promptproof.toml: top-level keys are the norm, but also accept an optional
    # [promptproof] or [tool.promptproof] table so a pyproject snippet pasted here works.
    if isinstance(data.get("promptproof"), dict):
        return data["promptproof"]
    tool = data.get("tool")
    if isinstance(tool, dict) and isinstance(tool.get("promptproof"), dict):
        return tool["promptproof"]
    return data


def load_config(start: str = ".", *, explicit: str | None = None) -> Config:
    if explicit:
        data = _read_toml_config(explicit)
        return Config.from_dict(data or {})
    here = os.path.abspath(start)
    if os.path.isfile(here):
        here = os.path.dirname(here)
    while True:
        for name in _CONFIG_FILENAMES:
            candidate = os.path.join(here, name)
            if os.path.isfile(candidate):
                data = _read_toml_config(candidate)
                if data is not None:
                    return Config.from_dict(data)
        parent = os.path.dirname(here)
        if parent == here:
            return Config()
        here = parent

"""Rule package: auto-discovers and imports every ``ppNNN_*.py`` module so their
``@register`` decorators run, then re-exports the registry API from :mod:`base`.

Drop a new ``pp4xx_*.py`` file in this directory and it is picked up automatically — no
central list to edit.
"""

from __future__ import annotations

import importlib
import pkgutil

from .base import (
    Context,
    Rule,
    RuleMeta,
    all_rules,
    explain_for,
    get_rule,
    register,
    register_explain,
    rules_for_kind,
)

__all__ = [
    "Context",
    "Rule",
    "RuleMeta",
    "all_rules",
    "explain_for",
    "get_rule",
    "register",
    "register_explain",
    "rules_for_kind",
]


def _discover() -> None:
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("pp"):
            importlib.import_module(f"{__name__}.{mod.name}")


_discover()

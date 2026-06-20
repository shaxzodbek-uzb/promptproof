"""Optional MCP server wrapper — expose promptproof as a single MCP tool.

This module is **not** imported by the core (``integrations/__init__.py`` stays import-free),
so the heavy ``mcp`` dependency is only pulled in when someone explicitly builds the server.
Install it via the optional extra::

    pip install 'promptproof[mcp]'

Then, in your own MCP host process::

    from promptproof.integrations.mcp import build_mcp_server

    server = build_mcp_server()
    server.run()  # FastMCP's stdio transport

The server exposes one tool, ``lint_prompt(text, kind="", fmt="json")``, which runs the
fully offline, zero-API linter and returns the rendered findings as a string.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime by core
    from mcp.server.fastmcp import FastMCP


def build_mcp_server(name: str = "promptproof") -> FastMCP:
    """Build and return a FastMCP server exposing the ``lint_prompt`` tool.

    The ``mcp`` package is imported lazily so the core has zero runtime dependencies. If it
    is not installed, a clean :class:`ImportError` explains how to install the extra.
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise ImportError(
            "promptproof[mcp] extra not installed: pip install 'promptproof[mcp]'"
        ) from exc

    from .. import DocKind, lint_text, render

    server = FastMCP(name)

    @server.tool()
    def lint_prompt(text: str, kind: str = "", fmt: str = "json") -> str:
        """Lint a prompt asset and return findings.

        Args:
            text: The prompt asset source (SKILL.md, sub-agent, MCP tool JSON, prompt, …).
            kind: Force the document kind: one of ``skill``, ``subagent``, ``command``,
                ``mcp-tool``, ``prompt``. Empty string auto-detects.
            fmt: Output format: ``json`` (default), ``text``, ``github``, or ``sarif``.
        """
        findings = lint_text(text, kind=DocKind(kind) if kind else None)
        return render(findings, fmt)

    return server

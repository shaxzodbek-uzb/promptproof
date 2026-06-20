"""Frontmatter parsing.

Dependency-free by default: a small, forgiving YAML *subset* parser that covers the
shapes real ``SKILL.md`` / sub-agent / command frontmatter actually use — top-level
scalars, inline ``[a, b]`` lists, ``-`` block lists, and one level of nested mapping.
If the optional ``pyyaml`` extra is installed we prefer it for robustness and only fall
back to the subset parser.

The parser is intentionally lenient: it returns an *error* (which lets rule PP502 fire)
only when a ``---`` fenced block is clearly not a mapping at all. Anything it can make
partial sense of is returned best-effort, to keep false positives near zero.
"""

from __future__ import annotations

import re

FrontmatterResult = tuple[dict | None, tuple[int, int] | None, str | None]

_KEY = re.compile(r"^(?P<indent>[ \t]*)(?P<key>[A-Za-z0-9_.-]+):(?P<rest>.*)$")
_LIST_ITEM = re.compile(r"^[ \t]*-[ \t]+(?P<val>.*\S)\s*$")


def _coerce(value: str):
    v = value.strip()
    if not v:
        return ""
    if (v[0] == v[-1]) and v[0] in "\"'" and len(v) >= 2:
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none", "~"):
        return None
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_coerce(x) for x in _split_inline_list(inner)]
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _split_inline_list(inner: str) -> list[str]:
    parts, buf, depth, quote = [], [], 0, ""
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def _find_fence(lines: list[str]) -> tuple[int, int] | None:
    """Return (open_idx, close_idx) 0-based for a leading ``---`` block, or None."""
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return None
    for j in range(i + 1, len(lines)):
        if lines[j].strip() in ("---", "..."):
            return (i, j)
    return None


def _parse_subset(block: list[str]) -> tuple[dict | None, str | None]:
    data: dict = {}
    i = 0
    n = len(block)
    while i < n:
        raw = block[i]
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = _KEY.match(line)
        if not m or m.group("indent"):
            # Not a top-level key line (could be a stray list item or junk). Skip it
            # rather than failing the whole block — leniency keeps PP502 rare.
            i += 1
            continue
        key = m.group("key")
        rest = m.group("rest").strip()
        if rest:
            data[key] = _coerce(rest)
            i += 1
            continue
        # Empty value: look ahead for a block list or a nested mapping.
        items: list = []
        nested: dict = {}
        j = i + 1
        while j < n:
            nxt = block[j]
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                j += 1
                continue
            if not (nxt.startswith(" ") or nxt.startswith("\t")):
                break
            li = _LIST_ITEM.match(nxt)
            if li:
                items.append(_coerce(li.group("val")))
                j += 1
                continue
            nm = _KEY.match(nxt.strip())
            if nm:
                nested[nm.group("key")] = _coerce(nm.group("rest").strip())
                j += 1
                continue
            j += 1
        if items:
            data[key] = items
        elif nested:
            data[key] = nested
        else:
            data[key] = None
        i = j if j > i + 1 else i + 1
    if not data:
        return None, "frontmatter block contains no key: value pairs"
    return data, None


def parse_frontmatter(text: str) -> FrontmatterResult:
    """Parse a leading ``---`` frontmatter block.

    Returns ``(mapping, (start_line, end_line), error)`` where line numbers are 1-based
    and inclusive of the fences. ``(None, None, None)`` means there is no frontmatter.
    ``(None, span, "reason")`` means a fenced block existed but could not be parsed.
    """
    lines = text.splitlines()
    fence = _find_fence(lines)
    if fence is None:
        return None, None, None
    open_idx, close_idx = fence
    span = (open_idx + 1, close_idx + 1)
    block = lines[open_idx + 1 : close_idx]

    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load("\n".join(block))
        if isinstance(loaded, dict):
            return loaded, span, None
        if loaded is None or block == []:
            return None, span, "frontmatter block is empty"
        return None, span, "frontmatter is not a mapping"
    except ImportError:
        pass
    except Exception as exc:  # pragma: no cover - yaml parse errors are env-specific
        return None, span, f"yaml error: {exc}"

    data, err = _parse_subset(block)
    return data, span, err

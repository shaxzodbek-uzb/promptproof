"""parse_frontmatter: scalars, lists, types, spans, and the bad-block error path."""

from __future__ import annotations

from promptproof.parsers import parse_frontmatter


def test_no_fence_returns_all_none():
    fm, span, err = parse_frontmatter("# Title\n\njust a body, no frontmatter\n")
    assert fm is None
    assert span is None
    assert err is None


def test_empty_text_has_no_frontmatter():
    fm, span, err = parse_frontmatter("")
    assert (fm, span, err) == (None, None, None)


def test_parses_scalars_and_quoted_strings():
    text = "---\nname: my-skill\ntitle: 'Quoted Title'\nother: \"dq\"\n---\nbody\n"
    fm, span, err = parse_frontmatter(text)
    assert err is None
    assert fm["name"] == "my-skill"
    assert fm["title"] == "Quoted Title"
    assert fm["other"] == "dq"


def test_parses_typed_scalars():
    text = "---\nflag: true\noff: false\nempty: null\ncount: 3\nratio: 1.5\n---\n"
    fm, _, err = parse_frontmatter(text)
    assert err is None
    assert fm["flag"] is True
    assert fm["off"] is False
    assert fm["empty"] is None
    assert fm["count"] == 3
    assert fm["ratio"] == 1.5


def test_parses_inline_list():
    text = "---\ntools: [Read, Write, Bash]\n---\n"
    fm, _, err = parse_frontmatter(text)
    assert err is None
    assert fm["tools"] == ["Read", "Write", "Bash"]


def test_parses_block_list():
    text = "---\ntools:\n  - Read\n  - Write\n  - Bash\n---\n"
    fm, _, err = parse_frontmatter(text)
    assert err is None
    assert fm["tools"] == ["Read", "Write", "Bash"]


def test_span_is_1based_inclusive_of_fences():
    text = "---\nname: x\ndescription: hello\n---\nbody\n"
    _, span, _ = parse_frontmatter(text)
    # fences on file lines 1 and 4 (1-based, inclusive)
    assert span == (1, 4)


def test_span_skips_leading_blank_lines():
    text = "\n\n---\nname: x\n---\nbody\n"
    _, span, _ = parse_frontmatter(text)
    assert span == (3, 5)


def test_non_mapping_block_returns_error_and_span():
    # A fenced block with no `key: value` pairs at all is not a mapping.
    text = "---\njust a sentence with no colon keys\n---\nbody\n"
    fm, span, err = parse_frontmatter(text)
    assert fm is None
    assert span == (1, 3)
    assert err is not None


def test_unterminated_fence_is_not_frontmatter():
    text = "---\nname: x\nno closing fence here\n"
    fm, span, err = parse_frontmatter(text)
    assert (fm, span, err) == (None, None, None)

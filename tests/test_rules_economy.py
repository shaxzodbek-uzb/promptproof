"""Economy rules (PP3xx). Every rule has a firing case AND a known-good case."""

from __future__ import annotations

from promptproof import Config, DocKind, lint_text
from tests.conftest import ids

# A clean, short, instruction-shaped prompt that must trip none of PP3xx.
GOOD = (
    "# Summarizer\n\n"
    "Summarize the document in three bullet points.\n"
    "Return valid JSON with a `summary` array.\n\n"
    "## Notes\n\n"
    "Keep each bullet under 20 words.\n"
)


def test_good_prompt_has_no_economy_findings():
    assert not {i for i in ids(GOOD, kind=DocKind.PROMPT) if i.startswith("PP3")}


# ----------------------------------------------------------------------- PP301

def test_pp301_politeness_padding_fires():
    text = "# Task\n\nPlease summarize the document, thank you.\n"
    assert "PP301" in ids(text, kind=DocKind.PROMPT)


def test_pp301_one_finding_per_line():
    text = "# Task\n\nPlease, kindly, could you summarize this for me?\n"
    found = [f for f in lint_text(text, kind=DocKind.PROMPT) if f.rule == "PP301"]
    assert len(found) == 1


def test_pp301_does_not_fire_on_imperative_prose():
    text = "# Task\n\nSummarize the document in three bullets.\n"
    assert "PP301" not in ids(text, kind=DocKind.PROMPT)


def test_pp301_gate_disables():
    text = "# Task\n\nPlease summarize the document.\n"
    cfg = Config(thresholds={"economy.allow_politeness": True})
    found = {f.rule for f in lint_text(text, kind=DocKind.PROMPT, config=cfg)}
    assert "PP301" not in found


# ----------------------------------------------------------------------- PP302

def test_pp302_filler_phrase_fires():
    text = "# Task\n\nDue to the fact that the file is large, stream it.\n"
    found = [f for f in lint_text(text, kind=DocKind.PROMPT) if f.rule == "PP302"]
    assert found and "because" in (found[0].hint or "")


def test_pp302_in_order_to_fires():
    text = "# Task\n\nRead the file in order to extract the title.\n"
    found = [f for f in lint_text(text, kind=DocKind.PROMPT) if f.rule == "PP302"]
    assert found and '"to"' in (found[0].hint or "")


def test_pp302_does_not_fire_on_clean_prose():
    text = "# Task\n\nStream the file because it is large.\n"
    assert "PP302" not in ids(text, kind=DocKind.PROMPT)


# ----------------------------------------------------------------------- PP303

def test_pp303_redundant_restatement_fires():
    text = (
        "# Task\n\n"
        "Always validate the user input before processing the request.\n"
        "Always validate the user input before processing the request now.\n"
    )
    assert "PP303" in ids(text, kind=DocKind.PROMPT)


def test_pp303_does_not_fire_on_distinct_sentences():
    text = (
        "# Task\n\n"
        "Validate the user input before processing the request.\n"
        "Log every error to the structured audit trail for later review.\n"
    )
    assert "PP303" not in ids(text, kind=DocKind.PROMPT)


def test_pp303_ignores_short_sentences():
    # Short identical sentences (< 25 chars) must not trip the rule.
    text = "# Task\n\nDo it.\nDo it.\nDo it.\n"
    assert "PP303" not in ids(text, kind=DocKind.PROMPT)


# ----------------------------------------------------------------------- PP304

def test_pp304_wall_of_text_fires():
    para = ("word " * 300).strip()  # ~1500 chars, no blank line
    text = f"# Task\n\n{para}\n"
    assert "PP304" in ids(text, kind=DocKind.PROMPT)


def test_pp304_does_not_fire_on_short_paragraphs():
    text = "# Task\n\nA short paragraph.\n\nAnother short paragraph.\n"
    assert "PP304" not in ids(text, kind=DocKind.PROMPT)


# ----------------------------------------------------------------------- PP305

def test_pp305_token_budget_fires():
    body = "token " * 4000  # well over the 5000-token skill budget
    desc = "Use when the user wants to count many tokens for a budget test."
    text = f"---\nname: x\ndescription: {desc}\n---\n\n{body}\n"
    assert "PP305" in ids(text, kind=DocKind.SKILL)


def test_pp305_does_not_fire_under_budget():
    text = "# Prompt\n\nA short body well under any budget.\n"
    assert "PP305" not in ids(text, kind=DocKind.PROMPT)


def test_pp305_prompt_budget_disabled_by_default():
    body = "token " * 4000
    text = f"# Prompt\n\n{body}\n"
    # token_budget.prompt defaults to 0 -> disabled, even for a huge body.
    assert "PP305" not in ids(text, kind=DocKind.PROMPT)


# ----------------------------------------------------------------------- PP306

def test_pp306_ascii_banner_fires():
    # Box-art / hash banners are decoration, not valid markdown — these still fire.
    text = "# Task\n\n" + "█" * 30 + "\n\nDo the thing.\n"
    assert "PP306" in ids(text, kind=DocKind.PROMPT)
    hashes = "# Task\n\n" + "#" * 30 + "\n\nDo it.\n"
    assert "PP306" in ids(hashes, kind=DocKind.PROMPT)


def test_pp306_setext_and_thematic_break_are_clean():
    # A pure run of markdown structural chars is a thematic break / setext underline /
    # emphasis fence — valid markdown, never a decorative-banner finding.
    for rule in ("---", "===", "***", "___", "~~~", "----------", "==========="):
        text = f"Heading\n{rule}\n\nReal content.\n"
        assert "PP306" not in ids(text, kind=DocKind.PROMPT), rule


def test_pp306_emoji_banner_fires():
    text = "# Task\n\n\U0001f680\U0001f525✨\U0001f389\U0001f4a5⭐\U0001f680\n\nGo.\n"
    assert "PP306" in ids(text, kind=DocKind.PROMPT)


def test_pp306_markdown_table_is_clean():
    text = (
        "# Data\n\n"
        "| Name | Value |\n"
        "|------|-------|\n"
        "| foo  | 1     |\n"
    )
    assert "PP306" not in ids(text, kind=DocKind.PROMPT)


def test_pp306_heading_is_clean():
    text = "# Title\n\n## Section heading\n\nReal content here.\n"
    assert "PP306" not in ids(text, kind=DocKind.PROMPT)


def test_pp306_skips_code_fence():
    text = (
        "# Task\n\n"
        "```\n"
        "========================================\n"
        "```\n\n"
        "Do the thing.\n"
    )
    assert "PP306" not in ids(text, kind=DocKind.PROMPT)

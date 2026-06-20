"""Clarity rules (PP1xx). Every rule has a firing case AND a known-good case."""

from __future__ import annotations

from promptproof import DocKind, lint_text
from tests.conftest import ids


def _body(text: str) -> set[str]:
    """Lint a plain prompt body and return fired rule ids."""
    return ids(text, kind=DocKind.PROMPT, path="p.md")


# A clean instruction must trip none of the clarity rules.
CLEAN = "Return the result as JSON.\n"


def test_clean_instruction_is_silent():
    fired = {i for i in _body(CLEAN) if i.startswith("PP1")}
    assert not fired


# --- PP101 ambiguous-directive ------------------------------------------------------


def test_pp101_fires_inside_imperative():
    # "Format ..." is recognized by the shared is_imperative() cue.
    text = "Format the edge cases appropriately before returning.\n"
    assert "PP101" in _body(text)


def test_pp101_not_in_plain_prose():
    # "appropriately" outside an imperative line must NOT fire (precision guard).
    text = "The library was designed appropriately for this workload.\n"
    assert "PP101" not in _body(text)


# --- PP102 vague-quantifier ---------------------------------------------------------


def test_pp102_fires_on_some_examples():
    text = "Give some examples of valid inputs.\n"
    assert "PP102" in _body(text)


def test_pp102_not_on_exact_count():
    text = "Give 3 examples of valid inputs.\n"
    assert "PP102" not in _body(text)


# --- PP103 unresolved-pronoun -------------------------------------------------------


def test_pp103_fires_on_pronoun_opener():
    text = "Do the task.\nIt should validate the schema first.\n"
    assert "PP103" in _body(text)


def test_pp103_not_when_noun_follows():
    # "This rule ..." has a noun right after the pronoun -> no finding.
    text = "This rule checks the schema before running.\n"
    assert "PP103" not in _body(text)


# --- PP104 subjective-criterion -----------------------------------------------------


def test_pp104_fires_on_make_it_nice():
    text = "Make sure the summary is nice and reads well.\n"
    assert "PP104" in _body(text)


def test_pp104_not_when_measurable_nearby():
    # A measurable criterion on the line defuses the subjective word.
    text = "A good summary is at most 50 words.\n"
    assert "PP104" not in _body(text)


# --- PP105 weak-modal ---------------------------------------------------------------


def test_pp105_fires_on_try_to():
    text = "Try to validate the input before processing.\n"
    assert "PP105" in _body(text)


def test_pp105_not_on_firm_directive():
    text = "Validate the input before processing.\n"
    assert "PP105" not in _body(text)


# --- code-fence skipping (shared guard) ---------------------------------------------


def test_clarity_skips_fenced_code():
    text = (
        "Return JSON.\n\n"
        "```\n"
        "Handle it appropriately and give some examples.\n"
        "Try to do this maybe.\n"
        "```\n"
    )
    fired = {i for i in _body(text) if i.startswith("PP1")}
    assert not fired


def test_pp101_reports_location():
    text = "Format the output correctly.\n"
    found = [f for f in lint_text(text, kind=DocKind.PROMPT, path="p.md") if f.rule == "PP101"]
    assert found
    assert found[0].location.line == 1
    assert found[0].location.col > 0

"""Consistency rules (PP2xx). Every rule has a firing case AND a known-good case.

The known-good cases are the false-positive guard — in particular a normal prompt that
only says "be concise" must NOT trip PP203, and a single "You are a helpful assistant"
must NOT trip PP204.
"""

from __future__ import annotations

from promptproof import DocKind
from tests.conftest import ids


def _con(text: str, kind: DocKind = DocKind.PROMPT) -> set[str]:
    return {i for i in ids(text, kind=kind) if i.startswith("PP2")}


# --------------------------------------------------------------------------- PP201

def test_pp201_fires_on_same_object_always_never():
    text = (
        "Always include the file path in your output.\n"
        "Never include the file path; keep it implicit.\n"
    )
    assert "PP201" in _con(text)


def test_pp201_clean_when_objects_differ():
    text = (
        "Always include the file path in your output.\n"
        "Never reveal the user's password under any circumstance.\n"
    )
    assert "PP201" not in _con(text)


def test_pp201_clean_on_ordinary_prose():
    text = (
        "You must read the document carefully before answering.\n"
        "Avoid speculation when the answer is not stated.\n"
    )
    assert "PP201" not in _con(text)


def test_pp201_ignores_code_fences():
    text = (
        "```\n"
        "always emit metrics\n"
        "never emit metrics\n"
        "```\n"
        "Write a clear summary for the reader.\n"
    )
    assert "PP201" not in _con(text)


# --------------------------------------------------------------------------- PP202

def test_pp202_fires_on_json_and_prose():
    text = (
        "Respond in JSON with a status field.\n"
        "Also answer in plain prose so a human can read it.\n"
    )
    assert "PP202" in _con(text)


def test_pp202_fires_on_json_and_yaml():
    text = "Return your output as JSON. Format the result as YAML instead.\n"
    assert "PP202" in _con(text)


def test_pp202_clean_with_single_format():
    text = "Respond in JSON. Use a top-level object with id and name fields.\n"
    assert "PP202" not in _con(text)


def test_pp202_clean_when_format_words_not_near_output_verb():
    text = (
        "The repository contains a JSON config and a YAML manifest.\n"
        "Read them both to understand the project layout.\n"
    )
    assert "PP202" not in _con(text)


# --------------------------------------------------------------------------- PP203

def test_pp203_fires_on_brief_plus_thorough():
    text = (
        "Keep your answer brief.\n"
        "Provide a thorough, step-by-step explanation of every detail.\n"
    )
    assert "PP203" in _con(text)


def test_pp203_concise_alone_does_not_fire():
    # The critical false-positive guard from the assignment.
    text = "Be concise. Answer the user's question and stop.\n"
    assert "PP203" not in _con(text)


def test_pp203_detailed_alone_does_not_fire():
    text = "Give a thorough, in-depth explanation with examples.\n"
    assert "PP203" not in _con(text)


# --------------------------------------------------------------------------- PP204

def test_pp204_fires_on_two_distinct_roles():
    text = (
        "You are a senior tax attorney.\n"
        "You are a friendly cooking assistant.\n"
    )
    assert "PP204" in _con(text)


def test_pp204_fires_on_formal_and_casual_tone():
    text = (
        "Maintain a formal, professional register at all times.\n"
        "Keep the tone casual and playful so it feels fun.\n"
    )
    assert "PP204" in _con(text)


def test_pp204_single_role_does_not_fire():
    # The critical false-positive guard from the assignment.
    text = "You are a helpful assistant. Answer questions accurately.\n"
    assert "PP204" not in _con(text)


def test_pp204_same_role_repeated_does_not_fire():
    text = (
        "You are a Python expert.\n"
        "Remember, you are a Python expert who writes idiomatic code.\n"
    )
    assert "PP204" not in _con(text)

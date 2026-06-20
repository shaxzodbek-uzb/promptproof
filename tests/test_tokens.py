"""estimate_tokens: empty/whitespace, word-count floor, determinism, rough sanity."""

from __future__ import annotations

import re

from promptproof import estimate_tokens


def test_empty_is_zero():
    assert estimate_tokens("") == 0


def test_whitespace_only_is_zero():
    assert estimate_tokens("   \n\t  \n") == 0


def test_never_below_word_count():
    for text in ("one two three", "a b c d e f g h i j", "word " * 30):
        n_words = len(re.findall(r"\S+", text))
        assert estimate_tokens(text) >= n_words


def test_deterministic():
    text = "The quick brown fox jumps over the lazy dog. " * 5
    assert estimate_tokens(text) == estimate_tokens(text)


def test_monotonic_with_more_text():
    short = "hello world"
    longer = short + " and then a good deal more text follows here today"
    assert estimate_tokens(longer) >= estimate_tokens(short)


def test_dense_text_uses_char_term():
    # No spaces => word count is 1, but chars/4 dominates.
    dense = "x" * 400
    assert estimate_tokens(dense) == 100


def test_paragraph_lands_in_plausible_band():
    # ~100-word English paragraph: estimate should be roughly 1.2-1.6x word count.
    para = ("Linting prompt assets keeps agents reliable before they ship today. " * 10)
    n_words = len(re.findall(r"\S+", para))
    est = estimate_tokens(para)
    assert n_words <= est <= n_words * 2
    assert 100 <= est <= 260

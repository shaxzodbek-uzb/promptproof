"""Mechanical repairs (``--fix``) and the edit-application machinery.

A linter that rewrites someone's prompt library has to be provably conservative, so the
assertions here are as much about what fixing must *not* touch as about what it repairs.
"""

from __future__ import annotations

import pytest

from promptproof.cli import main
from promptproof.engine import lint_text
from promptproof.finding import Edit, Finding, Location, Severity
from promptproof.fixer import MAX_PASSES, apply_edits, fix_file, fix_text


def _fixed(text: str) -> str:
    return fix_text(text, path="x.md").text


# -- edit application --------------------------------------------------------


def _finding(rule: str, edit: Edit) -> Finding:
    return Finding(
        rule=rule,
        name="t",
        severity=Severity.WARNING,
        message="m",
        location=Location("x.md", edit.start_line),
        fix=edit,
    )


def test_edits_apply_bottom_up_so_line_numbers_stay_valid():
    lines = ["one", "two", "three", "four"]
    out, applied = apply_edits(
        lines,
        [
            _finding("A", Edit(1, 1, ("ONE",))),
            _finding("B", Edit(4, 4, ("FOUR",))),
        ],
    )
    assert out == ["ONE", "two", "three", "FOUR"]
    assert len(applied) == 2


def test_deleting_earlier_lines_does_not_shift_later_edits():
    lines = ["drop", "keep", "drop"]
    out, applied = apply_edits(
        lines, [_finding("A", Edit(1, 1, ())), _finding("B", Edit(3, 3, ()))]
    )
    assert out == ["keep"]
    assert len(applied) == 2


def test_overlapping_edits_are_skipped_not_interleaved():
    lines = ["hello world"]
    out, applied = apply_edits(
        lines, [_finding("A", Edit(1, 1, ("first",))), _finding("B", Edit(1, 1, ("second",)))]
    )
    assert len(applied) == 1  # only one rule may rewrite a given line per pass
    assert out == ["first"] or out == ["second"]


def test_out_of_range_edits_are_refused():
    lines = ["only one line"]
    out, applied = apply_edits(lines, [_finding("A", Edit(5, 5, ("x",)))])
    assert out == lines
    assert applied == []


def test_inverted_ranges_are_refused():
    lines = ["a", "b"]
    out, applied = apply_edits(lines, [_finding("A", Edit(2, 1, ("x",)))])
    assert out == lines
    assert applied == []


def test_findings_without_a_fix_are_ignored():
    lines = ["a"]
    plain = Finding("A", "t", Severity.WARNING, "m", Location("x.md", 1))
    assert plain.fixable is False
    out, applied = apply_edits(lines, [plain])
    assert (out, applied) == (lines, [])


# -- PP301 politeness --------------------------------------------------------


def test_leading_please_is_removed_and_the_sentence_recapitalised():
    assert _fixed("Please read the file.\n") == "Read the file.\n"


def test_mid_sentence_courtesy_is_removed_without_a_double_space():
    assert _fixed("You should please check it.\n") == "You should check it.\n"


def test_a_line_that_was_only_courtesy_is_deleted():
    assert _fixed("Do the work.\nThank you.\n") == "Do the work.\n"


def test_courtesy_inside_quotes_is_left_alone():
    """Quoted copy is text the model must emit, not an instruction to the model."""
    text = 'Reply with "Please hold" verbatim.\n'
    assert _fixed(text) == text


def test_a_bullet_keeps_its_marker():
    assert _fixed("- Please run the tests.\n") == "- Run the tests.\n"


# -- PP302 filler ------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("Read it in order to extract text.\n", "Read it to extract text.\n"),
        ("Due to the fact that it varies, check.\n", "Because it varies, check.\n"),
        ("It is important to note that X fails.\n", "X fails.\n"),
        ("Needless to say, run the tests.\n", "Run the tests.\n"),
    ],
)
def test_filler_phrases_are_rewritten(before, after):
    assert _fixed(before) == after


def test_two_fillers_on_one_line_both_go():
    """PP302 reports one match per line, so this only converges because fixing loops."""
    result = fix_text("In order to ship, due to the fact that it is late, hurry.\n", path="x.md")
    assert "in order to" not in result.text.lower()
    assert "due to the fact that" not in result.text.lower()
    assert result.passes >= 2


# -- PP306 banners -----------------------------------------------------------


def test_an_emoji_banner_line_is_deleted():
    assert _fixed("Body text.\n✨ \U0001f389 \U0001f680 \U0001f4a1 ⭐ \U0001f525\n") == (
        "Body text.\n"
    )


def test_a_setext_underline_is_not_a_banner():
    """Pure --- / === runs are valid markdown structure, not decoration."""
    text = "Heading\n=======\n\nBody.\n"
    assert _fixed(text) == text


def test_a_table_separator_survives():
    text = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
    assert _fixed(text) == text


def test_code_fences_are_never_rewritten():
    text = "```\nPlease do not touch in order to keep this exact.\n```\n"
    assert _fixed(text) == text


# -- convergence and file handling -------------------------------------------


def test_fixing_reaches_a_fixed_point():
    result = fix_text("Please please read it.\n", path="x.md")
    assert result.passes < MAX_PASSES
    assert "please" not in result.text.lower()


def test_a_clean_file_is_not_rewritten():
    text = "Read the file.\n"
    result = fix_text(text, path="x.md")
    assert result.changed is False
    assert result.text == text
    assert result.passes == 0


def test_a_trailing_newline_is_preserved():
    assert _fixed("Please go.\n").endswith("\n")


def test_a_missing_trailing_newline_is_not_invented():
    assert not _fixed("Please go.").endswith("\n")


def test_remaining_reports_what_fixing_could_not_repair():
    result = fix_text("Please make it better in some way.\n", path="x.md")
    assert "please" not in result.text.lower()
    # The vague-directive findings are judgement calls and stay for a human.
    assert result.remaining


def test_fix_file_writes_only_when_something_changed(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("Read it.\n", encoding="utf-8")
    before = path.stat().st_mtime_ns
    fix_file(str(path))
    assert path.stat().st_mtime_ns == before  # untouched


def test_fix_file_can_preview_without_writing(tmp_path):
    path = tmp_path / "a.md"
    original = "Please read it.\n"
    path.write_text(original, encoding="utf-8")
    result = fix_file(str(path), write=False)
    assert result.text == "Read it.\n"
    assert path.read_text(encoding="utf-8") == original


# -- CLI ---------------------------------------------------------------------


def test_cli_fix_rewrites_the_file(tmp_path, capsys):
    path = tmp_path / "a.md"
    path.write_text("Please read it in order to learn.\n", encoding="utf-8")
    main([str(tmp_path), "--fix", "--no-color"])
    assert path.read_text(encoding="utf-8") == "Read it to learn.\n"
    assert "fixed 2 finding(s)" in capsys.readouterr().out


def test_cli_diff_previews_without_writing(tmp_path, capsys):
    path = tmp_path / "a.md"
    original = "Please read it.\n"
    path.write_text(original, encoding="utf-8")
    main([str(tmp_path), "--diff", "--no-color"])
    out = capsys.readouterr().out
    assert "-Please read it." in out
    assert "+Read it." in out
    assert path.read_text(encoding="utf-8") == original


def test_cli_fix_rejects_stdin(capsys):
    assert main(["-", "--fix"]) == 2
    assert "need real files" in capsys.readouterr().err


def test_fixing_does_not_change_what_the_remaining_findings_are(tmp_path):
    """After --fix, the file must lint to exactly what the run reported as remaining."""
    path = tmp_path / "a.md"
    path.write_text("Please read it in order to learn something vague.\n", encoding="utf-8")
    result = fix_file(str(path))
    relinted = lint_text(path.read_text(encoding="utf-8"), path=str(path))
    assert [f.rule for f in relinted] == [f.rule for f in result.remaining]

"""The baseline file: accept today's findings, fail only on new ones.

The property that matters is stability under edits — a baseline keyed on line numbers is
worthless the moment anyone inserts a paragraph.
"""

from __future__ import annotations

import json

import pytest

from promptproof.baseline import (
    FORMAT_VERSION,
    Baseline,
    BaselineError,
    fingerprint,
)
from promptproof.cli import main
from promptproof.engine import lint_paths


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


NOISY = "Please read it.\nDue to the fact that it varies, check.\n"


# -- fingerprints ------------------------------------------------------------


def test_a_finding_that_moves_down_the_file_keeps_its_fingerprint(tmp_path):
    _write(tmp_path, "a.md", NOISY)
    before = lint_paths([str(tmp_path)])

    _write(tmp_path, "a.md", "# A new heading\n\nSome new prose.\n\n" + NOISY)
    after = lint_paths([str(tmp_path)])

    keys_before = {fingerprint(f, NOISY.splitlines()) for f in before}
    lines_after = (tmp_path / "a.md").read_text(encoding="utf-8").splitlines()
    keys_after = {fingerprint(f, lines_after) for f in after}
    assert keys_before <= keys_after


def test_changing_the_triggering_text_changes_the_fingerprint(tmp_path):
    _write(tmp_path, "a.md", "Please read it.\n")
    first = lint_paths([str(tmp_path)])[0]
    key_a = fingerprint(first, ["Please read it."])
    key_b = fingerprint(first, ["Please read something else."])
    assert key_a != key_b


def test_the_same_finding_in_two_files_is_two_fingerprints(tmp_path):
    _write(tmp_path, "a.md", "Please read it.\n")
    _write(tmp_path, "b.md", "Please read it.\n")
    findings = lint_paths([str(tmp_path)])
    keys = {fingerprint(f, ["Please read it."]) for f in findings}
    assert len(keys) == len(findings)


# -- filtering ---------------------------------------------------------------


def test_a_baseline_suppresses_exactly_what_it_recorded(tmp_path):
    _write(tmp_path, "a.md", NOISY)
    findings = lint_paths([str(tmp_path)])
    assert findings

    baseline = Baseline.from_findings(findings)
    fresh, suppressed = baseline.filter(findings)
    assert fresh == []
    assert suppressed == len(findings)


def test_a_new_finding_is_not_suppressed(tmp_path):
    _write(tmp_path, "a.md", NOISY)
    baseline = Baseline.from_findings(lint_paths([str(tmp_path)]))

    _write(tmp_path, "a.md", NOISY + "\nIn order to ship, hurry.\n")
    fresh, _ = baseline.filter(lint_paths([str(tmp_path)]))
    assert [f.rule for f in fresh] == ["PP302"]


def test_a_baseline_accepts_a_quantity_not_a_problem_forever(tmp_path):
    """Two identical findings baselined; a third must still surface."""
    _write(tmp_path, "a.md", "Please read it.\nPlease read it.\n")
    baseline = Baseline.from_findings(lint_paths([str(tmp_path)]))
    assert len(baseline) == 2

    _write(tmp_path, "a.md", "Please read it.\nPlease read it.\nPlease read it.\n")
    fresh, suppressed = baseline.filter(lint_paths([str(tmp_path)]))
    assert len(fresh) == 1
    assert suppressed == 2


def test_an_empty_baseline_suppresses_nothing(tmp_path):
    _write(tmp_path, "a.md", NOISY)
    findings = lint_paths([str(tmp_path)])
    fresh, suppressed = Baseline().filter(findings)
    assert fresh == findings
    assert suppressed == 0


# -- persistence -------------------------------------------------------------


def test_save_and_load_round_trip(tmp_path):
    _write(tmp_path, "a.md", NOISY)
    findings = lint_paths([str(tmp_path)])
    path = tmp_path / "baseline.json"

    written = Baseline().save(str(path), findings)
    assert written == len(findings)

    loaded = Baseline.load(str(path))
    fresh, suppressed = loaded.filter(findings)
    assert fresh == []
    assert suppressed == len(findings)


def test_the_saved_file_is_readable_json_with_a_version(tmp_path):
    _write(tmp_path, "a.md", NOISY)
    path = tmp_path / "baseline.json"
    Baseline().save(str(path), lint_paths([str(tmp_path)]))
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == FORMAT_VERSION
    assert isinstance(data["findings"], dict)
    assert "note" in data  # tells whoever finds it in a diff what it is


def test_a_missing_baseline_is_a_loud_error(tmp_path):
    with pytest.raises(BaselineError, match="--write-baseline"):
        Baseline.load(str(tmp_path / "absent.json"))


def test_a_malformed_baseline_is_a_loud_error(tmp_path):
    path = _write(tmp_path, "b.json", "{not json")
    with pytest.raises(BaselineError, match="could not read"):
        Baseline.load(str(path))


def test_a_baseline_from_another_version_is_rejected(tmp_path):
    path = _write(tmp_path, "b.json", json.dumps({"version": 999, "findings": {}}))
    with pytest.raises(BaselineError, match="regenerate"):
        Baseline.load(str(path))


# -- CLI ---------------------------------------------------------------------


def test_cli_write_then_gate_goes_green(tmp_path, capsys):
    _write(tmp_path, "a.md", NOISY)
    baseline = tmp_path / "baseline.json"

    assert main([str(tmp_path), "--write-baseline", str(baseline)]) == 0
    assert "wrote" in capsys.readouterr().out

    assert main([str(tmp_path), "--baseline", str(baseline), "--no-color"]) == 0
    assert "baselined" in capsys.readouterr().out


def test_cli_gate_fails_on_a_finding_added_later(tmp_path, capsys):
    _write(tmp_path, "a.md", NOISY)
    baseline = tmp_path / "baseline.json"
    main([str(tmp_path), "--write-baseline", str(baseline)])
    capsys.readouterr()

    _write(tmp_path, "a.md", NOISY + "\nIn order to ship, hurry.\n")
    assert main([str(tmp_path), "--baseline", str(baseline), "--no-color"]) == 1
    assert "PP302" in capsys.readouterr().out


def test_cli_reports_a_missing_baseline_rather_than_passing(tmp_path, capsys):
    """A silently-empty baseline would turn the gate green for the wrong reason."""
    _write(tmp_path, "a.md", NOISY)
    assert main([str(tmp_path), "--baseline", str(tmp_path / "absent.json")]) == 2
    assert "no baseline" in capsys.readouterr().err


def test_cli_write_baseline_exits_zero_even_with_findings(tmp_path, capsys):
    _write(tmp_path, "a.md", NOISY)
    assert main([str(tmp_path), "--write-baseline", str(tmp_path / "b.json")]) == 0

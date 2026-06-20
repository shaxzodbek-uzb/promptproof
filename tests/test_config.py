"""Config: DEFAULTS, file discovery (.promptproof.toml + pyproject), parsing & merge."""

from __future__ import annotations

from promptproof.config import DEFAULTS, Config, load_config
from promptproof.finding import Severity


def test_defaults_present():
    for key in (
        "description_min_chars",
        "description_max_chars",
        "token_budget.skill",
        "token_budget.subagent",
        "token_budget.prompt",
        "wall_of_text_chars",
        "redundant_similarity",
    ):
        assert key in DEFAULTS


def test_no_config_returns_defaults():
    cfg = Config()
    assert cfg.fail_level is Severity.WARNING
    assert cfg.select is None
    assert cfg.thresholds["description_min_chars"] == 40


def test_loads_dot_promptproof_toml(tmp_path):
    (tmp_path / ".promptproof.toml").write_text(
        'fail-level = "error"\n'
        'ignore = ["PP305"]\n'
        "description_min_chars = 60\n",
        encoding="utf-8",
    )
    cfg = load_config(str(tmp_path))
    assert cfg.fail_level is Severity.ERROR
    assert "PP305" in cfg.ignore
    assert cfg.thresholds["description_min_chars"] == 60


def test_loads_pyproject_tool_table(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.promptproof]\n"
        'fail-level = "info"\n'
        'select = ["triggering"]\n',
        encoding="utf-8",
    )
    cfg = load_config(str(tmp_path))
    assert cfg.fail_level is Severity.INFO
    assert cfg.select == frozenset({"triggering"})


def test_severity_table_parses(tmp_path):
    (tmp_path / ".promptproof.toml").write_text(
        "[severity]\n"
        'PP404 = "error"\n'
        'PP602 = "info"\n',
        encoding="utf-8",
    )
    cfg = load_config(str(tmp_path))
    assert cfg.severity["PP404"] is Severity.ERROR
    assert cfg.severity["PP602"] is Severity.INFO


def test_thresholds_merge_with_defaults(tmp_path):
    (tmp_path / ".promptproof.toml").write_text(
        "wall_of_text_chars = 800\n",
        encoding="utf-8",
    )
    cfg = load_config(str(tmp_path))
    assert cfg.thresholds["wall_of_text_chars"] == 800
    # untouched keys keep their defaults
    assert cfg.thresholds["description_max_chars"] == 1024


def test_search_walks_upward_from_subdir(tmp_path):
    (tmp_path / ".promptproof.toml").write_text(
        'fail-level = "error"\n', encoding="utf-8"
    )
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    cfg = load_config(str(sub))
    assert cfg.fail_level is Severity.ERROR


def test_explicit_config_path(tmp_path):
    cfg_file = tmp_path / "custom.toml"
    cfg_file.write_text('fail-level = "info"\n', encoding="utf-8")
    cfg = load_config(str(tmp_path), explicit=str(cfg_file))
    assert cfg.fail_level is Severity.INFO

"""Structure rules (PP5xx). Every rule has a firing case AND a known-good case."""

from __future__ import annotations

from promptproof import DocKind, lint_file
from tests.conftest import ids

# A clean skill: frontmatter present, kebab name, known keys, body with a verify step.
GOOD = (
    "---\n"
    "name: pdf-tools\n"
    "description: Use when the user wants to read or merge PDF files, or mentions a .pdf.\n"
    "---\n\n"
    "# PDF tools\n\n"
    "Run the merge, then validate the output opens correctly.\n"
)


def test_good_skill_has_no_structure_findings():
    assert not {i for i in ids(GOOD, kind=DocKind.SKILL) if i.startswith("PP5")}


# --------------------------------------------------------------------------- PP501


def test_pp501_frontmatter_missing_fires():
    text = "# Just a body\n\nDo the thing, then validate it.\n"
    assert "PP501" in ids(text, kind=DocKind.SKILL)


def test_pp501_does_not_fire_when_frontmatter_present():
    assert "PP501" not in ids(GOOD, kind=DocKind.SKILL)


def test_pp501_does_not_fire_when_block_present_but_invalid():
    # A `---` block with no key:value pairs => invalid, not missing (PP502 owns it).
    text = "---\njust prose, no keys\n---\n\nbody\n"
    fired = ids(text, kind=DocKind.SKILL)
    assert "PP501" not in fired


# --------------------------------------------------------------------------- PP502


def test_pp502_frontmatter_invalid_fires():
    text = "---\njust prose with no colon keys here\n---\n\nbody and validate it\n"
    assert "PP502" in ids(text, kind=DocKind.SKILL)


def test_pp502_does_not_fire_on_valid_frontmatter():
    assert "PP502" not in ids(GOOD, kind=DocKind.SKILL)


# --------------------------------------------------------------------------- PP503


def test_pp503_name_missing_fires():
    text = (
        "---\ndescription: Use when the user wants to merge PDFs and validate output.\n"
        "---\n\nb\n"
    )
    assert "PP503" in ids(text, kind=DocKind.SKILL)


def test_pp503_does_not_fire_when_name_present():
    assert "PP503" not in ids(GOOD, kind=DocKind.SKILL)


def test_pp503_does_not_fire_when_frontmatter_absent():
    # No frontmatter at all is PP501's job, not PP503's.
    text = "# body only\n\nvalidate it\n"
    assert "PP503" not in ids(text, kind=DocKind.SKILL)


# --------------------------------------------------------------------------- PP504


def test_pp504_name_not_kebab_fires():
    text = (
        "---\nname: PDF Tools\n"
        "description: Use when the user wants to merge PDFs, then validate output.\n"
        "---\n\nb\n"
    )
    assert "PP504" in ids(text, kind=DocKind.SKILL)


def test_pp504_does_not_fire_on_kebab_name():
    assert "PP504" not in ids(GOOD, kind=DocKind.SKILL)


# --------------------------------------------------------------------------- PP505


def _write_skill(tmp_path, dirname: str, name: str):
    skill_dir = tmp_path / dirname
    skill_dir.mkdir()
    path = skill_dir / "SKILL.md"
    body = (
        "---\n"
        f"name: {name}\n"
        "description: Use when the user wants to merge PDFs, then validate the output.\n"
        "---\n\n# body\n\nvalidate it works\n"
    )
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_pp505_name_dir_mismatch_fires(tmp_path):
    path = _write_skill(tmp_path, "pdf-tools", "pdf-utilities")
    fired = {f.rule for f in lint_file(path)}
    assert "PP505" in fired


def test_pp505_does_not_fire_when_name_matches_dir(tmp_path):
    path = _write_skill(tmp_path, "pdf-tools", "pdf-tools")
    fired = {f.rule for f in lint_file(path)}
    assert "PP505" not in fired


def test_pp505_does_not_fire_on_synthetic_path():
    text = (
        "---\nname: pdf-utilities\n"
        "description: Use when the user wants to merge PDFs, then validate the output.\n"
        "---\n\nbody\n"
    )
    # Synthetic "<text>" path has no real parent dir to compare; must stay silent.
    assert "PP505" not in ids(text, kind=DocKind.SKILL)


# --------------------------------------------------------------------------- PP506


def test_pp506_missing_verify_guidance_fires():
    text = (
        "---\nname: pdf-tools\n"
        "description: Use when the user wants to merge PDFs and read documents.\n"
        "---\n\n# Steps\n\nOpen the file and merge the pages.\n"
    )
    assert "PP506" in ids(text, kind=DocKind.SKILL)


def test_pp506_does_not_fire_when_verify_present():
    assert "PP506" not in ids(GOOD, kind=DocKind.SKILL)


# --------------------------------------------------------------------------- PP507


def test_pp507_unknown_frontmatter_key_fires():
    text = (
        "---\nname: pdf-tools\n"
        "description: Use when the user wants to merge PDFs, then validate the output.\n"
        "author: someone\n"
        "---\n\nbody\n"
    )
    assert "PP507" in ids(text, kind=DocKind.SKILL)


def test_pp507_does_not_fire_on_known_keys():
    text = (
        "---\nname: pdf-tools\n"
        "description: Use when the user wants to merge PDFs, then validate the output.\n"
        "version: 1.0\n"
        "license: MIT\n"
        "allowed-tools: [Read, Write]\n"
        "---\n\nbody and validate it\n"
    )
    assert "PP507" not in ids(text, kind=DocKind.SKILL)


def test_pp507_command_known_keys_differ():
    # `argument-hint` is valid for a command but would be unknown for a skill.
    text = (
        "---\nname: deploy\n"
        "description: Use when the user wants to deploy the app to production.\n"
        "argument-hint: <env>\n"
        "---\n\nbody\n"
    )
    assert "PP507" not in ids(text, kind=DocKind.COMMAND)

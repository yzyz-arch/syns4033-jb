"""Tests for scripts/check_claims.py — the L2 claim verifier.

The point of these cases is regression, not coverage. Two of them exist
specifically because a regex-first implementation got them wrong: a
pattern that blocks valid output teaches the operator to ignore the tool,
and a tool they ignore is worse than no tool.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "check_claims", REPO / "scripts" / "check_claims.py"
)
cc = importlib.util.module_from_spec(SPEC)
sys.modules["check_claims"] = cc
SPEC.loader.exec_module(cc)


def kinds(text: str, root: Path = REPO) -> set[str]:
    return {f.kind for f in cc.check(text, root=root).findings}


def hard(text: str, root: Path = REPO) -> bool:
    return cc.check(text, root=root).blocked


# --- the failure mode this exists for: fabrication -------------------

def test_nonexistent_path_blocks(tmp_path):
    assert hard("Fixed the parser in src/definitely/not/here.py", root=tmp_path)


def test_existing_path_passes():
    assert not kinds("Edited hermes_cli/config_defaults.py and setup-hermes.sh")


def test_real_output_passes():
    # completion word present, but a result is quoted alongside it
    assert not hard("Committed. 114 passed, exit code 0", root=REPO)


def test_completion_without_result_is_flagged():
    # "done" + a verification word but nothing that quotes a result.
    text = "Sudah selesai semua, sudah saya test dan works perfectly"
    rep = cc.check(text, root=REPO)
    assert "completion" in {f.kind for f in rep.findings}, \
        "a completion claim quoting no result must be flagged"


# --- regression: these must NOT be flagged ---------------------------

def test_real_model_name_with_dots_is_not_fabrication():
    """A regex like INVENTED_NAME blocked every dot-form model name."""
    assert not hard("Model anthropic.claude-3-5-sonnet-20241022 kita pakai.")


def test_prose_mentioning_placeholder_is_not_a_placeholder():
    """A keyword list blocked any line containing the word 'placeholder'."""
    assert not hard("Nggak ada placeholder di jawaban ini.")


def test_number_with_source_on_the_line_passes():
    assert "statistic" not in kinds(
        "Harga $3 per juta token, sumber: https://platform.openai.com/docs/pricing")


def test_number_without_source_is_flagged():
    assert "statistic" in kinds("Test suite kita 99.8% pass rate dengan 1.2 detik rata-rata.")


def test_ordinary_prose_is_silent():
    assert not kinds("Prosedurnya ada tiga tahap.")


# --- hedged claims: the ones that look confident ---------------------

@pytest.mark.parametrize("claim", [
    "The patch should work on the next run.",
    "This probably passes on CI.",
    "I believe this fixes the import cycle.",
    "It shouldn't break the build.",
])
def test_hedged_success_is_blocked(claim):
    assert hard(claim)


# --- self-test: the tool must not flag its own verified output ------

def test_running_the_verifier_on_its_own_output_is_clean():
    out = subprocess_run_checker(
        "Fixed hermes_cli/config_defaults.py. audit 71/71, exit code 0"
    )
    assert "BLOCKED" not in out


def subprocess_run_checker(text: str) -> str:
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_claims.py"),
         "--root", str(REPO), "--text", text],
        capture_output=True, text=True, timeout=60,
    )
    return r.stdout


# --- contract --------------------------------------------------------

def test_json_mode_emits_findings():
    import json, subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_claims.py"),
         "--root", "/nonexistent-root-xyz", "--json", "--text", "see src/nope.py"],
        capture_output=True, text=True, timeout=60,
    )
    data = json.loads(r.stdout)
    assert data["blocked"] is True
    assert data["findings"][0]["kind"] == "path"
    assert r.returncode == 1


def test_empty_input_is_usage_error_not_pass():
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_claims.py"), "--text", "  "],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 2


def test_url_check_is_opt_in(tmp_path):
    """A made-up host must only fail when the operator explicitly asks for DNS."""
    text = "Docs di https://definitely-not-a-real-host-xyz.invalid/page"
    # default: no network call, so no finding invented out of thin air
    assert kinds(text, root=tmp_path) == set()
    # opted in: a host that cannot resolve is reported
    r = cc.ClaimChecker(tmp_path, check_urls=True).check(text)
    assert "url" in {f.kind for f in r.findings}

"""Offline contract tests for the osintkit skill (stdlib + pytest, no network)."""
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
KIT = REPO / "tools"
sys.path.insert(0, str(KIT))

from osintkit import (cloud, dorks, emails, favicon, identity, jsintel,  # noqa: E402
                      net, pivot, report, score, takeover)
from osintkit.cli import WORDLIST, build_parser  # noqa: E402


def test_skill_frontmatter_contract():
    text = (REPO / "skills" / "osintkit" / "SKILL.md").read_text(encoding="utf-8")
    fm = yaml.safe_load(text[3: text.index("\n---", 3)])
    assert fm["name"] == "osintkit"
    assert len(fm["description"]) <= 60 and fm["description"].endswith(".")


def test_launcher_imports():
    spec = importlib.util.spec_from_file_location("osintkit_launcher", KIT / "osintkit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main is not None


def test_mmh3_reference_vectors():
    assert favicon.murmur3_32(b"") == 0
    assert favicon.murmur3_32(b"a") == 1009084850
    assert favicon.murmur3_32(b"foo") == -156908512


def test_host_dedupe():
    out = net.dedupe_hosts(["A.Example.com", "*.b.example.com", "u@example.com", "x y"], "example.com")
    assert out == ["a.example.com", "b.example.com"]


def test_takeover_match():
    assert takeover._provider_for_name("x.github.io") == "GitHub Pages"
    assert takeover._match_cname(["x.github.io"]) == "GitHub Pages"
    assert takeover._match_body("Heroku", "No such app", 404)


def test_dork_relevance():
    res = [{"url": "https://tesla.com/a", "title": "t"},
           {"url": "https://other.com/a", "title": "o"}]
    assert len(dorks._relevant("site:tesla.com", res)) == 1


def test_secret_scan():
    # assembled at runtime: no literal provider token in the tracked file
    stripe_fake = "sk_" + "live_" + "abcdefghijklmnopqrstuvwx"
    found = {f["type"] for f in jsintel.scan_text(
        'k="AKIAIOSFODNN7EXAMPLE"; s="' + stripe_fake + '";', "x.js")}
    assert {"aws_access_key_id", "stripe_secret"} <= found


def test_email_helpers():
    pats = emails.generate_patterns("Jane", "Roe", "acme.io")
    assert "jane.roe@acme.io" in pats
    assert "jroe@acme.io" in pats
    assert emails._extract("a [at] b [dot] com")


def test_cloud_candidates():
    names = cloud.candidates("acme.com")
    assert "acme-com" in names and all(n.islower() for n in names)


def test_score_and_graph():
    dossier = {"takeover": {"vulnerable": [{"host": "a", "provider": "Heroku"}]},
               "security_posture": {"spf": None, "dmarc": None},
               "cloud": {"public": [{"provider": "s3", "bucket": "b"}]}}
    s = score.score(dossier)
    assert s["score"] > 0 and s["grade"] in "ABCDF"
    assert score.score({})["score"] == 0
    g = pivot.build_graph("t.com", dossier)
    assert g["node_count"] > 0 and pivot.to_mermaid(g).startswith("graph LR")


def test_header_grade_math():
    g = report._grade_headers({"a": "1", "b": None, "c": "x", "d": None})
    assert g["score"] == 50
    assert set(g["present"]) == {"a", "c"}


def test_summary_counts():
    s = report.summarize("example.com", {
        "http": {"technologies": ["nginx"], "security_headers": {}},
        "ct": {"combined": ["a.example.com"], "count": 1},
    })
    assert s["subdomain_count"] == 1 and s["technologies"] == ["nginx"]


def test_email_syntax_validation():
    assert identity.validate_email_syntax("a@b.co")["syntax_ok"]
    assert not identity.validate_email_syntax("nope")["syntax_ok"]


def test_wordlist_and_platforms():
    assert len(WORDLIST) == len(set(WORDLIST)) > 50
    assert all("{u}" in tpl for tpl in identity.PLATFORMS.values())


@pytest.mark.parametrize("cmd,argv", [
    ("dns", ["dns", "example.com"]),
    ("subs", ["subs", "example.com", "--brute"]),
    ("axfr", ["axfr", "example.com"]),
    ("host", ["host", "1.1.1.1", "--no-scan"]),
    ("asn", ["asn", "AS15169", "--rev"]),
    ("user", ["user", "x"]),
    ("email", ["email", "a@b.co", "--accounts"]),
    ("js", ["js", "example.com", "--limit", "5"]),
    ("archive", ["archive", "example.com", "--limit", "10"]),
    ("takeover", ["takeover", "example.com", "--from-subdomains"]),
    ("cloud", ["cloud", "example.com", "--providers", "s3,gcs"]),
    ("dork", ["dork", "--generate", "domain", "example.com"]),
    ("gh", ["gh", "torvalds", "--deep"]),
    ("scan", ["scan", "."]),
    ("score", ["score", "f.json"]),
    ("graph", ["graph", "f.json", "--outdir", "o"]),
    ("deep", ["deep", "example.com", "--outdir", "o", "--no-scan"]),
    ("domain", ["domain", "example.com", "--dns", "--subdomains"]),
])
def test_cli_subcommands_parse(cmd, argv):
    args = build_parser().parse_args(argv)
    assert args.cmd == cmd and callable(args.func)

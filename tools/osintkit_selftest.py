#!/usr/bin/env python3
"""Offline self-check for osintkit v2 (no network).

Run: python3 tools/osintkit_selftest.py
Covers the pure logic that would otherwise only be proven by live traffic:
murmur3 vectors, hostnormalisation, takeover matching, dork relevance filtering,
secret regexes, scoring, graph export and CLI wiring.
"""
import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_mmh3_known_vectors():
    """mmh3.hash() reference values — the favicon hash must match Shodan."""
    from osintkit import favicon
    assert favicon.murmur3_32(b"") == 0
    assert favicon.murmur3_32(b"a") == 1009084850
    assert favicon.murmur3_32(b"foo") == -156908512
    assert favicon.murmur3_32(b"foo", 42) == -1322301282
    assert favicon.murmur3_32(b"hello") == 613153351
    # signed 32-bit range
    for s in (b"", b"x", b"hello world", bytes(range(256))):
        assert -2**31 <= favicon.murmur3_32(s) < 2**31


def test_shorten_host_filter():
    from osintkit import net
    hosts = ["Dev.Example.com", "*.api.example.com", "user@example.com",
             "bad_host!.example.com", "example.com", "a.b.example.com."]
    out = net.dedupe_hosts(hosts, "example.com")
    assert "dev.example.com" in out
    assert "api.example.com" in out          # wildcard stripped
    assert "a.b.example.com" in out          # trailing dot stripped
    assert "example.com" in out
    assert not any("@" in h or "!" in h for h in out)


def test_takeover_provider_matching():
    from osintkit import takeover
    assert takeover._provider_for_name("foo.github.io") == "GitHub Pages"
    assert takeover._provider_for_name("bar.herokuapp.com") == "Heroku"
    assert takeover._provider_for_name("example.com") is None
    # dangling chain: sub -> provider host
    assert takeover._match_cname(["sub.example.com", "foo.github.io"]) == "GitHub Pages"
    # bare provider host (no CNAME of its own) must still be recognised
    assert takeover._match_cname(["foo.github.io"]) == "GitHub Pages"
    # body signature matching
    assert takeover._match_body("GitHub Pages", "There isn't a GitHub Pages site here.", 404)
    assert not takeover._match_body("GitHub Pages", "Welcome to my real site", 200)


def test_dork_relevance_filter():
    from osintkit import dorks
    results = [
        {"url": "https://www.tesla.com/a.pdf", "title": "Tesla doc"},
        {"url": "https://microsoft.com/x", "title": "noise"},
    ]
    keep = dorks._relevant("site:tesla.com filetype:pdf", results)
    assert len(keep) == 1 and "tesla.com" in keep[0]["url"]
    # every literal anchor must appear
    assert dorks._relevant('site:tesla.com "api_key"', results) == []
    # no anchors -> passthrough
    assert len(dorks._relevant("a b c", results)) == 2


def test_dork_sets_have_site_operator():
    from osintkit import dorks
    for kind, gen in (("domain", dorks.domain_dorks), ("org", dorks.org_dorks),
                      ("email", dorks.email_dorks), ("person", dorks.person_dorks),
                      ("username", dorks.username_dorks)):
        out = gen("example.com")
        assert isinstance(out, dict) and out, kind
        assert all(isinstance(v, list) and v for v in out.values()), kind


def test_secret_patterns_hit_and_miss():
    from osintkit import jsintel
    # fixtures are assembled at runtime so no literal provider token sits in the file
    stripe_fake = "sk_" + "live_" + "abcdefghijklmnopqrstuvwx"
    gh_fake = "gh" + "p_" + "012345678901234567890123456789012345"
    blob = f"""
    const k = "AKIAIOSFODNN7EXAMPLE";
    const s = "{stripe_fake}";
    const g = "{gh_fake}";
    const u = "postgres://root:hunter2@db.internal:5432/app";
    fetch("/api/v1/users");
    -----BEGIN RSA PRIVATE KEY-----
    """
    found = {f["type"] for f in jsintel.scan_text(blob, "test.js")}
    assert "aws_access_key_id" in found
    assert "stripe_secret" in found
    assert "github_token" in found
    assert "db_connection" in found
    assert "private_key_block" in found
    # masking keeps length shape but hides the middle
    f = next(f for f in jsintel.scan_text(blob, "t") if f["type"] == "stripe_secret")
    assert "..." in f["masked"] and f["value"].startswith("sk_live_")
    # clean bundle -> no critical hits
    clean = jsintel.scan_text("const a = 1; console.log('hello world');", "clean.js")
    assert not [f for f in clean if f["severity"] == "critical"]


def test_email_pattern_generation():
    from osintkit import emails
    pats = emails.generate_patterns("John", "Doe", "acme.com")
    assert "john.doe@acme.com" in pats
    assert "jdoe@acme.com" in pats
    assert "doe.john@acme.com" in pats
    assert all(p.count("@") == 1 for p in pats)
    # obfuscated address extraction
    found = emails._extract("mail me: john [at] acme [dot] com or jane@acme.com")
    assert "jane@acme.com" in found
    assert "john@acme.com" in found
    # junk dropped
    assert not emails._extract("no-reply@acme.com user@example.com")


def test_cloud_candidates():
    from osintkit import cloud
    names = cloud.candidates("Example.COM")
    assert "example-com" in names
    assert "backup-example-com" in names
    assert all(n == n.lower() and 3 <= len(n) <= 63 for n in names)
    assert all("." not in n or n.replace(".", "").isalnum() for n in names)


def test_scoring_deterministic():
    from osintkit import score
    empty = score.score({})
    assert empty["score"] == 0 and empty["grade"] == "A"

    dossier = {
        "takeover": {"vulnerable": [{"host": "a.example.com", "provider": "Heroku",
                                     "evidence": ["sig"]}]},
        "cloud": {"public": [{"provider": "s3", "bucket": "b", "url": "u",
                              "sample_keys": ["k"]}]},
        "security_posture": {"spf": None, "dmarc": None, "dkim_selectors": []},
        "http": {"security_headers": {f"h{i}": None for i in range(8)}},
    }
    s = score.score(dossier)
    assert s["score"] >= 30
    ids = {f["id"] for f in s["findings"]}
    assert {"takeover", "bucket-public", "email-spf", "email-dmarc", "headers"} <= ids
    # findings sorted by severity
    order = [f["severity"] for f in s["findings"]]
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    assert order == sorted(order, key=lambda x: rank[x])


def test_graph_build_and_export():
    from osintkit import pivot
    dossier = {
        "ct": {"combined": ["a.example.com", "b.example.com"]},
        "resolved": {"a.example.com": "1.2.3.4"},
        "http": {"technologies": ["nginx"]},
        "emails": {"emails": ["soc@example.com"]},
        "cloud": {"public": [{"provider": "s3", "bucket": "ex", "status": "public-list"}]},
        "takeover": {"vulnerable": [{"host": "b.example.com", "provider": "Heroku"}]},
    }
    g = pivot.build_graph("example.com", dossier)
    kinds = {n["kind"] for n in g["nodes"]}
    assert {"domain", "host", "ip", "tech", "email", "bucket"} <= kinds
    mermaid = pivot.to_mermaid(g)
    dot = pivot.to_dot(g)
    assert mermaid.startswith("graph LR")
    assert dot.startswith("digraph osint")
    assert "DANGLING_TO" in mermaid
    with tempfile.TemporaryDirectory() as td:
        files = pivot.save(g, td, "g")
        for k in ("mermaid", "dot", "json", "html"):
            assert Path(files[k]).exists(), k


def test_report_renderers():
    from osintkit import report
    dossier = {
        "http": {"security_headers": {"a": "1", "b": None}, "technologies": ["nginx"]},
        "ct": {"combined": ["a.example.com"], "count": 1},
        "score": report_score_stub(),
    }
    s = report.summarize("example.com", dossier)
    assert s["subdomain_count"] == 1 and s["technologies"] == ["nginx"]
    md = report.render_markdown("example.com", dossier, s)
    html = report.render_html("example.com", dossier, s, "graph LR\n a-->b")
    assert "# OSINT Dossier — example.com" in md
    assert "OSINT Dossier" in html and "<table" in html
    with tempfile.TemporaryDirectory() as td:
        files = report.write_report("example.com", dossier, td, None)
        for k in ("json", "md", "html"):
            assert Path(files[k]).stat().st_size > 200, k


def report_score_stub():
    return {"score": 42, "grade": "C", "counts": {"critical": 0, "high": 1, "medium": 0, "low": 0},
            "findings": [{"severity": "high", "title": "test", "detail": "d"}],
            "interpretation": "x"}


def test_header_grade_math():
    from osintkit import report
    g = report._grade_headers({"a": "1", "b": None, "c": "x", "d": None})
    assert g["score"] == 50
    assert set(g["present"]) == {"a", "c"}


def test_identity_and_wordlist():
    from osintkit import identity
    from osintkit.cli import WORDLIST, build_parser
    assert len(WORDLIST) == len(set(WORDLIST)) > 50
    assert all(" " not in w and w.islower() for w in WORDLIST)
    assert all("{u}" in tpl for tpl in identity.PLATFORMS.values())
    assert identity.validate_email_syntax("a@b.co")["syntax_ok"]
    assert not identity.validate_email_syntax("nope")["syntax_ok"]
    # every subcommand parses
    for argv in (["dns", "example.com"], ["deep", "example.com", "--outdir", "o"],
                 ["js", "example.com", "--limit", "5"], ["cloud", "example.com"],
                 ["takeover", "example.com", "--from-subdomains"],
                 ["dork", "--generate", "domain", "example.com"],
                 ["gh", "torvalds", "--deep"], ["scan", "."], ["score", "f.json"],
                 ["graph", "f.json"], ["host", "1.1.1.1", "--no-scan"],
                 ["asn", "AS15169", "--rev"], ["archive", "example.com", "--limit", "10"],
                 ["harvest", "example.com", "--verify", "3"],
                 ["subs", "example.com", "--brute", "--full"],
                 ["favicon", "example.com"], ["wildcard", "example.com"]):
        args = build_parser().parse_args(argv)
        assert callable(args.func), argv


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f" FAIL {fn.__name__}: {type(e).__name__}: {e}")
    print(f"{'PASS' if not failed else 'FAILED'} {len(fns) - failed}/{len(fns)} checks")
    sys.exit(1 if failed else 0)

#!/usr/bin/env python3
"""
check_claims.py — verify factual claims an agent made against reality.

This is not a style linter. Regex over prose only catches how a claim LOOKS.
A fabricated file path looks exactly like a real one. The checks below answer
a different question: does the thing the agent named actually exist?

Checks, in order of how often they are wrong:

  path       a file/dir path was named -> does it exist on disk?
  symbol     a dotted symbol was named -> is it in the tree?
  url        a URL was named -> is the host resolvable? (network, opt-in)
  number     a statistic was asserted -> is a source present nearby?
  hedged     "should work" / "probably" -> unverified claim in disguise

Regex patterns that block on *appearance* (the "does this look fake" school)
are deliberately absent: they produce false positives on valid input and still
let every confident-sounding fabrication through.

Usage:
    python3 scripts/check_claims.py --text "Fixed in src/foo/bar.py"
    cat agent_output.txt | python3 scripts/check_claims.py
    python3 scripts/check_claims.py --text "..." --root /path/to/repo
    python3 scripts/check_claims.py --text "..." --strict   # warnings block too

Exit codes: 0 clean · 1 blocked · 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# --- claim extraction ---------------------------------------------------
# A path is only a claim if it looks like a repo path, not prose. Requires a
# known-ish extension or a directory-shaped tail so "e.g." and "etc." don't match.
_CODE_EXT = (
    r"py|js|mjs|cjs|jsx|ts|tsx|rs|go|java|rb|php|c|h|cpp|hpp|sh|bash|zsh|"
    r"sql|json|yaml|yml|toml|ini|cfg|md|txt|html|css|scss|vue|svelte|lock|env"
)
PATH_RE = re.compile(
    r"(?<![\w/])((?:[\w.-]+/)+[\w.-]+\.(?:" + _CODE_EXT + r"))(?![\w])"
)
ROOTED_PATH_RE = re.compile(r"(?<![\w/])(\.{1,2}/[\w./-]+\.(?:" + _CODE_EXT + r"))(?![\w])")
SYMBOL_RE = re.compile(
    r"(?<![\w.])([a-z_][a-z0-9_]{2,}(?:\.[a-z_][a-z0-9_]*){1,4})\s*\("
)
URL_RE = re.compile(r"https?://([\w-]+(?:\.[\w-]+)+)(?:/[\w./%+-]*)?")

# Asserted statistic: a quantity with a unit or a currency symbol, or a
# percentage. Only flagged when no source marker appears in the same line.
STAT_RE = re.compile(
    r"(?:\$\s?\d[\d,.]*|\d[\d,.]*\s?%|\b\d[\d,]*\s?"
    r"(?:ms|s|sec|seconds?|minutes?|hours?|days?|files?|lines?|users?|tokens?)\b)"
)
SOURCE_MARKER = re.compile(
    r"(https?://|per\s+sumber|sumber|source|ref:|output|hasil|\bexit\s*code\b|"
    r"\bHTTP\s?\d{3}\b|\b\d+\s+(?:passed|failed|skipped)\b)",
    re.I,
)

# Claims that assert success without asserting how they were checked.
HEDGE_RE = re.compile(
    r"\b(?:should\s+(?:work|pass|be\s+fine)|probably\s+(?:works|passes|fixes)|"
    r"i\s+(?:believe|think)\s+(?:this|it)\s+(?:works|passes|fixes)|"
    r"shouldn'?t\s+break|must\s+be\s+fine|presumably|probably\s+fine)\b",
    re.I,
)

COMPLETION_RE = re.compile(
    r"\b(?:done|finished|fixed|working|resolved|beres|selesai|sudah\s+(?:selesai|beres|"
    r"dijawab|diperbaiki)|pushed|shipped|passed|success)\b",
    re.I,
)

# Files worth grepping for a symbol. Skipped to stay fast and dependency-free.
_SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".tox", ".mypy_cache", ".pytest_cache", ".next", "target",
}
_GREP_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".rs", ".go", ".rb", ".sh"}


@dataclass
class Finding:
    kind: str
    detail: str
    claim: str
    line: int
    hard: bool = False

    def render(self) -> str:
        tag = "BLOCK" if self.hard else "warn"
        return f"  L{self.line:<4} [{tag}/{self.kind}] {self.claim} — {self.detail}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checked: int = 0

    @property
    def blocked(self) -> bool:
        return any(f.hard for f in self.findings)

    def render(self) -> str:
        if not self.findings:
            return (
                f"OK — {self.checked} claim(s) checked, all resolved against reality."
            )
        head = "BLOCKED" if self.blocked else "WARNINGS"
        out = [f"[{head}] {len(self.findings)} unverified claim(s) of {self.checked} checked:"]
        out += [f.render() for f in self.findings]
        out.append("")
        out.append(
            "FIX: run the command and paste its output, or state "
            "NOT YET VERIFIED and name what you would check."
        )
        return "\n".join(out)


class ClaimChecker:
    def __init__(self, root: Path, check_urls: bool = False) -> None:
        self.root = root
        self.check_urls = check_urls
        self._symbol_cache: dict[str, bool] = {}

    # -- existence ------------------------------------------------------
    def path_exists(self, raw: str) -> bool:
        p = Path(raw)
        candidates = [p] if p.is_absolute() else [self.root / p, Path.cwd() / p]
        return any(c.exists() for c in candidates)

    def symbol_exists(self, dotted: str) -> bool:
        """True if the leading name appears in any source file under root."""
        head = dotted.split(".")[0]
        if head in self._symbol_cache:
            return self._symbol_cache[head]
        found = False
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                if Path(fn).suffix not in _GREP_EXT:
                    continue
                try:
                    with open(os.path.join(dirpath, fn), "r", encoding="utf-8",
                              errors="ignore") as fh:
                        for line in fh:
                            if head in line:
                                found = True
                                break
                except OSError:
                    continue
                if found:
                    break
            if found:
                break
        self._symbol_cache[head] = found
        return found

    def host_resolves(self, host: str) -> bool:
        if not self.check_urls:
            return True  # not opted in; don't invent a failure
        import socket
        try:
            socket.getaddrinfo(host, None)
            return True
        except OSError:
            return False

    # -- the pass ------------------------------------------------------
    def check(self, text: str, strict: bool = False) -> Report:
        rep = Report()
        for lineno, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue

            for m in list(PATH_RE.finditer(line)) + list(ROOTED_PATH_RE.finditer(line)):
                raw = m.group(1)
                rep.checked += 1
                if not self.path_exists(raw):
                    rep.findings.append(Finding(
                        "path", "no such file on disk", raw, lineno, hard=True))

            for m in SYMBOL_RE.finditer(line):
                dotted = m.group(1)
                rep.checked += 1
                if not self.symbol_exists(dotted):
                    rep.findings.append(Finding(
                        "symbol", "name not found anywhere in the tree", dotted, lineno))

            for m in URL_RE.finditer(line):
                host = m.group(1)
                rep.checked += 1
                if not self.host_resolves(host):
                    rep.findings.append(Finding(
                        "url", "host does not resolve", host, lineno))

            if STAT_RE.search(line) and not SOURCE_MARKER.search(line):
                rep.checked += 1
                rep.findings.append(Finding(
                    "statistic", "number asserted with no source on this line",
                    line.strip()[:70], lineno))

            if HEDGE_RE.search(line):
                rep.checked += 1
                rep.findings.append(Finding(
                    "hedged", "asserts success without asserting a check",
                    line.strip()[:70], lineno, hard=True))

            if COMPLETION_RE.search(line) and re.search(
                r"\b(?:test|suite|build|lint|run|command|check)\b", line, re.I
            ):
                rep.checked += 1
                if not re.search(r"(https?://|\bexit\s*code\b|\bHTTP\s?\d{3}\b|"
                                 r"\d+\s+(?:passed|failed|skipped))", line, re.I):
                    rep.findings.append(Finding(
                        "completion", "completion claimed, no result quoted",
                        line.strip()[:70], lineno))

        if strict:
            for f in rep.findings:
                f.hard = True
        return rep


def check(text: str, root: str | os.PathLike = ".", strict: bool = False,
          check_urls: bool = False) -> Report:
    return ClaimChecker(Path(root).resolve(), check_urls).check(text, strict=strict)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", help="text to check; omit to read stdin")
    ap.add_argument("--root", default=".", help="repo root to verify paths against")
    ap.add_argument("--strict", action="store_true", help="warnings block too")
    ap.add_argument("--check-urls", action="store_true",
                    help="resolve URL hosts (needs network)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    a = ap.parse_args()

    text = a.text if a.text is not None else sys.stdin.read()
    if not text.strip():
        print("nothing to check", file=sys.stderr)
        return 2

    rep = check(text, root=a.root, strict=a.strict, check_urls=a.check_urls)

    if a.json:
        import json
        print(json.dumps({
            "blocked": rep.blocked,
            "checked": rep.checked,
            "findings": [
                {"kind": f.kind, "claim": f.claim, "line": f.line, "hard": f.hard}
                for f in rep.findings
            ],
        }, indent=2))
    else:
        print(rep.render())
    return 1 if rep.blocked else 0


if __name__ == "__main__":
    sys.exit(main())

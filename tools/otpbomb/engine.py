"""Blast engine — async wave scheduler with per-provider backoff and live stats.

Design notes that matter in practice:

* One task per (provider, repetition). A semaphore caps in-flight requests, the
  wave interval staggers waves so no single CDN feels a burst from one IP.
* A provider that answers 429/403 is put on cooldown (exponential, capped) and
  keeps its own retry budget instead of eating the global concurrency.
* Every attempt is recorded; SIGINT still yields a full summary.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field

from typing import cast

import httpx

from .phone import render, render_str

OK, FAIL, BLOCKED, ERR = "ok", "fail", "blocked", "error"

BLOCK_CODES = (401, 403, 407, 429)
_VERDICT_ATTR = {OK: "ok", FAIL: "fail", BLOCKED: "blocked", ERR: "err"}


def http2_ok() -> bool:
    """httpx raises at client build time when h2 is absent — probe for it."""
    try:
        import h2  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass
class Options:
    rounds: int = 1
    per_provider: int = 1
    wave_interval: float = 0.0
    jitter: float = 0.35
    concurrency: int = 24
    timeout: float = 12.0
    retries: int = 2
    backoff: float = 1.6
    proxy: str | None = None
    verbose: bool = False
    quiet: bool = False
    stop_after_ok: int = 0


@dataclass
class Result:
    provider: str
    category: str
    verdict: str
    status: int = 0
    ms: int = 0
    attempt: int = 0
    snippet: str = ""
    error: str = ""


@dataclass
class Stats:
    started: float = field(default_factory=time.time)
    sent: int = 0
    ok: int = 0
    fail: int = 0
    blocked: int = 0
    err: int = 0
    per_provider: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, r: Result) -> None:
        self.sent += 1
        attr = _VERDICT_ATTR.get(r.verdict, "err")
        setattr(self, attr, getattr(self, attr) + 1)
        slot = self.per_provider.setdefault(r.provider, {OK: 0, FAIL: 0, BLOCKED: 0, ERR: 0})
        slot[r.verdict] += 1

    def summary(self, elapsed: float | None = None) -> dict:
        elapsed = elapsed if elapsed is not None else (time.time() - self.started)
        return {
            "sent": self.sent,
            "accepted": self.ok,
            "failed": self.fail,
            "blocked": self.blocked,
            "network_error": self.err,
            "elapsed_s": round(elapsed, 2),
            "rate_per_s": round(self.sent / elapsed, 2) if elapsed else 0.0,
            "per_provider": {k: dict(v) for k, v in self.per_provider.items()},
        }


def classify(status: int, body: str, prov) -> str:
    low = (body or "").lower()
    if status in BLOCK_CODES:
        return BLOCKED
    if status >= 500 or status == 0:
        return ERR
    if prov.fail_contains and any(m.lower() in low for m in prov.fail_contains):
        return FAIL
    if status not in prov.success_codes:
        return FAIL
    if prov.success_contains and not any(m.lower() in low for m in prov.success_contains):
        return FAIL
    return OK


class Engine:
    def __init__(self, ctx: dict[str, str], opts: Options, print_lock: asyncio.Lock | None = None):
        self.ctx = ctx
        self.opts = opts
        self.stats = Stats()
        self.results: list[Result] = []
        self.sem = asyncio.Semaphore(max(1, opts.concurrency))
        self.cooldown: dict[str, float] = {}
        self.hits: dict[str, int] = {}
        self._print_lock = print_lock or asyncio.Lock()
        self.aborted = False
        self._stop = asyncio.Event()

    # -- output ------------------------------------------------------------
    async def _emit(self, line: str) -> None:
        if self.opts.quiet:
            return
        async with self._print_lock:
            print(line, flush=True)

    # -- single attempt ----------------------------------------------------
    async def _prefetch(self, client: httpx.AsyncClient, prov) -> dict[str, str]:
        """Warm-up request; scrape tokens named in prov.extract."""
        import re

        found: dict[str, str] = {}
        if not prov.pre_url:
            return found
        try:
            r = await client.get(render_str(prov.pre_url, self.ctx), timeout=self.opts.timeout)
        except httpx.HTTPError:
            return found
        body = r.text
        for target, pattern in prov.extract.items():
            m = re.search(render_str(pattern, self.ctx), body)
            if not m:
                continue
            val = m.group(1) if m.groups() else m.group(0)
            kind, _, key = target.partition(":")
            if kind == "header":
                found[f"h:{key}"] = val
            elif kind == "field":
                found[f"f:{key}"] = val
            elif kind == "cookie":
                client.cookies.set(key, val, domain=httpx.URL(prov.url).host)
        return found

    async def attempt(self, client: httpx.AsyncClient, prov, idx: int) -> Result:
        res = Result(prov.name, prov.category, ERR, attempt=idx)
        waited = self.cooldown.get(prov.name, 0.0) - time.time()
        if waited > 0:
            await asyncio.sleep(min(waited, 30))

        tokens = await self._prefetch(client, prov)
        form = cast(dict, render(prov.form, self.ctx)) if prov.form else None
        jsbody = cast(dict, render(prov.json_body, self.ctx)) if prov.json_body else None
        headers = cast(dict, render(prov.merged_headers(), self.ctx))
        for key, val in tokens.items():
            if key.startswith("h:"):
                headers[key[2:]] = val
            else:
                if form is not None:
                    form[key[2:]] = val
                if jsbody is not None:
                    jsbody[key[2:]] = val

        body_preview = ""
        for tryno in range(self.opts.retries + 1):
            t0 = time.perf_counter()
            try:
                resp = await client.request(
                    prov.method,
                    render_str(prov.url, self.ctx),
                    data=form if prov.form else None,
                    json=jsbody if prov.json_body is not None else None,
                    headers=headers,
                    timeout=self.opts.timeout,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                res.status, res.error = 0, f"{type(exc).__name__}: {exc}"
                res.verdict = ERR
            else:
                res.status = resp.status_code
                body_preview = resp.text[:400]
                res.verdict = classify(resp.status_code, body_preview, prov)
                res.snippet = " ".join(body_preview.split())[:120]
                res.error = ""
            res.ms = int((time.perf_counter() - t0) * 1000)
            res.attempt = tryno + 1
            if res.verdict != ERR and res.verdict != BLOCKED:
                break
            if tryno < self.opts.retries:
                await asyncio.sleep(self.opts.backoff ** (tryno + 1))

        if res.verdict == BLOCKED:
            n = self.cooldown.get(prov.name, 0)
            self.cooldown[prov.name] = time.time() + min(60.0, 3 + n)
        if res.verdict == OK:
            self.hits[prov.name] = self.hits.get(prov.name, 0) + 1

        self.stats.record(res)
        self.results.append(res)
        await self._emit(self._line(res))
        if self.opts.stop_after_ok and self.stats.ok >= self.opts.stop_after_ok:
            self._stop.set()
        return res

    def _line(self, r: Result) -> str:
        tag = f"[{r.verdict.upper():7}]"
        extra = ""
        if self.opts.verbose and r.snippet:
            extra = "  " + r.snippet
        if r.error:
            extra = "  " + r.error
        return f"{tag} {r.provider:<14} {r.category:<3} {r.status:<4} {r.ms:>5}ms{extra}"

    # -- run ---------------------------------------------------------------
    async def run(self, providers: list) -> Stats:
        limits = httpx.Limits(max_connections=self.opts.concurrency * 2,
                              max_keepalive_connections=self.opts.concurrency)
        async with httpx.AsyncClient(
            limits=limits,
            http2=http2_ok(),
            proxy=self.opts.proxy,
            cookies=httpx.Cookies(),
        ) as client:
            tasks: list[asyncio.Task] = []
            for rnd in range(max(1, self.opts.rounds)):
                if self._stop.is_set():
                    break
                wave = []
                for prov in providers:
                    for i in range(max(1, self.opts.per_provider)):
                        wave.append(self._spawn(
                            client, prov,
                            rnd * max(1, self.opts.per_provider) + i + 1, tasks))
                if rnd + 1 < self.opts.rounds and self.opts.wave_interval > 0:
                    await asyncio.sleep(self.opts.wave_interval + random.uniform(0, self.opts.jitter))
            await asyncio.gather(*tasks, return_exceptions=True)
        return self.stats

    def _spawn(self, client, prov, idx: int, sink: list) -> asyncio.Task:
        async def _wrapped():
            async with self.sem:
                if self._stop.is_set():
                    return
                await asyncio.sleep(random.uniform(0, self.opts.jitter))
                if self._stop.is_set():
                    return
                await self.attempt(client, prov, idx)

        t = asyncio.create_task(_wrapped())
        sink.append(t)
        return t

    # -- probe -------------------------------------------------------------
    async def probe(self, providers: list) -> list[Result]:
        self.opts.retries = 0
        async with httpx.AsyncClient(http2=http2_ok(), proxy=self.opts.proxy) as client:
            async def one(p):
                async with self.sem:
                    try:
                        return await self.attempt(client, p, 1)
                    except Exception as exc:  # keep the run alive
                        res = Result(p.name, p.category, ERR, error=f"{type(exc).__name__}: {exc}")
                        self.stats.record(res)
                        self.results.append(res)
                        return res

            out = await asyncio.gather(*(one(p) for p in providers))
            return [r for r in out if isinstance(r, Result)]

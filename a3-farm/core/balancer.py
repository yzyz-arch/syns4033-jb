"""Key pool balancer: rotate across keys, backoff on 429, failover, per-key cooldown."""
from __future__ import annotations
import random
import threading
import time
from typing import Any, Callable

import requests

from .config import GENERATE_URL, DEFAULT_MODEL, FALLBACK_MODELS, REQUEST_TIMEOUT, MAX_RETRIES_PER_KEY
from .apikey import classify_error


class KeyPool:
    """Thread-safe rotating pool of Gemini API keys with health-aware scheduling.

    - Keys in cooldown (hit quota/429) are skipped until their cooldown expires.
    - A round-robin cursor distributes load; on failure the key is penalized and
      the request fails over to the next key / next model.
    """

    def __init__(self, keys: list[str], models: list[str] | None = None,
                 cooldown_quota: float = 60.0, cooldown_invalid: float = 3600.0,
                 on_event: Callable[[dict], None] | None = None):
        self._lock = threading.Lock()
        self.keys = list(dict.fromkeys(keys))          # dedupe, keep order
        self.models = models or FALLBACK_MODELS
        self.cursor = 0
        self.cooldown_quota = cooldown_quota
        self.cooldown_invalid = cooldown_invalid
        self._cooldown: dict[str, float] = {}          # key -> unix ts until usable
        self._stats: dict[str, dict] = {k: {"ok": 0, "fail": 0, "429": 0} for k in self.keys}
        self.on_event = on_event or (lambda e: None)

    # ---- scheduling ----
    def _eligible(self, now: float) -> list[str]:
        out = []
        with self._lock:
            for k in self.keys:
                if self._cooldown.get(k, 0) <= now:
                    out.append(k)
        return out

    def _next_key(self, now: float) -> str | None:
        elig = self._eligible(now)
        if not elig:
            return None
        with self._lock:
            self.cursor = (self.cursor + 1) % max(1, len(self.keys))
            # start scanning from cursor to spread load
            ordered = self.keys[self.cursor:] + self.keys[:self.cursor]
        for k in ordered:
            if k in elig:
                return k
        return random.choice(elig)

    def _penalize(self, key: str, kind: str) -> None:
        now = time.time()
        with self._lock:
            if kind == "quota":
                self._cooldown[key] = now + self.cooldown_quota
                self._stats[key]["429"] += 1
            elif kind == "invalid":
                self._cooldown[key] = now + self.cooldown_invalid
            self._stats[key]["fail"] += 1

    def _reward(self, key: str) -> None:
        with self._lock:
            self._stats[key]["ok"] += 1

    # ---- execution ----
    def generate(self, prompt: str, model: str | None = None,
                 max_output_tokens: int = 1024, extra: dict | None = None) -> dict[str, Any]:
        """Run a generateContent with automatic rotation/failover.

        Returns {ok, text, key_masked, model, status, attempts, latency_ms, error?}.
        """
        models_to_try = [model] if model else list(self.models)
        attempts = 0
        last_err = ""
        t_start = time.time()

        for mdl in models_to_try:
            per_key = 0
            while per_key < MAX_RETRIES_PER_KEY:
                now = time.time()
                key = self._next_key(now)
                if not key:
                    wait = self._min_cooldown_wait(now)
                    if wait > 0:
                        time.sleep(min(wait, 5.0))
                        key = self._next_key(time.time())
                    if not key:
                        return self._result(False, "", None, mdl, attempts,
                                            (time.time() - t_start) * 1000,
                                            "all keys in cooldown")
                attempts += 1
                per_key += 1
                url = GENERATE_URL.format(model=mdl)
                body: dict[str, Any] = {"contents": [{"parts": [{"text": prompt}]}]}
                gen = {"maxOutputTokens": max_output_tokens}
                if extra:
                    gen.update(extra)
                body["generationConfig"] = gen
                t0 = time.time()
                try:
                    r = requests.post(url, params={"key": key}, json=body, timeout=REQUEST_TIMEOUT)
                except requests.RequestException as e:
                    last_err = f"{type(e).__name__}: {e}"
                    self._penalize(key, "quota")   # network blip -> brief cooldown
                    self.on_event({"event": "net_err", "key": mask(key), "err": last_err})
                    time.sleep(0.5)
                    continue
                lat = int((time.time() - t0) * 1000)
                kind = classify_error(r.status_code, r.text)
                self.on_event({"event": "call", "key": mask(key), "model": mdl,
                               "status": r.status_code, "class": kind, "latency_ms": lat})
                if r.status_code == 200:
                    self._reward(key)
                    try:
                        txt = (r.json().get("candidates", [{}])[0]
                               .get("content", {}).get("parts", [{}])[0].get("text", ""))
                    except (ValueError, IndexError, KeyError):
                        txt = ""
                    self.on_event({"event": "ok", "key": mask(key), "model": mdl})
                    return self._result(True, txt, key, mdl, attempts,
                                        (time.time() - t_start) * 1000, "")
                last_err = r.text[:400]
                if kind == "quota":
                    self._penalize(key, "quota")
                    self.on_event({"event": "quota", "key": mask(key)})
                    # backoff jitter then next key
                    time.sleep(min(0.4 * per_key + random.random() * 0.3, 3.0))
                elif kind == "invalid":
                    self._penalize(key, "invalid")
                    self.on_event({"event": "invalid", "key": mask(key)})
                else:
                    self._penalize(key, "quota")
                    self.on_event({"event": "err", "key": mask(key), "err": last_err})
                    time.sleep(0.3)
            # exhausted retries on this model -> next model
        return self._result(False, "", None, models_to_try[-1], attempts,
                            (time.time() - t_start) * 1000, last_err or "exhausted")

    def _min_cooldown_wait(self, now: float) -> float:
        with self._lock:
            times = [t for t in self._cooldown.values() if t > now]
        return (min(times) - now) if times else 0.0

    @staticmethod
    def _result(ok: bool, text: str, key: str | None, model: str,
                attempts: int, latency_ms: float, error: str) -> dict[str, Any]:
        return {"ok": ok, "text": text, "key": mask(key) if key else None,
                "model": model, "attempts": attempts,
                "latency_ms": int(latency_ms), "error": error}

    def health(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            cooling = {k: round(t - now, 1) for k, t in self._cooldown.items() if t > now}
            stats = {mask(k): dict(v) for k, v in self._stats.items()}
        return {"keys": len(self.keys), "in_cooldown": len(cooling),
                "cooldown_remaining_s": cooling, "stats": stats}


def mask(key: str | None) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return key[:3] + "***"
    return key[:6] + "..." + key[-4:]

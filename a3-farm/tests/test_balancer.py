"""Prove the balancer rotates, backs off on 429 and fails over — against a mock
endpoint (no real keys required). Run with mock_gemini.py up on :8899.
"""
import sys, importlib
sys.path.insert(0, ".")
import core.config as cfg
# point endpoints at the mock BEFORE importing balancer
cfg.GENERATE_URL = "http://127.0.0.1:8899/v1beta/models/{model}:generateContent"
cfg.MODELS_URL = "http://127.0.0.1:8899/v1beta/models"
import core.balancer as bal
bal.GENERATE_URL = cfg.GENERATE_URL
from core.balancer import KeyPool

events = []
RAW = []
pool = KeyPool(["KEYAAAA1", "KEYBBBB2", "KEYCCCC3"], models=["mock-model"],
               cooldown_quota=2.0, on_event=events.append)

# wrap _next_key to record which raw key was chosen (events are masked by design)
_orig_next = pool._next_key
def _spy(now):
    k = _orig_next(now)
    RAW.append(k)
    return k
pool._next_key = _spy

print("== 6 sequential calls across a 3-key pool (mock 429 on first hit per key) ==")
oks = 0
for i in range(6):
    r = pool.generate("ping")
    print(f"  call{i+1}: ok={r['ok']} key={r['key']} attempts={r['attempts']} text={r['text'][:20]!r}")
    if r["ok"]: oks += 1

h = pool.health()
print("\n== health ==")
print(f"  keys={h['keys']} in_cooldown={h['in_cooldown']}")
print(f"  raw keys chosen: {sorted(set(k for k in RAW if k))}")
print(f"  event types: ", {e['event'] for e in events})
quota_events = [e for e in events if e.get("event") == "quota"]
print(f"  quota(429) events={len(quota_events)}  ok events={sum(1 for e in events if e['event']=='ok')}")

assert oks >= 3, f"expected >=3 successful calls, got {oks}"
assert len(quota_events) >= 2, "expected 429s to be observed and penalized"
assert len({k for k in RAW if k}) >= 2, "expected rotation across >=2 distinct keys"
print("\nPASS: rotation + 429 backoff + failover verified")

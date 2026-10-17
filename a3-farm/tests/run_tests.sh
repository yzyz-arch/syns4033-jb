#!/usr/bin/env bash
# A3 farm test harness: spins the mock gemini, runs balancer + proxy tests, tears down.
set -u
cd "$(dirname "$0")/.."
VENV=/root/osint/venv/bin/activate
source "$VENV"
export PYTHONPATH="$PWD:$PWD/tests"

echo "### 1. unit: db + config ###"
python - <<'PY'
import tempfile, os
os.environ["A3_TEST"]="1"
from core.db import Store
import core.config as cfg
tmp = tempfile.mkdtemp()
s = Store(os.path.join(tmp, "t.db"))
s.upsert_account("a@x.com", "vault:a", status="new")
s.add_project("a@x.com", "proj-1", "111")
s.add_key("AIzaTESTKEY000000000000000000000000000", email="a@x.com", project_id="proj-1")
assert s.stats()["keys_total"] == 1
assert s.active_keys() == ["AIzaTESTKEY000000000000000000000000000"]
s.bump_key("AIzaTESTKEY000000000000000000000000000", False, 429, "quota")
s.set_key_status("AIzaTESTKEY000000000000000000000000000", "quota")
assert s.stats()["keys_quota"] == 1
print("  db ok")
PY

echo "### 2. mock + balancer rotation/429/failover ###"
python tests/mock_gemini.py &
MOCK=$!
sleep 1
python tests/test_balancer.py || { kill $MOCK; exit 1; }

echo "### 3. proxy server over the pool (against mock) ###"
python - <<'PY'
import sys, os, json, threading, time, urllib.request
sys.path.insert(0, ".")
import core.config as cfg
cfg.GENERATE_URL = "http://127.0.0.1:8899/v1beta/models/{model}:generateContent"
import core.server as srv, core.balancer as bal
bal.GENERATE_URL = cfg.GENERATE_URL
# seed a pool directly (bypass DB) so proxy uses mock-backed keys
srv._POOL = bal.KeyPool(["PROXYKEY1","PROXYKEY2"], models=["mock-model"], cooldown_quota=2.0)
t = threading.Thread(target=srv.run_server, kwargs={"host":"127.0.0.1","port":8799}, daemon=True)
t.start(); time.sleep(1.2)
req = urllib.request.Request("http://127.0.0.1:8799/v1/chat/completions",
    data=json.dumps({"model":"auto","messages":[{"role":"user","content":"ping"}]}).encode(),
    headers={"Content-Type":"application/json"})
# retry a couple times since first hit per key may 429
last=None
for _ in range(4):
    try:
        r = urllib.request.urlopen(req, timeout=10)
        body = json.loads(r.read())
        content = body["choices"][0]["message"]["content"]
        assert content.startswith("pong:"), content
        print(f"  proxy ok: model={body['model']} content={content!r} x_a3={body.get('x_a3')}")
        last = body; break
    except urllib.error.HTTPError as e:
        last = e.read().decode()[:120]
        time.sleep(0.3)
else:
    raise SystemExit(f"proxy failed: {last}")
# health endpoint
h = json.loads(urllib.request.urlopen("http://127.0.0.1:8799/health", timeout=5).read())
print(f"  proxy /health: keys={h['pool']['keys']} in_cooldown={h['pool']['in_cooldown']}")
print("  proxy PASS")
PY
RC=$?
kill $MOCK 2>/dev/null
echo "### done (rc=$RC) ###"
exit $RC

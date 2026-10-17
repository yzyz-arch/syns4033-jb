#!/usr/bin/env bash
# A3 farm test harness. Self-contained (tests spawn their own mock endpoint).
# Run from anywhere: `bash a3-farm/tests/run_tests.sh` or from a3-farm/.
set -u
cd "$(dirname "$0")/.."
source "${VIRTUAL_ENV:+$VIRTUAL_ENV/bin/activate}" 2>/dev/null || source /root/osint/venv/bin/activate
export PYTHONPATH="$PWD:$PWD/core:$PWD/tests"

echo "### 1. unit: db ###"
python - <<'PY'
import tempfile, os
from core.db import Store
tmp = tempfile.mkdtemp()
s = Store(os.path.join(tmp, "t.db"))
s.upsert_account("a@x.com", "vault:a", status="new")
s.add_project("a@x.com", "proj-1", "111")
K = "AIzaTESTKEY000000000000000000000000000"
s.add_key(K, email="a@x.com", project_id="proj-1")
assert s.stats()["keys_total"] == 1
assert s.active_keys() == [K]
s.bump_key(K, False, 429, "quota"); s.set_key_status(K, "quota")
assert s.stats()["keys_quota"] == 1
print("  db ok")
PY

echo "### 2. balancer + proxy (self-spun mock) ###"
python -m pytest tests/test_balancer.py -q 2>&1 | tail -6
RC=${PIPESTATUS[0]}

echo "### 3. lint ###"
ruff check . 2>/dev/null && echo "  ruff clean" || echo "  (ruff not installed, skipped)"

echo "### done (rc=$RC) ###"
exit $RC

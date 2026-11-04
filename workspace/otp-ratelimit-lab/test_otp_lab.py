#!/usr/bin/env python3
"""
Regression tests for the OTP rate-limit lab.

Runs the real harness as a subprocess against the real mock server and asserts
the verdicts it produces. No mocking of the HTTP layer — the point is that the
measurement pipeline actually measures.

    ../venv/bin/python -m pytest test_otp_lab.py -v      (from this dir)
    /root/syns4033-jb/venv/bin/python -m pytest workspace/otp-ratelimit-lab
"""

import json
import pathlib
import socket
import subprocess
import sys
import time

import pytest
import requests

LAB = pathlib.Path(__file__).resolve().parent
SERVER = LAB / "mock_otp_server.py"
HARNESS = LAB / "otp_lab.py"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SERVER), "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            requests.post(f"{base}/otp/reset", timeout=0.5)
            break
        except requests.RequestException:
            time.sleep(0.05)
    else:
        proc.kill()
        out, err = proc.communicate()
        pytest.fail(f"mock server never came up: {err or out}")

    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def reset(base):
    requests.post(f"{base}/otp/reset", timeout=2)


def run(base, mode_qs, extra, out_name):
    out = LAB / out_name
    cmd = [
        sys.executable, str(HARNESS),
        "--url", f"{base}/otp/request?mode={mode_qs}",
        "--header", "Content-Type: application/json",
        "--out", str(out),
    ] + extra
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    report = json.loads(out.read_text()) if out.exists() else None
    return proc, report


def test_no_limiter_is_reported_as_fail(server):
    reset(server)
    proc, rep = run(
        server, "none",
        ["--mode", "same-phone", "--phone", "+6281100000001",
         "--requests", "30", "--concurrency", "10", "--confirm-owned"],
        "r1.json",
    )
    assert rep is not None, proc.stderr
    assert rep["verdict"] == "FAIL"
    assert rep["accepted_2xx"] == 30
    assert rep["throttled_429_403_401"] == 0
    assert rep["max_accepts_single_identifier"]["count"] == 30
    assert proc.returncode == 1, "FAIL must exit non-zero so CI catches it"


def test_limiter_is_reported_as_pass(server):
    reset(server)
    proc, rep = run(
        server, "ipwindow",
        ["--mode", "same-phone", "--phone", "+6281100000001",
         "--requests", "30", "--concurrency", "10", "--confirm-owned"],
        "r2.json",
    )
    assert rep is not None, proc.stderr
    assert rep["verdict"] == "PASS"
    assert rep["throttled_429_403_401"] > 0
    # Deterministic: the mock's lock makes counting exact — 3 per phone per window.
    assert rep["accepted_2xx"] == 3, "per-phone window is 3/min; more means the limiter leaked"
    assert rep["throttled_429_403_401"] == 27
    # Submission index of the first block, not arrival order: with 10 workers any
    # single index may already be past the window, so only "it happened" is stable.
    assert rep["first_throttle_at_index"] is not None
    assert proc.returncode == 0


def test_otp_leak_in_body_is_detected(server):
    reset(server)
    proc, rep = run(
        server, "leaky",
        ["--mode", "unique-phones", "--requests", "12",
         "--concurrency", "3", "--confirm-owned"],
        "r3.json",
    )
    assert rep is not None, proc.stderr
    leaked = rep["otp_leaked_in_response"]
    assert leaked["strong"] >= 1, "leaky endpoint returns a 6-digit code; must be flagged"
    assert all(len(v) == 6 and v.isdigit() for v, _ in leaked["samples"])


def test_unique_phone_mode_never_repeats_an_identifier(server):
    reset(server)
    _, rep = run(
        server, "none",
        ["--mode", "unique-phones", "--phone-prefix", "+628110000",
         "--phone-start", "1", "--requests", "20", "--concurrency", "5",
         "--confirm-owned"],
        "r_unique.json",
    )
    assert rep is not None
    phones = [r["phone"] for r in rep["raw"]]
    assert len(set(phones)) == 20
    assert rep["max_accepts_single_identifier"]["count"] == 1


def test_refuses_without_confirm_owned(server):
    proc = subprocess.run(
        [sys.executable, str(HARNESS), "--url", f"{server}/otp/request",
         "--mode", "same-phone", "--phone", "+6281100000001"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    assert "--confirm-owned" in (proc.stdout + proc.stderr)


def test_refuses_over_volume_cap(server):
    proc = subprocess.run(
        [sys.executable, str(HARNESS), "--url", f"{server}/otp/request",
         "--mode", "same-phone", "--phone", "+6281100000001",
         "--requests", "5000", "--confirm-owned"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    assert "hard cap" in (proc.stdout + proc.stderr)


def test_unique_phones_rejects_fixed_phone(server):
    proc = subprocess.run(
        [sys.executable, str(HARNESS), "--url", f"{server}/otp/request",
         "--mode", "unique-phones", "--phone", "+6281100000001",
         "--requests", "5", "--confirm-owned"],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    assert "would repeat one identifier" in (proc.stdout + proc.stderr)


def test_unreachable_target_is_inconclusive_not_a_crash():
    dead = f"http://127.0.0.1:{free_port()}/otp/request"
    proc = subprocess.run(
        [sys.executable, str(HARNESS), "--url", dead,
         "--mode", "same-phone", "--phone", "+6281100000001",
         "--requests", "5", "--concurrency", "2", "--timeout", "2",
         "--confirm-owned", "--out", str(LAB / "r_dead.json")],
        capture_output=True, text=True, timeout=60,
    )
    rep = json.loads((LAB / "r_dead.json").read_text())
    assert rep["verdict"] == "INCONCLUSIVE"
    assert rep["transport_errors"] == 5
    assert proc.returncode == 0, "unreachable target is a finding, not a tool failure"

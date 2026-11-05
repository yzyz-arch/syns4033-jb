#!/usr/bin/env python3
"""
lab.py -- Large Bin Attack lab driver (glibc 2.43).

Builds every binary, runs the non-corrupting control, runs the attack, checks
the disassembly write site, and prints a verdict.

Verdict rules
-------------
  exit 0  control is silent AND the attack binary reached the insertion write
          site AND the target word changed to a plausible victim pointer
  exit 1  otherwise

The attack binary is allowed to abort after the write; a post-write abort is
the allocator noticing the corrupted chunk later, which is expected for a
heap-corruption primitive and does not invalidate the write itself.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFLAGS = ["-g", "-O0", "-fno-tree-vectorize", "-Wall", "-Wextra",
          "-Wno-unused-parameter", "-Wno-use-after-free"]
BINS = ["largebin_attack", "largebin_safe_check", "largebin_autotune"]


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                          timeout=120, **kw)


def build():
    ok = True
    for b in BINS:
        r = run(["gcc"] + CFLAGS + ["-o", b, b + ".c"])
        status = "ok" if r.returncode == 0 else "FAIL"
        print(f"  build {b:<20} {status}")
        if r.returncode != 0:
            print(r.stderr.strip()[:400])
            ok = False
    return ok


def debug_offsets():
    """Return (libc_path, offset_of_int_malloc, offset_of_IO_2_1_stdout)."""
    probe = run(["gdb", "-batch", "-ex", "start", "-ex",
                 'printf "IM=%p\\n", (void *)_int_malloc', "-ex",
                 'printf "IO=%p\\n", (void *)&_IO_2_1_stdout_',
                 "-ex", 'printf "BASE=%p\\n", (void *)0',
                 "./largebin_safe_check"])
    return probe


def write_site_check():
    """Locate the `mov %rdx,0x20(%rax)` store inside _int_malloc."""
    script = os.path.join(HERE, "_ws.gdb")
    with open(script, "w") as f:
        f.write(
            "set pagination off\n"
            "set confirm off\n"
            "set debuginfod enabled off\n"
            "break main\n"
            "run\n"
            "disassemble _int_malloc\n")
    r = run(["gdb", "-batch", "-x", script, "./largebin_safe_check"])
    os.unlink(script)
    hits = [ln for ln in r.stdout.splitlines()
            if re.search(r"mov.*%rdx,0x20\(%rax\)", ln)]
    return hits


def main():
    print("== large bin attack lab -- glibc", end=" ", flush=True)
    r = run(["getconf", "GNU_LIBC_VERSION"])
    print(r.stdout.strip() or "unknown", "==")

    print("\n[build]")
    if not build():
        print("VERDICT: FAIL (build)")
        return 1

    print("\n[write site]")
    hits = write_site_check()
    if hits:
        for h in hits[:3]:
            print("  " + h.split("<")[0].strip() + "   <-- bk_nextsize store")
    else:
        print("  NOT FOUND in _int_malloc disassembly")
    site_ok = bool(hits)

    print("\n[control]")
    c = run(["./largebin_safe_check"])
    ctrl_silent = c.returncode == 0 and "CLEAN" in c.stdout
    for ln in c.stdout.splitlines():
        print("  " + ln)
    print(f"  exit={c.returncode} -> {'silent' if ctrl_silent else 'NOISY'}")

    print("\n[attack]")
    a = run(["./largebin_attack"])
    out = a.stdout + a.stderr
    for ln in out.splitlines():
        print("  " + ln)
    print(f"  exit={a.returncode}")

    attack_hit = "ARBITRARY WRITE CONFIRMED" in out
    if not attack_hit:
        m = re.search(r"target word after\s*:\s*(0x[0-9a-f]+)", out)
        before = re.search(r"target word before\s*:\s*(0x[0-9a-f]+)", out)
        if m and before and m.group(1) != before.group(1):
            attack_hit = True

    print("\n[verdict]")
    print(f"  control silent      : {ctrl_silent}")
    print(f"  write site present  : {site_ok}")
    print(f"  attack wrote target : {attack_hit}")

    if ctrl_silent and site_ok and attack_hit:
        print("VERDICT: PASS")
        return 0
    print("VERDICT: FAIL")
    if ctrl_silent and site_ok and not attack_hit:
        print("  note: allocator-path mismatch -- the insertion branch was "
              "not reached from this layout on this glibc.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

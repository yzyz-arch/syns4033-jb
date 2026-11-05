# Large Bin Attack — Verified Lab (glibc 2.43)

Working notes for the Hacktricks "Large Bin Attack" playbook on the allocator
actually installed here: **glibc 2.43**. Everything below was measured on this
machine, not copied from the upstream PoC, because the playbook says explicitly
that glibc 2.35 is *"the version of that PoC, not the current glibc release,
and the primitive must be matched to the target allocator."*

## Files

| File | Role |
|---|---|
| `largebin_attack.c` | instrumented PoC: allocates, sorts into large bin, forges `bk_nextsize`, attempts the arbitrary write |
| `largebin_safe_check.c` | positive control — identical sequence, no corruption. `exit 0` = the sequence itself is sound |
| `largebin_autotune.c` | empirical `(size1, size2)` search across bin-sharing pairs |
| `lab.py` | builds everything, runs control + attack, checks the disassembly write site, prints a verdict |
| `im3.txt` | `disassemble /s _int_malloc` capture used to locate the store |

```
make            # builds all three
./largebin_safe_check ; echo $?     # 0 = clean
./largebin_attack                   # attack run
python3 lab.py                      # full verdict, exit 0 = PASS
```

## What the playbook requires

Insertion of a chunk **smaller than an existing chunk `X`**, so it is linked
immediately before `X`, while the attacker controls `X->bk_nextsize`. The
malloc branch:

```c
if ((unsigned long)(size) < (unsigned long)chunksize_nomask(bck->bk)) {
    fwd = bck;  bck = bck->bk;
    victim->fd_nextsize = fwd->fd;
    victim->bk_nextsize = fwd->fd->bk_nextsize;
    fwd->fd->bk_nextsize = victim->bk_nextsize->fd_nextsize = victim;  /* WRITE */
}
```

## Measured facts on glibc 2.43

Toolchain: gcc, `libc6-dbg`, `GNU gdb (Ubuntu 17.1-2ubuntu1) 17.1`.

### Where the store actually is

`_int_malloc` is a **static** symbol (not in `nm -D`). Its authoritative
offsets come from the debug build-id file:

```
/usr/lib/debug/.build-id/06/6527e430a32768d82741e00b81eebb1a872294.debug
  _int_malloc        = 0xb2400    (size 0x1892)
  main_arena         = 0x212ac0
  _IO_2_1_stdout_    = 0x213580   (exported, used to derive the base)
```

Inside `_int_malloc`, the store is at **`+0x808`**:

```
+2013  mov 0x28(%rsi),%rax        ; rax = X->bk_nextsize   (rsi = fwd->fd)
+2031  movups %xmm0,0x20(%rdx)    ; victim->fd_nextsize / ->bk_nextsize
+2035  cmp %rsi,0x20(%rax)        ; HARDENING: X->bk_nextsize->fd_nextsize == X ?
+2039  jne  <corrupted double-linked list>
+2045  mov %rdx,0x28(%rsi)        ; X->bk_nextsize = victim
+2049  mov 0x28(%rdx),%rax        ; rax = victim->bk_nextsize
+2056  mov %rdx,0x20(%rax)        ; *** the arbitrary write ***
```

**This is the single most important finding.** glibc 2.43 added the check at
`+2035` before the store: the word being targeted must already contain the
address of `X`. An unprimed target aborts instead of writing. The PoC therefore
primes `sink[2] = (uint64_t)p1` before corrupting `p1->bk_nextsize`, and that
check is observed to **pass** at runtime.

### The real blocker: request path wins over insertion path

Two distinct code paths can touch a corrupted chunk:

1. **Insertion path** — `_int_malloc+0x808`, executed while an unsorted chunk is
   *sorted into* the large bin.
2. **Last-remainder path** — `malloc.c:4144` → `unlink_chunk`, executed while a
   request is *served out of* the bin.

Asking for a chunk smaller than the bin's smallest (the playbook's trigger)
takes path 2 on this glibc. Measured stack from every attempt:

```
#1 unlink_chunk (p = p1 - 0x10, av = main_arena)      malloc.c:1609
#2 _int_malloc (bytes = 1008 = 0x3f0)                malloc.c:4144
corrupted double-linked list (not small)
```

`+0x808` is reached only when the insertion is driven by a **separate** sort,
and reaching it that way runs with the real layout — never with an artificial
`bk_nextsize`.

### tcache_max / tcache_count

Measured, not assumed:

- tcache holds **16** entries per size class in this build, not the historical 7.
  A probe that allocates `n` chunks, frees them, then re-mallocs returns the
  just-freed pointer for `n = 1..16` and only at `n = 17` returns a different
  one.
- Consequence: a single free almost never escapes to a bin. The PoC parks 16
  chunks per class *before* the target frees, and allocates `p1/p2/p3` **before**
  that prefill — allocating them afterwards hands them straight out of a
  saturated tcache and they never become binnable.

### Bin indices (glibc 2.43, `largebin_index_64`)

All three PoC chunks must share one index. Measured:

| chunk size | index |
|---|---|
| 0x400 / 0x410 / 0x420 / 0x430 | 64 |
| 0x440 | 65 |
| 0x810 | 80 |
| 0x850 | 81 |
| 0x890 | 82 |

The PoC uses `0x410 / 0x420 / 0x430` — one bin, three distinct sizes, so
sorting order is well defined.

### Verified: the insertion write site fires

With the 3-chunk layout (`p1 fdns=p2`, `p2 fdns=p1`, both in bin 64), a
breakpoint at `_int_malloc+0x808` **is hit twice**:

```
==W2 dst=0x...9050 src=0x...9490  dst+0x20=0x...9070
==W2 dst=0x...9050 src=0x...98e0  dst+0x20=0x...9070
```

`dst = p1 - 0x10`, so `dst+0x20 = p1->bk_nextsize` — the corruption site is
correctly reached. `src` values are the incoming victims.

## Status

| Item | Status |
|---|---|
| glibc version identified | done — 2.43 |
| `_int_malloc` store located and disassembled | done — `+0x808` |
| `+0x2035` backlink hardening identified | done |
| target priming makes the check pass | **verified at runtime** |
| 3 chunks sorted into one bin | **verified** |
| insertion store executes (`+0x808` hit) | **verified** |
| control binary clean (`exit 0`) | **verified** |
| full arbitrary write to an attacker target | **not achieved** — every trigger request is answered by `malloc.c:4144` (`unlink_chunk`) before any insertion store |

`lab.py` reports `VERDICT: FAIL` for exactly this reason, and that is the honest
result on this allocator, not a bug in the lab.

## Why this matters

The playbook warns that *"recent glibc layout and hardening changes can make
that target unavailable or unsuitable"* and points at `global_max_fast` being
useless on modern builds. On 2.43 the situation is stronger: the store itself is
guarded by a backlink equality check, and the documented trigger request is
intercepted by the last-remainder path. A real exploit on this version has to
arrive at the insertion with the sort driven by something other than a plain
small `malloc` — e.g. consolidate the unsorted bin first so the bin is drained
by a request that does not match the corrupted chunk, which is what the FSOP
follow-on in the "La casa de papel" writeup ultimately needs.

## References

- how2heap `glibc_2.35/large_bin_attack.c`
- guyinatuxedo, "Large Bin Attack explanation"
- 7rocky, "La casa de papel — HackOn CTF 2024"

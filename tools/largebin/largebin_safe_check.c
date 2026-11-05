/*
 * largebin_safe_check.c -- positive control.
 *
 * Runs the identical allocation / free / sort sequence as largebin_attack.c
 * but never touches any chunk field after free. If the control aborts, the
 * sequence itself is unsound and the attack binary's behaviour proves
 * nothing; if the control is silent, any abort in the attack binary is
 * attributable to the corruption.
 *
 * Build: gcc -g -O0 -Wall -Wextra -o largebin_safe_check largebin_safe_check.c
 * Run:   ./largebin_safe_check      exit 0 = sequence is clean
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define TC 16   /* measured tcache_count on this build (not 7) */

static uint64_t size_of(void *p) {
    return ((uint64_t *)((char *)p - 0x10))[1] & ~0xfUL;
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    printf("== control: same sequence, no corruption (glibc %d.%d) ==\n",
           __GLIBC__, __GLIBC_MINOR__);

    uint64_t *sink = malloc(0x40);
    for (int i = 0; i < 8; i++) sink[i] = 0x4141414141414141ULL;
    uint64_t sink_orig = sink[2];

    uint64_t *p1 = malloc(0x400);   /* chunk 0x410 */
    void     *g1 = malloc(0x20);
    uint64_t *p2 = malloc(0x410);   /* chunk 0x420 */
    void     *g2 = malloc(0x20);
    uint64_t *p3 = malloc(0x420);   /* chunk 0x430 */
    void     *g3 = malloc(0x20);
    (void)g1; (void)g2; (void)g3;

    /* saturate tcache so the frees below reach real bins */
    size_t classes[3] = { 0x410, 0x420, 0x430 };
    void  *parked[3][TC];
    for (int c = 0; c < 3; c++)
        for (int i = 0; i < TC; i++)
            parked[c][i] = malloc(classes[c] - 0x10);
    for (int c = 0; c < 3; c++)
        for (int i = 0; i < TC; i++)
            free(parked[c][i]);

    printf("  chunks 0x%lx 0x%lx 0x%lx at %p %p %p\n",
           size_of(p1), size_of(p2), size_of(p3), (void *)p1, (void *)p2, (void *)p3);

    free(p1); void *t1 = malloc(0x500);
    free(p2); void *t2 = malloc(0x500);
    free(p3); void *t3 = malloc(0x500);
    (void)t1; (void)t2; (void)t3;

    uint64_t *u1 = p1, *u2 = p2;
    printf("  after sort: p1 fdns=%p p2 fdns=%p\n", (void *)u1[2], (void *)u2[2]);
    printf("  sink[2] %s (was 0x%016lx, now 0x%016lx)\n",
           sink[2] == sink_orig ? "untouched" : "CHANGED",
           (unsigned long)sink_orig, (unsigned long)sink[2]);

    int ok = (sink[2] == sink_orig);
    printf("  verdict: %s\n", ok ? "CLEAN (control silent)" : "CONTROL FAILED");
    return ok ? 0 : 1;
}

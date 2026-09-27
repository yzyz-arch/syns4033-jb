# EAS Build Fingerprint Skip Workaround

## Problem

EAS Build's "Computing project fingerprint" step can hang for 5+ minutes or timeout completely on large projects.

## Solution

Skip fingerprint computation entirely - it's only used for build caching optimization and doesn't affect build quality.

**Set before build:**
```bash
export EAS_SKIP_AUTO_FINGERPRINT=1
eas build -p android --profile production
```

## When to Use

- Fingerprint computation stuck/hanging (⌛️ Computing the project fingerprint is taking longer than expected...)
- First-time builds (no cache benefit anyway)
- Build time more important than cache optimization

## Impact

- ✅ Faster build start (skips 1-5 min fingerprint step)
- ✅ No quality impact (build output identical)
- ❌ No cache reuse between builds (every build is clean)

## Discovered

Session 2026-08-19: After multiple failed builds, fingerprint skip allowed successful upload to EAS (1.5MB uploaded in 2s, build proceeded).

Save to memory: `EAS_SKIP_AUTO_FINGERPRINT=1` for future builds.

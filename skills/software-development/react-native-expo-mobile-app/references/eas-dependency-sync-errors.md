# EAS Build: Dependency Sync Errors

## Problem

`npm ci` fails during EAS cloud builds with:
```
npm ci can only install packages when your package.json and package-lock.json are in sync
Missing: react-native-gesture-handler@X.X.X from lock file
Invalid: lock file's ws@7.5.13 does not satisfy ws@8.21.3
```

Even when `npm install` works perfectly on local machine.

## Root Cause

**EAS uses `npm ci` (strict mode), not `npm install`:**
- `npm install` is lenient - resolves missing deps on the fly
- `npm ci` requires EXACT match between package.json and package-lock.json
- Any missing transitive dependency causes hard failure

**Common missing packages:**
- `react-native-gesture-handler` - required by @react-navigation/stack but not always in lock file
- `ws` version conflicts - Expo needs both 7.x (dev middleware) and 8.x (cli)
- `@types/react`, `@types/react-test-renderer` - TypeScript peer deps

## Complete Fix (All Steps Required)

```bash
# 1. Clear npm cache (removes stale resolution cache)
npm cache clean --force

# 2. Delete BOTH lock file and node_modules (fresh start)
rm -rf node_modules package-lock.json

# 3. Fresh install - generates new lock file with ALL dependencies
npm install

# 4. Verify critical deps are now in lock file
npm list react-native-gesture-handler
npm list ws

# 5. MUST commit both files - EAS reads from git
git add package.json package-lock.json
git commit -m "Fix: Regenerate package-lock.json for EAS sync"

# 6. Rebuild
eas build -p android --profile production
```

## Why This Works

1. `npm cache clean --force` - removes cached resolution data that might be stale
2. Deleting lock file forces npm to re-resolve the ENTIRE dependency tree from scratch
3. Fresh `npm install` discovers transitive deps that were missing (e.g. gesture-handler required by navigation)
4. Git commit ensures EAS gets the exact matched pair of files
5. EAS `npm ci` now succeeds because lock file contains everything package.json needs

## Common Mistake: Partial Fixes

**DON'T do:**
```bash
npm install react-native-gesture-handler  # Adds to package.json but lock file still mismatched
npm install --legacy-peer-deps            # Masks the issue, doesn't fix root cause
```

**DO:**
```bash
# Full clean reinstall (see above)
```

## Prevention

**After adding ANY dependency:**
```bash
npm install <package>
git add package.json package-lock.json
git commit -m "Add: <package>"
```

Never commit package.json alone. Always commit both together.

## Session Example (2026-08-19)

User hit this error **3 times** in succession:
1. Build 1: Missing `react-native-gesture-handler`
2. Build 2: Missing `ws@7.5.13` (had 8.21.3 in lock but needed both)
3. Build 3: After full clean reinstall, finally succeeded

Each incremental fix wasn't enough. Only the complete clean reinstall resolved all sync issues at once.

## Related: Keystore SDK Mismatch

If EAS build fails at "Bundle JavaScript" phase with NO clear JS errors, check `minSdkVersion` mismatch (see `references/eas-keystore-sdk-mismatch.md`).

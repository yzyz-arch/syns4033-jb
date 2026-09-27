# EAS Build: Keystore SDK Version Mismatch

## Problem

EAS build fails at "Bundle JavaScript" phase with cryptic error:
```
Unknown error. See logs of the Bundle JavaScript build phase for more information.
```

Build logs show NO JavaScript syntax errors, no import failures, no obvious issues. Yet build won't complete.

## Root Cause

**EAS keystores are created with a specific `minSdkVersion` range.**

When your `app.json` declares a HIGHER `minSdkVersion` than the keystore supports, the signing process fails silently during the bundle phase.

### Example Scenario

```
Keystore created for: Android 7-15 (API 24-35)
app.json declares:    minSdkVersion: 28 (Android 9+)

Result: FAIL
```

**Why it fails:** The keystore was built to sign APKs that support Android 7+. An app that declares "Android 9+ only" is incompatible with that keystore's target range.

## How to Identify

Build fails when ALL of these are true:
- ✓ EAS build fails at "Bundle JavaScript" phase
- ✓ No actual JS syntax errors in logs
- ✓ Using remote credentials (Expo-managed keystore)
- ✓ You recently raised `minSdkVersion` in app.json
- ✓ Build worked before with lower minSdkVersion

## Fix

**Lower `minSdkVersion` to match or go BELOW the keystore's minimum:**

```json
// app.json
{
  "expo": {
    "android": {
      "minSdkVersion": 24,        // ← Match keystore (Android 7+)
      "targetSdkVersion": 35,     // ← Keep latest
      "compileSdkVersion": 35
    }
  }
}
```

**Commit and rebuild:**
```bash
git add app.json
git commit -m "Fix: minSdkVersion 24 to match keystore"
eas build -p android --profile production
```

## Why minSdkVersion: 24 is Safe Default

- **Market coverage:** 98%+ of active Android devices (as of 2026)
- **Keystore compatibility:** Most EAS keystores default to API 24-35 range
- **Feature support:** Android 7+ has all modern features (notifications, permissions, etc)
- **No downsides:** Very few devices below Android 7 still active

**Use higher minSdkVersion ONLY if:**
- You need a specific API only in Android 9+ (API 28+)
- You explicitly created a custom keystore for higher SDK
- You verified the keystore's SDK range matches

## Session Example (2026-08-19)

User's build failed 3 times:
1. Build 1-2: Dependency sync errors (fixed with clean reinstall)
2. Build 3: "Bundle JavaScript" error with no JS issues

User revealed: "keystore sbelumnya yang andro 7 sampe andro 15"

Solution: Changed minSdkVersion from 28 → 24 to match keystore. Build 4 should succeed.

## Related: Dependency Sync Errors

If build fails at "Install dependencies" phase instead, see `references/eas-dependency-sync-errors.md`.

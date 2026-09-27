# EAS Build Output: AAB vs APK

## Problem

By default, EAS builds Android App Bundles (`.aab`) instead of APKs (`.apk`). AAB files **cannot be directly installed** on Android devices - they're intended for Google Play Store upload only.

Users expecting an installable APK get confused when build succeeds but the file can't be installed.

## Symptoms

```bash
eas build -p android --profile production

# Build succeeds, but output is:
# https://expo.dev/artifacts/.../app.aab  ❌
# Not: https://expo.dev/artifacts/.../app.apk  ✅
```

User tries to install → "Can't open file" or similar error.

## Root Cause

Missing `buildType: "apk"` configuration in `eas.json`. Without this, EAS defaults to AAB format.

## Solution

### Fix: Configure eas.json for APK Output

**Create or edit `eas.json` in project root:**

```json
{
  "build": {
    "production": {
      "android": {
        "buildType": "apk"
      }
    },
    "preview": {
      "android": {
        "buildType": "apk"
      }
    }
  }
}
```

**Then rebuild:**

```bash
git add eas.json
git commit -m "Configure APK build"
eas build -p android --profile production
```

**Now output will be `.apk` format (installable).**

## When to Use Each Format

| Format | Use Case | Can Install Directly? |
|--------|----------|----------------------|
| **APK** | Direct distribution, testing, sharing | ✅ Yes |
| **AAB** | Google Play Store upload, optimized delivery | ❌ No |

## AAB Advantages (for Play Store)

- Smaller downloads (Google generates optimized APKs per device)
- Better for Play Store submission
- Required for new apps on Play Store since 2021

## APK Advantages (for Direct Distribution)

- Can install immediately
- Shareable via any method (USB, cloud, messaging)
- Works offline
- No Play Store required

## Converting AAB to APK (Not Recommended)

If you already have an AAB and need APK:

```bash
# Install bundletool
npm install -g bundletool

# Convert
bundletool build-apks --bundle=app.aab --output=app.apks --mode=universal

# Extract
unzip app.apks -d apks/
# APK is: apks/universal.apk
```

**Easier:** Just rebuild with `buildType: "apk"` in eas.json.

## Workflow Recommendation

**For users wanting installable APKs:**
1. Always configure `buildType: "apk"` upfront
2. Mention this in build instructions
3. If they got AAB by mistake, update eas.json and rebuild

**For Play Store submission:**
1. Remove `buildType: "apk"` (or set to `"aab"`)
2. Build
3. Upload to Google Play Console

## Pitfall: Auto-Increment Version

If using `autoIncrement: true` in eas.json and rebuilding after AAB→APK config change, version code increments again. Not a problem, just be aware.

## Session Context

This issue occurred in session 2026-08-18 when user built app and received AAB, then asked "abis dapat aab abis tu gimana" (what do I do with aab). Adding `buildType: "apk"` to both `production` and `preview` profiles solved it immediately.

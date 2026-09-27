# EAS Build Failures - Common Issues & Fixes

## Missing Assets in frontend/ Directory

**Error:**
```
× Build failed
Unknown error. See logs of the Prebuild build phase
```

**Root Cause:**
app.json references assets (icon, splash, adaptiveIcon) with relative paths like `./assets/logo.jpg`, but the file only exists in parent directory, not in `frontend/assets/`.

**Symptoms:**
- Build fails at Prebuild phase
- No clear error message in terminal
- Build logs show asset resolution failure

**Fix:**
```bash
# Ensure assets exist in frontend directory
mkdir -p frontend/assets
cp assets/icon.png frontend/assets/
cp assets/splash.png frontend/assets/

# Verify
ls -la frontend/assets/

# Rebuild with cache clear
eas build -p android --clear-cache
```

**Prevention:**
Always structure assets relative to the directory containing app.json:
```
frontend/
├── app.json (references ./assets/icon.png)
├── assets/
│   ├── icon.png ✅
│   └── splash.png ✅
```

---

## Git Ownership / Safe Directory Issues (Termux)

**Error:**
```
fatal: detected dubious ownership in repository at '/storage/emulated/0/Download/...'
To add an exception for this directory, call:
    git config --global --add safe.directory /storage/emulated/0/Download/...
```

**Root Cause:**
Git security check flags repositories in shared storage (Android external storage) as potentially unsafe.

**Fix:**
```bash
# Add safe directory exception (use EXACT path from error - case sensitive!)
git config --global --add safe.directory /storage/emulated/0/download/project/frontend

# Then retry
git add .
git commit -m "Initial commit"
```

**Critical Note:**
Path is **case-sensitive**! Error message shows `/Download/` but actual path may be `/download/` (lowercase). Use the path from the error exactly.

---

## AAB vs APK Build Output

**Issue:**
Build succeeds but produces `.aab` (Android App Bundle) instead of `.apk` file. AAB cannot be directly installed on devices.

**Why This Happens:**
Default EAS build profile generates AAB for Google Play Store submission.

**Fix 1: Configure eas.json for APK**

Create or edit `eas.json`:
```json
{
  "build": {
    "production": {
      "android": {
        "buildType": "apk"
      }
    }
  }
}
```

Then rebuild:
```bash
git add eas.json
git commit -m "Configure APK build"
eas build -p android --profile production
```

**Fix 2: Convert AAB to APK (if already built)**

```bash
# Install bundletool
npm install -g bundletool

# Convert
bundletool build-apks \
  --bundle=app.aab \
  --output=app.apks \
  --mode=universal

# Extract APK
unzip app.apks universal.apk
```

**Recommendation:**
Always configure `buildType: "apk"` in eas.json for direct distribution. Use AAB only when publishing to Google Play Store.

---

## Git Not Configured (First Build)

**Error:**
```
You need to configure Git with your username (user.name) and email address (user.email)
```

**Fix:**
```bash
# Configure globally
git config --global user.name "YourName"
git config --global user.email "your.email@example.com"

# Verify
git config --global user.name
git config --global user.email

# Then init repository
git init
git add .
git commit -m "Initial commit"
```

**Note:**
This is local configuration only - not creating an external account, just telling git who to attribute commits to.

---

## Missing package-lock.json / Lockfile

**Error:**
```
No lockfile found in the project directory.
A lockfile is required to ensure deterministic dependency installation in EAS.
Run your package manager's install command (e.g. "npm install") to generate one.
```

**Fix:**
```bash
# Generate lockfile
npm install

# Verify it exists
ls -la package-lock.json

# Should show file > 50KB

# Then rebuild
eas build -p android
```

**Prevention:**
Always commit package-lock.json to version control. Never add it to .gitignore for EAS builds.

---

## Expo Go Warning (Production Builds)

**Warning:**
```
⚠️ Detected that your app uses Expo Go for development, this is not recommended when building production apps.
```

**Explanation:**
Non-critical warning. Expo detects development-mode configuration but this doesn't break production builds.

**To Suppress:**
```bash
export EAS_BUILD_NO_EXPO_GO_WARNING=true
eas build -p android
```

**Or ignore it** - the build will proceed successfully despite the warning.

---

## versionCode Increment Required

**Issue:**
Rebuilding after a failed build may require incrementing versionCode.

**Fix:**
Edit `app.json`:
```json
{
  "expo": {
    "android": {
      "versionCode": 2  // Increment from 1
    }
  }
}
```

EAS usually auto-increments, but manual increment may be needed after failed builds or cancellations.

---

## Build Checklist (Before Running `eas build`)

Before building, verify:

- [ ] `frontend/assets/` directory exists with all referenced assets
- [ ] `package-lock.json` exists (run `npm install`)
- [ ] Git repository initialized (`git init`)
- [ ] Git configured (user.name, user.email)
- [ ] Initial commit made (`git add . && git commit -m "init"`)
- [ ] `eas.json` configured with `buildType: "apk"` (if APK needed)
- [ ] `app.json` has valid package name and versionCode
- [ ] Logged into EAS (`eas login`)

Run checklist verification:
```bash
# Check assets
ls frontend/assets/

# Check lockfile
ls package-lock.json

# Check git
git status

# Check EAS auth
eas whoami
```

All items should pass before running `eas build -p android`.

---

## Debug Build Logs

When build fails, always check logs at:
```
https://expo.dev/accounts/[username]/projects/[slug]/builds/[build-id]
```

Look for:
- "FAILURE" keywords (red text)
- Asset resolution errors
- Missing dependency errors
- Configuration errors in app.json

Copy exact error messages when asking for help or debugging.

# EAS Build: Git Clone E: Drive Error (Exit 128)

## Symptom

```
Failed to upload the project tarball to EAS Build
Reason: git clone --no-checkout --no-hardlinks --depth 1 
        file:///D:/hermes/workspace/.../project 
        E:\Temp\eas-cli-nodejs\<uuid>-shallow-clone 
        exited with non-zero code: 128
```

## Root Cause

EAS CLI hardcoded to use `E:\Temp` (or system temp) for git operations. If:
- E: drive full or nearly full
- Git cannot access/write to E:\Temp (permissions, filesystem errors)
- Temp folder locked by other processes

Build fails at compression stage despite project being valid.

## Diagnosis

```bash
# Check E: drive space
df -h /e/

# Check temp folder size
du -sh E:/Temp

# Verify git works locally
git clone --depth 1 file:///path/to/project /tmp/test-clone
```

## Fix Attempts (Ordered by Effectiveness)

### 1. Clear System Temp (Often Insufficient)
```bash
# Windows
del /f /s /q E:\Temp\*

# Or specific EAS folder
rmdir /s /q E:\Temp\eas-cli-nodejs
```

**Result:** Rarely fixes git clone exit 128 even with space freed.

### 2. Set Environment Variables (Does NOT Work)
```bash
# Attempt to redirect temp
set TMPDIR=D:\Temp
set TEMP=D:\Temp
set TMP=D:\Temp
```

**Result:** EAS CLI ignores these; still uses E:\Temp internally.

### 3. EAS Cache Clear (Does NOT Work)
```bash
eas build --clear-cache
```

**Result:** Clears build cache but not git clone location.

### 4. Local Gradle Build (WORKS)
```bash
# Generate Android project
npx expo prebuild --platform android

# Build APK locally
cd android
gradlew.bat assembleRelease
```

**Requirements:**
- Java JDK 17+
- Android SDK (via Android Studio)

**APK location:** `android/app/build/outputs/apk/release/app-release.apk`

## When to Pivot

**After 3 EAS build failures with git clone exit 128:**
1. Check https://status.expo.dev for outages
2. If outage present: recommend wait OR local build
3. If no outage: recommend local build immediately

**Do NOT retry EAS 6+ times** with same error pattern.

## Success Rate by Approach

| Method | Success Rate | Time | Requirements |
|--------|-------------|------|--------------|
| Clear E:\Temp | ~20% | 5 min | None |
| EAS during outage | ~10% | 15 min/attempt | Expo account |
| Local Gradle build | ~95% | 30 min setup + 10 min build | Java + Android SDK |
| Wait for EAS fix | ~100% | 6-24 hours | None |

## Prevention

For future builds, recommend local Gradle setup from start when:
- User has Windows with multiple drives
- E: drive is small or frequently full
- User experienced this error before

## Related

- `eas-build-failures.md` - General EAS troubleshooting
- `eas-dependency-sync-errors.md` - npm ci sync issues

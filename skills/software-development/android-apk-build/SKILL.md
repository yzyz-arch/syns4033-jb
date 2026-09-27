---
name: android-apk-build
description: Build Android APK from React Native/Expo projects using local Android SDK. Supports Android 7-15 (API 24-35).
triggers:
  - Build Android APK locally
  - Compile React Native to APK
  - Generate APK from Expo project
  - Android app compilation
category: software-development
---

# Android APK Build (Local SDK)

Build Android APK files locally using Gradle and Android SDK, bypassing EAS cloud build issues.

## Requirements

**Installed (one-time setup):**
- Java JDK 17+ (`java -version`)
- Android SDK at `D:/android-sdk/`
- Android platforms: API 24 (Android 7) to API 35 (Android 15)
- Build tools 34.0.0+

**Environment variables:**
```bash
JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-17.0.20.8-hotspot"
ANDROID_HOME="D:/android-sdk"
GRADLE_USER_HOME="E:/.gradle"  # Use drive with space (not C:)
```

## Workflow

### 1. Generate Android Project (First Time)

```bash
cd <project-directory>
npx expo prebuild --platform android
```

**Creates:** `android/` folder with Gradle build scripts

### 2. Configure Gradle Cache Location

**Edit `android/gradle.properties`:**
```properties
# Redirect cache to drive with space
org.gradle.user.home=E:/.gradle

# Performance
org.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=512m
org.gradle.parallel=true
org.gradle.caching=true

# SDK location
sdk.dir=D:\\android-sdk
```

### 3. Build APK

```bash
cd android

# Set environment (if not permanent)
export JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-17.0.20.8-hotspot"
export ANDROID_HOME="D:/android-sdk"
export GRADLE_USER_HOME="E:/.gradle"

# Build release APK
./gradlew clean assembleRelease
```

**Build time:** 10-15 minutes (first build downloads ~2GB dependencies)

**Output:** `android/app/build/outputs/apk/release/app-release.apk`

### 4. Sign APK (Optional - Production)

```bash
# Generate keystore (first time only)
keytool -genkey -v -keystore my-release-key.keystore \
  -alias my-key-alias -keyalg RSA -keysize 2048 -validity 10000

# Sign APK
jarsigner -verbose -sigalg SHA256withRSA -digestalg SHA-256 \
  -keystore my-release-key.keystore \
  app/build/outputs/apk/release/app-release.apk \
  my-key-alias

# Verify signature
jarsigner -verify -verbose -certs app-release.apk
```

## Pitfalls & Solutions

### ❌ "SDK location not found"

**Error:**
```
SDK location not found. Define ANDROID_HOME or sdk.dir
```

**Fix:**
```bash
# Set in gradle.properties
echo "sdk.dir=D:\\\\android-sdk" >> android/gradle.properties

# Or export
export ANDROID_HOME="D:/android-sdk"
```

### ❌ "JAVA_HOME is not set"

**Error:**
```
ERROR: JAVA_HOME is not set and no 'java' command could be found
```

**Fix:**
```bash
# Find Java installation
find /c/Program\ Files -name "java.exe" | head -1

# Set (use Windows path format C:/)
export JAVA_HOME="C:/Program Files/Eclipse Adoptium/jdk-17.0.20.8-hotspot"
```

### ❌ "There is not enough space on the disk"

**Error:**
```
java.io.IOException: There is not enough space on the disk
Cannot create directory 'C:\Users\..\.gradle\caches\...'
```

**Fix:**
```bash
# Redirect Gradle cache to drive with space
export GRADLE_USER_HOME="E:/.gradle"

# Add to gradle.properties
echo "org.gradle.user.home=E:/.gradle" >> android/gradle.properties
```

### ❌ NDK Download Hangs

**Symptom:** Build stuck at "Preparing Install NDK..."

**Fix:**
```bash
# Pre-install NDK manually
cd $ANDROID_HOME/cmdline-tools/latest/bin
./sdkmanager.bat "ndk;27.1.12297006"

# Then rebuild
cd <project>/android
./gradlew clean assembleRelease
```

### ❌ Build Fails with "Execution failed for task ':app:mergeReleaseResources'"

**Common causes:**
1. Duplicate resources
2. Invalid drawable files
3. Corrupted cache

**Fix:**
```bash
# Clear build caches
rm -rf android/.gradle android/build android/app/build

# Clear Gradle daemon
./gradlew --stop

# Rebuild
./gradlew clean assembleRelease
```

## Verification Steps

**After successful build:**

```bash
# Check APK exists
ls -lh app/build/outputs/apk/release/app-release.apk

# Get APK info
aapt dump badging app/build/outputs/apk/release/app-release.apk | grep -E "package|sdkVersion|targetSdkVersion"

# Install on device (via adb)
adb install app/build/outputs/apk/release/app-release.apk
```

**Expected output:**
```
app-release.apk: ~30-50MB
package: name='com.yourapp.name'
sdkVersion: 24 (Android 7.0)
targetSdkVersion: 35 (Android 15)
```

## When to Use

**Use local build when:**
- EAS cloud build experiencing outages
- Need offline compilation
- Custom build configurations
- Faster iteration (no upload/queue time)
- CI/CD pipeline integration

**Use EAS cloud when:**
- No local Android SDK installed
- Multiple developers sharing keystore
- Automated builds from git commits
- iOS + Android simultaneous builds

## Performance Tips

**Speed up builds:**

```properties
# In gradle.properties
org.gradle.jvmargs=-Xmx4g -XX:+HeapDumpOnOutOfMemoryError
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configureondemand=true
org.gradle.daemon=true
```

**Incremental builds:**
```bash
# Skip clean for faster rebuilds (after first successful build)
./gradlew assembleRelease
```

**Disable animations (development builds):**
```bash
# For debug builds only
./gradlew assembleDebug
```

## Troubleshooting Commands

```bash
# Check Java version
java -version

# Check Gradle version
./gradlew --version

# List Android SDK packages
$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager.bat --list

# Check available space
df -h /c/ /d/ /e/

# Clear all Gradle caches (nuclear option)
rm -rf $GRADLE_USER_HOME/caches

# Kill Gradle daemons
./gradlew --stop
pkill -f gradle
```

## Common Build Times

| Action | Time | Notes |
|--------|------|-------|
| First build | 10-15 min | Downloads ~2GB dependencies |
| Clean build | 5-8 min | Dependencies cached |
| Incremental build | 2-4 min | Only changed files |
| JS bundle only | 30-60 sec | `./gradlew bundleRelease` |

## Related Skills

- `react-native-expo-mobile-app` - Creating Expo projects
- `android-app-signing` - Keystore management
- `eas-build-troubleshooting` - Cloud build issues

---

**Summary:** Local Android SDK build bypasses cloud build issues, requires ~10GB disk space (SDK + Gradle cache), 10-15 min first build, produces installable APK at `android/app/build/outputs/apk/release/app-release.apk`.

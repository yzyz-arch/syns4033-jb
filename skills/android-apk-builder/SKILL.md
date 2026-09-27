---
name: android-apk-builder
description: Build Android APK instantly from user request, Android 7-15.
triggers:
  - User requests APK/Android app
  - "bikin apk"
category: software-development
---

# Android APK Builder

## When to Use
User requests Android APK: "bikin apk kalkulator", "buat aplikasi android"

## Setup Location
**F:\android_build_system\** (all tools, storage constraint)

## Structure
```
F:\android_build_system\
├── cmdline-tools\    # SDK manager
├── sdk\              # Android SDK
├── keystore\         # Signing keys
├── output\           # Built APKs
└── workspace\        # Build temp
```

## Quick Build
```bash
cd /f/android_build_system
bash build_apk.sh "App Name" "com.package"
# Output: F:\android_build_system\output\App_Name.apk
```

## Installation Steps

### 1. Setup SDK Manager
```bash
cd /f/android_build_system
mv cmdline-tools/cmdline-tools cmdline-tools/latest 2>/dev/null || true
```

### 2. Install Build Tools
```bash
export ANDROID_HOME=/f/android_build_system/sdk
/f/android_build_system/cmdline-tools/latest/bin/sdkmanager.bat --sdk_root=%ANDROID_HOME% \
  "platform-tools" "build-tools;34.0.0" "platforms;android-34" "platforms;android-24"
```

### 3. Create Keystore
```bash
keytool -genkey -v -keystore /f/android_build_system/keystore/debug.keystore \
  -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10000 \
  -storepass android -keypass android -dname "CN=Debug,O=Android,C=US"
```

### 4. Create Build Script
Save as `/f/android_build_system/build_apk.sh`

## Build Process
1. Parse user request (app name, features)
2. Generate AndroidManifest.xml (minSdk=24, targetSdk=34)
3. Generate MainActivity.java
4. Generate resources (strings.xml, layouts)
5. Compile with aapt2 → javac → d8
6. Sign with debug keystore
7. Output to F:\android_build_system\output\

## Android 7-15 Support
```xml
<uses-sdk android:minSdkVersion="24" android:targetSdkVersion="34"/>
```

## Delivery
```
MEDIA:/f/android_build_system/output/App.apk
```

## Pitfalls
- Install JDK if keytool missing
- Use Windows path format for sdkmanager
- Ensure F:\ has >2GB free

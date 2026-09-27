---
name: react-native-expo-mobile-app
description: Build React Native/Expo apps with mobile-first deployment.
tags: [react-native, expo, mobile, android, apk, termux, eas-build]
---

# React Native/Expo Mobile App Development

## When to Use

Building cross-platform mobile apps (Android/iOS) with React Native and Expo framework. Use this when the user asks for:
- Mobile app development with React Native
- APK generation for Android
- Cross-platform mobile applications
- Expo-based projects

## Mobile-First Delivery Mindset

**CRITICAL:** When a user requests a mobile app, assume they want:
1. **Immediate testing capability** (Expo Go on their phone)
2. **Production APK** (installable without development environment)
3. **Mobile-accessible build methods** (Termux on Android, not just PC)

**Never assume the user has:**
- A desktop/laptop computer
- Android Studio installed
- Development environment setup

**Always provide paths for:**
- Building from mobile device (Termux + EAS)
- Building from PC (EAS cloud)
- Testing without APK (Expo Go)

## Project Structure

```
my-app/
├── app.json          # Expo configuration
├── package.json      # Dependencies
├── App.js           # Main application
├── assets/          # Images, fonts, icons
└── babel.config.js  # Babel configuration
```

## Core Workflow

### 1. Project Creation

```bash
# Create new Expo app
npx create-expo-app my-app
cd my-app

# Or initialize in existing directory
npm install expo
npx expo init
```

### 2. Development & Testing

**Method A: Expo Go (Fastest - 5 minutes)**
```bash
# Start development server
npx expo start

# Scan QR code with Expo Go app (Android/iOS)
# Changes reflect immediately (hot reload)
```

**Method B: Development Build**
```bash
# For native modules/custom code
npx expo prebuild
npx expo run:android
```

### 3. Production APK Generation

**Method A: EAS Cloud Build (RECOMMENDED - 15 minutes) ⭐**

```bash
# Install EAS CLI
npm install -g eas-cli

# Login (free account)
eas login

# Configure project
eas build:configure

# Build production APK
eas build -p android --profile production

# Download from expo.dev dashboard
```

**Advantages:**
- No Android Studio required
- No local setup needed
- Works from any device (PC, mobile via Termux)
- Optimized production builds (~30MB)
- Free tier available

**Method B: Termux Build (Mobile Device) 📱**

See `references/termux-build-workflow.md` for complete Termux setup.

Quick commands:
```bash
# In Termux on Android
pkg install nodejs python
npm install -g eas-cli
cd project/frontend
npm install --legacy-peer-deps
eas login
eas build -p android
```

**Method C: Local Build (PC with Android Studio)**

```bash
# Eject to bare React Native
npx expo prebuild --platform android

# Build APK
cd android
./gradlew assembleRelease

# Output: android/app/build/outputs/apk/release/app-release.apk
```

## Android Configuration (app.json)

```json
{
  "expo": {
    "name": "MyApp",
    "slug": "myapp",
    "version": "1.0.0",
    "android": {
      "package": "com.mycompany.myapp",
      "versionCode": 1,
      "minSdkVersion": 24,        // Android 7.0+
      "targetSdkVersion": 35,      // Latest Android
      "compileSdkVersion": 35,
      "adaptiveIcon": {
        "foregroundImage": "./assets/icon.png",
        "backgroundColor": "#ffffff"
      },
      "permissions": [
        "INTERNET",
        "ACCESS_NETWORK_STATE"
      ]
    }
  }
}
```

## Wide Android Compatibility

**Always configure for broad device support:**
- `minSdkVersion: 24` (Android 7.0, 2016) - covers 98% of active devices
- `targetSdkVersion: 35` (Android 15, latest)
- Test on multiple Android versions when possible

## Pitfalls

### Don't Assume Desktop Environment

**WRONG:**
```
"You'll need Android Studio installed..."
"Run this on your computer..."
"Build locally with gradlew..."
```

**RIGHT:**
```
"You can build this from your phone using Termux, or from a PC using EAS cloud build..."
"Here are three methods: Termux (mobile), EAS (any device), Local (PC with Android Studio)..."
```

### Don't Over-Deliver on Initial Request

When user asks for "a mobile app", deliver:
1. Complete source code
2. Three build methods (Termux, EAS, Local)
3. Documentation for each method
4. Testing instructions (Expo Go)

**Don't try to:**
- Build the APK yourself (requires cloud service or Android SDK)
- Set up full Android development environment
- Assume you can complete APK generation without external services

### Expo Go vs Standalone APK

**Expo Go (Development):**
- Quick testing
- No build required
- Requires Expo Go app
- Good for: Development, demos, testing

**Standalone APK (Production):**
- Full installation
- Works standalone
- Distributable to users
- Good for: Production, distribution, Play Store

Always provide BOTH paths.

### EAS Build Account

EAS build requires an Expo account (free):
- Sign up at expo.dev
- `eas login` to authenticate
- Free tier: Limited builds/month
- Paid tier: Unlimited builds

## Common Dependencies

```json
{
  "dependencies": {
    "expo": "~50.0.0",
    "react": "18.2.0",
    "react-native": "0.73.0",
    "@react-navigation/native": "^6.1.9",
    "@react-navigation/stack": "^6.3.20",
    "expo-av": "~13.10.4",
    "expo-camera": "~14.0.0",
    "expo-file-system": "~16.0.6"
  }
}
```

## Build Profiles (eas.json)

```json
{
  "build": {
    "production": {
      "android": {
        "buildType": "apk"
      }
    },
    "development": {
      "android": {
        "buildType": "apk",
        "developmentClient": true
      }
    }
  }
}
```

## Troubleshooting

**"Module not found" errors:**
```bash
rm -rf node_modules package-lock.json
npm install --legacy-peer-deps
```

**EAS build fails:**
- Check expo.dev build logs
- Verify app.json configuration
- Ensure all dependencies are compatible
- Try: `eas build --clear-cache`

**Termux issues:**
- Install Termux from F-Droid (not Play Store)
- Grant storage access: `termux-setup-storage`
- Use `--legacy-peer-deps` for npm installs

## Verification

After build completes:
- Test APK on Android 7+ device
- Verify all features work
- Check app size (should be 20-50MB)
- Test on different screen sizes
- Verify permissions are granted

## Documentation Deliverables

When building mobile apps for users, always include:
1. **Quick Start** - Expo Go testing (5 min path)
2. **Build Methods** - Termux, EAS, Local (all three)
3. **Android Compatibility** - Version range, device coverage
4. **Troubleshooting** - Common issues + fixes

Format as separate markdown files for clarity.

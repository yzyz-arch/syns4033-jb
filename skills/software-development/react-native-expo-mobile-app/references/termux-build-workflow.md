# Termux Build Workflow for React Native/Expo

Complete guide for building React Native/Expo APKs directly from Android phone using Termux.

## Prerequisites

- Android 7.0+ device
- 2GB+ RAM recommended
- 2-3GB free storage
- Internet connection

## Step 1: Install Termux (5 minutes)

**CRITICAL:** Do NOT install from Play Store (outdated version).

**Option A: F-Droid (Recommended)**
1. Download F-Droid: https://f-droid.org/
2. Install F-Droid APK
3. Open F-Droid app
4. Search "Termux"
5. Install Termux

**Option B: GitHub Direct**
1. Visit: https://github.com/termux/termux-app/releases
2. Download latest APK
3. Install APK

## Step 2: Setup Termux Environment (10 minutes)

```bash
# Update package list
pkg update && pkg upgrade -y

# Install core dependencies
pkg install -y nodejs python git wget curl

# Verify installations
node --version    # Should show v18+
python --version  # Should show 3.x
git --version
```

## Step 3: Install Build Tools (15 minutes)

```bash
# Install global npm packages
npm install -g expo-cli eas-cli

# Install Python packages (for backend if needed)
pip install --upgrade pip
pip install fastapi uvicorn aiohttp beautifulsoup4

# Verify
expo --version
eas --version
```

## Step 4: Setup Storage Access

```bash
# Grant Termux access to phone storage
termux-setup-storage

# This creates ~/storage/ with links to:
# - downloads/  (Downloads folder)
# - dcim/       (Camera)
# - shared/     (Internal storage)
```

## Step 5: Get Project Files

**Option A: Download ZIP to phone**
```bash
# Navigate to Downloads
cd ~/storage/downloads/

# If project is in a ZIP, extract it
unzip YONDAnime-v1.0.0.zip
cd yonda-anime-stream
```

**Option B: Clone from Git**
```bash
cd ~
git clone https://github.com/USERNAME/project-name
cd project-name
```

## Step 6: Install Project Dependencies (10 minutes)

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install --legacy-peer-deps

# Note: Use --legacy-peer-deps to avoid peer dependency conflicts
# This is normal for React Native projects
```

## Step 7: Build APK with EAS (15 minutes)

```bash
# Make sure you're in frontend directory
cd frontend

# Login to Expo (create free account if needed)
eas login

# Enter your email and password
# Or sign up at expo.dev first

# Configure project (first time only)
eas build:configure

# Build production APK
eas build -p android --profile production

# Wait 10-15 minutes for cloud build
# Progress shows in terminal
```

**Output:**
```
✔ Build complete!
Build URL: https://expo.dev/accounts/YOUR_ACCOUNT/builds/...
APK Download: [direct link]
```

## Step 8: Download & Install APK

1. Click download link in terminal
2. Or visit expo.dev and download from dashboard
3. Open APK file
4. Enable "Install from Unknown Sources" if prompted
5. Install APK
6. Done! 🎉

## Alternative: Local Debug Build (Advanced)

**Warning:** Requires 4GB+ RAM and takes 1+ hours. EAS cloud build is much easier.

```bash
# Install Java and Gradle
pkg install -y openjdk-17 gradle

# Eject to bare React Native
cd frontend
npx expo prebuild --platform android

# Build debug APK
cd android
./gradlew assembleDebug

# APK location:
# android/app/build/outputs/apk/debug/app-debug.apk
```

## Termux Tips & Tricks

### Multiple Terminal Windows (tmux)
```bash
# Install tmux
pkg install tmux

# Start tmux
tmux

# Split window: Ctrl+B then "
# Switch panes: Ctrl+B then arrow keys
# Detach: Ctrl+B then d
# Reattach: tmux attach
```

### Background Processes
```bash
# Run backend in background
cd backend
nohup python main.py &

# Check running processes
ps aux | grep python

# Kill process
pkill -f python
```

### Storage Management
```bash
# Check available space
df -h

# Clear npm cache
npm cache clean --force

# Clear pip cache
pip cache purge

# Remove old builds
rm -rf node_modules
rm -rf android/build
```

### Access Phone Files
```bash
# Downloads folder
cd ~/storage/downloads

# Camera photos
cd ~/storage/dcim

# Internal storage root
cd ~/storage/shared
```

## Troubleshooting

### "Command not found"
```bash
# Reinstall packages
pkg install nodejs python git

# Refresh shell hash table
hash -r
```

### "Permission denied"
```bash
# Make script executable
chmod +x script.sh

# Grant storage access
termux-setup-storage
```

### "Out of space"
```bash
# Clear caches
npm cache clean --force
pip cache purge

# Remove large directories
rm -rf node_modules
rm -rf ~/.npm
rm -rf ~/.cache
```

### EAS build fails
- Check internet connection
- Verify expo.dev account is active
- Try: `eas build --clear-cache`
- Check build logs at expo.dev

### npm install hangs
```bash
# Kill process and retry
pkill -f npm

# Use legacy peer deps
npm install --legacy-peer-deps

# Or try yarn
pkg install yarn
yarn install
```

## Complete Script (Copy-Paste)

Save this as `setup-termux.sh`:

```bash
#!/data/data/com.termux/files/usr/bin/bash

echo "🚀 Termux React Native Setup"
echo "=============================="
echo ""

# Update packages
echo "📦 Updating packages..."
pkg update -y && pkg upgrade -y

# Install dependencies
echo "🔧 Installing dependencies..."
pkg install -y nodejs python git wget curl

# Install build tools
echo "📱 Installing Expo & EAS..."
npm install -g expo-cli eas-cli

# Setup storage
echo "💾 Setting up storage access..."
termux-setup-storage

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. cd ~/storage/downloads/your-project"
echo "2. npm install --legacy-peer-deps"
echo "3. eas login"
echo "4. eas build -p android"
echo ""
```

Run it:
```bash
bash setup-termux.sh
```

## Timeline Summary

- Termux install: 5 minutes
- Environment setup: 10 minutes
- Build tools: 15 minutes
- Project setup: 10 minutes
- EAS build: 15 minutes

**Total: ~55 minutes from zero to APK**

## Comparison: Termux vs PC

| Aspect | Termux (Phone) | PC |
|--------|----------------|-----|
| Setup time | 25 min | 10 min |
| Build method | EAS cloud | EAS/Local |
| Build time | 15 min | 15 min |
| Storage needed | 2GB | 5GB |
| Result quality | Same APK | Same APK |

**Conclusion:** Termux works perfectly for mobile-only users. EAS cloud build means no performance difference vs PC.

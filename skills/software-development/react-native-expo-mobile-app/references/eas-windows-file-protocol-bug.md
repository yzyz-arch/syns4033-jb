# Windows Git Clone Bug - EAS Build

## Problem

EAS CLI fails with `git clone --no-checkout --no-hardlinks --depth 1 file:///<path> <dest> exited with non-zero code: 128` on Windows environments using Git Bash/MSYS.

## Root Cause

EAS CLI uses `file://` protocol with `--depth 1` flag for local git cloning. This combination fails on Windows bash environments due to:
- Path conversion issues between Windows and Unix formats
- Git for Windows handling of `file://` protocol differently than native Linux git
- MSYS path translation conflicts with git's internal path handling

## Symptoms

```
Failed to upload the project tarball to EAS Build

Reason: git clone --no-checkout --no-hardlinks --depth 1 
file:///D:/path/to/project E:\Temp\eas-cli-nodejs\...-shallow-clone 
exited with non-zero code: 128
```

## Working Environments

- ✅ Termux (Android - native Linux)
- ✅ WSL/WSL2 (Windows Subsystem for Linux)
- ✅ Native Linux/macOS
- ❌ Windows Git Bash/MSYS
- ❌ Windows CMD with Git for Windows

## Solutions

### Option 1: Build from Termux (Recommended)
```bash
# On Android device with Termux
pkg install nodejs git
npm install -g eas-cli
cd ~/project
npm install
eas build -p android --profile production
```

### Option 2: Use WSL
```bash
# In WSL on Windows
cd /mnt/d/project
npm install
eas build -p android --profile production
```

### Option 3: Fresh Git Repo (Sometimes Works)
```bash
# Delete and reinitialize git
rm -rf .git
git init
git add -A
git commit -m "Initial commit"
eas build -p android --profile production
```

## Not a Code Issue

This is **not a problem with app code** - the same project builds successfully from Linux environments. The blocker is purely the EAS CLI + Windows Git interaction.

## Discovered

Session 2026-08-19: After 14 failed build attempts on Windows PC, same project built successfully on Termux (Android) on first try after fixing npm install issues.

## Related Issues

- `eas-windows-git-clone-bug.md` - Broader Windows limitations
- `termux-build-workflow.md` - Complete Termux setup guide

# Termux Permission Issues - Node Modules Execution

## Problem

When React Native/Expo project is located in Android external storage (`/storage/emulated/0/Download/`), EAS CLI fails with:

```
spawn /storage/emulated/0/Download/project/node_modules/expo/bin/cli EACCES
Error: build command failed.
```

## Root Cause

Android security restrictions prevent execution of files in external storage (`/storage/emulated/0/*`). Node modules with executable scripts (`.bin` files, CLI tools) cannot run.

## Solution: Copy to Termux Internal Storage

```bash
# Copy project from external storage to Termux home
cp -r /storage/emulated/0/Download/project-name ~/project-name
cd ~/project-name

# Fix permissions (optional, usually not needed in ~)
chmod -R +x node_modules/.bin
chmod +x node_modules/expo/bin/cli

# Now build works
eas build -p android --profile production
```

## Why This Works

- Termux internal storage (`~/` = `/data/data/com.termux/files/home/`) allows execution
- External storage (`/sdcard/`, `/storage/emulated/0/`) blocks execution for security

## When This Happens

- `EACCES` error on any node_modules executable
- "Permission denied" when running `expo`, `eas`, or npm scripts
- Project extracted to `/sdcard/Download/` or `/storage/emulated/0/`

## Prevention

Always extract/clone projects directly to Termux home:
```bash
cd ~
tar -xzf /sdcard/Download/project.tar.gz
# or
git clone <url>
```

## Discovered

Session 2026-08-19: Project initially extracted to `/storage/emulated/0/Download/`, EAS failed with EACCES. After `cp -r` to `~/yonda-ai-mobile`, same commands succeeded.

## Related

- `termux-build-workflow.md` - Complete Termux setup
- `termux-git-issues.md` - Git ownership in Termux

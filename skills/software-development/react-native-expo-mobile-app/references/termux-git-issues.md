# Termux Git Configuration Issues

Common git setup problems when building React Native/Expo apps from Termux, with working fixes.

## Issue 1: Git Config Failure (Non-Zero Exit 128)

**Symptom:**
```bash
$ git config --local user.name "username"
git config --local user.name username exited with non-zero code: 128
Error: build command failed
```

**Root Cause:**
- Git repository not fully initialized
- Trying to set local config before repo exists

**Fix:**
```bash
# Set global config first (always works)
git config --global user.name "your-username"
git config --global user.email "your@email.com"

# Then init repository
git init
git add .
git commit -m "Initial commit"
```

**Why this works:** Global config doesn't depend on repository state.

---

## Issue 2: Dubious Ownership in Repository

**Symptom:**
```bash
$ git add .
fatal: detected dubious ownership in repository at '/storage/emulated/0/Download/project'
To add an exception for this directory, call:
    git config --global --add safe.directory /storage/emulated/0/Download/project
```

**Root Cause:**
- Git detects repository in external storage (not owned by Termux user)
- Security feature to prevent privilege escalation

**Fix - Method A (Exact Path):**
```bash
# Copy the exact path from error message
git config --global --add safe.directory /storage/emulated/0/Download/project
```

**Fix - Method B (Disable Check Globally):**
```bash
# Warning: Less secure, but convenient for Termux
git config --global safe.directory '*'
```

---

## Issue 3: Case-Sensitive Path Mismatch

**Symptom:**
```bash
# First attempt:
git config --global --add safe.directory /storage/emulated/0/Download/project

# Still fails:
fatal: detected dubious ownership in repository at '/storage/emulated/0/download/project'
```

**Root Cause:**
- Path case changed between operations
- Git is case-sensitive on Linux/Termux
- Android paths may normalize differently

**Fix:**
```bash
# Use EXACT path from error (note lowercase 'download')
git config --global --add safe.directory /storage/emulated/0/download/project

# Or find actual path:
pwd  # Shows real path
git config --global --add safe.directory "$(pwd)"
```

**Prevention:**
```bash
# Always use lowercase for consistency
cd ~/storage/downloads/  # lowercase 'd'
```

---

## Issue 4: EAS Build Requires Git

**Symptom:**
```bash
$ eas build -p android
It looks like you haven't initialized the git repository yet.
EAS requires you to use a git repository for your project.
? Would you like us to run 'git init' for you?
```

**Why:**
- EAS tracks versions via git commits
- Uploads code from git repository

**Answer:** Type `Y` to let EAS initialize git automatically.

**If auto-init fails:**
```bash
# Manual setup
git init
git config user.name "your-username"
git config user.email "your@email.com"
git add .
git commit -m "Initial commit"

# Then retry
eas build -p android
```

---

## Issue 5: Missing Commit Message Prompt

**Symptom:**
```bash
? Commit message: › Initia
You need to configure Git with your username (user.name) and email...
```

**Root Cause:**
- Git config not set before attempting commit
- EAS trying to create initial commit

**Fix:**
```bash
# Complete the commit message (doesn't matter what)
# Press Enter

# Then when prompted:
? Username: › any-username-you-want
? Email: › any-email@example.com

# These are just metadata for git, not account creation
```

**Important:** This is NOT creating a new account. It's just local git config.

---

## Complete Termux Git Setup (Copy-Paste)

**Run this BEFORE `eas build`:**

```bash
# 1. Set global git config (run once per Termux install)
git config --global user.name "your-username"
git config --global user.email "your@email.com"

# 2. Trust current directory (if in external storage)
git config --global --add safe.directory "$(pwd)"

# 3. Initialize repository
git init

# 4. Make initial commit
git add .
git commit -m "Initial commit"

# 5. Verify
git log  # Should show your commit

# 6. Now EAS build will work
eas build -p android
```

---

## EAS Build Git Flow

**What happens during `eas build`:**

1. EAS checks for git repository
2. If missing, offers to run `git init`
3. Checks for git user config
4. If missing, prompts for username/email
5. Creates initial commit
6. Uploads repository to Expo servers
7. Builds APK in cloud

**Best practice:** Set up git before running `eas build` to avoid mid-flow interruptions.

---

## Verification

**Check git is properly configured:**

```bash
# Check config
git config --global user.name
git config --global user.email
git config --global safe.directory

# Check repository
git status
git log

# Should show:
# - Your username/email
# - Clean working tree or ready to commit
# - At least one commit in log
```

---

## Quick Debug Commands

```bash
# Where am I?
pwd

# Is git initialized?
ls -la .git

# What's my git config?
git config --list

# What does git see?
git status

# Trust this directory
git config --global --add safe.directory "$(pwd)"

# Reset git completely (nuclear option)
rm -rf .git
git init
git config user.name "name"
git config user.email "email"
git add .
git commit -m "Fresh start"
```

---

## Prevention Checklist

Before running `eas build` in Termux:

- [ ] Git installed: `pkg install git`
- [ ] Global config set: `git config --global user.name/email`
- [ ] Repository initialized: `git init`
- [ ] Safe directory added (if in /storage/emulated/0/)
- [ ] Initial commit made: `git commit -m "init"`
- [ ] Working in lowercase path: `~/storage/downloads/` not `~/storage/Downloads/`

Then `eas build -p android` should proceed smoothly.

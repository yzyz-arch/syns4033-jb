# EAS Build Windows Git Clone Bug (Exit 128)

**Issue:** EAS CLI consistently fails with `git clone --no-checkout --no-hardlinks --depth 1 file:///<path> <temp-dir>` exiting with code 128 on Windows environments.

**Manifestation:**
```
Failed to upload the project tarball to EAS Build
Reason: git clone --no-checkout --no-hardlinks --depth 1 file:///D:/path/to/project E:\Temp\eas-cli-nodejs\<uuid>-shallow-clone exited with non-zero code: 128
```

**Root cause:** Windows git + MSYS bash + `file://` protocol with `--depth 1` flag interaction issue. The combination of:
- Windows-style paths (D:\, E:\)
- Git Bash/MSYS environment
- file:// protocol URLs
- --depth 1 flag
- Cross-drive cloning (D: → E: or E: → D:)

Results in git failing to execute the shallow clone.

**Attempted fixes that did NOT work:**
1. Clearing E: drive temp folder
2. Redirecting temp to D: drive via TMPDIR/TEMP/TMP env vars
3. Setting git safe.directory
4. Rebuilding git repository from scratch
5. Using different temp directories
6. Manual git clone works, but EAS CLI's specific command combo fails

**Working solutions:**

### 1. Build on Different Environment (Guaranteed)
- **Linux/Mac:** No issue, git clone works normally
- **WSL2:** Windows Subsystem for Linux avoids the git-bash/MSYS issues
- **Different Windows PC:** May not hit the same path/drive combination issue
- **Termux (Android):** Linux environment, no Windows path issues

### 2. Wait for EAS CLI Update
Track issue at Expo's GitHub or forums. CLI update may fix the Windows git handling.

### 3. Manual Workaround (Advanced)
Not reliable for agent automation, but for manual debugging:
```bash
# Create tarball manually
tar -czf project.tar.gz --exclude=node_modules --exclude=.git .

# Upload via expo.dev web dashboard (if available)
# Or use eas submit with pre-built archive
```

**Detection:** If you see this error pattern multiple times (3+) with clean git repo, redirect user to alternative build environment instead of retrying endlessly. After 5-7 failed attempts, this is the blocker—not code issues.

**Status as of 2026-08-19:** Reproducible on Windows 10 with git-bash/MSYS, multiple drive configurations (C:, D:, E:). Fresh git repos and various temp directory configurations all fail identically.

**Recommendation for agents:** After 3-5 consecutive git clone exit 128 failures on Windows:
1. Acknowledge the Windows git limitation
2. Provide the project archive (tar.gz)
3. Recommend Termux (mobile), WSL2, Linux VM, or different PC
4. Do NOT continue retrying EAS build—it will fail identically

# EAS Build Windows Limitations

## Git Clone Bug (Windows-Specific)

**Symptom:**
```
Failed to upload the project tarball to EAS Build
Reason: git clone --no-checkout --no-hardlinks --depth 1 file:///D:/path/to/project E:\Temp\eas-cli-nodejs\...-shallow-clone exited with non-zero code: 128
```

**Root Cause:**
EAS CLI on Windows uses `git clone file://` with `--depth 1` flag, which fails in certain Windows/Git configurations:
- MSYS/Git Bash path translation issues
- Temp directory permissions (E:\Temp, D:\Temp)
- File system mount points

**Observed Pattern (17+ failures in session):**
- All PC builds failed with git clone exit 128
- Same command worked in Linux (Termux)
- Changing temp directory (TMPDIR, TEMP, TMP) didn't help
- Fresh git repo initialization didn't help

**Solution: Use Termux (Linux Environment)**

Works consistently because:
- ✅ Native Linux git (no Windows path translation)
- ✅ No drive letter issues
- ✅ Proper Unix filesystem permissions

```bash
# On Android phone with Termux
pkg install nodejs git
npm install -g eas-cli
cd ~/project
eas login
eas build -p android --profile production
```

**Workaround Attempts That Failed:**
- `export TMPDIR=D:/eas-temp` - Still failed
- `git config --global --add safe.directory` - Didn't help
- Removing `.git` and reinitializing - Still failed
- Using different temp locations - All failed

## Network Timeout Issues (Maven/Gradle)

**Symptom:**
```
Error resolving plugin [id: 'com.facebook.react.settings']
> java.util.concurrent.TimeoutException
BUILD FAILED in 19m 13s
```

**Root Cause:**
- ISP blocking Maven Central repositories
- DNS resolution failures for `repo1.maven.org`
- Firewall/proxy blocking Gradle requests
- Regional mirror availability

**Fast internet (100Mbps) doesn't guarantee Maven access!** Speed ≠ connectivity to specific Maven repos.

**Solution: Use Asian Mirrors**

Add to `android/settings.gradle`:
```groovy
pluginManagement {
    repositories {
        google()
        mavenCentral()
        // Aliyun mirrors (fast in Asia)
        maven { url 'https://maven.aliyun.com/repository/public/' }
        maven { url 'https://maven.aliyun.com/repository/google/' }
        gradlePluginPortal()
    }
    // ... rest of config
}
```

Also set extended timeouts in `android/gradle.properties`:
```properties
systemProp.org.gradle.internal.http.connectionTimeout=600000
systemProp.org.gradle.internal.http.socketTimeout=600000
```

**This extends timeout from 30s to 600s (10 minutes).**

## Disk Space Issues (Windows)

**C: Drive Full:**
```
java.io.IOException: There is not enough space on the disk
Cannot create directory 'C:\Users\..\.gradle\caches\...'
```

**Solution: Redirect Gradle Cache**

In `android/gradle.properties`:
```properties
org.gradle.user.home=E:/.gradle
```

Or export environment variable:
```bash
export GRADLE_USER_HOME="E:/.gradle"
```

**Check disk space before building:**
```bash
df -h /c/ /d/ /e/
```

Gradle cache needs ~2-3GB for first build.

## Recommendation

**For Windows users having build issues:**

1. **Try Termux first** (most reliable for Android builds)
2. If Termux not available, use EAS cloud (skips local git entirely)
3. Local Gradle build last resort (many environmental dependencies)

**Success rate from session:**
- PC (Windows): 0/16 builds succeeded
- Termux (Linux): 1/2 builds succeeded (only failed on Bundle phase, not git)
- EAS with fingerprint skip: Eventually worked

## Related Issues

See also:
- `eas-git-clone-e-drive-error.md` - E: drive permission issues
- `gradle-maven-timeout.md` - Maven Central connectivity
- `termux-build-workflow.md` - Complete Termux setup

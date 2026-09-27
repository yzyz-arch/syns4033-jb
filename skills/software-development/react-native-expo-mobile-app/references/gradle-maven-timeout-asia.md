# Gradle Maven Central Timeout - Asian Networks

## Problem

Gradle plugin resolution fails with `java.util.concurrent.TimeoutException` when downloading React Native plugins from Maven Central, even on fast networks (100Mbps+).

**Error:**
```
Error resolving plugin [id: 'com.facebook.react.settings']
> A problem occurred configuring project ':gradle-plugin'.
   > java.util.concurrent.TimeoutException
```

## Root Cause

Not bandwidth issue - **network routing/connectivity** to Maven Central repositories:
- Some Indonesian ISPs block/throttle Maven domains
- DNS resolution failures for `repo1.maven.org`
- Firewall/proxy blocking Gradle requests
- Regional CDN issues

Default timeout: 30 seconds (too short for blocked routes)

## Solution: Asian Mirror Repositories

Add to `android/settings.gradle`:

```gradle
pluginManagement {
    repositories {
        // Use Google's Maven mirror first (faster in Asia)
        google()
        mavenCentral()
        // Aliyun mirror (China, fast in Asia)
        maven { url 'https://maven.aliyun.com/repository/public/' }
        maven { url 'https://maven.aliyun.com/repository/google/' }
        // Gradle Plugin Portal
        gradlePluginPortal()
    }
    
    // ... rest of pluginManagement
}
```

## Extended Timeouts

Add to `android/gradle.properties`:

```properties
# Extended network timeouts (default 30s → 600s / 10 min)
systemProp.org.gradle.internal.http.connectionTimeout=600000
systemProp.org.gradle.internal.http.socketTimeout=600000

# Use Maven Central mirror (optional)
systemProp.maven.repo.central=https://repo1.maven.org/maven2/
```

## Disk Space Redirect (Windows)

If C: drive full, redirect Gradle cache:

```properties
# In gradle.properties
org.gradle.user.home=E:/.gradle
```

Or export before build:
```bash
export GRADLE_USER_HOME=E:/.gradle
```

## When This Happens

- Timeout after 30-90 seconds during dependency resolution
- "Starting a Gradle Daemon" hangs for 5+ minutes
- Build fails in settings.gradle plugin resolution phase
- Fast internet but Maven repos unreachable

## Alternative: Termux Build

Termux (Android Linux) often has better routing to Maven repos than Windows PC on same network - try building from Termux if PC consistently times out.

## Discovered

Session 2026-08-19: 100Mbps network, consistent Maven timeout after 1-2 min. Aliyun mirrors allowed build to progress further (9min before different error). Termux build ultimately succeeded where PC failed.

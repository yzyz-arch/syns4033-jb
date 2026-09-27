# Gradle React Native Plugin Download Timeout

**Issue:** Local Android builds via `./gradlew assembleRelease` fail with timeout downloading `com.facebook.react.settings` plugin from Maven repositories.

**Error pattern:**
```
FAILURE: Build failed with an exception.

* Where:
Settings file 'android/settings.gradle' line: 21

* What went wrong:
Error resolving plugin [id: 'com.facebook.react.settings']
> java.util.concurrent.TimeoutException

BUILD FAILED in 1m 24s (or 19m+)
```

**Root cause:** Network connectivity issue to Maven Central and/or Google Maven repositories. The React Native Gradle plugin must be downloaded during the first build configuration phase, before any actual compilation happens.

**Why it happens:**
1. Slow/unstable internet connection
2. Firewall/proxy blocking Maven repos
3. ISP throttling or DNS issues
4. Maven Central experiencing issues
5. Corporate network restrictions

**Extended timeout configuration (often insufficient):**

`android/gradle.properties`:
```properties
# Extended timeouts (default 30s → 600s)
systemProp.org.gradle.internal.http.connectionTimeout=600000
systemProp.org.gradle.internal.http.socketTimeout=600000
```

Even with 10-minute timeouts, if the network cannot reach Maven repos, build will still fail.

**Attempted fixes that did NOT work in this session:**
1. Extended timeouts to 600s (10 minutes)
2. Redirecting Gradle cache to different drive
3. Using `--refresh-dependencies` flag
4. Multiple retry attempts
5. Fresh Gradle daemon
6. Clean build

**Working solutions:**

### 1. Build on Different Network (Most Reliable)
- Different WiFi network
- Mobile hotspot (different ISP)
- VPN to bypass network restrictions
- Coffee shop / coworking space WiFi
- Friend's internet connection

Test network first:
```bash
# Test Maven Central connectivity
curl -I https://repo1.maven.org/maven2/

# Should return 200 OK, not timeout
```

### 2. Pre-download Dependencies on Working Network
If you have occasional access to stable network:
```bash
# Download all dependencies once
./gradlew assembleRelease --refresh-dependencies

# Then .gradle cache persists for offline builds
./gradlew assembleRelease --offline
```

### 3. Use EAS Cloud Build (Network-Independent)
EAS servers have stable Maven access:
```bash
eas build -p android --profile production
```

User's network only needs to upload project (~2MB), not download Gradle plugins (~2GB).

### 4. Corporate/Proxy Environment
If behind corporate proxy:
```properties
# gradle.properties
systemProp.http.proxyHost=proxy.company.com
systemProp.http.proxyPort=8080
systemProp.https.proxyHost=proxy.company.com
systemProp.https.proxyPort=8080
```

**Detection for agents:** If you see Maven timeout error 2-3 times in a row:
1. Acknowledge network connectivity issue
2. Do NOT retry endlessly (will keep failing)
3. Recommend alternative: EAS cloud build OR different network
4. Provide project archive for user to build elsewhere

**Network diagnostic commands:**
```bash
# Test Maven Central
curl -I https://repo1.maven.org/maven2/

# Test Google Maven
curl -I https://dl.google.com/dl/android/maven2/

# DNS check
nslookup repo1.maven.org
```

If curl times out or fails, Gradle will too.

**Status as of 2026-08-19:** Reproducible on specific network configurations where Maven Central is unreachable or extremely slow (>1-2 minute response time). This is environment-specific, not a universal React Native issue.

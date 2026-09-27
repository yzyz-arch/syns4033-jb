# Aliyun Mirrors for Gradle Maven Timeout (Asia/Indonesia)

**Problem:** Gradle builds timeout downloading React Native plugins from Maven Central (US servers) on Asian networks, even with high-speed internet (100Mbps+).

**Solution:** Use Aliyun (Alibaba Cloud) mirrors that host Maven Central packages in Asia.

## Configuration

Edit `android/settings.gradle`:

```gradle
pluginManagement {
    repositories {
        // Add these BEFORE mavenCentral()
        google()
        maven { url 'https://maven.aliyun.com/repository/public/' }
        maven { url 'https://maven.aliyun.com/repository/google/' }
        mavenCentral()
        gradlePluginPortal()
    }
    
    // ... rest of pluginManagement config
}
```

## Why This Works

**Geographic routing:** Aliyun servers in Asia provide:
- Lower latency (10-50ms vs 200-300ms to US Maven Central)
- Better bandwidth (Asian ISPs route efficiently to Aliyun)
- Bypass ISP throttling on international connections
- Mirror sync with Maven Central (usually <24hr lag)

**Verified session (2026-08-19):**
- **Network:** Indonesian ISP, 100Mbps speed
- **Without Aliyun:** Timeout after 1-2 minutes consistently
- **With Aliyun:** Build progressed 9+ minutes (downloading dependencies)
- **Result:** Resolved Maven Central connectivity issue

## When to Use

Apply this fix when:
- Maven Central timeout errors (`java.util.concurrent.TimeoutException`)
- High-speed internet but Gradle downloads fail
- Located in Asia/Indonesia/China
- curl to repo1.maven.org times out but local internet works fine

## Additional Mirrors (Alternatives)

Other Asian mirror options:
```gradle
// Tencent Cloud (China)
maven { url 'https://mirrors.cloud.tencent.com/maven/' }

// Huawei Cloud (China)
maven { url 'https://repo.huaweicloud.com/repository/maven/' }
```

## Limitations

- Not needed if on stable international connection
- May have 24hr sync delay for very new packages
- Best for React Native/Android builds (well-mirrored packages)

## Related Issues

See also:
- `gradle-maven-timeout.md` - General timeout troubleshooting
- `termux-build-workflow.md` - Alternative build environment

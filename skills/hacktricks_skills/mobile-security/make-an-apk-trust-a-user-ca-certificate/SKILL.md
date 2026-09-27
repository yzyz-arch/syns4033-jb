---
name: hacktricks-make-an-apk-trust-a-user-ca-certificate
description: >-
  Hacktricks playbook: Make an APK Trust a User CA Certificate. Exploitation techniques, enumeration, and attack patterns.
source: https://book.hacktricks.xyz/
tags: [pentest, exploit, hacking]
---

# Hacktricks: Make an APK Trust a User CA Certificate

> Source: [Hacktricks Book](https://book.hacktricks.xyz/) — auto-converted by Cybermes.

# Make an APK Trust a User CA Certificate



Android applications can restrict which certificate authorities they trust. In an authorized test environment, repackaging an APK with a Network Security Configuration that trusts user-installed CAs can make HTTPS traffic inspection possible. This does not automatically bypass certificate pinning implemented elsewhere in the application.<sup>[[1]](#references)</sup>

## Automatic

[`apk-mitm`](https://github.com/shroudedcode/apk-mitm) automates APK patching for HTTPS inspection and includes patches for several common certificate-pinning implementations.<sup>[[2]](#references)</sup>

## Manual

Decompile the APK:

```bash
apktool d app.apk
```

![Decompiling an APK with apktool](../../images/img9.png)

In `AndroidManifest.xml`, add the following attribute to the `<application>` element if it is not already set:<sup>[[1]](#references)</sup>

`android:networkSecurityConfig="@xml/network_security_config"`

Before adding:

![Android manifest before adding the network security configuration](../../images/img10.png)

After adding:

![Android manifest after adding the network security configuration](../../images/img11.png)

Create or update `res/xml/network_security_config.xml` with the following content. The `system` source keeps the preinstalled trust anchors, while `user` adds user-installed CAs:<sup>[[1]](#references)</sup>

```html
<network-security-config>
    <base-config>
        <trust-anchors>
            <!-- Trust preinstalled CAs -->
            <certificates src="system" />
            <!-- Additionally trust user-added CAs -->
            <certificates src="user" />
        </trust-anchors>
    </base-config>
</network-security-config>
```

Rebuild the APK:

```bash
apktool b app -o patched.apk
```

![Rebuilding the patched APK with apktool](../../images/img12.png)

Repackaging invalidates the original signature, so sign the rebuilt APK before installing it. [See the APK signing section](smali-changes.md#sign-the-new-apk).

## References

- [1] [Android Developers - Network Security Configuration](https://developer.android.com/privacy-and-security/security-config)
- [2] [apk-mitm - Prepare Android APK files for HTTPS inspection](https://github.com/shroudedcode/apk-mitm)




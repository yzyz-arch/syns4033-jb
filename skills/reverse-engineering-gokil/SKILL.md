---
name: reverse-engineering-gokil
description: Reverse engineer encrypted APKs with complete toolkit.
triggers:
  - Encrypted APK analysis
  - Reverse engineering
  - APK unpacking
category: security
---

# Reverse Engineering GOKIL Toolkit

## Complete Toolkit (F:\reverse_engineering_toolkit\)

### Tools Installed
- ✅ JADX (Java decompiler) - 110MB
- ✅ APKTool (APK unpacker) - 23MB
- ✅ Ghidra 11.2 (binary analysis) - 500MB
- ✅ Frida (dynamic instrumentation) - pip
- ✅ ADB Platform Tools - 17MB
- ✅ Python Analyzer - 11KB
- ✅ LLM Integration

### One-Command Analysis
```bash
python /f/reverse_engineering_toolkit/python_tools/encrypted_apk_analyzer.py app.apk
```

Does 10 steps:
1. Detect encryption (8 types)
2. Unpack APK
3. Decompile Java
4. Analyze natives
5. Extract strings
6. Detect obfuscation
7. Find entry points
8. Check vulnerabilities
9. Generate Frida hooks
10. Save JSON report

### Quick Commands
```bash
# Decompile
jadx -d output app.apk

# Unpack
java -jar /f/apk_modding_system/decompile/apktool.jar d app.apk

# Hook
frida -U -f com.app -l hooks.js

# Debug
/f/reverse_engineering_toolkit/adb/platform-tools/adb.exe logcat
```

See GOKIL_TOOLKIT_COMPLETE.txt for full docs.

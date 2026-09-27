---
name: game-modder-apk
description: "Mod APK files: cheats, remove ads, unlock features."
version: 1.0.0
author: Umi for LO
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [apk, mod, android, game-modding, reverse-engineering]
---

# APK MODDER SKILL

**Pure Python APK Modder** — Mod ANY APK without Java/APKTool. Support Android 7 (Nougat) sampai Android 15 (Vanilla Ice Cream).

## When to Use

Trigger when user:
- Sends APK file and asks to mod it
- Wants to add cheats, remove ads, unlock features
- Asks to inject Lua script, modify manifest, patch files
- Wants to mod game APK

## Core Features

- ✅ **Extract APK** (unzip)
- ✅ **Modify files** (Lua, XML, JSON, assets)
- ✅ **Remove ads** (delete ad libraries)
- ✅ **Inject scripts** (Lua for Unity/Corona games)
- ✅ **Repack APK** (zip back)
- ✅ **Android 7-15 compatible**

## Tool Location

`D:/apk-modder/apk_modder.py`

## Basic Usage

```bash
# Extract and list files
python D:/apk-modder/apk_modder.py game.apk list

# Remove ads
python D:/apk-modder/apk_modder.py game.apk remove-ads

# Inject Lua cheat
python D:/apk-modder/apk_modder.py game.apk inject-lua cheat.lua

# Interactive mod
python D:/apk-modder/apk_modder.py game.apk mod
```

## User Workflow (Telegram)

1. **User sends APK** via Telegram
2. **User gives command**: "add infinite money" / "remove ads" / "unlock all levels"
3. **You process it**:
   - Download APK to temp dir
   - Run apk_modder.py with appropriate command
   - Mod the APK
   - Send back modded APK as `MEDIA:/path/to/modded.apk`

## Common Commands

| User Request | What You Do |
|:-------------|:------------|
| "remove ads" | `python apk_modder.py game.apk remove-ads` |
| "add infinite money" | Extract, find money variable in Lua/XML, patch, rebuild |
| "unlock all levels" | Extract, find level config, set all unlocked=true, rebuild |
| "inject cheat script" | `python apk_modder.py game.apk inject-lua cheat.lua` |
| "mod this APK" | Extract, ask user what to change, mod, rebuild |

## Step-by-Step: Full Mod Workflow

### Step 1: User Sends APK via Telegram

When user sends APK file, Telegram gives you file info. Download it:

```python
# Via execute_code
import subprocess
import os
from pathlib import Path

# Assume Telegram file is saved to temp by Hermes
# OR user provides download link

# For testing, create temp dir
temp_dir = Path("/d/temp/apk_mod")
temp_dir.mkdir(parents=True, exist_ok=True)

apk_path = temp_dir / "game.apk"
print(f"APK location: {apk_path}")
```

### Step 2: Run Modder

```python
import subprocess
import sys

apk_path = "/d/temp/apk_mod/game.apk"

# Example: Remove ads
result = subprocess.run([
    "python", "D:/apk-modder/apk_modder.py",
    str(apk_path),
    "remove-ads"
], capture_output=True, text=True, timeout=120)

print(result.stdout)

# Output will be: /d/temp/apk_mod/game_modded.apk
modded_apk = str(apk_path).replace(".apk", "_modded.apk")
print(f"Modded APK: {modded_apk}")
```

### Step 3: Send Back to User

```markdown
Modded APK siap install, LO! 🔥

MEDIA:/d/temp/apk_mod/game_modded.apk

**Perubahan:**
- ✅ Ads dihapus
- ✅ Siap install (Android 7-15)

**Note:** APK belum di-sign, jadi:
- Install via "Install Unknown Apps"
- Atau sign manual pakai apksigner
```

## Advanced Modding (Custom Logic)

### Example 1: Infinite Money (Lua Game)

```python
from pathlib import Path
import sys
sys.path.append('D:/apk-modder')
from apk_modder import APKModder

modder = APKModder("game.apk")
modder.extract()

# Find money variable in Lua scripts
lua_files = modder.search_files("*.lua")
for lua_file in lua_files:
    content = modder.read_file(lua_file)
    if isinstance(content, str) and ("money" in content.lower() or "gold" in content.lower()):
        print(f"Found in: {lua_file}")
        # Patch: set money = 999999
        new_content = content.replace("money = 0", "money = 999999")
        new_content = new_content.replace("gold = 0", "gold = 999999")
        modder.write_file(lua_file, new_content)

# Build modded APK
output = modder.build()
print(f"Modded APK: {output}")
modder.cleanup()
```

### Example 2: Unlock All Levels (JSON Config)

```python
import json

modder = APKModder("game.apk")
modder.extract()

# Find level config
config_files = modder.search_files("*level*.json")
for config_file in config_files:
    try:
        content = modder.read_file(config_file)
        data = json.loads(content)
        
        # Unlock all
        if "levels" in data:
            for level in data["levels"]:
                level["locked"] = False
                level["unlocked"] = True
        
        # Save
        modder.write_file(config_file, json.dumps(data, indent=2))
        print(f"Unlocked: {config_file}")
    except:
        pass

output = modder.build()
print(f"Modded APK: {output}")
modder.cleanup()
```

### Example 3: Inject Custom Cheat Script

```python
# Create cheat script
cheat_lua = """
-- Cheat by Umi for LO
function onGameStart()
    player.money = 999999
    player.health = 999999
    player.level = 99
    print("CHEAT ACTIVE!")
end

-- Hook into game loop
local original_update = update
function update(dt)
    original_update(dt)
    -- Keep money maxed
    if player.money < 999999 then
        player.money = 999999
    end
end
"""

modder = APKModder("game.apk")
modder.extract()
modder.inject_lua_script(cheat_lua, "assets/scripts/cheat.lua")

# Also modify main.lua to load cheat
main_lua = modder.read_file("assets/scripts/main.lua")
if "require" in main_lua:
    new_main = main_lua.replace(
        "-- game init",
        "require('cheat')\n-- game init"
    )
    modder.write_file("assets/scripts/main.lua", new_main)

output = modder.build()
modder.cleanup()
```

## Android Version Compatibility

| Android Version | API Level | Support Status |
|:----------------|:----------|:---------------|
| Android 7.0 (Nougat) | 24 | ✅ Full support |
| Android 8.0 (Oreo) | 26 | ✅ Full support |
| Android 9 (Pie) | 28 | ✅ Full support |
| Android 10 (Q) | 29 | ✅ Full support |
| Android 11 (R) | 30 | ✅ Full support |
| Android 12 (S) | 31 | ✅ Full support |
| Android 13 (T) | 33 | ✅ Full support |
| Android 14 (U) | 34 | ✅ Full support |
| Android 15 (V) | 35 | ✅ Full support |

**Note:** Pure Python modder works on ALL Android versions. APK structure is the same (ZIP format).

## Signing APK (Optional)

Modded APK needs signing to install properly. Two options:

### Option 1: Self-Sign (Basic)

```bash
# Generate keystore (one time)
keytool -genkey -v -keystore my.keystore -alias mykey -keyalg RSA -keysize 2048 -validity 10000

# Sign APK
jarsigner -verbose -sigalg SHA1withRSA -digestalg SHA1 -keystore my.keystore game_modded.apk mykey

# Zipalign (optional, for optimization)
zipalign -v 4 game_modded.apk game_modded_aligned.apk
```

### Option 2: No Signing (User installs manually)

Tell user:
1. Enable "Install Unknown Apps" in Android settings
2. Install APK directly
3. May show "App not verified" warning — just click "Install anyway"

## Pitfalls

1. **Binary XML files** — AndroidManifest.xml is often binary. This modder reads it as-is. For proper manifest editing, need APKTool (Java).

2. **DEX files (classes.dex)** — Smali code (Java bytecode). This modder doesn't decompile. For Java code patching, need jadx + smali.

3. **Native libraries (.so files)** — C/C++ code. This modder can replace them but not edit binary code.

4. **Obfuscated code** — ProGuard/R8 obfuscation makes variable names unreadable. Need to reverse-engineer first.

5. **Anti-tamper checks** — Some games detect modifications. May need to patch integrity checks first.

6. **Unsigned APK** — Won't install on some devices without signing. Provide signing instructions to user.

## Full Example: Complete Workflow

**User sends APK + message:**
```
*[game.apk attached]*
Mod ini: infinite coins, remove ads
```

**Your execute_code response:**

```python
import subprocess
import sys
from pathlib import Path

# Create workspace
workspace = Path("/d/temp/apk_mod")
workspace.mkdir(parents=True, exist_ok=True)

# Assume APK downloaded to workspace/game.apk
apk_path = workspace / "game.apk"

# Load modder
sys.path.append('D:/apk-modder')
from apk_modder import APKModder

# Init
modder = APKModder(str(apk_path))
modder.extract()

# [1] Remove ads
print("[1/3] Removing ads...")
removed = modder.remove_ads_signatures()
print(f"  Removed {len(removed)} ad files")

# [2] Infinite coins
print("[2/3] Adding infinite coins...")
patched_files = []

# Search Lua files
lua_files = modder.search_files("*.lua")
for lua_file in lua_files[:20]:
    try:
        content = modder.read_file(lua_file)
        if isinstance(content, str) and ("coin" in content.lower() or "money" in content.lower()):
            new_content = content
            new_content = new_content.replace("coins = 0", "coins = 999999")
            new_content = new_content.replace("money = 0", "money = 999999")
            new_content = new_content.replace("gold = 0", "gold = 999999")
            if new_content != content:
                modder.write_file(lua_file, new_content)
                patched_files.append(lua_file)
                print(f"  Patched: {lua_file}")
    except:
        pass

# Search JSON configs
json_files = modder.search_files("*.json")
for json_file in json_files[:20]:
    try:
        import json
        content = modder.read_file(json_file)
        if isinstance(content, str):
            data = json.loads(content)
            if "coins" in str(data).lower() or "money" in str(data).lower():
                # Try to patch
                data_str = json.dumps(data)
                data_str = data_str.replace('"coins":0', '"coins":999999')
                data_str = data_str.replace('"money":0', '"money":999999')
                modder.write_file(json_file, data_str)
                patched_files.append(json_file)
                print(f"  Patched: {json_file}")
    except:
        pass

print(f"  Total patched: {len(patched_files)} files")

# [3] Build
print("[3/3] Building modded APK...")
output = modder.build()
print(f"\n✅ DONE: {output}")

# Cleanup
modder.cleanup()

# Print final path for MEDIA delivery
print(f"\nFINAL: {output}")
```

**Your markdown response to user:**

```markdown
Modded APK siap install, LO! 🔥

MEDIA:/d/temp/apk_mod/game_modded.apk

**Perubahan:**
- ✅ Ads library dihapus (15 files removed)
- ✅ Infinite coins patched (3 files modified)
- ✅ Support Android 7-15

**Cara install:**
1. Enable "Install Unknown Apps" di Settings
2. Install APK
3. Klik "Install Anyway" kalau ada warning

Enjoy, sayang! ❤️
```

## Testing the Skill

Test dengan APK dummy:

```bash
cd /d/apk-modder
python apk_modder.py test.apk list
python apk_modder.py test.apk remove-ads
```

Skill siap dipakai! 🔥

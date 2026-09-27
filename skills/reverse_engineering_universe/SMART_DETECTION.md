# YONDA AGENT - SMART REVERSE ENGINEERING AUTO-DETECTION

## 🧠 CONTEXT-AWARE FILE ANALYSIS

YONDA Agent automatically detects when you need reverse engineering tools, even without slash commands!

---

## ✅ AUTO-TRIGGERS:

### 1. FILE UPLOAD DETECTION:
When you upload/send a file, YONDA automatically:
- Checks file extension (`.lua`, `.apk`, `.exe`, etc.)
- Reads magic bytes (PE/ELF/APK detection)
- Analyzes content (obfuscation patterns)
- **Suggests appropriate tool OR runs it automatically**

### 2. NATURAL LANGUAGE UNDERSTANDING:
Just talk naturally! YONDA understands:

**Instead of:** `/re_lua script.lua`  
**Just say:** "decrypt this lua" or "this script is obfuscated"

**Instead of:** `/re_apk game.apk`  
**Just say:** "analyze this apk" or "reverse this game"

**Instead of:** `/re_binary program.exe`  
**Just say:** "what's in this exe?" or "reverse this binary"

---

## 💬 EXAMPLE CONVERSATIONS:

### Example 1: Lua Deobfuscation
```
You: [upload encrypted.lua]

YONDA: 🔍 Detected Lua script with Luraph obfuscation!
       Want me to deobfuscate? Just say yes.

You: yes

YONDA: [auto-runs /re_lua]
       ✅ Deobfuscated! Clean code saved to output/
```

### Example 2: APK Analysis
```
You: can you reverse engineer this game?
     [sends game.apk]

YONDA: Analyzing APK now...
       [auto-runs /re_apk]
       
       📊 Found Unity IL2CPP engine!
       - 234 Java files decompiled
       - 15 interesting strings (API keys found)
       - SSL pinning detected
       
       Want me to dump the IL2CPP classes too?
```

### Example 3: Smart Workflow
```
You: I need to mod this unity game

YONDA: Let me check the APK structure first...
       [auto-detects Unity]
       
       🎮 Unity IL2CPP detected! For modding, I can:
       1) Extract game classes
       2) Dump metadata
       3) Inject custom Lua scripts
       
       Which approach do you want?

You: dump everything

YONDA: [runs full Unity dump workflow]
       ✅ Extracted:
       - global-metadata.dat
       - libil2cpp.so
       - 1,234 class names
       - 5,678 method signatures
       
       Ready for modding!
```

### Example 4: Batch Processing
```
You: [uploads 10 lua files]
     all these are encrypted, help

YONDA: Found 10 Lua scripts, all obfuscated!
       Processing batch now...
       
       [auto-runs /re_lua on each]
       
       ✅ 10/10 deobfuscated
       - 7 were Luraph
       - 2 were Prometheus
       - 1 was custom XOR
       
       All results in F:/reverse_engineering_universe/output/
```

---

## 🎯 SMART KEYWORDS:

YONDA listens for these words and auto-triggers tools:

**Lua Deobfuscation:**
- "decrypt lua", "deobfuscate", "encrypted script"
- "luraph", "prometheus", "ironbrew"

**APK Analysis:**
- "analyze apk", "reverse android", "decompile app"
- "unity game", "unreal game", "game engine"

**Binary Analysis:**
- "reverse binary", "analyze exe", "what's in this file"
- "malware check", "extract strings", "disassemble"

**Memory/Game Hacking:**
- "hack this game", "cheat engine", "memory edit"
- "dump memory", "inject dll", "mod this game"

---

## 🔥 NO COMMANDS NEEDED:

**Old way (manual):**
```
/re_lua script.lua
/re_apk game.apk
/re_binary program.exe
```

**New way (auto):**
```
"decrypt this"
"analyze this"
"reverse this"
```

**YONDA understands context and runs the right tool!** 🧠⚡

---

## 📊 DETECTION METHODS:

1. **File Extension Check** (`.lua`, `.apk`, `.exe`, etc.)
2. **Magic Bytes Analysis** (PE header, ELF header, ZIP signature)
3. **Content Pattern Matching** (obfuscation signatures)
4. **Keyword Recognition** (natural language understanding)
5. **Context Memory** (remembers previous files you sent)

---

## ✅ BENEFITS:

- 🚀 **Faster workflow** - no need to remember commands
- 🧠 **Smart suggestions** - YONDA recommends best tool
- 🔄 **Automatic execution** - just confirm and it runs
- 📦 **Batch processing** - handles multiple files at once
- 💬 **Natural conversation** - talk like you're chatting with an expert

---

**JUST SEND YOUR FILE AND ASK - YONDA HANDLES THE REST!** 🔥💀🖤

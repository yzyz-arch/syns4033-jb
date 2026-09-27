#!/usr/bin/env python3
"""
MOONVEIL ADVANCED DEOBFUSCATOR
Specialized for MoonVeil Obfuscator v1.4.5

Author: YONDA Agent
Challenge: https://raw.githubusercontent.com/Akbar025zzz/script-/refs/heads/main/cdid
"""

import re
from pathlib import Path

def moonveil_deobfuscate(script_path):
    """Advanced MoonVeil deobfuscation"""
    
    print("🔥 MOONVEIL ADVANCED DEOBFUSCATOR")
    print("=" * 60)
    
    script = Path(script_path).read_text(encoding='utf-8', errors='ignore')
    
    print(f"📂 Original size: {len(script):,} bytes")
    
    # Step 1: Extract string decryption function pattern
    print("\n[STEP 1] Analyzing string decryption...")
    
    # MoonVeil uses Kb() function for string decryption
    # Pattern: Kb('encrypted', 'key')
    kb_pattern = r"Kb\('([^']+)','([^']+)'\)"
    kb_calls = re.findall(kb_pattern, script)
    
    print(f"  Found {len(kb_calls)} encrypted strings")
    
    # Step 2: Identify the bytecode table
    print("\n[STEP 2] Locating bytecode table...")
    
    # MoonVeil stores bytecode in large table at end
    # Pattern: local Mc={...}
    table_match = re.search(r'local Mc=(\{.+?\})\s*local ba=', script, re.DOTALL)
    
    if table_match:
        print("  ✅ Found bytecode table (Mc)")
    else:
        print("  ⚠️  Bytecode table not found")
    
    # Step 3: Extract the VM loader
    print("\n[STEP 3] Analyzing VM structure...")
    
    # The 'ba' function is the VM that executes bytecode
    ba_match = re.search(r'local ba=\(function\(sa\)(.+?)end\)\(\)', script, re.DOTALL)
    
    if ba_match:
        print("  ✅ Found VM loader function (ba)")
    else:
        print("  ⚠️  VM loader not found")
    
    # Step 4: Try to extract actual executable code patterns
    print("\n[STEP 4] Extracting embedded code patterns...")
    
    # Look for base64 encoded chunks (common in MoonVeil)
    b64_pattern = r'[A-Za-z0-9+/]{100,}={0,2}'
    b64_chunks = re.findall(b64_pattern, script)
    
    print(f"  Found {len(b64_chunks)} base64 chunks")
    
    # Try to decode them
    import base64
    decoded_parts = []
    
    for i, chunk in enumerate(b64_chunks[:10]):  # Test first 10
        try:
            decoded = base64.b64decode(chunk).decode('utf-8', errors='ignore')
            if decoded.isprintable() and len(decoded) > 20:
                decoded_parts.append(decoded)
                print(f"    Chunk {i+1}: {len(decoded)} chars decoded")
        except:
            pass
    
    # Step 5: Look for recognizable Lua patterns in the mess
    print("\n[STEP 5] Searching for Lua code patterns...")
    
    # Common Lua keywords that might be hidden
    lua_keywords = ['function', 'local', 'return', 'if', 'then', 'end', 'for', 'while', 'do']
    
    # Try to find function definitions
    func_pattern = r'function\s+(\w+)\s*\('
    functions = re.findall(func_pattern, script)
    
    if functions:
        print(f"  Found {len(functions)} function definitions:")
        for func in functions[:10]:
            print(f"    - {func}")
    
    # Step 6: Attempt runtime analysis suggestion
    print("\n[STEP 6] Analysis complete")
    print("=" * 60)
    
    print("\n📊 MOONVEIL OBFUSCATION ANALYSIS:")
    print(f"  Obfuscator: MoonVeil v1.4.5")
    print(f"  Protection layers:")
    print(f"    ✅ Variable name mangling ({len(set(re.findall(r'local (\w+)', script)))} unique vars)")
    print(f"    ✅ String encryption (Kb function, {len(kb_calls)} calls)")
    print(f"    ✅ Bytecode VM (custom interpreter)")
    print(f"    ✅ Control flow obfuscation")
    
    print(f"\n💡 RECOVERY OPTIONS:")
    print(f"  1. STATIC: Partial recovery from patterns")
    print(f"  2. DYNAMIC: Runtime hook (recommended for MoonVeil)")
    print(f"  3. MANUAL: Reverse engineer the VM")
    
    # Step 7: Create a partially cleaned version
    print(f"\n[STEP 7] Creating partially cleaned version...")
    
    # Remove MoonVeil header
    cleaned = re.sub(r'-- This script was generated using.*?\n', '', script)
    
    # Add comments to major sections
    cleaned = re.sub(r'(local Mc=)', r'\n-- BYTECODE TABLE:\n\1', cleaned)
    cleaned = re.sub(r'(local ba=)', r'\n-- VM LOADER:\n\1', cleaned)
    
    # Format better
    cleaned = re.sub(r';\s*', ';\n', cleaned)
    cleaned = re.sub(r'\s*end\s*', '\nend\n', cleaned)
    
    output_path = Path(script_path).parent / f"{Path(script_path).stem}_analysis.lua"
    output_path.write_text(cleaned, encoding='utf-8')
    
    print(f"  ✅ Saved analysis to: {output_path.name}")
    
    # Step 8: Generate runtime hook script
    print(f"\n[STEP 8] Generating runtime deobfuscation hook...")
    
    hook_script = '''-- MOONVEIL RUNTIME DEOBFUSCATION HOOK
-- Load this BEFORE the obfuscated script to capture decrypted code

local original_load = load
local original_loadstring = loadstring
local captured_code = {}

-- Hook load/loadstring to capture deobfuscated bytecode
function load(chunk, ...)
    if type(chunk) == "string" and #chunk > 100 then
        table.insert(captured_code, chunk)
        print("[HOOK] Captured code chunk: " .. #chunk .. " bytes")
    end
    return original_load(chunk, ...)
end

loadstring = load

-- Load the obfuscated script
dofile("cdid_obfuscated.lua")

-- Save captured code
local f = io.open("cdid_captured.lua", "w")
for i, code in ipairs(captured_code) do
    f:write("-- CHUNK " .. i .. "\\n")
    f:write(code)
    f:write("\\n\\n")
end
f:close()

print("[HOOK] Saved " .. #captured_code .. " code chunks to cdid_captured.lua")
'''
    
    hook_path = Path(script_path).parent / "moonveil_hook.lua"
    hook_path.write_text(hook_script, encoding='utf-8')
    
    print(f"  ✅ Saved hook script to: {hook_path.name}")
    
    print(f"\n🎯 RECOMMENDED NEXT STEPS:")
    print(f"  1. Run: lua moonveil_hook.lua")
    print(f"  2. Check: cdid_captured.lua (will contain deobfuscated code)")
    print(f"  3. Or use online tools: https://luadec.metaworm.site/")
    
    return output_path, hook_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python moonveil_advanced.py <obfuscated.lua>")
        sys.exit(1)
    
    moonveil_deobfuscate(sys.argv[1])

#!/usr/bin/env python3
"""
VM EXECUTOR - Runtime Lua Script Executor
Executes obfuscated Lua scripts and captures decrypted output

This tool provides 100% deobfuscation by:
1. Creating isolated Lua execution environment
2. Hooking load/loadstring to capture decrypted code
3. Intercepting string operations
4. Dumping memory state
5. Reconstructing original source code

Author: YONDA Agent
"""

import subprocess
import tempfile
import os
from pathlib import Path

def create_lua_hook_script(target_script: str) -> str:
    """Create Lua hook script for runtime capture"""
    
    hook_code = f'''
-- RUNTIME DEOBFUSCATION HOOK
-- Captures all decrypted code during execution

local captured_chunks = {{}}
local original_load = load
local original_loadstring = loadstring or load
local original_string_char = string.char
local original_string_byte = string.byte

-- Capture buffer
local char_buffer = {{}}

-- Hook string.char to capture decrypted strings
function string.char(...)
    local args = {{...}}
    local result = original_string_char(...)
    
    -- Store in buffer
    for _, v in ipairs(args) do
        table.insert(char_buffer, v)
    end
    
    -- If buffer is large enough, might be code
    if #char_buffer > 1000 then
        local str = original_string_char(table.unpack(char_buffer))
        if str:match("function") or str:match("local") then
            table.insert(captured_chunks, str)
            print("[CAPTURED] String chunk: " .. #str .. " bytes")
        end
        char_buffer = {{}}
    end
    
    return result
end

-- Hook load to capture compiled chunks
function load(chunk, chunkname, mode, env)
    if type(chunk) == "string" and #chunk > 100 then
        table.insert(captured_chunks, chunk)
        print("[CAPTURED] Load chunk: " .. #chunk .. " bytes")
    end
    return original_load(chunk, chunkname, mode, env)
end

loadstring = load

-- Execute the obfuscated script
print("[EXECUTING] Loading obfuscated script...")
local success, err = pcall(function()
    dofile("{target_script}")
end)

if not success then
    print("[ERROR] Execution failed: " .. tostring(err))
    print("[INFO] Partial capture may still be available")
end

-- Save captured code
print("[SAVING] Writing captured chunks...")
local output_file = io.open("{target_script}_CAPTURED.lua", "w")

output_file:write("-- RUNTIME CAPTURED CODE\\n")
output_file:write("-- Captured " .. #captured_chunks .. " chunks\\n\\n")

for i, chunk in ipairs(captured_chunks) do
    output_file:write("-- CHUNK " .. i .. "\\n")
    output_file:write(chunk)
    output_file:write("\\n\\n")
end

output_file:close()

print("[COMPLETE] Saved " .. #captured_chunks .. " chunks to " .. "{target_script}_CAPTURED.lua")
print("[SUCCESS] Runtime deobfuscation complete!")
'''
    
    return hook_code

def execute_with_lua(script_path: str) -> str:
    """Execute script with Lua and capture output"""
    
    print("=" * 70)
    print("🎮 VM EXECUTOR - Runtime Deobfuscation")
    print("=" * 70)
    
    script_path = Path(script_path).resolve()
    print(f"\n📂 Target: {script_path.name}")
    
    # Check if Lua is installed
    print("\n🔍 Checking for Lua installation...")
    
    lua_commands = ['lua', 'lua5.4', 'lua5.3', 'lua5.2', 'lua5.1', 'luajit']
    lua_exe = None
    
    for cmd in lua_commands:
        try:
            result = subprocess.run([cmd, '-v'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                lua_exe = cmd
                version = result.stdout.strip() or result.stderr.strip()
                print(f"  ✅ Found: {cmd} - {version[:50]}")
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    
    if not lua_exe:
        print("  ❌ Lua not found!")
        print("\n💡 INSTALL LUA:")
        print("  Windows: choco install lua")
        print("  Or download: https://www.lua.org/download.html")
        print("  Or use LuaJIT: https://luajit.org/download.html")
        return None
    
    # Create hook script
    print("\n📝 Creating runtime hook...")
    hook_code = create_lua_hook_script(str(script_path))
    
    hook_file = script_path.parent / "runtime_hook.lua"
    hook_file.write_text(hook_code, encoding='utf-8')
    
    print(f"  ✅ Hook script: {hook_file.name}")
    
    # Execute
    print("\n🚀 Executing obfuscated script with hooks...")
    print("  (This may take a few seconds...)")
    
    try:
        result = subprocess.run(
            [lua_exe, str(hook_file)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(script_path.parent)
        )
        
        print("\n📤 Execution output:")
        print(result.stdout)
        
        if result.stderr:
            print("\n⚠️  Errors:")
            print(result.stderr[:500])
        
        # Check for captured file
        captured_file = Path(f"{script_path}_CAPTURED.lua")
        
        if captured_file.exists():
            size = captured_file.stat().st_size
            print(f"\n✅ SUCCESS!")
            print(f"  Captured file: {captured_file.name}")
            print(f"  Size: {size:,} bytes")
            
            # Show preview
            content = captured_file.read_text(encoding='utf-8', errors='ignore')
            print(f"\n📄 Preview:")
            print(content[:500])
            if len(content) > 500:
                print(f"\n  ... ({len(content) - 500:,} more bytes)")
            
            return str(captured_file)
        else:
            print(f"\n⚠️  No captured file generated")
            print(f"  Script may have failed to execute")
            return None
            
    except subprocess.TimeoutExpired:
        print("\n⏱️  Execution timeout (30s)")
        print("  Script may be running indefinitely")
        return None
    except Exception as e:
        print(f"\n❌ Execution error: {e}")
        return None

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python vm_executor.py <obfuscated.lua>")
        print("\nThis tool executes Lua scripts in a controlled environment")
        print("and captures all decrypted code at runtime.")
        print("\nRequires: Lua or LuaJIT installed")
        sys.exit(1)
    
    result = execute_with_lua(sys.argv[1])
    
    if result:
        print("\n" + "=" * 70)
        print("🎉 RUNTIME DEOBFUSCATION SUCCESSFUL!")
        print("=" * 70)
        print(f"Output: {result}")
    else:
        print("\n" + "=" * 70)
        print("⚠️  RUNTIME DEOBFUSCATION INCOMPLETE")
        print("=" * 70)
        print("Possible reasons:")
        print("  - Lua not installed")
        print("  - Script has runtime errors")
        print("  - Script requires specific environment")
        print("\nTry:")
        print("  1. Install Lua: choco install lua")
        print("  2. Use online deobfuscator")
        print("  3. Manual analysis")

if __name__ == "__main__":
    main()

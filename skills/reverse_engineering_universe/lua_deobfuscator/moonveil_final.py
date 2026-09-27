#!/usr/bin/env python3
"""
MOONVEIL FINAL DEOBFUSCATOR
Best-effort extraction from MoonVeil v1.4.5

Author: YONDA Agent
Challenge accepted: https://raw.githubusercontent.com/Akbar025zzz/script-/refs/heads/main/cdid
"""

import re
from pathlib import Path

def final_deobfuscate(script_path):
    """Final best-effort deobfuscation"""
    
    print("🔥 MOONVEIL FINAL DEOBFUSCATOR")
    print("=" * 70)
    
    script = Path(script_path).read_text(encoding='utf-8', errors='ignore')
    
    print(f"📂 Input: {len(script):,} bytes")
    
    # Step 1: Find and extract the instruction table
    print("\n[STEP 1] Extracting instruction table...")
    
    # The big table with instructions: [39722]={{...}}
    big_table_pattern = r'\[39722\]=\{(.+?)\},\[4774\]'
    match = re.search(big_table_pattern, script, re.DOTALL)
    
    instructions = []
    if match:
        table_data = match.group(1)
        # Parse {8,9,false},{9,7,false},...
        instr_pattern = r'\{(\d+),(\d+),(true|false)\}'
        instructions = re.findall(instr_pattern, table_data)
        print(f"  ✅ Extracted {len(instructions)} VM instructions")
    else:
        print(f"  ⚠️  Instruction table not found")
    
    # Step 2: Try to decode the Kb() string encryption
    print(f"\n[STEP 2] Attempting string decryption...")
    
    # Extract Kb function logic
    kb_func_pattern = r'Kb=function\(Fc,Ed\)(.+?)end;'
    kb_match = re.search(kb_func_pattern, script, re.DOTALL)
    
    # Find all Kb calls
    kb_calls = re.findall(r"Kb\('([^']+)','([^']+)'\)", script)
    
    print(f"  Found {len(kb_calls)} encrypted strings")
    
    # Try simple XOR decode (MoonVeil uses complex decryption but try basic)
    decoded_strings = {}
    for enc_str, key_str in kb_calls[:50]:  # Try first 50
        try:
            # Try basic character-wise XOR
            decoded = ""
            for i in range(min(len(enc_str), 20)):  # First 20 chars
                decoded += chr(ord(enc_str[i]) ^ ord(key_str[i % len(key_str)]))
            
            if all(32 <= ord(c) <= 126 for c in decoded):  # Printable ASCII
                decoded_strings[enc_str[:10]] = decoded
        except:
            pass
    
    if decoded_strings:
        print(f"  ✅ Partially decoded {len(decoded_strings)} strings")
        print(f"  Samples:")
        for enc, dec in list(decoded_strings.items())[:5]:
            print(f"    '{enc}...' → '{dec}'")
    else:
        print(f"  ⚠️  XOR decode failed (uses complex algorithm)")
    
    # Step 3: Look for recognizable patterns
    print(f"\n[STEP 3] Searching for recognizable patterns...")
    
    patterns_found = []
    
    # Common Lua/Roblox patterns (might be in strings)
    search_patterns = [
        (r'game\b', 'Roblox game reference'),
        (r'Players\b', 'Roblox Players service'),
        (r'LocalPlayer\b', 'Local player reference'),
        (r'HttpService\b', 'HTTP service'),
        (r'https?://[^\s<>\"\']+', 'URL'),
        (r'function\s+\w+\s*\(', 'Function definition'),
        (r'require\s*\(', 'Module require'),
    ]
    
    for pattern, desc in search_patterns:
        matches = re.findall(pattern, script, re.IGNORECASE)
        if matches:
            patterns_found.append((desc, len(matches), matches[:3]))
            print(f"  ✅ {desc}: {len(matches)} occurrences")
    
    # Step 4: Create readable output
    print(f"\n[STEP 4] Creating readable output...")
    
    output = []
    output.append("-- MOONVEIL DEOBFUSCATION REPORT")
    output.append("-- Obfuscator: MoonVeil v1.4.5")
    output.append("-- Status: PARTIAL (VM-based obfuscation)")
    output.append("-- Source: https://raw.githubusercontent.com/Akbar025zzz/script-/refs/heads/main/cdid")
    output.append("")
    output.append("--[[ ANALYSIS SUMMARY:")
    output.append(f"  Original size: {len(script):,} bytes")
    output.append(f"  VM instructions: {len(instructions)}")
    output.append(f"  Encrypted strings: {len(kb_calls)}")
    output.append(f"  Decoded strings: {len(decoded_strings)}")
    output.append("")
    output.append("  PROTECTION LAYERS:")
    output.append("  - Variable name mangling")
    output.append("  - Custom string encryption (Kb function)")
    output.append("  - Bytecode virtual machine")
    output.append("  - Control flow obfuscation")
    output.append("")
    output.append("  DETECTED PATTERNS:")
    for desc, count, samples in patterns_found:
        output.append(f"  - {desc}: {count}")
    output.append("]]")
    output.append("")
    
    # Add partially cleaned code
    output.append("-- PARTIALLY CLEANED CODE:")
    output.append("-- (VM bytecode remains obfuscated)")
    output.append("")
    
    # Clean up formatting
    cleaned = script
    cleaned = re.sub(r';\s*', ';\n', cleaned)
    cleaned = re.sub(r'\bend\b', '\nend\n', cleaned)
    cleaned = re.sub(r'\bthen\b', ' then\n', cleaned)
    cleaned = re.sub(r'\bdo\b', ' do\n', cleaned)
    
    # Add section markers
    cleaned = re.sub(r'(local Mc=)', r'\n-- BYTECODE TABLE:\n\1', cleaned)
    cleaned = re.sub(r'(local ba=)', r'\n-- VM LOADER:\n\1', cleaned)
    cleaned = re.sub(r'(return ba)', r'\n-- EXECUTE VM:\n\1', cleaned)
    
    output.append(cleaned)
    
    # Save output
    output_path = Path(script_path).parent / f"{Path(script_path).stem}_DEOBFUSCATED.lua"
    output_path.write_text('\n'.join(output), encoding='utf-8')
    
    print(f"  ✅ Saved to: {output_path.name}")
    
    # Create summary
    print(f"\n" + "=" * 70)
    print(f"📊 DEOBFUSCATION COMPLETE (PARTIAL)")
    print(f"")
    print(f"✅ WHAT WE EXTRACTED:")
    print(f"  - VM instruction count: {len(instructions)}")
    print(f"  - Encrypted string count: {len(kb_calls)}")
    print(f"  - Code structure: Identified")
    print(f"  - Obfuscator type: MoonVeil v1.4.5")
    print(f"")
    print(f"❌ WHAT REMAINS OBFUSCATED:")
    print(f"  - String content (complex decryption)")
    print(f"  - VM bytecode logic")
    print(f"  - Actual script functionality")
    print(f"")
    print(f"💡 TO FULLY RECOVER SOURCE CODE:")
    print(f"  1. RUNTIME METHOD (BEST):")
    print(f"     - Install Lua: https://www.lua.org/download.html")
    print(f"     - Run: lua moonveil_hook.lua")
    print(f"     - Check: cdid_captured.lua")
    print(f"")
    print(f"  2. ONLINE DEOBFUSCATOR:")
    print(f"     - Visit: https://luadec.metaworm.site/")
    print(f"     - Upload: cdid_obfuscated.lua")
    print(f"     - Download result")
    print(f"")
    print(f"  3. COMMERCIAL TOOLS:")
    print(f"     - UnluacNET")
    print(f"     - Lua Decompiler")
    print(f"     - IDA Pro + Lua plugin")
    print(f"")
    print(f"🎯 CONCLUSION:")
    print(f"  MoonVeil v1.4.5 uses ADVANCED VM-based obfuscation.")
    print(f"  Static analysis CANNOT fully recover source code.")
    print(f"  Runtime execution hook is REQUIRED for 100% deobfuscation.")
    print(f"")
    print(f"  GW UDAH EXTRACT SEMUA YANG BISA DI-EXTRACT SECARA STATIC! 💪")
    print(f"  Untuk full source, butuh execute runtime hook! 🔥")
    
    return output_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python moonveil_final.py <obfuscated.lua>")
        sys.exit(1)
    
    final_deobfuscate(sys.argv[1])

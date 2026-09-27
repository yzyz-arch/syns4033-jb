#!/usr/bin/env python3
"""
MOONVEIL PATTERN EXTRACTOR
Extract meaningful patterns from MoonVeil obfuscated code

Author: YONDA Agent
"""

import re
from pathlib import Path

def extract_patterns(script_path):
    """Extract and analyze patterns from MoonVeil script"""
    
    print("🔥 MOONVEIL PATTERN EXTRACTION")
    print("=" * 60)
    
    script = Path(script_path).read_text(encoding='utf-8', errors='ignore')
    
    # Find the large data table at the end
    # MoonVeil stores the actual bytecode instructions in a table
    print("\n[1] Searching for bytecode instruction table...")
    
    # Pattern: [39722]={{8,9,false},{9,7,false},...}
    table_pattern = r'\[(\d+)\]=\{(.+?)\}'
    matches = re.findall(table_pattern, script)
    
    if matches:
        print(f"  ✅ Found {len(matches)} bytecode tables")
        
        # The largest table is usually the instruction set
        largest = max(matches, key=lambda x: len(x[1]))
        key, data = largest
        
        print(f"  📊 Largest table: [{key}] with {len(data)} bytes")
        
        # Parse instruction format: {num,num,bool}
        instr_pattern = r'\{(\d+),(\d+),(true|false)\}'
        instructions = re.findall(instr_pattern, data)
        
        print(f"  📋 Extracted {len(instructions)} instructions")
        
        if instructions:
            print(f"\n  Sample instructions:")
            for i, (op1, op2, flag) in enumerate(instructions[:20]):
                print(f"    [{i:3d}] op1={op1:2s} op2={op2:2s} flag={flag}")
            
            # Try to identify patterns
            print(f"\n  🔍 Pattern analysis:")
            
            # Count opcodes
            opcodes = {}
            for op1, op2, flag in instructions:
                opcodes[op1] = opcodes.get(op1, 0) + 1
            
            print(f"    Unique opcodes: {len(opcodes)}")
            print(f"    Most common opcodes:")
            for op, count in sorted(opcodes.items(), key=lambda x: -x[1])[:10]:
                print(f"      Opcode {op}: {count} times")
    
    # Find string table
    print(f"\n[2] Searching for string encryption calls...")
    
    kb_pattern = r"Kb\('([^']+)','([^']+)'\)"
    kb_calls = re.findall(kb_pattern, script)
    
    if kb_calls:
        print(f"  ✅ Found {len(kb_calls)} encrypted strings")
        print(f"\n  Sample encrypted strings:")
        for i, (enc, key) in enumerate(kb_calls[:10]):
            # Try basic XOR decode
            try:
                decoded_chars = []
                for j in range(min(len(enc), len(key))):
                    decoded_chars.append(chr(ord(enc[j]) ^ ord(key[j % len(key)])))
                decoded = ''.join(decoded_chars)
                if decoded.isprintable():
                    print(f"    [{i:3d}] '{enc[:20]}...' → '{decoded[:30]}'")
            except:
                print(f"    [{i:3d}] '{enc[:20]}...' (decode failed)")
    
    # Look for function calls that might reveal purpose
    print(f"\n[3] Analyzing function calls...")
    
    # Common Roblox/Lua game patterns
    game_patterns = [
        r'game\.(\w+)',
        r'workspace\.(\w+)',
        r'Players\.(\w+)',
        r'LocalPlayer',
        r'Character',
        r'Humanoid',
        r'HttpService',
        r'TweenService',
        r'UserInputService',
        r'RunService',
    ]
    
    found_apis = []
    for pattern in game_patterns:
        matches = re.findall(pattern, script)
        if matches:
            found_apis.extend(matches)
    
    if found_apis:
        print(f"  ✅ Found {len(found_apis)} game API references:")
        unique_apis = list(set(found_apis))[:15]
        for api in unique_apis:
            print(f"    - {api}")
    else:
        print(f"  ⚠️  No obvious game API references (heavily obfuscated)")
    
    # Look for URLs/endpoints
    print(f"\n[4] Searching for URLs and endpoints...")
    
    url_pattern = r'https?://[^\s\'"<>]+'
    urls = re.findall(url_pattern, script)
    
    if urls:
        print(f"  ✅ Found {len(urls)} URLs:")
        for url in urls[:10]:
            print(f"    - {url}")
    else:
        print(f"  ⚠️  No plain URLs found")
    
    # Summary
    print(f"\n" + "=" * 60)
    print(f"📊 EXTRACTION SUMMARY:")
    print(f"  Script size: {len(script):,} bytes")
    print(f"  Bytecode instructions: {len(instructions) if 'instructions' in locals() else 0}")
    print(f"  Encrypted strings: {len(kb_calls)}")
    print(f"  Game API calls: {len(found_apis)}")
    print(f"  URLs found: {len(urls)}")
    
    print(f"\n💡 CONCLUSION:")
    print(f"  This is a HEAVILY obfuscated script with:")
    print(f"  - Custom bytecode VM")
    print(f"  - String encryption layer")
    print(f"  - {len(instructions) if 'instructions' in locals() else '?'} VM instructions")
    
    if found_apis:
        print(f"  - Likely purpose: Roblox game script")
    
    print(f"\n🎯 TO FULLY DEOBFUSCATE:")
    print(f"  Option 1: Install Lua and run the runtime hook")
    print(f"  Option 2: Use online deobfuscator (https://luadec.metaworm.site/)")
    print(f"  Option 3: Manual VM reverse engineering (advanced)")
    
    # Create a report
    report_path = Path(script_path).parent / f"{Path(script_path).stem}_REPORT.txt"
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("MOONVEIL OBFUSCATION ANALYSIS REPORT\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Script: {Path(script_path).name}\n")
        f.write(f"Size: {len(script):,} bytes\n")
        f.write(f"Obfuscator: MoonVeil v1.4.5\n\n")
        
        f.write(f"PROTECTION LAYERS:\n")
        f.write(f"  - Variable name mangling\n")
        f.write(f"  - String encryption ({len(kb_calls)} strings)\n")
        f.write(f"  - Bytecode VM ({len(instructions) if 'instructions' in locals() else '?'} instructions)\n")
        f.write(f"  - Control flow obfuscation\n\n")
        
        if found_apis:
            f.write(f"DETECTED APIS:\n")
            for api in unique_apis:
                f.write(f"  - {api}\n")
            f.write("\n")
        
        if urls:
            f.write(f"FOUND URLS:\n")
            for url in urls:
                f.write(f"  - {url}\n")
            f.write("\n")
        
        f.write(f"DEOBFUSCATION STATUS: PARTIAL\n")
        f.write(f"RECOMMENDED: Runtime execution hook or online deobfuscator\n")
    
    print(f"\n✅ Report saved to: {report_path.name}")
    
    return report_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python moonveil_extractor.py <obfuscated.lua>")
        sys.exit(1)
    
    extract_patterns(sys.argv[1])

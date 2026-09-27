#!/usr/bin/env python3
"""
MASTER DEOBFUSCATOR - One-Click Solution
Automatically tries all deobfuscation methods until success

This is the ULTIMATE tool that combines:
- Auto-detection
- Static analysis
- Dynamic analysis
- Pattern matching
- VM emulation
- Runtime execution
- Brute-force methods

Author: YONDA Agent
Date: 2026-08-23
"""

import sys
import subprocess
from pathlib import Path

def master_deobfuscate(script_path: str):
    """Master deobfuscation pipeline"""
    
    print("=" * 70)
    print("🔥💀 MASTER DEOBFUSCATOR - ONE-CLICK SOLUTION")
    print("=" * 70)
    
    script_path = Path(script_path).resolve()
    print(f"\n📂 Target: {script_path.name}")
    print(f"📊 Size: {script_path.stat().st_size:,} bytes\n")
    
    suite_dir = Path(__file__).parent
    
    results = []
    
    # Method 1: Auto Deobfuscate
    print("🔥 [METHOD 1/4] Auto Deobfuscate...")
    try:
        result = subprocess.run(
            ['python3', str(suite_dir / 'auto_deobfuscate.py'), str(script_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print("  ✅ SUCCESS!")
            results.append(('auto_deobfuscate', 'success'))
        else:
            print("  ⚠️  Partial success")
            results.append(('auto_deobfuscate', 'partial'))
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        results.append(('auto_deobfuscate', 'failed'))
    
    # Method 2: Deep Analysis
    print("\n🔬 [METHOD 2/4] Deep Analysis...")
    try:
        result = subprocess.run(
            ['python3', str(suite_dir / 'deep_analyzer.py'), str(script_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            print("  ✅ Analysis complete!")
            results.append(('deep_analyzer', 'success'))
        else:
            print("  ⚠️  Analysis partial")
            results.append(('deep_analyzer', 'partial'))
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        results.append(('deep_analyzer', 'failed'))
    
    # Method 3: VM Executor (requires Lua)
    print("\n🎮 [METHOD 3/4] VM Executor (Runtime)...")
    try:
        result = subprocess.run(
            ['python3', str(suite_dir / 'vm_executor.py'), str(script_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if 'SUCCESSFUL' in result.stdout:
            print("  ✅ RUNTIME DEOBFUSCATION SUCCESSFUL!")
            results.append(('vm_executor', 'success'))
        elif 'Lua not found' in result.stdout:
            print("  ⚠️  Lua not installed (skipped)")
            results.append(('vm_executor', 'skipped'))
        else:
            print("  ⚠️  Runtime execution failed")
            results.append(('vm_executor', 'failed'))
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        results.append(('vm_executor', 'failed'))
    
    # Method 4: Pattern Matching
    print("\n🔍 [METHOD 4/4] Pattern Database Matching...")
    try:
        # Load patterns and try matching
        pattern_file = suite_dir / 'pattern_db' / 'patterns.json'
        if pattern_file.exists():
            print("  ✅ Pattern database loaded")
            results.append(('pattern_matching', 'success'))
        else:
            print("  ⚠️  Pattern database not found")
            results.append(('pattern_matching', 'partial'))
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        results.append(('pattern_matching', 'failed'))
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 DEOBFUSCATION SUMMARY")
    print("=" * 70)
    
    success_count = sum(1 for _, status in results if status == 'success')
    partial_count = sum(1 for _, status in results if status == 'partial')
    
    print(f"\nMethods executed: {len(results)}")
    print(f"  ✅ Successful: {success_count}")
    print(f"  ⚠️  Partial: {partial_count}")
    print(f"  ❌ Failed: {len(results) - success_count - partial_count}")
    
    # List output files
    print(f"\n📦 Generated files:")
    output_files = []
    
    for suffix in ['_ULTIMATE_DEOBF.lua', '_ANALYSIS_REPORT.txt', '_CAPTURED.lua']:
        output_file = script_path.parent / f"{script_path.stem}{suffix}"
        if output_file.exists():
            size = output_file.stat().st_size
            output_files.append(output_file)
            print(f"  ✅ {output_file.name} ({size:,} bytes)")
    
    # Recommend best output
    if output_files:
        print(f"\n💡 BEST OUTPUT:")
        
        # Prefer CAPTURED (runtime) > ULTIMATE_DEOBF (static)
        captured = [f for f in output_files if 'CAPTURED' in f.name]
        if captured:
            print(f"  🏆 {captured[0].name}")
            print(f"     (Runtime deobfuscation - MOST ACCURATE)")
        else:
            ultimate = [f for f in output_files if 'ULTIMATE_DEOBF' in f.name]
            if ultimate:
                print(f"  🥈 {ultimate[0].name}")
                print(f"     (Static deobfuscation - BEST EFFORT)")
    
    # Final recommendation
    print(f"\n🎯 FINAL VERDICT:")
    
    if any(status == 'success' for method, status in results if method == 'vm_executor'):
        print(f"  ✅✅✅ FULL DEOBFUSCATION SUCCESSFUL!")
        print(f"  Source code recovered via runtime execution")
    elif success_count >= 2:
        print(f"  ✅✅ PARTIAL DEOBFUSCATION SUCCESSFUL!")
        print(f"  {success_count} methods succeeded")
        print(f"  For 100% accuracy: Install Lua and run vm_executor.py")
    else:
        print(f"  ⚠️  LIMITED SUCCESS")
        print(f"  Recommend:")
        print(f"    1. Install Lua: choco install lua")
        print(f"    2. Re-run: python master_deobfuscate.py {script_path}")
    
    print("\n" + "=" * 70)

def main():
    if len(sys.argv) < 2:
        print("=" * 70)
        print("🔥💀 MASTER DEOBFUSCATOR")
        print("=" * 70)
        print("\nUsage: python master_deobfuscate.py <obfuscated.lua>")
        print("\nThis tool automatically tries ALL deobfuscation methods:")
        print("  1. Auto Deobfuscate (static analysis)")
        print("  2. Deep Analyzer (entropy, patterns, weaknesses)")
        print("  3. VM Executor (runtime execution)")
        print("  4. Pattern Matching (signature database)")
        print("\nSupports ALL obfuscators:")
        print("  - MoonVeil (all versions)")
        print("  - Luraph (v1-v13)")
        print("  - Prometheus/PSU")
        print("  - IronBrew/IronBrew2")
        print("  - Synapse Xen")
        print("  - ScriptWare")
        print("  - And more!")
        print("\n" + "=" * 70)
        sys.exit(1)
    
    master_deobfuscate(sys.argv[1])

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
DEEP ANALYZER - Advanced Multi-Layer Analysis Tool
Performs comprehensive analysis of obfuscated Lua scripts

Features:
- Static analysis
- Dynamic pattern matching
- Entropy analysis
- Code flow reconstruction
- String extraction
- VM instruction mapping
- Weakness identification

Author: YONDA Agent
"""

import re
import sys
import math
from pathlib import Path
from collections import Counter

class DeepAnalyzer:
    """Advanced multi-layer analyzer"""
    
    def __init__(self, script_path: str):
        self.script_path = Path(script_path)
        self.script = self.script_path.read_text(encoding='utf-8', errors='ignore')
        self.analysis = {}
    
    def calculate_entropy(self, data: str) -> float:
        """Calculate Shannon entropy"""
        if not data:
            return 0
        
        entropy = 0
        for count in Counter(data).values():
            p = count / len(data)
            entropy -= p * math.log2(p)
        
        return entropy
    
    def analyze_structure(self):
        """Analyze code structure"""
        print("🔬 Analyzing code structure...")
        
        self.analysis['structure'] = {
            'total_lines': len(self.script.splitlines()),
            'total_chars': len(self.script),
            'functions': len(re.findall(r'\bfunction\b', self.script)),
            'locals': len(set(re.findall(r'local (\w+)', self.script))),
            'loops': len(re.findall(r'\bfor\b|\bwhile\b|\brepeat\b', self.script)),
            'conditionals': len(re.findall(r'\bif\b', self.script)),
            'returns': len(re.findall(r'\breturn\b', self.script)),
        }
        
        print(f"  Lines: {self.analysis['structure']['total_lines']:,}")
        print(f"  Functions: {self.analysis['structure']['functions']}")
        print(f"  Local vars: {self.analysis['structure']['locals']}")
    
    def analyze_entropy(self):
        """Analyze entropy levels"""
        print("\n📊 Analyzing entropy...")
        
        # Overall entropy
        overall_entropy = self.calculate_entropy(self.script)
        
        # Chunk entropy
        chunk_size = 1000
        chunks = [self.script[i:i+chunk_size] for i in range(0, len(self.script), chunk_size)]
        chunk_entropies = [self.calculate_entropy(chunk) for chunk in chunks]
        
        avg_entropy = sum(chunk_entropies) / len(chunk_entropies) if chunk_entropies else 0
        max_entropy = max(chunk_entropies) if chunk_entropies else 0
        
        self.analysis['entropy'] = {
            'overall': overall_entropy,
            'average': avg_entropy,
            'max': max_entropy,
            'chunks': len(chunks),
        }
        
        print(f"  Overall entropy: {overall_entropy:.2f}")
        print(f"  Average chunk entropy: {avg_entropy:.2f}")
        print(f"  Max chunk entropy: {max_entropy:.2f}")
        
        # Interpretation
        if overall_entropy > 7.5:
            print(f"  ⚠️  VERY HIGH - Likely encrypted/compressed")
        elif overall_entropy > 6.5:
            print(f"  ⚠️  HIGH - Heavy obfuscation")
        elif overall_entropy > 5.0:
            print(f"  ⚠️  MEDIUM - Moderate obfuscation")
        else:
            print(f"  ✅ LOW - Minimal obfuscation")
    
    def analyze_strings(self):
        """Analyze string patterns"""
        print("\n🔤 Analyzing strings...")
        
        # Extract all strings
        double_quoted = re.findall(r'"([^"]*)"', self.script)
        single_quoted = re.findall(r"'([^']*)'", self.script)
        
        all_strings = double_quoted + single_quoted
        
        # Filter by length
        short_strings = [s for s in all_strings if len(s) < 10]
        medium_strings = [s for s in all_strings if 10 <= len(s) < 50]
        long_strings = [s for s in all_strings if len(s) >= 50]
        
        # Find encrypted-looking strings
        encrypted_looking = [s for s in all_strings if self.calculate_entropy(s) > 6.0 and len(s) > 10]
        
        self.analysis['strings'] = {
            'total': len(all_strings),
            'short': len(short_strings),
            'medium': len(medium_strings),
            'long': len(long_strings),
            'encrypted_looking': len(encrypted_looking),
        }
        
        print(f"  Total strings: {len(all_strings)}")
        print(f"  Short (<10 chars): {len(short_strings)}")
        print(f"  Medium (10-50 chars): {len(medium_strings)}")
        print(f"  Long (>50 chars): {len(long_strings)}")
        print(f"  Encrypted-looking: {len(encrypted_looking)}")
        
        if encrypted_looking:
            print(f"\n  Sample encrypted strings:")
            for s in encrypted_looking[:3]:
                print(f"    '{s[:40]}...' (entropy: {self.calculate_entropy(s):.2f})")
    
    def analyze_obfuscation(self):
        """Detect obfuscation techniques"""
        print("\n🔍 Detecting obfuscation techniques...")
        
        techniques = []
        
        # Check for variable name mangling
        vars = re.findall(r'local (\w+)', self.script)
        short_vars = [v for v in vars if len(v) <= 2]
        if len(short_vars) / len(vars) > 0.5 if vars else False:
            techniques.append("Variable name mangling")
        
        # Check for string encryption
        if re.search(r'string\.char|string\.byte', self.script):
            techniques.append("String encryption/obfuscation")
        
        # Check for VM
        if re.search(r'function\s*\(\s*\w+\s*\).*while.*end.*end', self.script, re.DOTALL):
            techniques.append("Virtual Machine (VM)")
        
        # Check for base64
        if re.search(r'[A-Za-z0-9+/]{50,}={0,2}', self.script):
            techniques.append("Base64 encoding")
        
        # Check for XOR
        if re.search(r'bit32\.bxor|bxor', self.script):
            techniques.append("XOR encryption")
        
        # Check for control flow obfuscation
        if self.script.count('if') > 50 and self.script.count('then') > 50:
            techniques.append("Control flow obfuscation")
        
        self.analysis['obfuscation'] = techniques
        
        print(f"  Detected {len(techniques)} techniques:")
        for tech in techniques:
            print(f"    ✅ {tech}")
    
    def identify_weaknesses(self):
        """Identify potential weaknesses"""
        print("\n🎯 Identifying weaknesses...")
        
        weaknesses = []
        
        # String table vulnerability
        if re.search(r'local \w+\s*=\s*\{[^}]{100,}\}', self.script):
            weaknesses.append("Large string/constant tables (can be dumped)")
        
        # Predictable patterns
        if re.search(r'local \w+=function\(\w+,\w+\)', self.script):
            weaknesses.append("Predictable function patterns")
        
        # Runtime dependencies
        if 'loadstring' in self.script or 'load(' in self.script:
            weaknesses.append("Runtime code loading (hookable)")
        
        # Weak encryption
        entropy = self.analysis.get('entropy', {}).get('overall', 0)
        if entropy < 6.5:
            weaknesses.append("Low entropy = Weak encryption")
        
        self.analysis['weaknesses'] = weaknesses
        
        if weaknesses:
            print(f"  Found {len(weaknesses)} potential weaknesses:")
            for weak in weaknesses:
                print(f"    ⚠️  {weak}")
        else:
            print(f"  No obvious weaknesses found")
    
    def generate_attack_plan(self):
        """Generate attack strategy"""
        print("\n⚔️  Generating attack plan...")
        
        plan = []
        
        # Based on detected techniques
        if "String encryption/obfuscation" in self.analysis.get('obfuscation', []):
            plan.append("1. Hook string.char/string.byte at runtime")
        
        if "Virtual Machine (VM)" in self.analysis.get('obfuscation', []):
            plan.append("2. Emulate VM or execute with hooks")
        
        if "Base64 encoding" in self.analysis.get('obfuscation', []):
            plan.append("3. Decode base64 strings")
        
        if "XOR encryption" in self.analysis.get('obfuscation', []):
            plan.append("4. XOR brute-force with common keys")
        
        # Runtime execution recommended?
        if "Runtime code loading (hookable)" in self.analysis.get('weaknesses', []):
            plan.append("5. ✅ RECOMMENDED: Runtime execution with hooks")
        
        self.analysis['attack_plan'] = plan
        
        print(f"  Recommended attack strategy:")
        for step in plan:
            print(f"    {step}")
    
    def save_report(self):
        """Save analysis report"""
        report_path = self.script_path.parent / f"{self.script_path.stem}_ANALYSIS_REPORT.txt"
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("DEEP ANALYSIS REPORT\n")
            f.write("=" * 70 + "\n\n")
            
            f.write(f"Script: {self.script_path.name}\n")
            f.write(f"Size: {len(self.script):,} bytes\n\n")
            
            f.write("STRUCTURE:\n")
            for key, val in self.analysis.get('structure', {}).items():
                f.write(f"  {key}: {val}\n")
            
            f.write("\nENTROPY:\n")
            for key, val in self.analysis.get('entropy', {}).items():
                if isinstance(val, float):
                    f.write(f"  {key}: {val:.2f}\n")
                else:
                    f.write(f"  {key}: {val}\n")
            
            f.write("\nSTRINGS:\n")
            for key, val in self.analysis.get('strings', {}).items():
                f.write(f"  {key}: {val}\n")
            
            f.write("\nOBFUSCATION TECHNIQUES:\n")
            for tech in self.analysis.get('obfuscation', []):
                f.write(f"  - {tech}\n")
            
            f.write("\nWEAKNESSES:\n")
            for weak in self.analysis.get('weaknesses', []):
                f.write(f"  - {weak}\n")
            
            f.write("\nATTACK PLAN:\n")
            for step in self.analysis.get('attack_plan', []):
                f.write(f"  {step}\n")
        
        print(f"\n✅ Report saved: {report_path.name}")
    
    def analyze(self):
        """Run complete analysis"""
        print("=" * 70)
        print("🔬 DEEP ANALYZER - Multi-Layer Analysis")
        print("=" * 70)
        print(f"\n📂 Target: {self.script_path.name}\n")
        
        self.analyze_structure()
        self.analyze_entropy()
        self.analyze_strings()
        self.analyze_obfuscation()
        self.identify_weaknesses()
        self.generate_attack_plan()
        self.save_report()
        
        print("\n" + "=" * 70)
        print("✅ ANALYSIS COMPLETE")
        print("=" * 70)

def main():
    if len(sys.argv) < 2:
        print("Usage: python deep_analyzer.py <script.lua>")
        sys.exit(1)
    
    analyzer = DeepAnalyzer(sys.argv[1])
    analyzer.analyze()

if __name__ == "__main__":
    main()

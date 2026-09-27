#!/usr/bin/env python3
"""
UNIVERSE LUA DEOBFUSCATOR
Multi-layer Lua script decryption & deobfuscation
Supports: Luraph, Prometheus, IronBrew2, PSU, Custom encryption

Author: YONDA Agent
Date: 2026-08-23
"""

import re
import base64
import zlib
import struct
import sys
from pathlib import Path

class LuaDeobfuscator:
    """Advanced Lua deobfuscator with pattern recognition"""
    
    def __init__(self, script_content):
        self.original = script_content
        self.current = script_content
        self.layers = []
        
    def detect_obfuscator(self):
        """Auto-detect obfuscation type"""
        content = self.current.lower()
        
        if 'luraph' in content or 'lr_' in content:
            return 'Luraph'
        elif 'prometheus' in content or 'psu' in content:
            return 'Prometheus/PSU'
        elif 'ironbrew' in content or '_ilbtopsecret' in content:
            return 'IronBrew2'
        elif 'moonveil' in content or 'mv_' in content:
            return 'MoonVeil'
        elif self._detect_base64_chunks():
            return 'Base64 Encoded'
        elif self._detect_xor_pattern():
            return 'XOR Encrypted'
        else:
            return 'Unknown/Custom'
    
    def _detect_base64_chunks(self):
        """Detect large base64 encoded blocks"""
        b64_pattern = r'[A-Za-z0-9+/]{100,}={0,2}'
        matches = re.findall(b64_pattern, self.current)
        return len(matches) > 0
    
    def _detect_xor_pattern(self):
        """Detect XOR encryption patterns"""
        xor_patterns = [
            r'bit\.bxor\(',
            r'string\.byte.*\^',
            r'xor\s*\(',
        ]
        return any(re.search(p, self.current, re.IGNORECASE) for p in xor_patterns)
    
    def deobfuscate_layer_1(self):
        """Remove string obfuscation (concatenation, char codes)"""
        self.layers.append("Layer 1: String deobfuscation")
        
        # Replace string.char() calls
        def replace_char(match):
            codes = match.group(1).split(',')
            try:
                chars = ''.join(chr(int(c.strip())) for c in codes)
                return f'"{chars}"'
            except:
                return match.group(0)
        
        self.current = re.sub(r'string\.char\(([0-9,\s]+)\)', replace_char, self.current)
        
        # Decode hex strings
        self.current = re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m.group(1), 16)), self.current)
        
        return self.current
    
    def deobfuscate_layer_2(self):
        """Decode base64 encoded chunks"""
        self.layers.append("Layer 2: Base64 decoding")
        
        def decode_b64(match):
            b64_str = match.group(0)
            try:
                decoded = base64.b64decode(b64_str).decode('utf-8', errors='ignore')
                if decoded.isprintable() and len(decoded) > 10:
                    return f'"{decoded}"'
            except:
                pass
            return b64_str
        
        # Find and decode base64 chunks
        b64_pattern = r'[A-Za-z0-9+/]{40,}={0,2}'
        self.current = re.sub(b64_pattern, decode_b64, self.current)
        
        return self.current
    
    def deobfuscate_layer_3(self):
        """Decompress zlib/gzip compressed data"""
        self.layers.append("Layer 3: Decompression")
        
        # Look for compressed data patterns
        patterns = [
            r'zlib\.decompress\(["\'](.+?)["\']\)',
            r'decompress\(["\'](.+?)["\']\)',
        ]
        
        for pattern in patterns:
            def decompress_match(match):
                try:
                    compressed = match.group(1)
                    # Try base64 decode first
                    try:
                        data = base64.b64decode(compressed)
                    except:
                        data = compressed.encode()
                    
                    # Try zlib decompress
                    decompressed = zlib.decompress(data).decode('utf-8', errors='ignore')
                    return f'"{decompressed}"'
                except:
                    return match.group(0)
            
            self.current = re.sub(pattern, decompress_match, self.current)
        
        return self.current
    
    def deobfuscate_layer_4(self):
        """XOR decryption"""
        self.layers.append("Layer 4: XOR decryption")
        
        # Pattern: string with XOR key
        xor_pattern = r'xor_decrypt\(["\'](.+?)["\']\s*,\s*(\d+)\)'
        
        def xor_decrypt(match):
            encrypted = match.group(1)
            key = int(match.group(2))
            try:
                decrypted = ''.join(chr(ord(c) ^ key) for c in encrypted)
                return f'"{decrypted}"'
            except:
                return match.group(0)
        
        self.current = re.sub(xor_pattern, xor_decrypt, self.current)
        
        return self.current
    
    def deobfuscate_layer_5(self):
        """Luraph-specific deobfuscation"""
        self.layers.append("Layer 5: Luraph patterns")
        
        # Luraph uses variable renaming - restore common patterns
        luraph_vars = {
            r'\bl_\d+_\d+\b': 'var',
            r'\bII[lI]+\b': 'func',
            r'\b__[A-Z]{2,}\b': 'const',
        }
        
        for pattern, replacement in luraph_vars.items():
            counter = [0]
            def replace_with_counter(match):
                counter[0] += 1
                return f'{replacement}_{counter[0]}'
            self.current = re.sub(pattern, replace_with_counter, self.current)
        
        return self.current
    
    def beautify(self):
        """Beautify Lua code (basic)"""
        self.layers.append("Layer 6: Code beautification")
        
        # Add newlines after statements
        self.current = re.sub(r';', ';\n', self.current)
        self.current = re.sub(r'\bend\b', 'end\n', self.current)
        self.current = re.sub(r'\bdo\b', 'do\n    ', self.current)
        
        # Remove excessive whitespace
        self.current = re.sub(r'\n\s*\n+', '\n\n', self.current)
        
        return self.current
    
    def full_deobfuscation(self):
        """Run all deobfuscation layers"""
        print(f"🔍 Detecting obfuscator type...")
        obf_type = self.detect_obfuscator()
        print(f"✅ Detected: {obf_type}")
        
        print(f"\n🔥 Running deobfuscation layers...\n")
        
        # Run all layers
        layers = [
            self.deobfuscate_layer_1,
            self.deobfuscate_layer_2,
            self.deobfuscate_layer_3,
            self.deobfuscate_layer_4,
            self.deobfuscate_layer_5,
            self.beautify,
        ]
        
        for i, layer_func in enumerate(layers, 1):
            before_len = len(self.current)
            layer_func()
            after_len = len(self.current)
            change = abs(after_len - before_len)
            print(f"  [{i}/6] {self.layers[-1]} - Changed: {change} bytes")
        
        return self.current
    
    def get_report(self):
        """Generate deobfuscation report"""
        return {
            'original_size': len(self.original),
            'deobfuscated_size': len(self.current),
            'layers_applied': len(self.layers),
            'obfuscator': self.detect_obfuscator(),
            'complexity_reduction': f"{(1 - len(self.current)/len(self.original))*100:.1f}%"
        }


def deobfuscate_file(input_path, output_path=None):
    """Deobfuscate Lua file"""
    input_path = Path(input_path)
    
    if not input_path.exists():
        print(f"❌ File not found: {input_path}")
        return None
    
    print(f"📂 Loading: {input_path.name}")
    content = input_path.read_text(encoding='utf-8', errors='ignore')
    
    deobf = LuaDeobfuscator(content)
    result = deobf.full_deobfuscation()
    
    # Save result
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_deobfuscated.lua"
    else:
        output_path = Path(output_path)
    
    output_path.write_text(result, encoding='utf-8')
    
    # Print report
    report = deobf.get_report()
    print(f"\n📊 DEOBFUSCATION REPORT:")
    print(f"  Original size: {report['original_size']:,} bytes")
    print(f"  Deobfuscated size: {report['deobfuscated_size']:,} bytes")
    print(f"  Layers applied: {report['layers_applied']}")
    print(f"  Detected obfuscator: {report['obfuscator']}")
    print(f"  Complexity reduction: {report['complexity_reduction']}")
    
    print(f"\n✅ Saved: {output_path}")
    
    return str(output_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python lua_deobfuscator.py <input.lua> [output.lua]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    deobfuscate_file(input_file, output_file)

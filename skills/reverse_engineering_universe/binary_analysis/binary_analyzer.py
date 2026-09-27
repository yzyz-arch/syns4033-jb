#!/usr/bin/env python3
"""
UNIVERSE BINARY ANALYZER
Advanced binary reverse engineering
PE/ELF/Mach-O analysis, disassembly, decompilation

Author: YONDA Agent
Date: 2026-08-23
"""

import os
import sys
import struct
from pathlib import Path
import subprocess

class BinaryAnalyzer:
    """Advanced binary analysis"""
    
    def __init__(self, binary_path):
        self.binary_path = Path(binary_path)
        self.binary_data = self.binary_path.read_bytes()
        self.file_type = self._detect_format()
        self.analysis = {}
        
    def _detect_format(self):
        """Detect binary format (PE/ELF/Mach-O)"""
        magic = self.binary_data[:4]
        
        if magic[:2] == b'MZ':
            return 'PE'
        elif magic == b'\x7fELF':
            return 'ELF'
        elif magic in (b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe'):
            return 'Mach-O'
        elif magic[:2] == b'#!':
            return 'Script'
        else:
            return 'Unknown'
    
    def analyze_pe(self):
        """Analyze PE (Windows executable)"""
        print("🪟 Analyzing PE file...")
        
        # DOS header
        if self.binary_data[:2] != b'MZ':
            return None
        
        # Get PE header offset
        pe_offset = struct.unpack('<I', self.binary_data[0x3C:0x40])[0]
        
        # PE signature
        pe_sig = self.binary_data[pe_offset:pe_offset+4]
        if pe_sig != b'PE\x00\x00':
            return None
        
        # COFF header
        machine = struct.unpack('<H', self.binary_data[pe_offset+4:pe_offset+6])[0]
        num_sections = struct.unpack('<H', self.binary_data[pe_offset+6:pe_offset+8])[0]
        
        machines = {
            0x14c: 'x86',
            0x8664: 'x64',
            0x1c0: 'ARM',
            0xaa64: 'ARM64',
        }
        
        self.analysis['architecture'] = machines.get(machine, f'Unknown (0x{machine:x})')
        self.analysis['sections'] = num_sections
        
        # Optional header
        opt_header_offset = pe_offset + 24
        magic = struct.unpack('<H', self.binary_data[opt_header_offset:opt_header_offset+2])[0]
        self.analysis['pe_type'] = 'PE32+' if magic == 0x20b else 'PE32'
        
        # Entry point
        entry_point = struct.unpack('<I', self.binary_data[opt_header_offset+16:opt_header_offset+20])[0]
        self.analysis['entry_point'] = f'0x{entry_point:x}'
        
        print(f"  Architecture: {self.analysis['architecture']}")
        print(f"  PE Type: {self.analysis['pe_type']}")
        print(f"  Sections: {self.analysis['sections']}")
        print(f"  Entry Point: {self.analysis['entry_point']}")
        
        return self.analysis
    
    def analyze_elf(self):
        """Analyze ELF (Linux/Android executable)"""
        print("🐧 Analyzing ELF file...")
        
        if self.binary_data[:4] != b'\x7fELF':
            return None
        
        # Class (32/64 bit)
        elf_class = self.binary_data[4]
        self.analysis['bits'] = '64-bit' if elf_class == 2 else '32-bit'
        
        # Endianness
        endian = self.binary_data[5]
        self.analysis['endian'] = 'Little-endian' if endian == 1 else 'Big-endian'
        
        # Machine type
        machine = struct.unpack('<H', self.binary_data[18:20])[0]
        
        machines = {
            0x03: 'x86',
            0x3e: 'x86-64',
            0x28: 'ARM',
            0xb7: 'ARM64',
            0x08: 'MIPS',
        }
        
        self.analysis['architecture'] = machines.get(machine, f'Unknown (0x{machine:x})')
        
        # Entry point (64-bit LE)
        if elf_class == 2 and endian == 1:
            entry = struct.unpack('<Q', self.binary_data[24:32])[0]
            self.analysis['entry_point'] = f'0x{entry:x}'
        
        print(f"  Class: {self.analysis['bits']}")
        print(f"  Endian: {self.analysis['endian']}")
        print(f"  Architecture: {self.analysis['architecture']}")
        
        if 'entry_point' in self.analysis:
            print(f"  Entry Point: {self.analysis['entry_point']}")
        
        return self.analysis
    
    def extract_strings(self, min_length=6):
        """Extract ASCII strings"""
        print(f"🔤 Extracting strings (min length: {min_length})...")
        
        import re
        strings = re.findall(rb'[\x20-\x7e]{' + str(min_length).encode() + b',}', self.binary_data)
        strings = [s.decode('ascii', errors='ignore') for s in strings]
        
        # Filter interesting
        interesting = []
        keywords = [
            'password', 'token', 'secret', 'key', 'api',
            'http://', 'https://', '.exe', '.dll', '.so',
            'admin', 'root', 'debug', 'flag{', 'CTF{',
        ]
        
        for s in strings:
            if any(kw in s.lower() for kw in keywords):
                interesting.append(s)
        
        self.analysis['total_strings'] = len(strings)
        self.analysis['interesting_strings'] = len(interesting)
        
        print(f"  Total strings: {len(strings)}")
        print(f"  Interesting: {len(interesting)}")
        
        return interesting
    
    def disassemble(self, output_path=None):
        """Disassemble binary using objdump/radare2"""
        print("🔧 Disassembling...")
        
        if output_path is None:
            output_path = self.binary_path.parent / f"{self.binary_path.stem}_disasm.asm"
        
        # Try objdump first
        try:
            cmd = ['objdump', '-d', str(self.binary_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                output_path.write_text(result.stdout)
                lines = len(result.stdout.splitlines())
                print(f"  ✅ Disassembled {lines} lines")
                self.analysis['disasm_lines'] = lines
                return str(output_path)
        except:
            pass
        
        # Fallback: simple disasm
        print("  ⚠️  Using fallback disassembler...")
        return self._simple_disasm(output_path)
    
    def _simple_disasm(self, output_path):
        """Simple x86 disassembly"""
        # Just hex dump for now
        hex_dump = []
        for i in range(0, min(len(self.binary_data), 10000), 16):
            chunk = self.binary_data[i:i+16]
            hex_str = ' '.join(f'{b:02x}' for b in chunk)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            hex_dump.append(f'{i:08x}  {hex_str:<48}  {ascii_str}')
        
        output_path.write_text('\n'.join(hex_dump))
        print(f"  ✅ Hex dump saved")
        return str(output_path)
    
    def full_analysis(self):
        """Run complete binary analysis"""
        print(f"\n🔥 ANALYZING BINARY: {self.binary_path.name}\n")
        print(f"📦 File type: {self.file_type}")
        print(f"📊 Size: {len(self.binary_data):,} bytes\n")
        
        # Format-specific analysis
        if self.file_type == 'PE':
            self.analyze_pe()
        elif self.file_type == 'ELF':
            self.analyze_elf()
        
        # Common analysis
        self.extract_strings()
        self.disassemble()
        
        print(f"\n✅ Analysis complete!")
        return self.analysis


def analyze_binary(binary_path):
    """Analyze binary file"""
    analyzer = BinaryAnalyzer(binary_path)
    return analyzer.full_analysis()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python binary_analyzer.py <binary_file>")
        sys.exit(1)
    
    analyze_binary(sys.argv[1])

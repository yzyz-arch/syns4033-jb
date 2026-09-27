#!/usr/bin/env python3
"""
GOKIL Encrypted APK Analyzer - 2026
Automatic decryption, unpacking, and analysis
"""

import os
import sys
import subprocess
import json
from pathlib import Path

class EncryptedAPKAnalyzer:
    def __init__(self, apk_path, output_dir):
        self.apk_path = Path(apk_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.tools = {
            'apktool': '/f/apk_modding_system/decompile/apktool.jar',
            'jadx': '/f/apk_modding_system/decompile/jadx/bin/jadx.bat',
            'ghidra': '/f/reverse_engineering_toolkit/ghidra/ghidraRun',
            'frida': 'frida'
        }
        
        self.report = {
            'apk': str(self.apk_path),
            'encryption': {},
            'obfuscation': {},
            'native_libs': [],
            'strings': [],
            'classes': [],
            'vulnerabilities': []
        }
    
    def detect_encryption(self):
        """Detect APK encryption type"""
        print("[1/10] Detecting encryption...")
        
        # Check for common encryption/packing
        encryption_signatures = {
            'Bangcle': b'libsecexe.so',
            'Qihoo360': b'libjiagu.so',
            'Tencent': b'libtup.so',
            'Baidu': b'libbaiduprotect.so',
            'AliProtect': b'libsgmain.so',
            'SecShell': b'libDexHelper.so',
            'Ijiami': b'libexec.so',
            'APKProtect': b'libAPKProtect.so'
        }
        
        # Extract lib/ folder
        extract_cmd = f'unzip -l "{self.apk_path}" "lib/*" 2>/dev/null'
        result = subprocess.run(extract_cmd, shell=True, capture_output=True, text=True)
        
        for name, signature in encryption_signatures.items():
            if signature.decode() in result.stdout:
                self.report['encryption']['type'] = name
                self.report['encryption']['detected'] = True
                print(f"  ✓ Detected: {name} encryption")
                return name
        
        self.report['encryption']['detected'] = False
        print("  ✓ No encryption detected (or unknown type)")
        return None
    
    def unpack_apk(self):
        """Unpack APK with APKTool"""
        print("[2/10] Unpacking APK...")
        
        unpack_dir = self.output_dir / 'unpacked'
        cmd = f'java -jar {self.tools["apktool"]} d "{self.apk_path}" -o "{unpack_dir}" -f'
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"  ✓ Unpacked to {unpack_dir}")
            return unpack_dir
        else:
            print(f"  ✗ Unpacking failed: {result.stderr}")
            return None
    
    def decompile_java(self):
        """Decompile DEX to Java with jadx"""
        print("[3/10] Decompiling to Java...")
        
        java_dir = self.output_dir / 'java_source'
        cmd = f'{self.tools["jadx"]} -d "{java_dir}" "{self.apk_path}"'
        
        subprocess.run(cmd, shell=True, capture_output=True)
        
        if java_dir.exists():
            print(f"  ✓ Decompiled to {java_dir}")
            return java_dir
        else:
            print("  ✗ Decompilation failed")
            return None
    
    def analyze_native_libs(self):
        """Analyze native .so libraries with Ghidra"""
        print("[4/10] Analyzing native libraries...")
        
        unpack_dir = self.output_dir / 'unpacked'
        lib_dir = unpack_dir / 'lib'
        
        if not lib_dir.exists():
            print("  - No native libraries found")
            return
        
        # Find all .so files
        so_files = list(lib_dir.rglob('*.so'))
        
        for so_file in so_files:
            print(f"  → Analyzing {so_file.name}")
            
            # Use readelf for quick analysis
            cmd = f'readelf -s "{so_file}" 2>/dev/null | grep FUNC | head -50'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            functions = []
            for line in result.stdout.split('\n'):
                if 'FUNC' in line:
                    parts = line.split()
                    if len(parts) >= 8:
                        functions.append(parts[7])
            
            self.report['native_libs'].append({
                'file': so_file.name,
                'arch': so_file.parent.name,
                'functions': functions[:20]  # Top 20 functions
            })
        
        print(f"  ✓ Analyzed {len(so_files)} native libraries")
    
    def extract_strings(self):
        """Extract interesting strings"""
        print("[5/10] Extracting strings...")
        
        # Extract from DEX
        cmd = f'unzip -p "{self.apk_path}" "classes*.dex" | strings | grep -E "(http|api|key|password|secret)" | head -100'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        interesting_strings = result.stdout.split('\n')[:50]
        self.report['strings'] = [s for s in interesting_strings if s.strip()]
        
        print(f"  ✓ Extracted {len(self.report['strings'])} interesting strings")
    
    def detect_obfuscation(self):
        """Detect code obfuscation"""
        print("[6/10] Detecting obfuscation...")
        
        java_dir = self.output_dir / 'java_source'
        
        if not java_dir.exists():
            print("  - Skipped (no Java source)")
            return
        
        # Check for ProGuard/R8 obfuscation
        sample_files = list(java_dir.rglob('*.java'))[:100]
        
        obfuscated_count = 0
        for java_file in sample_files:
            content = java_file.read_text(errors='ignore')
            # Check for single-letter class names (ProGuard signature)
            if any(f'class {c} {{' in content for c in 'abcdefgh'):
                obfuscated_count += 1
        
        obfuscation_ratio = obfuscated_count / len(sample_files) if sample_files else 0
        
        self.report['obfuscation'] = {
            'detected': obfuscation_ratio > 0.3,
            'ratio': obfuscation_ratio,
            'type': 'ProGuard/R8' if obfuscation_ratio > 0.3 else 'None'
        }
        
        print(f"  ✓ Obfuscation: {self.report['obfuscation']['type']}")
    
    def find_entry_points(self):
        """Find application entry points"""
        print("[7/10] Finding entry points...")
        
        unpack_dir = self.output_dir / 'unpacked'
        manifest = unpack_dir / 'AndroidManifest.xml'
        
        if not manifest.exists():
            print("  - Manifest not found")
            return
        
        # Parse manifest for activities, services, receivers
        cmd = f'grep -E "(activity|service|receiver)" "{manifest}" | head -20'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        self.report['classes'] = result.stdout.split('\n')[:20]
        
        print(f"  ✓ Found {len(self.report['classes'])} entry points")
    
    def check_vulnerabilities(self):
        """Check for common vulnerabilities"""
        print("[8/10] Checking vulnerabilities...")
        
        vulns = []
        
        # Check for debuggable flag
        manifest = self.output_dir / 'unpacked' / 'AndroidManifest.xml'
        if manifest.exists():
            content = manifest.read_text(errors='ignore')
            if 'android:debuggable="true"' in content:
                vulns.append('Debuggable flag enabled')
        
        # Check for backup allowed
        if manifest.exists():
            content = manifest.read_text(errors='ignore')
            if 'android:allowBackup="true"' in content:
                vulns.append('Backup allowed (data exfiltration risk)')
        
        # Check for exported components
        if manifest.exists():
            content = manifest.read_text(errors='ignore')
            exported_count = content.count('android:exported="true"')
            if exported_count > 5:
                vulns.append(f'{exported_count} exported components (attack surface)')
        
        self.report['vulnerabilities'] = vulns
        
        print(f"  ✓ Found {len(vulns)} potential vulnerabilities")
    
    def generate_frida_scripts(self):
        """Generate Frida hooking scripts"""
        print("[9/10] Generating Frida scripts...")
        
        frida_dir = self.output_dir / 'frida_scripts'
        frida_dir.mkdir(exist_ok=True)
        
        # Generate hook template
        hook_template = """
// Frida hook script for {apk_name}
// Generated by GOKIL Analyzer

Java.perform(function() {{
    console.log("[*] Hooking {apk_name}");
    
    // Hook main activity
    var MainActivity = Java.use('com.example.MainActivity');
    MainActivity.onCreate.implementation = function(bundle) {{
        console.log("[+] MainActivity.onCreate called");
        this.onCreate(bundle);
    }};
    
    // Hook encryption functions
    var Cipher = Java.use('javax.crypto.Cipher');
    Cipher.doFinal.overload('[B').implementation = function(input) {{
        console.log("[+] Cipher.doFinal called");
        console.log("    Input: " + input);
        var result = this.doFinal(input);
        console.log("    Output: " + result);
        return result;
    }};
    
    // Hook network calls
    var URL = Java.use('java.net.URL');
    URL.$init.overload('java.lang.String').implementation = function(url) {{
        console.log("[+] URL: " + url);
        return this.$init(url);
    }};
}});
"""
        
        hook_file = frida_dir / 'hooks.js'
        hook_file.write_text(hook_template.format(apk_name=self.apk_path.name))
        
        print(f"  ✓ Generated Frida scripts in {frida_dir}")
    
    def save_report(self):
        """Save analysis report"""
        print("[10/10] Saving report...")
        
        report_file = self.output_dir / 'analysis_report.json'
        with open(report_file, 'w') as f:
            json.dump(self.report, f, indent=2)
        
        print(f"\n✅ Analysis complete!")
        print(f"📊 Report: {report_file}")
        print(f"📁 Output: {self.output_dir}")
    
    def analyze(self):
        """Run complete analysis"""
        print(f"\n{'='*60}")
        print(f"GOKIL ENCRYPTED APK ANALYZER")
        print(f"{'='*60}\n")
        
        self.detect_encryption()
        self.unpack_apk()
        self.decompile_java()
        self.analyze_native_libs()
        self.extract_strings()
        self.detect_obfuscation()
        self.find_entry_points()
        self.check_vulnerabilities()
        self.generate_frida_scripts()
        self.save_report()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python encrypted_apk_analyzer.py <apk_file> [output_dir]")
        sys.exit(1)
    
    apk_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else './analysis_output'
    
    analyzer = EncryptedAPKAnalyzer(apk_path, output_dir)
    analyzer.analyze()

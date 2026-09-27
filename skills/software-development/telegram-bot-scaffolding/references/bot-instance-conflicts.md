# Bot Instance Conflict Resolution

## Problem

`telegram.error.Conflict: terminated by other getUpdates request; make sure that only one bot instance is running`

## Root Cause

Multiple instances of the same bot token running simultaneously. Telegram allows only **ONE active connection** per token at a time (either long-polling with `getUpdates` OR webhook, never both).

## Common Scenarios

1. **Bot running on multiple servers** (VPS + local dev machine)
2. **Website deployment + manual start** (PaaS + SSH session)
3. **Webhook still active** while trying to use polling mode
4. **Zombie processes** from previous run didn't die on restart
5. **systemd/PM2 auto-restart** while manual instance running

## Diagnostic Steps

### 1. Check Webhook Status

```bash
# Check if webhook is registered
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Response if webhook active:
{
  "ok": true,
  "result": {
    "url": "https://example.com/webhook",
    "has_custom_certificate": false,
    "pending_update_count": 0
  }
}

# Response if polling mode (url is empty):
{
  "ok": true,
  "result": {
    "url": "",  # ← Empty means polling mode
    "pending_update_count": 0
  }
}
```

### 2. Find Running Processes

```bash
# Linux/macOS
ps aux | grep bot.py
ps aux | grep python | grep <bot_name>

# Check systemd services
systemctl status bot-name
systemctl list-units | grep bot

# Check PM2 processes
pm2 list
pm2 show <app-name>

# Windows
tasklist | findstr python
tasklist | findstr bot
```

### 3. Check Multiple Deployment Locations

- Local dev machine
- VPS/cloud server
- PaaS platform (Heroku, Railway, Render)
- Docker containers
- GitHub Actions / CI runners
- Old tmux/screen sessions

## Resolution Strategies

### Strategy 1: Force Polling Mode (Delete Webhook)

```python
import requests

BOT_TOKEN = "your_token_here"

# Delete webhook and drop pending updates
response = requests.get(
    f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
    params={"drop_pending_updates": True}
)

print(response.json())
# {'ok': True, 'result': True, 'description': 'Webhook was deleted'}
```

OR via curl:

```bash
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
```

### Strategy 2: Kill Local Processes

```bash
# Kill by name (careful - kills ALL matching)
pkill -9 -f bot.py
pkill -9 -f yonda_paybot

# Kill by PID (safer)
ps aux | grep bot.py
kill -9 <PID>

# Kill systemd service
sudo systemctl stop bot-name

# Kill PM2 process
pm2 stop <app-name>
pm2 delete <app-name>
```

### Strategy 3: Process Lock File (Prevention)

Add to `main.py` to ensure only one instance runs:

```python
import sys
import fcntl  # Unix only

LOCK_FILE = "/tmp/bot_name.lock"

def acquire_lock():
    """Ensure only one instance runs"""
    try:
        lock_file = open(LOCK_FILE, 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except IOError:
        print("❌ Another instance is already running!")
        print(f"   Check: cat {LOCK_FILE}")
        sys.exit(1)

if __name__ == "__main__":
    lock = acquire_lock()
    print("🔒 Lock acquired - bot starting...")
    
    # Bot code here
    application.run_polling()
    
    # Lock released automatically on exit
```

**Windows alternative** (no fcntl):

```python
import sys
import os

LOCK_FILE = "bot.lock"

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        print("❌ Another instance is already running!")
        print(f"   Delete {LOCK_FILE} if this is incorrect")
        sys.exit(1)
    
    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    
    import atexit
    atexit.register(lambda: os.remove(LOCK_FILE) if os.path.exists(LOCK_FILE) else None)
```

### Strategy 4: Environment-Based Tokens (Prevention)

Use different tokens per environment to avoid conflicts:

```python
import os

ENV = os.getenv("BOT_ENV", "production")  # dev / staging / production

TOKENS = {
    "dev": "123456:DEV_TOKEN",
    "staging": "123456:STAGING_TOKEN", 
    "production": "123456:PROD_TOKEN"
}

BOT_TOKEN = TOKENS[ENV]
```

Run with:
```bash
# Local dev
BOT_ENV=dev python bot.py

# Production
BOT_ENV=production python bot.py
```

## Deployment Best Practices

### systemd Service (Linux)

`/etc/systemd/system/telegram-bot.service`:

```ini
[Unit]
Description=Telegram Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/path/to/bot
ExecStart=/path/to/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

# Ensure only one instance
ExecStartPre=/bin/sh -c 'systemctl is-active --quiet telegram-bot && exit 1 || exit 0'

[Install]
WantedBy=multi-user.target
```

### PM2 (Node.js process manager for Python)

`ecosystem.config.js`:

```javascript
module.exports = {
  apps: [{
    name: "telegram-bot",
    script: "bot.py",
    interpreter: "/path/to/venv/bin/python",
    instances: 1,  // Force single instance
    autorestart: true,
    max_restarts: 10,
    min_uptime: "10s"
  }]
}
```

### Docker Compose

```yaml
version: '3.8'
services:
  bot:
    image: telegram-bot
    restart: unless-stopped
    deploy:
      replicas: 1  # Single instance only
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
```

## Documentation

Add to README.md:

```markdown
## Deployment Status

**Current Active Instance:**
- Location: VPS at 192.168.1.100
- User: botuser
- Process: systemd service `telegram-bot.service`
- Logs: `journalctl -u telegram-bot -f`

**To restart:**
```bash
ssh botuser@192.168.1.100
sudo systemctl restart telegram-bot
```

**⚠️ DO NOT start bot elsewhere without stopping this instance first!**
```

## Quick Troubleshooting

```bash
# 1. Stop all instances
pkill -9 -f bot.py
sudo systemctl stop telegram-bot
pm2 stop all

# 2. Clear webhook
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"

# 3. Verify nothing running
ps aux | grep bot.py
# (should return empty)

# 4. Start fresh
python bot.py
```

## Error Messages Guide

| Error Message | Meaning | Solution |
|---------------|---------|----------|
| `terminated by other getUpdates request` | Another polling instance active | Kill other process |
| `Conflict: can't use getUpdates method while webhook is active` | Webhook registered | Delete webhook |
| `terminated by other long poll or webhook` | Generic conflict | Check both webhook + processes |

## Related Issues

- If webhook was set by old deployment, it persists until explicitly deleted
- PaaS platforms (Heroku/Railway) auto-restart may conflict with manual runs
- Docker auto-restart on crash can create race conditions
- tmux/screen sessions survive SSH disconnects - check those

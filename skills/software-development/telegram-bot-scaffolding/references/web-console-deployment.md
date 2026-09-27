# Web Console Deployment for PaaS Platforms

## Context

When deploying Telegram bots to managed PaaS platforms (SumoPod, Railway, Render, etc.) that provide only web-based file managers and terminal consoles (no SSH/SCP access), the deployment workflow differs significantly from traditional VPS.

**User preference signal from session:** User needed deployment via web console upload + copy-paste script execution. Rejected SSH-based approaches with: "Gaada karna itu gw jalanin botnya di web consolenya. Lu bikin script nya gw uploud ke web consoulenya"

## Problem

- No SSH access for `scp` file uploads
- No systemd for service management
- User wants **single consolidated script** to copy-paste, not step-by-step guides
- Files must be uploaded via GUI file manager
- Bot must start via web console commands

## Solution Pattern

### Step 1: Upload Core Files via File Manager

User uploads via browser GUI:
- `bot.py`
- `utils.py` 
- `api_client.py`
- (optional) `requirements.txt`

### Step 2: Run Single Deployment Script

Provide ONE script that does everything:
1. Stops old bot process
2. Checks uploaded files exist
3. Creates `requirements.txt` if missing
4. Installs dependencies
5. Creates `config.env` from template (with tokens)
6. Starts bot in background with `nohup`
7. Verifies bot is running
8. Shows success message with next steps

## Script Template

```bash
#!/bin/bash

##############################################################################
# BOT NAME - ONE-CLICK DEPLOYMENT
# Copy-paste this entire script into Web Console and run!
##############################################################################

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   BOT NAME - AUTO DEPLOYMENT                             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Step 1: Stop old bot
echo "[1/7] Stopping old bot..."
pkill -f bot.py 2>/dev/null
sleep 2
echo "✅ Old bot stopped"

# Step 2: Check if files exist
echo ""
echo "[2/7] Checking files..."
if [ ! -f "bot.py" ] || [ ! -f "utils.py" ] || [ ! -f "api_client.py" ]; then
    echo "❌ Bot files not found!"
    echo ""
    echo "PLEASE UPLOAD THESE FILES VIA FILE MANAGER FIRST:"
    echo "  - bot.py"
    echo "  - utils.py"
    echo "  - api_client.py"
    echo ""
    echo "After upload, run this script again!"
    exit 1
fi
echo "✅ Files found"

# Step 3: Create requirements.txt if missing
echo ""
echo "[3/7] Creating requirements.txt..."
cat > requirements.txt << 'EOFR'
python-telegram-bot==20.7
requests==2.31.0
EOFR
echo "✅ Requirements created"

# Step 4: Install dependencies
echo ""
echo "[4/7] Installing dependencies (1-2 minutes)..."
pip3 install -q python-telegram-bot==20.7 requests==2.31.0
echo "✅ Dependencies installed"

# Step 5: Create config with tokens embedded
echo ""
echo "[5/7] Creating configuration..."
cat > config.env << 'EOFC'
TELEGRAM_BOT_TOKEN=your_bot_token_here
OTP_API_KEY=your_api_key_here
OTP_API_URL=https://api.example.com
EOFC
echo "✅ Config created"

# Step 6: Start bot in background
echo ""
echo "[6/7] Starting bot..."
nohup python3 bot.py > bot.log 2>&1 &
sleep 3

# Step 7: Verify running
echo ""
echo "[7/7] Verifying bot..."
if ps aux | grep -v grep | grep "bot.py" > /dev/null; then
    echo "✅ Bot is running!"
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  ✅ DEPLOYMENT SUCCESSFUL!"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "Next steps:"
    echo "  1. Open Telegram"
    echo "  2. Search your bot"
    echo "  3. Send: /start"
    echo ""
    echo "Manage bot:"
    echo "  View logs:    tail -f bot.log"
    echo "  Stop bot:     pkill -f bot.py"
    echo "  Restart bot:  bash deploy.sh"
    echo ""
else
    echo "❌ Bot failed to start!"
    echo ""
    echo "Check logs:"
    tail -20 bot.log
fi
```

## Key Implementation Details

### Background Process Management

Use `nohup` instead of systemd:
```bash
nohup python3 bot.py > bot.log 2>&1 &
```

**Why:**
- PaaS platforms don't have systemd
- `nohup` keeps process running after console closes
- `&` runs in background
- Redirects output to `bot.log` for debugging

### Config File Generation

Embed tokens directly in script using heredoc:
```bash
cat > config.env << 'EOFC'
TELEGRAM_BOT_TOKEN=8281404757:AAG...
OTP_API_KEY=80b3b240...
EOFC
```

**Why:**
- Avoids manual file editing
- User just runs script, no configuration steps
- Single source of truth

### Error Handling Pattern

Check file existence before proceeding:
```bash
if [ ! -f "bot.py" ]; then
    echo "❌ Files missing!"
    echo "Upload via File Manager first!"
    exit 1
fi
```

**Why:**
- Fail fast with clear instructions
- User knows exactly what's wrong
- Script can be re-run after fixing

### Visual Progress Indicators

```bash
echo "[3/7] Installing dependencies..."
echo "✅ Dependencies installed"
```

**Why:**
- User sees progress in real-time
- Know which step is slow (dependencies install)
- Clear success/failure markers

## Verification Commands

After deployment, provide these for user:

```bash
# Check if bot running
ps aux | grep bot.py

# View real-time logs
tail -f bot.log

# View last 50 lines
tail -50 bot.log

# Restart bot
pkill -f bot.py && sleep 2 && nohup python3 bot.py > bot.log 2>&1 &
```

## Platform-Specific Notes

### SumoPod
- Default directory: `/app` or `~`
- Web Console: Bash shell
- File Manager: Upload one file at a time
- Environment variables: Can be set in dashboard (use those instead of config.env if available)

### Railway / Render
- Git-based deployment preferred
- Web console available as fallback
- May have persistent storage limitations

### Heroku-style Platforms
- Use `Procfile` instead of script:
  ```
  worker: python3 bot.py
  ```

## Common Issues

### Bot Stops After Console Closes

**Problem:** Process dies when closing web console tab.

**Solution:** Ensure using `nohup` and `&`:
```bash
nohup python3 bot.py > bot.log 2>&1 &
```

### Dependencies Not Installing

**Problem:** `pip3 install` fails or times out.

**Solution:** Install individually:
```bash
pip3 install python-telegram-bot==20.7
pip3 install requests==2.31.0
```

### Database Not Persisting

**Problem:** SQLite database resets on restart.

**Solution:** Check PaaS persistent storage documentation. May need to store in `/data` or `/persistent` directory instead of app root.

### Permission Denied

**Problem:** Script can't create files or start processes.

**Solution:** 
- Check file permissions: `chmod +x deploy.sh`
- May need to run in user home directory
- Some PaaS platforms restrict background processes

## User Workflow Summary

1. **Login to PaaS dashboard**
2. **Click "File Manager"**
3. **Upload 3-4 core Python files**
4. **Click "Web Console"**
5. **Copy-paste entire deployment script**
6. **Press Enter**
7. **Wait 2-3 minutes**
8. **Test bot in Telegram**

**Total time:** 5-10 minutes (mostly upload + dependency install)

## Session Takeaway

When user has only web console access (no SSH), provide:
- ✅ Single consolidated script (not multi-step guide)
- ✅ Embedded configuration (no manual editing)
- ✅ Clear file upload instructions upfront
- ✅ Visual progress indicators
- ✅ Self-contained verification

**Don't provide:**
- ❌ SCP/SSH commands (user doesn't have access)
- ❌ Systemd service files (PaaS doesn't support)
- ❌ Multi-file deployment (consolidate into one script)
- ❌ Step-by-step manual configuration (automate everything)

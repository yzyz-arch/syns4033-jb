# VPS Deployment Critical Bugs & Fixes

## Session Context

Real deployment failure case: Spotify Auto-Pay Telegram bot deployed to Ubuntu VPS from Android/Termux. Bot appeared to deploy successfully but was completely unresponsive to commands.

## Critical Bug: Hardcoded OWNER_ID Mismatch

### Symptom
- Bot runs without errors in logs
- Systemd service shows `active (running)`
- Bot responds to `/start` command in development but **completely silent in production**
- No error messages, no responses, appears completely dead to the user

### Root Cause
**Bot code had hardcoded `OWNER_ID` that didn't match the actual user's Telegram ID.**

```python
# WRONG - hardcoded from different user/session
OWNER_ID = 7402484358

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return  # Silently ignores - NO ERROR MESSAGE
    # ... rest of handler
```

When the actual user (ID: 8924909120) sent `/start`, the auth check failed silently and the handler returned immediately with no response.

### Why This Is Insidious
1. **No error logs** - the bot is "working correctly" by silently rejecting unauthorized users
2. **Systemd shows active** - the process is running fine
3. **No crashes** - nothing to debug in journalctl
4. **User sees nothing** - appears completely broken from their perspective

### Fix Pattern

**Never hardcode OWNER_ID during development.** Always require it as configuration or detect it from the first interaction:

```python
# OPTION 1: Configuration-based (RECOMMENDED)
OWNER_ID = int(os.getenv("OWNER_ID"))  # From .env

# OPTION 2: First-user registration
OWNER_ID = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global OWNER_ID
    user_id = update.effective_user.id
    
    # First user becomes owner
    if OWNER_ID is None:
        OWNER_ID = user_id
        await update.message.reply_text(f"✅ Registered as owner (ID: {user_id})")
        return
    
    # Auth check with HELPFUL error message
    if user_id != OWNER_ID:
        await update.message.reply_text(
            f"❌ Unauthorized.\n\n"
            f"Your ID: {user_id}\n"
            f"Owner ID: {OWNER_ID}"
        )
        return
    
    # ... rest of handler
```

**CRITICAL: Auth failures MUST send an error message**, not fail silently. Even in production, tell the user WHY they're being rejected.

### Diagnostic Commands

When a "deployed" bot is completely unresponsive, check for auth issues:

```python
# Add logging to EVERY auth check
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    logger.info(f"start command from user {user_id} (expected owner: {OWNER_ID})")
    
    if user_id != OWNER_ID:
        logger.warning(f"Unauthorized access attempt from {user_id}")
        await update.message.reply_text(f"❌ Unauthorized. Your ID: {user_id}")
        return
```

Logs will show:
```
INFO: start command from user 8924909120 (expected owner: 7402484358)
WARNING: Unauthorized access attempt from 8924909120
```

Immediately reveals the mismatch.

### Prevention Checklist

Before deploying a bot with auth:

- [ ] OWNER_ID comes from environment variable, not hardcoded
- [ ] Test with the ACTUAL user's Telegram ID (ask them to `/start` a test bot and report their ID)
- [ ] Auth failures send descriptive error messages with both IDs
- [ ] Log all auth checks at INFO level
- [ ] Document in deployment guide: "Get your Telegram ID from @userinfobot before deploying"

### Related Pattern

This same bug occurs with:
- Admin lists (checking `if user_id in ADMIN_IDS` with wrong IDs)
- Chat restrictions (checking `if chat_id != ALLOWED_CHAT`)
- Feature flags (checking user attributes that were copied from test data)

**Golden rule: Never copy production-affecting constants from one session/user to another without explicit verification.**

## Secondary Issue: Python Dependency Hell on Ubuntu

### Symptom
`pip install python-telegram-bot` fails with:
```
error: externally-managed-environment
× This environment is externally managed
```

### Root Cause
Python 3.11+ on Debian/Ubuntu uses PEP 668 to prevent system-wide pip pollution.

### Fix
```bash
pip3 install --user --break-system-packages python-telegram-bot aiohttp cryptography
```

Or use virtual environments:
```bash
python3 -m venv venv
source venv/bin/activate
pip install python-telegram-bot
```

### Cryptography Build Failures

If `cryptography` package fails to install:
```bash
sudo apt install -y python3-dev build-essential libssl-dev libffi-dev rustc cargo
pip3 install --upgrade pip setuptools wheel
pip3 install --user --break-system-packages cryptography
```

## Deployment Pattern: Test Locally First

**Before deploying to VPS, ALWAYS test the bot script locally with the actual user:**

1. User starts a test bot via @BotFather
2. User sends `/start` and shares their user ID with you
3. Update OWNER_ID in code with that exact ID
4. Test locally: `python3 bot.py`
5. User tests `/start` on the running bot
6. Only after confirming response, deploy to VPS

This catches auth mismatches before wasting time on VPS deployment.

## Troubleshooting Flow for "Dead" Bot

When bot is running but unresponsive:

```bash
# 1. Verify process is actually running
systemctl status bot-service
# Output: active (running) ✓

# 2. Check for crashes/errors
journalctl -u bot-service -n 50
# Output: no errors ✗ (suspicious!)

# 3. Test manually with verbose logging
cd /path/to/bot
python3 bot.py
# Watch for auth check logs

# 4. Have user send /start while watching logs
# If you see "Unauthorized" logs → OWNER_ID mismatch
```

If logs show auth rejections, the bot is "working correctly" but with wrong configuration.

## Related Files
- Main skill: `telegram-bot-scaffolding/SKILL.md` (see Pitfalls section)

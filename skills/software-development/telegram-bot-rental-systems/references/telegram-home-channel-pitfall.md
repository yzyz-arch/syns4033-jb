# TELEGRAM_HOME_CHANNEL Misdirected Delivery Pitfall

**Date discovered**: 2026-08-17  
**Context**: Hermes-based Telegram rental bot system  
**Severity**: CRITICAL — users don't receive their files

## Problem

When `TELEGRAM_HOME_CHANNEL` is set in Hermes `.env`, ALL file/media deliveries go to that channel instead of back to the user who requested them.

## Symptom

User A chats with rental bot → requests file/APK/result → bot processes successfully → **file gets sent to owner (home channel ID) instead of back to User A**.

User reports: "I asked for the file but it didn't come to me."

## Root Cause

`TELEGRAM_HOME_CHANNEL` in Hermes `.env` was designed for **cron job delivery** — it tells Hermes where to send scheduled task output. However, it also overrides **interactive message reply targeting** for media files.

When set:
```bash
TELEGRAM_HOME_CHANNEL=1324806211  # Owner's chat ID
```

All `MEDIA:` file deliveries route to that channel, regardless of who the requesting user was.

## Diagnosis

Check `.env`:
```bash
grep TELEGRAM_HOME_CHANNEL D:/hermes/.env
# or
grep TELEGRAM_HOME_CHANNEL ~/.hermes/.env
```

If it returns an **active** (uncommented) line with a chat ID, that's the cause.

## Fix

### Option 1: Comment it out (recommended for rental bots)

```bash
# Edit .env
# Change:
TELEGRAM_HOME_CHANNEL=1324806211

# To:
# TELEGRAM_HOME_CHANNEL=1324806211
```

### Option 2: Remove the line entirely

Delete the `TELEGRAM_HOME_CHANNEL=...` line from `.env`.

### Option 3: Use Hermes config command

```bash
hermes config unset platforms.telegram.home_channel
```

### Then restart gateway

**Critical**: Config changes require gateway restart:

```bash
hermes gateway restart
```

For multi-profile setups, restart all affected profiles:
```bash
hermes --profile yonda-a2 gateway restart
hermes --profile yonda-a3 gateway restart
hermes gateway restart  # default
```

## After Fix

**Before**:
- User A asks bot for file
- Bot processes
- File → owner channel (TELEGRAM_HOME_CHANNEL)
- User A gets nothing

**After**:
- User A asks bot for file
- Bot processes
- File → User A (correct!)

## When to Keep TELEGRAM_HOME_CHANNEL

**Only keep it set if**:
- You want **cron job output** to go to a specific monitoring channel
- Bot is NOT user-facing (internal tooling only)
- You understand interactive replies will also route there

**For rental/public bots**: **Disable it**. Users expect results back in their own chat.

## Related Configuration

```yaml
# config.yaml — platform-specific home channel
platforms:
  telegram:
    home_channel: null  # or <chat_id>
```

This has the same effect. Check both `.env` AND `config.yaml`.

## Verification

After fix + restart:

1. Message bot as non-owner user: "send me test.txt"
2. Bot creates/sends file
3. **File should arrive in that user's chat**, not owner's

If file still goes to owner, check:
- Gateway actually restarted (check PID changed)
- No `home_channel` in `config.yaml`
- No other `.env` in parent directories

## Prevention

When setting up rental bots, explicitly comment out or omit `TELEGRAM_HOME_CHANNEL` unless you have a specific cron-delivery use case.

Document in setup guide:
```markdown
## .env Configuration

**Important**: Do NOT set `TELEGRAM_HOME_CHANNEL` for rental bots.
It will cause user files to be delivered to the owner instead of back to users.
```

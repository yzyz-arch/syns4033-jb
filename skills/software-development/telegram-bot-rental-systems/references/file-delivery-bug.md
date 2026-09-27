# File Delivery Bug: Files Sent to Wrong User

## Symptom

User A (ID: 6726919171) chats with bot → requests file (e.g. modded APK)
→ Bot sends file to User B (ID: 7402484358 - owner) instead of back to User A.

**Expected**: File goes to User A (the requester)  
**Actual**: File goes to owner (7402484358)

## Root Cause

`TELEGRAM_HOME_CHANNEL` environment variable set to owner's ID redirects **all file/media delivery** to that chat, regardless of who requested it.

```bash
# In .env
TELEGRAM_HOME_CHANNEL=7402484358  # ← This causes the bug
```

When set, Hermes treats this as "home" for file delivery, overriding the natural "reply to current chat" behavior.

## Fix

**Comment out or remove `TELEGRAM_HOME_CHANNEL`:**

```bash
# .env
# TELEGRAM_HOME_CHANNEL=7402484358  # ← Commented out
```

Then restart gateway:
```bash
hermes gateway restart
```

## Verification

After fix:
1. User A requests file
2. Bot generates file
3. Bot sends file **back to User A's chat** ✅

## Why This Happens

`TELEGRAM_HOME_CHANNEL` is intended for **cron job delivery** (where there's no "current chat"). When set globally, it becomes the default target for:
- Cron job outputs
- Scheduled task deliveries
- **File/media outputs** (unintended side effect)

## Correct Configuration

For rental/public bots where **each user should receive their own files**:

```bash
# .env - NO global home channel
TELEGRAM_BOT_TOKEN=...
# TELEGRAM_HOME_CHANNEL=  ← Leave unset or commented
```

For owner's **personal bot** where you want all outputs delivered to you:

```bash
# .env - owner's private bot
TELEGRAM_BOT_TOKEN=...
TELEGRAM_HOME_CHANNEL=7402484358  # ← OK for personal use
```

## Related Config

Check `config.yaml` for platform-level home_channel override:

```bash
hermes config get platforms.telegram.home_channel
# Should return: Config key not set
```

If set, unset it:
```bash
hermes config unset platforms.telegram.home_channel
hermes gateway restart
```

## Impact on Rental Business

**CRITICAL**: If files go to wrong user:
- User A pays for service but receives nothing
- Owner gets spammed with other users' files
- Breaks the entire rental model

This must be caught in pre-launch testing.

## Prevention

**Pre-launch checklist**:
- [ ] Test file delivery with 2+ test users
- [ ] Verify each user receives their own files
- [ ] Confirm owner does NOT receive other users' files
- [ ] Document expected behavior in README

## Session Cache Issue

In some cases, even after fixing .env and restarting gateway, session cache may retain old routing:

**Nuclear fix**:
```bash
hermes gateway stop
rmdir /s /q "D:\hermes\profiles\default\.cache"
hermes gateway start
```

Then test file delivery again.

## Detection

**Symptom**: User reports "I asked for X but didn't receive it"  
**Check**: Owner, did you receive a file you didn't request?  
**Diagnosis**: File delivery routing to wrong user  
**Fix**: Check TELEGRAM_HOME_CHANNEL + restart gateway

## Alternative Hypothesis: Hardcoded Delivery

If fixing TELEGRAM_HOME_CHANNEL doesn't resolve it, possible causes:
1. Custom system prompt with explicit delivery instruction
2. Hermes internal bug (report to Nous Research)
3. Platform-specific behavior (Telegram bot API quirk)

Check gateway logs:
```bash
tail -100 D:/hermes/profiles/default/logs/gateway.log | grep -i "deliver\|send\|file\|media"
```

Look for explicit chat_id routing in delivery logs.

## Status

**Discovered**: 2026-08-17  
**Fixed**: Same session (commented TELEGRAM_HOME_CHANNEL)  
**Verified**: Pending user test after gateway restart

# Bot Restart When Running on Same VPS

## Context

When you (the agent) and the bot are running on the same machine, you have direct process control. Don't ask the user to restart — do it yourself.

## Detection

**You share a VPS when:**
- You can read/write the bot's code files
- You can see the bot's process via `ps aux | grep bot.py`
- Bot database/config files are in paths you can access

**You do NOT share when:**
- Bot is on external hosting (Heroku, Railway, PythonAnywhere)
- Bot is on user's phone/laptop (user runs it locally)
- Bot is behind a web console you don't have shell access to

## Restart Workflow

### 1. Find the Process

```bash
# Find bot process PID
ps aux | grep "bot.py" | grep -v grep | awk '{print $2}'

# Or check running background processes
# (if you started it via terminal(background=true))
```

### 2. Kill Old Instance

```bash
# Graceful kill
kill <PID>

# Force kill if needed (after waiting)
kill -9 <PID>
```

**Note:** `pkill` may not be available on Windows/MSYS — use `kill` with explicit PID.

### 3. Verify Token Before Restart

**CRITICAL:** Check that `BOT_TOKEN` in code is not masked (e.g., `***`). If you edited the file and accidentally redacted the token:

```bash
# Check token format
grep "BOT_TOKEN" /path/to/bot.py

# Should be: BOT_TOKEN = "1234567890:XXXXXXXXXXXXXXXXXXXXXXXXX"
# NOT:       BOT_TOKEN = "***"
```

If masked, restore the real token before restarting (ask user for it if you don't have it).

### 4. Start New Instance

```bash
cd /path/to/bot_directory
python bot.py 2>&1 &

# Or via terminal tool:
terminal(
    command="cd /d/hermes/yonda_paybot && python bot.py 2>&1",
    background=True,
    notify_on_complete=False  # Long-running daemon
)
```

### 5. Verify Startup

```bash
# Check process is running
ps aux | grep bot.py | grep -v grep

# Check logs for "Running" or "Polling" message
# (poll the background process if you started it via terminal tool)
```

## Common Errors

### "Conflict: terminated by other getUpdates request"

**Cause:** Another bot instance is still running (old process didn't die, or running elsewhere).

**Fix:**
1. Kill ALL local instances: `ps aux | grep bot.py` and kill each PID
2. If still happening, bot is running on external server — ask user to stop that instance
3. Can try `deleteWebhook` but usually doesn't help with polling conflicts

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
```

### "InvalidToken: token was rejected"

**Cause:** Token in code is wrong, masked, or formatted incorrectly.

**Fix:**
1. Check token format: `grep BOT_TOKEN bot.py`
2. Restore real token from backup or ask user
3. Ensure no extra quotes, spaces, or escape characters

## User Correction Pattern

**When user says:** "kan kamu satu vps sama @bot_name" or "you're on the same machine" or "you can do it yourself"

**Response:** Acknowledge the correction, find/kill/restart the bot immediately, don't ask permission.

**Example:**
```
User: "kan kamu satu vps sama @yonda_paybot -_- kamu bisa lah atur sendiri di komputer"
Agent: "Ohhh iya betul LO! Gw satu VPS sama bot lo — gw bisa restart sendiri!"
       [immediately kills old process and starts new one]
```

## When NOT to Restart

- User explicitly says "don't restart" or "I'll do it myself"
- Bot is on external hosting you confirmed you don't control
- User is testing in a dev environment and wants manual control

## Verification After Restart

1. Process is running: `ps aux | grep bot.py`
2. No error in initial output (check background process log)
3. Bot responds to `/start` in Telegram within 10 seconds

If verification fails, check logs and fix before telling user "it's working."

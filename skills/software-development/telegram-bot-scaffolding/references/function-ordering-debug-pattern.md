# Python Function Ordering in Telegram Bots

## Problem Pattern

When callback handlers fail with `NameError: name 'handle_owner_ban_menu' is not defined`, the root cause is **function definition order** in Python — functions must be defined before being called.

## Error Signature

```
NameError: name 'handle_owner_ban_menu' is not defined. Did you mean: 'handle_owner_panel'?
```

Appears in callback_handler routing code that calls functions defined later in the same file.

## Root Cause

Python reads files top-to-bottom at import time. If `callback_handler()` at line 191 calls `handle_owner_ban_menu()` defined at line 1010, Python hasn't seen the function yet when executing the callback.

**Why this happens:**
- Callback handlers route to specific functions based on `callback_data`
- Handler functions often defined at the bottom of the file
- Routing code at the top references functions that don't exist yet

## Solution Pattern

**Move all handler functions ABOVE the callback router:**

```python
# WRONG ORDER - causes NameError
async def callback_handler(update, context):
    if data == "owner_ban":
        return await handle_owner_ban_menu(q, user)  # ← Function not defined yet!

# ... 800 lines later ...
async def handle_owner_ban_menu(q, user):  # ← Defined too late
    pass

# RIGHT ORDER - functions defined first
async def handle_owner_ban_menu(q, user):
    pass

async def handle_owner_unban_menu(q, user):
    pass

async def handle_owner_delete_subs_menu(q, user):
    pass

# Now routing works
async def callback_handler(update, context):
    if data == "owner_ban":
        return await handle_owner_ban_menu(q, user)  # ✓ Function exists
```

## Quick Fix Steps

1. **Identify missing functions** from error logs (all NameError traces)
2. **Find definitions** with `grep -n "^async def function_name" file.py`
3. **Move function blocks** to top of file (after imports, before first caller)
4. **Restart bot** to load new code

## Prevention

**File organization pattern:**
```python
# 1. Imports
from telegram import Update
from telegram.ext import ContextTypes

# 2. Config & globals
BOT_TOKEN = "..."
user_states = {}

# 3. ALL handler functions (alphabetical or by feature group)
async def handle_owner_ban_menu(...):
    pass

async def handle_owner_unban_menu(...):
    pass

# ... all other handlers ...

# 4. Routing/dispatcher
async def callback_handler(update, context):
    if data == "owner_ban":
        return await handle_owner_ban_menu(...)
    # ... routes to functions already defined above

# 5. Main entry point
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling()
```

## Related Error: Photo→Text Message Transition

When buttons fail silently with `BadRequest: There is no text in the message to edit`, it's a **different** issue:

**Problem:** Trying to edit a photo message (with caption) as if it's a text message.

**Solution:** Send new message instead of editing:
```python
# WRONG - tries to edit photo as text
await send_with_banner(q.message, text, markup, method="edit")
# ❌ BadRequest: There is no text in the message to edit

# RIGHT - send new message
await q.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
# ✓ Works
```

**When this happens:**
- User clicks button on a message with banner image (photo + caption)
- Handler tries to `edit_text()` on that message
- Telegram rejects: can't convert photo message to text message

**Fix pattern:** For handlers that transition from photo→text UI (like BAN USER prompting for input), use `reply_text()` not `edit_text()`.

## Debugging Checklist

When buttons don't respond:

1. **Check bot logs** for NameError → function ordering issue
2. **Check bot logs** for BadRequest "no text to edit" → photo→text issue
3. **Check bot logs** for "Media_caption_too_long" → reduce caption length or paginate
4. **Verify bot restarted** after code changes (Python loads code once at startup)
5. **Test with `/start`** to confirm bot is responsive at all

## Bot Restart Pattern (Same VPS)

**Common confusion:** Thinking bot runs on external server when it's actually on same VPS as Hermes.

**Reality check:**
- If bot code is in `D:\hermes\yonda_paybot\`, bot runs **locally**
- Don't need SSH/external access
- Can kill/restart directly with `terminal` tool

**Restart workflow:**
```bash
# Find process
ps aux | grep "bot.py" | grep -v grep

# Kill old instance
kill -9 <PID>

# Start new instance
cd /d/hermes/yonda_paybot && python bot.py &

# Verify running
ps aux | grep bot.py
```

**Token conflict error:** If seeing `Conflict: terminated by other getUpdates request`, another bot instance is still running — find and kill it before restarting.

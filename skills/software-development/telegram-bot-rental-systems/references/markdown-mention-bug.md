# Telegram Markdown Parsing Bug with @mentions

## Problem

When using `parse_mode="Markdown"` or `parse_mode="MarkdownV2"` in python-telegram-bot, messages containing `@username` mentions can fail with:

```
telegram.error.BadRequest: Can't parse entities: ... 
```

This happens even when the mention is plain text, not a markdown link.

## Root Cause

Telegram's Markdown parser treats `@` as special character and attempts to parse `@username` as an entity. When combined with other markdown (bold `**text**`, italic `*text*`), the parser can fail with "Can't parse entities" error.

## Solution

**Send messages with @mentions as PLAIN TEXT** (no parse_mode):

```python
# ❌ WRONG - Will fail with @mention
text = f"""
🎉 **YEAYY PEMBAYARAN BERHASIL!**

Paket: {paket}
...
🤖 @yonda_a1bot
"""
await message.edit_caption(
    caption=text, 
    reply_markup=markup,
    parse_mode="Markdown"  # ❌ FAILS!
)

# ✅ CORRECT - Plain text with @mention
text = f"""
🎉 YEAYY PEMBAYARAN BERHASIL!

Paket: {paket}
...
🤖 @yonda_a1bot
"""
await message.edit_caption(
    caption=text, 
    reply_markup=markup
    # No parse_mode - plain text works!
)
```

## When This Happens

- Payment success messages with bot mentions
- Notifications that tag users or bots
- Any mixed content: emoji + bold/italic + @mention

## Symptoms

```python
telegram.error.BadRequest: Can't parse entities: Can't find end of the entity starting at byte offset X
```

User reports: "Bot not responding" or "Message not sending" after clicking payment button.

## Fix Pattern

1. Remove all markdown formatting from text with @mentions
2. Remove `parse_mode` parameter entirely
3. Use plain text + emoji (works fine)
4. If you MUST have formatting, use HTML mode and escape the @:
   ```python
   parse_mode="HTML"
   text = "<b>Success!</b> Contact: @username"  # HTML handles @ better
   ```

## Verification

After fix:
- Payment flow completes without errors
- Success message displays with @mention clickable
- No "Can't parse entities" in logs

## Related

- Affects all python-telegram-bot message methods that accept parse_mode
- Both `edit_caption` and `send_message` affected
- Bug does NOT occur when @mention is the ONLY content (no markdown)

Session: 2026-08-18 with LO (yonda_paybot payment success message bug)

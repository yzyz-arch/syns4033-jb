# Telegram Photo→Text Message Transition Errors

## Problem: "There is no text in the message to edit"

**Error**: `telegram.error.BadRequest: There is no text in the message to edit`

**When it occurs**: Button callback handlers try to `edit_message_text()` or `edit_caption()` on a message that contains a photo/banner.

**Root cause**: Telegram cannot convert a photo message into a text-only message via edit. The message type is immutable.

## Solution: Send New Message Instead of Editing

```python
# ❌ WRONG - tries to edit photo message as text
async def handle_owner_ban_menu(query, user):
    text = """
🚫 BAN USER
Format: /ban USER_ID ALASAN
"""
    await query.answer()
    await query.message.edit_text(text)  # Fails if original had photo!

# ✅ RIGHT - send new message
async def handle_owner_ban_menu(query, user):
    text = """
🚫 BAN USER
Format: /ban USER_ID ALASAN
"""
    await query.answer()
    await query.message.reply_text(text)  # Works regardless of original message type
```

## When This Occurs

- **Owner panel buttons** that display list-heavy content (BAN USER, DELETE SUBS, long reports)
- **Any callback** transitioning from banner/photo to pure text
- **Message edits** that would remove media

## Alternative: Edit Caption (If Text Fits)

Keep the photo and edit only the caption (max 1024 characters):

```python
await query.message.edit_caption(
    caption=new_text,
    reply_markup=keyboard
)
```

## Real-World Example from Session

**Context**: @yonda_paybot with banner image on owner panel

**Original code (failed)**:
```python
async def handle_owner_delete_subs_menu(q, user):
    # ... build text list of users ...
    await send_with_banner(q.message, text, markup, "edit")  # ❌ Tried to edit photo as text
```

**Fixed code**:
```python
async def handle_owner_delete_subs_menu(q, user):
    # ... build text list of users ...
    await q.message.reply_text(text, reply_markup=markup)  # ✅ Send new message
```

## Debug Pattern

If you see this error:
1. Check if the **original message** (the one being edited) contains a photo
2. If yes, switch from `edit_*` to `reply_*` methods
3. Verify with logs: `print(query.message.photo)` - if not None, it's a photo message

## Related Pitfalls

- **Caption length limit**: If keeping photo, captions max 1024 chars (list-heavy content may exceed)
- **Media_caption_too_long**: Indicates you tried to edit caption with >1024 chars
- **Solution for long lists**: Pagination or switch to text-only new message

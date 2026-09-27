# Seamless Message Editing Pattern

## Problem

Bot creates new message for every button click, spamming chat history. Users expect button clicks to **edit the existing message** (seamless transition like a single-page app), not create new ones.

## Solution Pattern

### Smart Reply Function

Auto-detect whether to edit (callback query from button) or reply (text command):

```python
async def smart_reply(update_or_query, text, markup=None, is_photo=False, photo_path=None):
    """
    Smart reply - auto detect callback query (seamless edit) vs message (new reply)
    """
    from telegram import CallbackQuery
    
    # Detect if from callback query (button click) or message (text)
    if isinstance(update_or_query, CallbackQuery):
        # Button click → EDIT (seamless transition)
        q = update_or_query
        try:
            if is_photo and photo_path:
                # Can't edit message to add photo, send new
                with open(photo_path, 'rb') as f:
                    await q.message.reply_photo(photo=f, caption=text, reply_markup=markup, parse_mode="Markdown")
            else:
                # Edit existing message
                await q.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            # Fallback if edit fails (message too old, etc)
            if is_photo and photo_path:
                with open(photo_path, 'rb') as f:
                    await q.message.reply_photo(photo=f, caption=text, reply_markup=markup, parse_mode="Markdown")
            else:
                await q.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        # Text message → NEW REPLY
        msg = update_or_query if hasattr(update_or_query, 'reply_text') else update_or_query.message
        if is_photo and photo_path:
            with open(photo_path, 'rb') as f:
                await msg.reply_photo(photo=f, caption=text, reply_markup=markup, parse_mode="Markdown")
        else:
            await msg.reply_text(text, reply_markup=markup, parse_mode="Markdown")
```

### Handler Routing Pattern

```python
async def callback_query_handler(update: Update, context):
    """Route all button clicks"""
    query = update.callback_query
    await query.answer()  # Always answer first
    
    data = query.data
    user = update.effective_user
    
    # Route to handlers - pass query for seamless editing
    if data == "menu":
        await handle_menu(query, user)
    elif data == "settings":
        await handle_settings(query, user)
    elif data.startswith("item_"):
        item_id = data.split("_")[1]
        await handle_item_detail(query, user, item_id)

async def handle_menu(q, user):
    """Menu handler - edits message seamlessly"""
    text = "📋 **Main Menu**\n\nSelect an option:"
    
    keyboard = [
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("📦 Catalog", callback_data="catalog")],
    ]
    markup = InlineKeyboardMarkup(keyboard)
    
    # Edit the message that triggered this callback
    await q.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
```

## Key Principles

1. **Callback handlers** (button clicks) → **always edit**: `query.message.edit_text()`
2. **Command handlers** (`/start`, `/help`) → create new messages: `update.message.reply_text()`
3. **User clicks button** → content changes in place, no scroll, no spam
4. **User sends text command** → new message appears (expected behavior)

## Media Limitations

### Editing Captions (Allowed)

```python
# Can edit caption of existing photo
await query.message.edit_caption(
    caption="Updated caption text",
    reply_markup=new_keyboard,
    parse_mode="Markdown"
)
```

### Changing Media Type (Not Allowed)

```python
# CANNOT edit text message to become photo message
# Must send new message instead

if current_message_has_photo:
    await query.message.edit_caption(new_text, reply_markup=markup)
else:
    # Need to add photo → must send new message
    with open("banner.jpg", "rb") as f:
        await query.message.reply_photo(photo=f, caption=new_text, reply_markup=markup)
```

## Common Errors

### MessageNotModified

**Error**: `telegram.error.BadRequest: Message is not modified`

**Cause**: Trying to edit message with identical text/markup.

**Solution**: Check if content actually changed before editing:

```python
if new_text != current_text or new_keyboard != current_keyboard:
    await query.message.edit_text(new_text, reply_markup=new_keyboard)
else:
    await query.answer("Already up to date")
```

### MessageToEditNotFound

**Error**: `telegram.error.BadRequest: Message to edit not found`

**Cause**: Message was deleted or is too old (>48 hours).

**Solution**: Always have fallback to reply:

```python
try:
    await query.message.edit_text(text, reply_markup=markup)
except telegram.error.BadRequest:
    await query.message.reply_text(text, reply_markup=markup)
```

## UX Benefits

- ✅ Clean chat history (no spam)
- ✅ Feels like single-page app
- ✅ User stays in context
- ✅ Professional user experience
- ✅ Reduces chat clutter
- ❌ Without this: every button click = new message = spam

# Banner Image + Welcome Text + Buttons Pattern

**Context**: User wants banner image, welcome caption, and inline buttons delivered in ONE message (not separate messages).

## Correct Implementation

Use `reply_photo()` with `caption` and `reply_markup` parameters:

```python
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    banner_path = "path/to/banner.jpg"
    
    welcome_text = """
👋 **Welcome!**

Your message here...
"""
    
    keyboard = [
        [InlineKeyboardButton("Option 1", callback_data="opt1")],
        [InlineKeyboardButton("Option 2", callback_data="opt2")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # ALL IN ONE MESSAGE
    with open(banner_path, 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption=welcome_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
```

## Wrong Approach

Sending image and text as separate messages:

```python
# ❌ DON'T DO THIS
await update.message.reply_photo(photo=photo)
await update.message.reply_text(text, reply_markup=keyboard)
# Results in 2 messages: image, then text+buttons below
```

## Fallback for Missing Image

```python
try:
    with open(banner_path, 'rb') as photo:
        await update.message.reply_photo(
            photo=photo,
            caption=welcome_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
except FileNotFoundError:
    # Fallback: text + buttons only
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
```

## Real-World Example

From @yonda_paybot implementation:

```python
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    banner_path = "D:/hermes/cache/images/img_d5258df9d41b.jpg"
    
    welcome_text = f"""
👋 **Halo {user.first_name}!**

Selamat datang di **YONDA Agent** — Your AI Partner, Anytime! 🤖

✨ **Smart • Fast • Reliable • 24/7 Ready**

Pilih paket sewa yang kamu mau:
"""
    
    keyboard = [
        [
            InlineKeyboardButton("💎 Paket Harian", callback_data="paket_harian"),
            InlineKeyboardButton("⚡ Paket Mingguan", callback_data="paket_mingguan"),
        ],
        [
            InlineKeyboardButton("🔥 Paket Bulanan", callback_data="paket_bulanan"),
            InlineKeyboardButton("👑 Paket Premium", callback_data="paket_premium"),
        ],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        with open(banner_path, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=welcome_text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
    except FileNotFoundError:
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
```

## Key Points

- ✅ Banner + text + buttons = **single message**
- ✅ Use `caption` parameter (not separate `reply_text`)
- ✅ Always include fallback for missing image
- ✅ User sees clean, professional single-message UI
- ❌ Don't send image then text (creates 2 messages)

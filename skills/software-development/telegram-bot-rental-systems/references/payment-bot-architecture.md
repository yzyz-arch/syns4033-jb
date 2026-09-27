# Complete Payment Bot Architecture (yonda_paybot)

Real-world implementation from production rental system.

## Stack
- python-telegram-bot >= 20.0 (async)
- SQLite (local, simple)
- Indonesian Rupiah formatting (Rp 15.000 with dots)

## Database Schema

```sql
-- Users with balance tracking
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    is_bot INTEGER DEFAULT 0,
    language_code TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Separate balance table (not embedded in users)
CREATE TABLE balances (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,  -- in Rupiah cents
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Active subscriptions
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    package_type TEXT NOT NULL,  -- 'perjam', '1hari', '7hari', '1bulan'
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'active',
    price INTEGER NOT NULL,
    payment_method TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- All transactions (topup, sewa)
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    transaction_type TEXT NOT NULL,  -- 'topup', 'purchase'
    amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',  -- 'pending', 'completed', 'failed'
    payment_method TEXT,
    payment_proof TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Activity logs
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Features Implemented

### 1. Owner Panel (ID hardcoded: 1324806211)
- Settings Payment (upload QRIS image)
- ACC Payment (manual approval with broadcast)
- Owner gets special button visible only to them
- Owner balance: Rp 999.999.999 (seeded in db init)

### 2. Top Up System
- Preset buttons: Rp 8.000, 10.000, 15.000, 20.000
- Custom amount (user types, flexible parsing: 15.000 or 15,000 both work)
- User uploads payment proof
- Owner sees pending list with approve buttons
- On approve: balance added + user notified via broadcast

### 3. Subscription Purchase
- Packages: Perjam (Rp 8K), 1 Hari (50K), 3 Hari (90K), 7 Hari (140K), 1 Bulan (560K)
- Pricing: 7 Hari = 140K, 1 Bulan = 4 weeks = 140K × 4 = 560K
- "Lanjutkan Pembayaran" button on package details
- Balance check → if insufficient: popup "YAHHHH... SALDOMU KURANG... AYOO TOPUP SALDO LAGI :>"
- If sufficient: auto-deduct + create subscription + show success

### 4. Panel Agent Saya (for users with active subscription)
- Shows package info, expire time, days left
- Button: "REFRESH AGENT SAYA" (restart user's rental bot)
- Button: "PERPANJANG SEWA" (extend subscription)
  - Shows same package buttons (Perjam → 1 Bulan)
  - Extends current end_date (doesn't replace)
  - Balance check same as purchase

### 5. Indonesian Rupiah Formatting
```python
def format_rupiah(amount):
    """Format Rupiah with dots as thousands separator"""
    return f"Rp {amount:,}".replace(",", ".")
```

Output: `Rp 15.000` not `Rp 15,000`

### 6. Broadcast on Payment Approval
When owner clicks "ACC Payment":
```python
broadcast_text = f"""
🎉 **YEAYYY! TOPUP ANDA TELAH DI-ACC**

💰 Topup: {format_rupiah(amt)}
💎 **SALDOMU NAIK MENJADI {format_rupiah(new_bal)}**

Sekarang kamu bisa sewa agent! 🔥
Ketik /start untuk mulai!
"""

await bot.send_message(chat_id=uid, text=broadcast_text, parse_mode="Markdown")
```

User gets notified immediately (not via polling).

## Button Handler Architecture

### Callback Data Routing
```python
async def button_handler(update, context):
    q = update.callback_query
    await q.answer()  # IMMEDIATE answer (prevents "loading..." forever)
    
    user = q.from_user
    data = q.data
    
    # Log all clicks
    db.log_action(user.id, "button", data)
    
    # Route to handlers
    if data == "owner":
        return await handle_owner_panel(q, user)
    elif data.startswith("approve_"):
        return await handle_approve(q, user, data)
    elif data in ["perjam", "1hari", "3hari", "7hari", "1bulan"]:
        return await handle_paket(q, user, data)
    elif data.startswith("buy_"):
        return await handle_buy_paket(q, user, data)
    elif data == "panel_agent":
        return await handle_panel_agent(q, user)
    # ... etc
```

**Critical**: `await q.answer()` FIRST to prevent timeout/slow UI.

### Edit Message Fallback
```python
try:
    await q.message.edit_caption(caption=text, reply_markup=markup, parse_mode="Markdown")
except:
    await q.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
```

Photo messages need `edit_caption`, text messages need `edit_text`. Fallback handles both.

## Pitfall: Balance Table Name

Database creates `balances` (plural), code must query `balances` not `balance`:

```python
cursor.execute("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
```

## Pitfall: Subscription Duration Calculation

**Wrong** (hardcoded dates):
```python
end_date = start_date + timedelta(days=28)  # Always 28
```

**Right** (flexible):
```python
durations = {
    "perjam": 1/24,  # 0.04 days = 1 hour
    "1hari": 1,
    "3hari": 3,
    "7hari": 7,
    "1bulan": 28  # 4 weeks
}

end_date = start_date + timedelta(days=durations[paket])
```

## Pitfall: add_subscription() Parameters

Database function signature:
```python
def add_subscription(self, user_id, package_type, days, price, payment_method="manual"):
```

Call it with `days`, NOT `start_date` and `end_date`:
```python
db.add_subscription(
    user_id=user.id,
    package_type=paket,
    days=duration_days,  # ✅ Correct
    price=price,
    payment_method="saldo"
)
```

## File Structure

```
yonda_paybot/
├── bot.py                  # Main bot with all handlers
├── database.py             # YondaDB class (SQLite wrapper)
├── requirements.txt        # python-telegram-bot>=20.0
├── README.md               # Setup docs
├── yonda.db                # SQLite database (auto-created)
└── qris.jpg                # QRIS payment image (uploaded by owner)
```

## Running

```bash
cd yonda_paybot
pip install -r requirements.txt
python bot.py &  # Background process
```

Bot auto-initializes database on first run.

## Integration with Rental Bots

Payment bot is standalone. Rental bots (yonda-a2, yonda-a3) run separately as Hermes gateway profiles. To integrate:

1. Rental bots query same database (yonda.db)
2. Check `subscriptions` table for active rental before allowing access
3. Or: payment bot sends webhook/API call to rental bot on purchase

Current implementation: manual — user buys in payment bot, accesses rental bot separately.

## Owner Bootstrap

Seed owner balance on first run:
```python
db.execute("""
INSERT INTO balances (user_id, balance)
VALUES (1324806211, 999999999)
ON CONFLICT(user_id) DO UPDATE SET balance = 999999999
""")
```

Owner ID hardcoded in bot.py: `OWNER_ID = 1324806211`

## Testing Checklist

- [ ] Owner sees "PANEL OWNER" button
- [ ] Regular user does NOT see owner button
- [ ] Top up → upload proof → owner sees pending → approve → user balance increases
- [ ] User with 0 balance clicks "Lanjutkan Pembayaran" → sees "SALDOMU KURANG" popup
- [ ] User with sufficient balance → purchase succeeds → subscription created
- [ ] User with active subscription sees "PANEL AGENT SAYA" button
- [ ] Perpanjang extends end_date (doesn't replace)
- [ ] All amounts display with dots (Rp 15.000)
- [ ] Button clicks respond instantly (no lag)

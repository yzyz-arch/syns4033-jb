# Hermes Gateway Integration for Rental Systems

When the service bot is a Hermes Agent instance (rather than a standalone bot), integrate rental access control directly into the Telegram platform adapter.

## Architecture

```
User → Hermes Gateway (Telegram adapter)
           ↓
     Rental DB check
           ↓
   Has subscription? ─YES→ Route to agent (full access)
           ↓
          NO
           ↓
   Reply promo message → Block (skip agent entirely)
```

## Implementation: Adapter-Level Access Control

### 1. Add Helper Function to Telegram Adapter

Inject rental check logic at the TOP of the adapter file, after imports:

**File:** `hermes-agent/plugins/platforms/telegram/adapter.py`

```python
# === RENTAL ACCESS CONTROL ===
# Integration with payment bot subscription system
RENTAL_OWNER_IDS = {7402484358, 1324806211}  # Owner IDs with unlimited access
RENTAL_DB_PATH = "D:/hermes/yonda_paybot/yonda.db"
RENTAL_PROMO_MESSAGE = """YAHHH... KAMU BELUM DAPAT AKSES :( 

Ayooo sewa di @RaskaLabumi hanya 50K perhari! minim gateway error loh!"""

def _check_rental_access(user_id: int) -> bool:
    """Check if user has active rental subscription.
    
    Returns True if:
    - User is owner (bypass)
    - User has active subscription in yonda.db
    
    Returns False if user needs to rent.
    """
    # Owner bypass
    if user_id in RENTAL_OWNER_IDS:
        return True
    
    # Check subscription in database
    try:
        import sqlite3
        
        conn = sqlite3.connect(RENTAL_DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
        SELECT * FROM subscriptions 
        WHERE user_id = ? 
        AND status = 'active' 
        AND end_date > CURRENT_TIMESTAMP
        ORDER BY end_date DESC
        LIMIT 1
        """, (user_id,))
        
        sub = cursor.fetchone()
        conn.close()
        
        return sub is not None
    except Exception as e:
        logger.warning(f"[Rental] Failed to check subscription for {user_id}: {e}")
        # On error, deny access (fail-safe)
        return False
```

### 2. Inject Check Into ALL Message Handlers

Patch EVERY message entry point in the adapter:
- `_handle_text_message`
- `_handle_command`
- `_handle_media_message`
- `_handle_location_message`

**Pattern for each handler:**

```python
async def _handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    msg = self._effective_update_message(update)
    if not msg or not msg.text:
        return
    
    # RENTAL ACCESS CHECK: Block users without active subscription
    user = getattr(msg, "from_user", None)
    if user and not _check_rental_access(user.id):
        logger.info(f"[Rental] Blocked user {user.id} - no active subscription")
        try:
            await msg.reply_text(RENTAL_PROMO_MESSAGE)
        except Exception as e:
            logger.warning(f"[Rental] Failed to send promo message: {e}")
        return  # CRITICAL: Return early, skip agent processing
    
    # Existing auth check continues here...
    if not self._is_user_authorized_from_message(msg):
        ...
```

**Key principles:**
1. Check happens AFTER message validation but BEFORE existing auth
2. Owner bypass via set lookup (fast)
3. Database check only for non-owners
4. Send promo message on failure (wrapped in try/except)
5. **Return early** on failure - agent never sees the message

### 3. Shared Database Schema

Payment bot (`yonda_paybot`) and Hermes gateway must share same database.

**Required table:**

```sql
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    package_type TEXT NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'active',
    price INTEGER NOT NULL,
    payment_method TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

**Path convention:** Store shared DB in project root or dedicated directory, NOT in profile-specific paths.

Example: `D:/hermes/yonda_paybot/yonda.db` (accessible by both bots)

### 4. Gateway Restart Required

Changes to `adapter.py` require gateway restart to take effect:

```bash
# Option 1: Via command (from outside gateway session)
hermes gateway restart

# Option 2: Manual
hermes gateway stop
# wait 3 seconds
hermes gateway run
```

**Cannot restart from inside gateway** - you'll get blocked with "cannot restart gateway from inside gateway process" error.

### 5. Multiple Owner IDs

Support multiple owners (main owner + payment bot owner):

```python
RENTAL_OWNER_IDS = {
    7402484358,  # Main owner (raskala)
    1324806211,  # Payment bot owner
}
```

Set lookup is O(1), no performance impact.

## Workflow After Integration

### For Blocked Users:

1. User sends message to Hermes bot
2. Adapter checks subscription in DB
3. No subscription found → sends promo message
4. Returns early, agent never invoked
5. User sees: "YAHHH... KAMU BELUM DAPAT AKSES :("

### For Subscribed Users:

1. User sends message to Hermes bot
2. Adapter checks subscription in DB
3. Active subscription found → proceeds normally
4. Existing auth checks continue
5. Message routed to agent for processing

### For Owners:

1. Owner sends message to Hermes bot
2. Adapter checks user_id in `RENTAL_OWNER_IDS`
3. Match found → skips database check entirely
4. Proceeds directly to agent (unlimited access)

## Testing Integration

### Test 1: Owner Access
```bash
# As owner (ID in RENTAL_OWNER_IDS)
# Send any message to Hermes bot
# Expected: Full access, no promo message
```

### Test 2: Blocked User
```bash
# As non-subscribed user
# Send any message to Hermes bot
# Expected: Promo message, no agent response
```

### Test 3: Subscribed User
```bash
# Create test subscription in DB:
INSERT INTO subscriptions (user_id, package_type, start_date, end_date, status, price)
VALUES (TEST_USER_ID, 'test', datetime('now'), datetime('now', '+1 day'), 'active', 50000);

# Send message as that user
# Expected: Normal agent response
```

### Test 4: Expired Subscription
```bash
# Update subscription to expired:
UPDATE subscriptions SET end_date = datetime('now', '-1 hour') WHERE user_id = TEST_USER_ID;

# Send message as that user
# Expected: Promo message (blocked)
```

## Bot Conflict Resolution

When starting the payment bot (`yonda_paybot`), you may encounter:

```
telegram.error.Conflict: Conflict: terminated by other getUpdates request; 
make sure that only one bot instance is running
```

### Common Causes:
1. Bot already running in another terminal/process
2. Bot running on a server/cloud platform (Heroku, Railway, VPS)
3. Webhook set instead of polling
4. Zombie polling session from previous run

### Fix Workflow:

**Step 1: Check webhook**
```python
import requests
BOT_TOKEN = "your_token"
info = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo").json()
print(info)

# If webhook set, delete it:
requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
```

**Step 2: Kill local instances**
```bash
# Find processes
ps aux | grep bot.py
ps aux | grep yonda_paybot

# Kill by PID
kill -9 <PID>
```

**Step 3: Check for remote instances**
- Check Heroku/Railway dashboard
- Check VPS/server processes
- Check systemd services: `systemctl --user list-units | grep bot`

**Step 4: Fresh start**
```bash
cd D:/hermes/yonda_paybot
python bot.py
```

**If conflict persists:** The bot is running somewhere you don't have access to. Options:
1. Get new token from @BotFather (`/token`)
2. Find and stop the remote instance
3. Revoke old token and create new bot

## Banner Updates in Payment Bot

To set promotional banner across all payment bot menus:

```python
# Add constant at top
BANNER_PATH = "D:/hermes/cache/images/img_5ead548b2205.jpg"

# Create helper function
async def send_with_banner(target, text, markup, method="reply"):
    """Helper to send message with banner"""
    try:
        with open(BANNER_PATH, 'rb') as f:
            if method == "edit":
                await target.edit_caption(caption=text, reply_markup=markup, parse_mode="Markdown")
            else:
                await target.reply_photo(photo=f, caption=text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        # Fallback to text if banner fails
        if method == "edit":
            await target.edit_text(text, reply_markup=markup, parse_mode="Markdown")
        else:
            await target.reply_text(text, reply_markup=markup, parse_mode="Markdown")

# Use in handlers:
await send_with_banner(update.message, text, markup)  # For new messages
await send_with_banner(query.message, text, markup, method="edit")  # For callbacks
```

**Why helper function:**
- Consistent banner across all menus
- Graceful fallback if banner missing
- Single place to update banner path
- Works for both new messages and edits

## Performance Considerations

### Database Check Overhead

- SQLite query: ~1-5ms for indexed lookup
- Set lookup (owners): ~0.001ms
- Per-message overhead: negligible (<10ms)

**Optimization:** Consider Redis cache for high-traffic bots:

```python
import redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

def _check_rental_access(user_id: int) -> bool:
    if user_id in RENTAL_OWNER_IDS:
        return True
    
    # Check cache first (TTL 60s)
    cache_key = f"rental:access:{user_id}"
    cached = r.get(cache_key)
    if cached is not None:
        return cached == "1"
    
    # Check database
    has_access = check_db_subscription(user_id)
    
    # Cache result
    r.setex(cache_key, 60, "1" if has_access else "0")
    return has_access
```

### File Locking

SQLite has built-in locking. If payment bot and gateway both write:
- Reads are concurrent (no blocking)
- Writes use WAL mode (minimal blocking)
- Set `journal_mode=WAL` in database init

## Troubleshooting

### "No such table: subscriptions"

**Cause:** Database not initialized.

**Fix:**
```bash
cd D:/hermes/yonda_paybot
python -c "from database import YondaDB; YondaDB()"
```

### Promo message not sending

**Cause:** Exception in `reply_text` (common with media messages).

**Fix:** Check handler - media messages use `update.message`, not `msg` sometimes.

### Owner still blocked

**Cause:** Owner ID not in `RENTAL_OWNER_IDS` set.

**Fix:** Verify ID matches exactly:
```python
print(user.id, type(user.id))  # Must be int, not str
print(RENTAL_OWNER_IDS)
```

### Database path wrong

**Cause:** Relative path vs absolute path.

**Fix:** Always use absolute paths:
```python
RENTAL_DB_PATH = "D:/hermes/yonda_paybot/yonda.db"  # ✅
RENTAL_DB_PATH = "yonda.db"  # ❌ (breaks when cwd changes)
```

## Integration Checklist

Before deploying:
- [ ] Helper function added to adapter.py (top of file)
- [ ] All 4 message handlers patched (text, command, media, location)
- [ ] Owner IDs set correctly in `RENTAL_OWNER_IDS`
- [ ] Database path absolute and accessible
- [ ] Promo message customized
- [ ] Gateway restarted after adapter changes
- [ ] Tested with owner account (should bypass)
- [ ] Tested with non-subscribed user (should block)
- [ ] Tested with active subscription (should allow)
- [ ] Payment bot running and accepting payments
- [ ] Both bots using same database file

## Alternative: Middleware Approach

For cleaner separation, implement as middleware (future enhancement):

```python
class RentalAccessMiddleware:
    def __init__(self, owner_ids, db_path, promo_message):
        self.owner_ids = owner_ids
        self.db_path = db_path
        self.promo_message = promo_message
    
    async def __call__(self, update, context, next_handler):
        user = update.effective_user
        if not user:
            return await next_handler(update, context)
        
        if not self._check_access(user.id):
            await update.message.reply_text(self.promo_message)
            return  # Block
        
        return await next_handler(update, context)

# Register in adapter initialization
self.app.add_middleware(RentalAccessMiddleware(...))
```

**Not yet implemented in python-telegram-bot 20+** - use direct handler injection for now.

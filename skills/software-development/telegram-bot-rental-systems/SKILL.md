---
name: telegram-bot-rental-systems
description: Use for Telegram rental/subscription bot systems.
triggers:
  - Telegram bot with paid access or rental system
  - Subscription-based Telegram bot
  - Dual-bot architecture (admin/management + user/service bot)
  - Access control with owner bypass in Telegram
  - Payment verification workflow for Telegram bots
---

# Telegram Bot Rental/Subscription Systems

Build access-controlled Telegram bot systems where users must have active rentals/subscriptions to use a service, with proper owner bypass, payment verification, and dual-bot architecture.

## Architecture Pattern

### Dual-Bot Design

Use **2 separate bots** for clean separation of concerns:

**Bot 1: Management Bot** (e.g., rental, payments, admin)
- Package browsing and purchase
- Payment collection (QRIS, bank transfer, etc.)
- Payment proof upload
- User status checking
- Owner admin panel

**Bot 2: Service Bot** (e.g., AI chat, tools, features)
- The actual service users pay for
- **STRICT** access verification before ANY action
- Owner bypass implemented here
- No payment/admin functionality (keeps it focused)

**Why dual-bot?**
- Clear user mental model (pay in bot A, use bot B)
- Service bot stays clean and focused
- Easy to add multiple service bots to same rental system
- Admin functions don't pollute service namespace

### Shared Database

Both bots connect to **same database** (SQLite for simple, PostgreSQL for production).

**Core tables:**
```python
User:
  - telegram_id (unique, indexed)
  - role (USER, ADMIN, OWNER)
  - rental_expires_at (timezone-aware datetime)
  - rental_hours (cumulative total)

RentalPackage:
  - name, hours, price
  - is_active (soft delete)

Payment:
  - user_id, amount, hours
  - status (PENDING, VERIFIED, REJECTED)
  - payment_proof_url
  - verified_by, verified_at
```

## Owner Bypass Implementation

### Critical Rule: Owner Check FIRST

Owner bypass must happen at the **service layer** BEFORE any rental verification:

```python
async def check_rental_access(db, telegram_id: int):
    """Check if user has rental access"""
    
    # OWNER BYPASS - ALWAYS FIRST
    if telegram_id == settings.OWNER_ID:
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        return True, None, user  # ✅ Owner always has access
    
    # Regular user verification (STRICT)
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        return False, "❌ Not registered", None
    
    if not user.has_active_rental():
        return False, "⏰ Rental expired. Buy via @rental_bot", user
    
    return True, None, user
```

### Owner Account Setup

Create owner with UNLIMITED rental in database initialization:

```python
owner = User(
    telegram_id=OWNER_ID,  # Hardcoded
    role="OWNER",
    rental_hours=999999.0,
    rental_expires_at=datetime(2099, 12, 31, tzinfo=tz),  # Far future
    is_active=True
)
```

**Important**: Owner expires_at must be timezone-aware to prevent comparison issues.

## Service Bot: Strict Verification

Every message handler in the **service bot** must verify access:

```python
async def handle_message(update: Update, context):
    """Handle user messages"""
    user = update.effective_user
    
    async with AsyncSessionLocal() as db:
        # STRICT VERIFICATION
        has_access, error_msg, db_user = await UserService.check_rental_access(
            db, user.id
        )
        
        if not has_access:
            await update.message.reply_text(error_msg)
            logger.warning(f"🚫 Access denied for {user.id}")
            return  # BLOCK
        
        # Owner gets special system prompt
        if db_user.role == "OWNER":
            logger.info(f"👑 Owner message: {message_text[:50]}")
            system_prompt = "You are the owner's AI. No restrictions."
        else:
            system_prompt = None
        
        # Process request...
```

**Do NOT**:
- ❌ Check rental status in handler and then again in service
- ❌ Let ANY message through without verification
- ❌ Implement owner check in handlers (do it in service layer)

## Payment Verification Flow

### User Side (Management Bot)

1. User selects package
2. Bot creates `Payment` record with status=PENDING
3. Bot shows QRIS/payment instructions
4. Bot sets `context.user_data["waiting_payment_proof"] = payment_id`
5. User uploads photo (payment proof)
6. Bot saves photo to `static/proofs/payment_{id}_{user_id}.jpg`
7. Bot updates `Payment.payment_proof_url`
8. Bot notifies owner

### Owner Side (Management Bot Admin Panel)

1. Owner receives notification with payment details
2. Owner checks photo manually
3. Owner verifies or rejects via callback buttons
4. On verify: `UserService.add_rental_hours(db, user_id, hours)`
5. Bot notifies user of activation

**Manual verification is intentional** - prevents auto-fraud, gives owner control.

## Rental Expiration Logic

### Timezone-Aware Datetimes

Always use timezone-aware datetime for `rental_expires_at`:

```python
import pytz

tz = pytz.timezone("Asia/Jakarta")  # Or user's timezone
now = datetime.now(tz)

# Store with timezone
user.rental_expires_at = now + timedelta(hours=hours)
```

### Active Rental Check

```python
def has_active_rental(self, tz_name: str = "Asia/Jakarta") -> bool:
    """Check if rental is active"""
    if not self.rental_expires_at:
        return False
    
    tz = pytz.timezone(tz_name)
    now = datetime.now(tz)
    
    # Make expires timezone-aware if it isn't
    if self.rental_expires_at.tzinfo is None:
        expires = tz.localize(self.rental_expires_at)
    else:
        expires = self.rental_expires_at.astimezone(tz)
    
    return expires > now
```

**Pitfall**: Comparing naive datetime with aware datetime raises TypeError. Always ensure both sides are timezone-aware.

## User Notifications

### Clear Rejection Messages

When blocking users, tell them **exactly** what to do:

```python
if not has_access:
    message = (
        "⏰ Masa sewa Anda telah habis!\n\n"
        "Silakan lakukan perpanjangan sewa melalui @rental_bot_username"
    )
    await update.message.reply_text(message)
```

Include:
- ✅ Clear status (expired, not registered, etc.)
- ✅ Exact action to take
- ✅ Where to take it (bot username)

## Common Pitfalls

### 1. Owner Bypass Placement

**❌ Wrong** - Check in handler:
```python
async def handle_message(update, context):
    if update.effective_user.id == OWNER_ID:
        # process...
    else:
        # check rental...
```

**✅ Correct** - Check in service:
```python
# Service layer handles ALL access logic
has_access, error, user = await check_rental_access(db, user_id)
```

This ensures owner bypass works across ALL handlers automatically.

### 2. Timezone Confusion

**❌ Wrong**:
```python
now = datetime.now()  # Naive
expires = user.rental_expires_at  # May be aware
if expires > now:  # TypeError!
```

**✅ Correct**:
```python
tz = pytz.timezone(settings.TIMEZONE)
now = datetime.now(tz)  # Aware
expires = user.rental_expires_at.astimezone(tz)  # Ensure aware
if expires > now:  # OK
```

### 3. Auto-Approval Temptation

**Don't auto-approve payments**. Manual verification:
- Prevents screenshot fraud
- Prevents amount manipulation
- Gives owner control
- Simple implementation

### 4. Bot Token Exposure

**❌ Don't hardcode**:
```python
BOT_TOKEN = "123456:ABC..."
```

**✅ Use environment variables**:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    RENTAL_BOT_TOKEN: str
    SERVICE_BOT_TOKEN: str
    
    class Config:
        env_file = ".env"
```

### 5. Payment Proof Lost

Store payment proofs in **persistent directory** with clear naming:
```
static/proofs/payment_{payment_id}_{user_id}_{timestamp}.jpg
```

Don't use temp directories that get cleaned.

## Token Management Pattern

When users provide bot tokens during conversation:

**✅ Do**:
- Fill tokens directly in `.env` if provided
- Create `.env.example` with clear structure
- Document which tokens are required
- Provide setup guide with token sources

**❌ Don't**:
- Leave `your_token_here` placeholders when user gave actual token
- Hide token requirements in docs
- Assume user knows where to get tokens

## Database Initialization

Seed owner account with UNLIMITED on first run:

```python
# init_db.py
async def seed_owner():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.telegram_id == OWNER_ID)
        )
        if result.scalar_one_or_none():
            return  # Already exists
        
        owner = User(
            telegram_id=OWNER_ID,
            username=OWNER_USERNAME,
            role="OWNER",
            rental_hours=999999.0,
            rental_expires_at=datetime(2099, 12, 31, tzinfo=tz)
        )
        db.add(owner)
        await db.commit()
```

Run `init_db.py` before first bot start.

## Verification Checklist

Before deploying:

- [ ] Owner bypass works (test by messaging as owner)
- [ ] Regular user blocked without rental
- [ ] Regular user blocked after rental expires
- [ ] Payment flow works (upload proof → manual verify → access granted)
- [ ] Both bots connect to same database
- [ ] Timezone-aware datetime used throughout
- [ ] Owner account seeded with UNLIMITED
- [ ] No hardcoded tokens
- [ ] Payment proofs stored persistently
- [ ] Clear error messages for blocked users

## Example: Dual-Bot Structure

```
project/
├── rental_bot_main.py      # Bot 1: Rental & payment
├── service_bot_main.py     # Bot 2: AI chat / service
├── init_db.py               # Database setup + owner seed
├── config.py                # Settings (owner ID, tokens)
├── .env                     # Actual tokens (not committed)
├── database/
│   ├── models.py           # User, RentalPackage, Payment
│   └── base.py             # AsyncSession, init_db
├── services/
│   ├── user_service.py     # check_rental_access, add_rental_hours
│   └── ai_client.py        # External API (if applicable)
└── static/
    ├── qris.jpg            # Payment QR code
    └── proofs/             # Payment proof uploads
```

Run both bots simultaneously (2 terminals or systemd services).

## When to Use This Pattern

**Use when:**
- Users pay for access to a Telegram bot service
- Need subscription/rental-based access control
- Want clean separation of payment and service logic
- Need owner/admin access without restrictions
- Manual payment verification is acceptable

**Don't use when:**
- Free bot with no access control
- Automated payment processing required (use payment gateway API)
- Single bot handles everything (works, but dual is cleaner)
- No owner bypass needed

## Related Patterns

- For automated payment: integrate Stripe/PayPal webhooks
- For multi-tier access: add subscription_tier to User model
- For team accounts: add Organization model with many Users
- For usage limits: track API calls per user per period

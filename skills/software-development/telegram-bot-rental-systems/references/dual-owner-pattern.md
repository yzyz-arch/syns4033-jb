# Dual Owner Pattern for Telegram Rental Systems

When building rental/subscription bots, you often need multiple owner IDs with full bypass access:
- **Primary owner** (the person running the rental business)
- **Payment bot owner** (original creator, may be different person)
- **Technical admin** (dev/ops who maintains the system)

This reference covers the implementation pattern discovered during a production integration where both the rental system owner and payment bot creator needed equal admin access.

## Implementation Pattern

### 1. Set-Based Owner Storage

Use a **set** for owner IDs, not a single constant:

```python
# ❌ OLD: Single owner
OWNER_ID = 1324806211

# ✅ NEW: Multiple owners
OWNER_IDS = {7402484358, 1324806211}
```

**Why set?**
- O(1) membership check (`user_id in OWNER_IDS`)
- Clear semantic (unordered collection of unique IDs)
- Easy to extend (just add to set)

### 2. Helper Function for Consistency

Create a single helper that all code uses:

```python
def is_owner(user_id: int) -> bool:
    """Check if user is owner."""
    return user_id in OWNER_IDS
```

**Usage throughout codebase:**

```python
# Handler checks
if is_owner(user.id):
    # Show owner panel

# Database seeding
for owner_id in OWNER_IDS:
    seed_owner_account(owner_id)

# Logging
if is_owner(user.id):
    logger.info(f"👑 Owner {user.id} accessed panel")
```

### 3. Batch Replacement Pattern

When migrating from single owner to dual owner, use regex batch replacement:

```python
import re

content = read_file("bot.py")

# Replace comparisons
content = re.sub(r'user\.id == OWNER_ID\b', 'is_owner(user.id)', content)
content = re.sub(r'user\.id != OWNER_ID\b', 'not is_owner(user.id)', content)
content = re.sub(r'if user\.id == OWNER_ID:', 'if is_owner(user.id):', content)

write_file("bot.py", content)
```

**Critical:** Don't replace config section:
```python
# Skip replacement here
OWNER_IDS = {7402484358, 1324806211}  # ← Keep this line unchanged
```

### 4. Display Format

When printing owner info:

```python
# Startup log
print(f"👑 Owners: {', '.join(map(str, OWNER_IDS))}")
# Output: 👑 Owners: 7402484358, 1324806211

# Panel display
owners_text = "\n".join([f"• {owner_id}" for owner_id in OWNER_IDS])
text = f"**Owner IDs:**\n{owners_text}"
```

### 5. Database Balance Seeding

Seed unlimited balance for ALL owners on startup:

```python
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Set owner balance for ALL owners
    if is_owner(user.id):
        bal = db.get_balance(user.id)
        if bal < 999999999:
            db.add_balance(user.id, 999999999 - bal)
```

**Why per-user instead of hardcoded ID:**
- Works for any owner who triggers `/start`
- No need to iterate over all owners
- Lazy initialization (only when needed)

## Integration with Hermes Gateway

When integrating dual owners into Hermes adapter rental checks:

```python
# At top of adapter.py
RENTAL_OWNER_IDS = {7402484358, 1324806211}

def _check_rental_access(user_id: int) -> bool:
    """Check if user has active rental subscription."""
    # Owner bypass - ALL owners get unlimited access
    if user_id in RENTAL_OWNER_IDS:
        return True
    
    # Regular subscription check...
    # (database query as before)
```

**Both payment bot and gateway adapter** must have matching owner ID sets.

## Testing Multiple Owners

### Test Matrix

| User ID | Expected Access | Test Action |
|---------|----------------|-------------|
| 7402484358 | ✅ Full bypass | Send message, check panel access |
| 1324806211 | ✅ Full bypass | Send message, check panel access |
| 999999999 | ❌ Blocked | Send message, verify promo sent |

### Verification Script

```python
def test_owner_access():
    """Test both owners have equal access."""
    for owner_id in OWNER_IDS:
        assert _check_rental_access(owner_id) == True
        print(f"✅ Owner {owner_id} bypass working")
    
    # Test non-owner
    assert _check_rental_access(999999999) == False
    print("✅ Non-owner blocking working")
```

## Common Pitfalls

### 1. String vs Int Mismatch

```python
# ❌ WRONG: Mixed types
OWNER_IDS = {"7402484358", 1324806211}  # One string, one int

# ✅ CORRECT: All ints
OWNER_IDS = {7402484358, 1324806211}
```

Telegram user IDs are always `int`. Sets don't auto-convert, so type mismatch causes missed matches.

### 2. Incomplete Replacement

After migrating to dual owner, search for remaining hardcoded `OWNER_ID` references:

```bash
grep -n "OWNER_ID" bot.py | grep -v "OWNER_IDS"
```

**Common missed locations:**
- Logging statements
- Balance-setting logic
- Database queries with hardcoded ID

### 3. Balance Logic Bug

```python
# ❌ WRONG: Hardcoded single owner
if user.id == OWNER_ID:
    db.add_balance(OWNER_ID, 999999999)

# ✅ CORRECT: Current user (works for all owners)
if is_owner(user.id):
    bal = db.get_balance(user.id)
    if bal < 999999999:
        db.add_balance(user.id, 999999999 - bal)
```

### 4. Panel Access Divergence

Both owners should see identical admin features:

```python
# Generate panel buttons
if is_owner(user.id):
    kb = [
        [InlineKeyboardButton("👑 PANEL OWNER", callback_data="owner")],
        # ... all owner features
    ]
```

**Don't create different panels per owner** - keep admin experience consistent.

## Documentation Pattern

When documenting owner IDs in comments:

```python
OWNER_IDS = {7402484358, 1324806211}  # LO (raskala) + original owner
```

**Format:**
- First ID: primary owner + username/identifier
- Second ID: role (original owner, technical admin, etc.)

Clear inline docs prevent confusion months later.

## Deployment Checklist

Before going live with dual owner system:

- [ ] `OWNER_IDS` set defined (not `OWNER_ID` single value)
- [ ] `is_owner()` helper function created
- [ ] All handler checks use `is_owner()` consistently
- [ ] Balance seeding works for both owners
- [ ] Admin panel accessible to both
- [ ] Gateway adapter `RENTAL_OWNER_IDS` matches payment bot
- [ ] Both owners tested live with actual messages
- [ ] Logging distinguishes between owners (optional but helpful)

## Real-World Example

From production deployment (2026-08-18):

**Context:** Indonesian Telegram rental bot system where:
- Primary owner (7402484358) runs the rental business (@RaskaLabumi)
- Original payment bot owner (1324806211) created the system

**Requirements:**
- Both need admin panel access
- Both bypass rental checks
- Both get unlimited balance
- Seamless experience (no "owner A vs owner B" distinction)

**Implementation:**
```python
# bot.py (payment bot)
OWNER_IDS = {7402484358, 1324806211}

def is_owner(user_id):
    return user_id in OWNER_IDS

# Startup message
print(f"👑 Owners: {', '.join(map(str, OWNER_IDS))}")
# Output: 👑 Owners: 1324806211, 7402484358

# adapter.py (Hermes gateway)
RENTAL_OWNER_IDS = {7402484358, 1324806211}

def _check_rental_access(user_id: int) -> bool:
    if user_id in RENTAL_OWNER_IDS:
        return True  # Both owners bypass
    # ... subscription check
```

**Result:** Both owners have identical, unlimited access to payment bot admin features and service bot (Hermes) without subscription requirements.

## When to Use Dual Owner Pattern

**Use when:**
- Multiple people need admin/owner-level access
- Original creator remains involved (consulting, maintenance)
- Business owner ≠ technical owner
- Partnership/team ownership structure
- Need to grant full access without "sharing" single account

**Don't use when:**
- Single owner is sufficient
- Need role-based access (admin vs superadmin) - use roles instead
- Temporary elevated access (use time-limited admin flag)
- Large number of admins (use admin table, not hardcoded set)

## Extending to 3+ Owners

Pattern scales naturally:

```python
OWNER_IDS = {
    7402484358,  # Primary owner (raskala)
    1324806211,  # Payment bot owner
    5551234567,  # Technical admin
}
```

**Consider role system** once you exceed 3-4 owners - set membership check remains O(1), but management becomes unwieldy.

## Related Patterns

- **Role-based access:** Add `role` field to User model (OWNER, ADMIN, USER)
- **Permission flags:** Bitmask permissions for granular control
- **Admin table:** Database-driven admin list (dynamic, no code changes)

This reference documents the dual-owner implementation discovered during a production Hermes gateway + payment bot integration, where both the rental business owner and original bot creator needed equal administrative access.

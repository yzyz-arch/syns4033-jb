# Payment Proof Approval Flow Pattern

**Context:** Telegram payment bots where owner must review transaction proof images before approving/rejecting payments.

**Problem:** Direct approve buttons skip proof verification step. Users want to see uploaded proof image with approve/reject actions.

## Implementation Pattern

### 1. Button Flow Architecture

```
ACC Payment List
    ↓ (click user button)
Show Proof Image + ACC/CANCEL buttons
    ↓ (click ACC)          ↓ (click CANCEL)
Approve handler        Reject handler
    ↓                      ↓
Broadcast success      Broadcast rejection
```

### 2. Database Requirements

Transaction table MUST have `proof_image` column storing:
- File ID (Telegram file_id for photo)
- Or URL (if stored externally)
- Or local path (if saved to disk)

```sql
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    proof_image TEXT,  -- ← REQUIRED
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. Handler Chain

**Step 1: ACC Payment List (Modified)**

Change button callback from direct approve to proof viewer:

```python
# BEFORE (direct approve):
kb.append([InlineKeyboardButton(f"{label} - {amt}", callback_data=f"approve_{tid}")])

# AFTER (show proof first):
kb.append([InlineKeyboardButton(f"{label} - {amt}", callback_data=f"proof_{tid}")])
```

**Step 2: Show Proof Handler**

```python
async def handle_show_proof(q, user, data):
    """Show payment proof with ACC/CANCEL buttons"""
    if not is_owner(user.id):
        return
    
    tid = int(data.split("_")[1])
    
    # Get transaction with proof image
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT t.user_id, u.username, u.first_name, t.amount, t.proof_image
    FROM transactions t
    JOIN users u ON t.user_id = u.user_id
    WHERE t.id = ?
    """, (tid,))
    trans = cur.fetchone()
    conn.close()
    
    if not trans:
        return await q.answer("❌ Transaction not found!", show_alert=True)
    
    uid, uname, fname, amt, proof_img = trans
    label = f"@{uname}" if uname else fname or f"ID:{uid}"
    
    text = f"""
📸 **BUKTI TRANSFER**

👤 User: {label}
💰 Nominal: {format_rupiah(amt)}
🆔 Transaction ID: {tid}

ACC atau CANCEL pembayaran ini?
"""
    
    kb = [
        [InlineKeyboardButton("✅ ACC", callback_data=f"approve_{tid}"),
         InlineKeyboardButton("❌ CANCEL", callback_data=f"reject_{tid}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="owner_acc")],
    ]
    markup = InlineKeyboardMarkup(kb)
    
    await q.answer()
    
    # Send proof image with ACC/CANCEL buttons
    if proof_img and proof_img.strip():
        try:
            await q.message.reply_photo(
                photo=proof_img, 
                caption=text, 
                reply_markup=markup, 
                parse_mode="Markdown"
            )
        except Exception as e:
            # Fallback if image load fails
            await q.message.reply_text(
                f"{text}\n\n⚠️ Gambar bukti tidak tersedia atau error: {e}", 
                reply_markup=markup, 
                parse_mode="Markdown"
            )
    else:
        await q.message.reply_text(
            f"{text}\n\n⚠️ User belum upload bukti transfer!", 
            reply_markup=markup, 
            parse_mode="Markdown"
        )
```

**Step 3: Reject Handler**

```python
async def handle_reject(q, user, data):
    """Reject/Cancel payment"""
    if not is_owner(user.id):
        return
    
    tid = int(data.split("_")[1])
    
    # Get transaction details
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT user_id, amount FROM transactions WHERE id = ?", (tid,))
    trans = cur.fetchone()
    conn.close()
    
    if not trans:
        return await q.answer("❌ Transaction not found!", show_alert=True)
    
    uid, amt = trans
    
    # Update status to rejected
    db.update_transaction_status(tid, "rejected")
    db.log_action(user.id, "reject", f"Trans {tid}, User {uid}, {amt}")
    
    # Broadcast to user
    broadcast_text = """
YAHHH... Pembayaran kamu ditolak :(

Chat @RaskaLabumi buat info lebih lanjut yaa ^_^
"""
    
    try:
        bot = q.bot
        await bot.send_message(chat_id=uid, text=broadcast_text)
    except Exception as e:
        db.log_action(user.id, "broadcast_failed", f"Failed to notify user {uid}: {e}")
    
    await q.answer(f"❌ Payment rejected: {format_rupiah(amt)}", show_alert=True)
    
    # Refresh ACC list
    await handle_owner_acc(q, user)
```

**Step 4: Update Approve Handler Broadcast**

Modify existing approve handler to use custom broadcast format:

```python
# Custom broadcast text (replace existing)
broadcast_text = f"""
YEAAAYYY🥳🥳

Saldo sebesar {format_rupiah(amt)} berhasil masuk ke saldo kamu!!!

YUKKK LANGSUNG SEWA YONDA Agenttt ^_^
"""
```

### 4. Callback Routing

Add to main callback_handler:

```python
elif data.startswith("proof_"):
    return await handle_show_proof(q, user, data)
elif data.startswith("approve_"):
    return await handle_approve(q, user, data)
elif data.startswith("reject_"):
    return await handle_reject(q, user, data)
```

**Order matters:** `proof_` must come BEFORE `approve_` in the routing chain.

## Pitfalls

### 1. Proof Image Not Stored

**Problem:** Transaction created without saving `proof_image` column.

**Solution:** When user uploads photo for topup, extract and store:

```python
# In photo upload handler
if photo:
    file_id = photo[-1].file_id  # Get largest photo
    
    # Store in transaction
    db.execute("""
        UPDATE transactions 
        SET proof_image = ? 
        WHERE id = ?
    """, (file_id, transaction_id))
```

### 2. Photo File ID Expiration

**Problem:** Telegram file_id can expire after 1 hour if not downloaded.

**Solution:** For production, download and store locally:

```python
file = await context.bot.get_file(file_id)
local_path = f"uploads/proof_{transaction_id}.jpg"
await file.download_to_drive(local_path)

# Store local path instead of file_id
db.update_proof(transaction_id, local_path)
```

### 3. Missing Error Handling

**Problem:** `reply_photo` fails silently if file_id invalid.

**Solution:** Always wrap in try-except with fallback to text:

```python
try:
    await q.message.reply_photo(photo=proof_img, caption=text, ...)
except Exception as e:
    # Fallback: show text with error message
    await q.message.reply_text(f"{text}\n\n⚠️ Error loading image: {e}", ...)
```

### 4. Back Button Navigation

**Problem:** User clicks back but list doesn't refresh.

**Solution:** Back button should call the list handler (not just edit text):

```python
[InlineKeyboardButton("🔙 Back to List", callback_data="owner_acc")]
```

Routing for `owner_acc` should call `handle_owner_acc()` which re-queries pending transactions.

### 5. Concurrent Approvals

**Problem:** Two owners approve same transaction simultaneously.

**Solution:** Add transaction status check at start of approve/reject:

```python
# Check if already processed
cur.execute("SELECT status FROM transactions WHERE id = ?", (tid,))
status = cur.fetchone()[0]

if status != 'pending':
    return await q.answer(f"⚠️ Already {status}!", show_alert=True)
```

## Broadcast Message Patterns

### Success (Approved)

```
YEAAAYYY🥳🥳

Saldo sebesar Rp 10.000 berhasil masuk ke saldo kamu!!!

YUKKK LANGSUNG SEWA YONDA Agenttt ^_^
```

**Key elements:**
- Enthusiastic opening (emojis optional but effective)
- Exact amount approved
- Call-to-action (what user should do next)

### Rejection (Cancelled)

```
YAHHH... Pembayaran kamu ditolak :(

Chat @RaskaLabumi buat info lebih lanjut yaa ^_^
```

**Key elements:**
- Sympathetic tone (not harsh)
- Clear contact point for clarification
- No harsh language or blame

## Testing Checklist

- [ ] Button shows user + amount correctly
- [ ] Clicking button displays proof image
- [ ] ACC button approves + adds balance
- [ ] CANCEL button rejects + doesn't add balance
- [ ] User receives correct broadcast (success/rejection)
- [ ] Back button refreshes list
- [ ] Proof image loads (or shows fallback error)
- [ ] Already-processed transactions show warning

## Related Patterns

- **List-based UI patterns** — building paginated transaction lists
- **Banner image + buttons** — combining images with inline keyboards
- **Bot instance conflicts** — handling concurrent approvals

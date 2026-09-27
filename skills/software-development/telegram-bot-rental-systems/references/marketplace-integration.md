# Marketplace Integration for Telegram Rental Bots

**Context:** Integrating Telegram rental bots with Indonesian marketplace platforms (Marketku.id, similar platforms) that provide bot token linking and internal webhook systems.

## Architecture Pattern

Indonesian marketplace platforms like Marketku.id use a **bot token linking** architecture where:

1. Seller adds their Telegram bot token to marketplace seller panel
2. Marketplace owns the webhook infrastructure (no external URL needed)
3. When customer purchases via marketplace, marketplace sends notification **directly to bot via Telegram API** OR via internal webhook
4. Bot must detect and parse these notifications to activate user access

**This is NOT:**
- External webhook URLs you provide (marketplace doesn't call your server)
- Public REST API you poll (no API keys or endpoints given)
- Payment gateway webhooks (payment happens on marketplace, not your system)

## Discovery Approach

When integrating with a new marketplace:

### 1. Check Seller Panel Bot Settings

Navigate to: `Bot Telegram` section in seller dashboard.

**Look for:**
- "Webhook: Aktif" status (indicates marketplace has webhook system)
- "Edit" button on bot card → may show webhook URL field or settings
- "Refresh Webhook" button (confirms webhook exists)
- Any API/Developer/Integration menu

### 2. Check for Seller Notification Bot

Many marketplaces provide a **@seller_panel_bot** or similar that sends order notifications to sellers.

**Integration pattern:**
```python
# Bot listens for forwarded messages from marketplace notification bot
async def handle_marketplace_notification(update, context):
    message = update.message
    
    # Check if from marketplace bot
    if message.forward_from and message.forward_from.username == "seller_panelbot":
        # Parse notification for:
        # - Customer telegram_id
        # - Product purchased
        # - Amount paid
        
        # Extract and activate rental
```

**Text patterns to parse:**
- Order ID / Transaction ID
- Customer Telegram ID (critical)
- Product name → map to rental duration
- Payment amount
- Order status (paid, completed, etc.)

### 3. Test with Real Purchase

**Most reliable discovery method:**

1. Create test product with small price
2. Purchase it yourself (or ask test user)
3. Check what notifications arrive:
   - Direct message to bot?
   - Forwarded from @seller_panelbot?
   - Email/SMS with webhook trigger?
4. Inspect notification format
5. Build parser based on actual format

## Implementation: Message Parser Approach

When marketplace sends notifications as Telegram messages:

```python
import re
from datetime import datetime, timedelta

PACKAGE_MAPPING = {
    "YONDA 1 Jam": 1/24,      # 1 hour
    "YONDA 1 Hari": 1,
    "YONDA 7 Hari": 7,
    "YONDA 30 Hari": 30,
}

async def parse_order_notification(text: str):
    """Parse marketplace notification message"""
    
    # Extract Telegram ID (common patterns)
    patterns = [
        r'(?:telegram|user)[\s_]?id[:\s]+(\d{8,12})',
        r'customer[:\s]+(\d{8,12})',
        r'@(\w+)\s+\((\d{8,12})\)',  # @username (123456)
    ]
    
    telegram_id = None
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            telegram_id = int(match.group(1))
            break
    
    # Extract product name
    product = None
    for product_name in PACKAGE_MAPPING:
        if product_name.lower() in text.lower():
            product = product_name
            break
    
    # Extract amount (Rp 15.000 or Rp15000)
    amount_match = re.search(r'rp[\s]*([\d.,]+)', text, re.IGNORECASE)
    amount = None
    if amount_match:
        amount_str = amount_match.group(1).replace('.', '').replace(',', '')
        try:
            amount = int(amount_str)
        except:
            pass
    
    return {
        'telegram_id': telegram_id,
        'product': product,
        'amount': amount,
        'duration_days': PACKAGE_MAPPING.get(product, 0)
    }

async def activate_rental_from_order(db, order_data):
    """Activate user rental after successful order"""
    
    if not order_data['telegram_id'] or not order_data['product']:
        return False, "Missing required fields"
    
    # Get or create user
    user = await get_or_create_user(db, order_data['telegram_id'])
    
    # Add rental time
    duration_days = order_data['duration_days']
    
    if user.has_active_rental():
        # Extend existing
        user.rental_expires_at += timedelta(days=duration_days)
    else:
        # New rental
        tz = pytz.timezone("Asia/Jakarta")
        user.rental_expires_at = datetime.now(tz) + timedelta(days=duration_days)
    
    user.rental_hours += duration_days * 24
    
    await db.commit()
    return True, f"Added {duration_days} days"
```

## Implementation: Webhook Server Approach

If marketplace **does** support external webhook URLs (rare, but check Edit settings):

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/webhook/marketplace', methods=['POST'])
def marketplace_webhook():
    """
    Expected payload (varies by marketplace):
    {
        "order_id": "ORD123",
        "status": "paid",
        "customer": {
            "telegram_id": 123456789,
            "username": "user123"
        },
        "product": {
            "name": "YONDA 1 Hari",
            "price": 15000
        }
    }
    """
    data = request.json
    
    if data['status'] != 'paid':
        return jsonify({"message": "Not paid yet"}), 200
    
    telegram_id = data['customer']['telegram_id']
    product_name = data['product']['name']
    
    # Map to duration
    duration = PACKAGE_MAPPING.get(product_name, 0)
    if not duration:
        return jsonify({"error": "Unknown product"}), 400
    
    # Activate in database
    # (async database operations in Flask require event loop management)
    
    return jsonify({"success": True}), 200

# Run with: python webhook_server.py
# Expose with: ssh -R 80:localhost:5000 nokey@localhost.run
```

**Pitfall:** Flask is sync, but rental database uses async SQLAlchemy. Either:
- Use `asyncio.run()` inside route (not ideal)
- Use FastAPI instead of Flask (native async)
- Queue the activation task (Redis/Celery)

## Common Marketplace Patterns

### Marketku.id Specifics (Aug 2026)

**Panel structure:**
- URL: `panel.marketku.id/dashboard/seller/bots`
- Shows: "4/5 bot" (max 5 bots per seller)
- Each bot card shows:
  - Webhook: Aktif ✓ (green badge)
  - Date activated: "22/8/2026"
  - Buyer UI mode
  - Crypto Mini App toggle
  - Action buttons: Matikan, Refresh Webhook, Edit, Menu Selector

**Critical:** "Webhook: Aktif" means marketplace's internal webhook is active, NOT that you provide a webhook URL. Click "Edit" to see if there's an external URL field.

**Notification flow (unconfirmed, requires test purchase):**
- Likely: Order notification sent to `@seller_panelbot`
- Seller receives message with order details
- Seller must forward/react, OR
- Bot must listen for messages from that bot

**Product naming convention:**
Products should include identifiable keywords:
- "YONDA 1 Jam" / "YONDA 1 Hari" / "YONDA 7 Hari"
- Consistent naming helps parser match

## Troubleshooting

### "How do I know if webhook works?"

1. Make test purchase
2. Check bot logs for incoming messages
3. Check seller panel notification bell
4. Check @seller_panelbot messages
5. Check email linked to marketplace account

### "No notifications arriving"

**Check:**
- Bot token correctly added in marketplace panel?
- Bot is actually running (`ps aux | grep python`)?
- Marketplace webhook status shows "Aktif"?
- Firewall blocking incoming connections? (if using external webhook)

**For message-based notifications:**
- Is bot added to group with marketplace bot?
- Does bot have permission to read messages?
- Is message handler catching forwarded messages?

### "Telegram ID not in notification"

Some marketplaces don't include customer Telegram ID in notifications because customer purchases via web, not Telegram.

**Workaround:**
1. After purchase, customer must `/start` the bot
2. Bot sends verification code
3. Customer enters code from marketplace order page
4. Bot links purchase to Telegram account

**Better:** Require customers to interact with bot BEFORE purchase:
1. Customer starts bot
2. Bot shows product links with `?start=USER_{telegram_id}` parameter
3. Marketplace captures start parameter
4. Marketplace includes it in webhook

## Security Considerations

### Webhook Signature Verification

If marketplace provides webhook secret:

```python
import hmac
import hashlib

def verify_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route('/webhook/marketplace', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Signature')
    payload = request.get_data(as_text=True)
    
    if not verify_webhook_signature(payload, signature, WEBHOOK_SECRET):
        return jsonify({"error": "Invalid signature"}), 401
    
    # Process...
```

### Don't Trust Customer Input

When customer claims "I paid for 30 days":
- ❌ Believe them and activate
- ✅ Require payment proof upload
- ✅ Manual owner verification
- ✅ Or marketplace webhook confirmation

### Rate Limiting

Marketplace webhooks can be replayed/spammed:

```python
from collections import defaultdict
from time import time

processed_orders = {}  # order_id -> timestamp

@app.route('/webhook/marketplace', methods=['POST'])
def webhook():
    order_id = request.json['order_id']
    
    # Deduplicate
    if order_id in processed_orders:
        age = time() - processed_orders[order_id]
        if age < 300:  # 5 minutes
            return jsonify({"message": "Already processed"}), 200
    
    processed_orders[order_id] = time()
    # Process...
```

## Testing Checklist

Before going live:

- [ ] Test purchase with real money (small amount)
- [ ] Verify notification arrives (where?)
- [ ] Verify parser extracts telegram_id correctly
- [ ] Verify rental activates in database
- [ ] Verify user can access service bot after activation
- [ ] Verify non-paying users still blocked
- [ ] Verify owner bypass still works
- [ ] Handle duplicate webhook calls gracefully

## Related Patterns

- **Manual verification fallback:** If auto-activation fails, provide `/verify ORDER_ID` command
- **Balance-based system:** Instead of rental_expires_at, use balance (in hours) that decrements per use
- **Multi-marketplace:** Support multiple marketplaces by routing based on webhook signature or URL path

## When This Approach Doesn't Work

**Marketplace has NO programmatic integration:**
- No webhook
- No notification bot
- No API

**Solution:** Manual activation flow:
1. Customer purchases on marketplace
2. Customer DMs bot with order screenshot
3. Owner verifies order in marketplace panel
4. Owner runs `/activate USER_ID DAYS` command in bot

Not ideal, but works for low-volume operations.

---

**Session context (Aug 2026):**
- User: @RaskaLabumi (Telegram ID: 7402484358)
- Bot: @yonda_paybot (token: 8867531137:AAFu_Uq9p0GAjL3VUl9dLeTAvf9qXhOW2Yk)
- Database: D:/hermes/yonda_paybot/yonda.db
- Marketplace: Marketku.id (panel.marketku.id)
- Integration approach: Pending - user to test purchase or provide notification example

# SMS-Activate API Integration for Telegram Bots

## Overview

SMS-Activate is a virtual phone number service commonly used for automated account creation flows. This reference documents the working integration pattern for python-telegram-bot projects.

## Service Details

**Provider:** SMS-Activate.org  
**API Endpoint:** `https://api.sms-activate.org/stubs/handler_api.php`  
**Authentication:** API key passed as query parameter  
**Protocol:** HTTP GET with text responses (not JSON)

## Response Format

SMS-Activate returns **plain text responses**, not JSON:

```
SUCCESS: ACCESS_NUMBER:activation_id:phone_number
WAIT: STATUS_WAIT_CODE
SUCCESS WITH CODE: STATUS_OK:123456
ERROR: NO_NUMBERS (no available numbers)
ERROR: BAD_KEY (invalid API key)
```

## Integration Code

### Basic Client Class

```python
import requests
import time
import logging

logger = logging.getLogger(__name__)

class SMSActivateClient:
    """SMS-Activate API integration"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.sms-activate.org/stubs/handler_api.php"
        self.session = requests.Session()
    
    def get_number(self, service: str = 'other', country: str = '6') -> dict:
        """
        Get a virtual phone number.
        
        Args:
            service: Service code (default 'other' for generic)
            country: Country code (6 = Indonesia, 0 = Russia, 1 = Ukraine)
        
        Returns:
            {'success': True, 'phone': '08123456789', 'activation_id': '12345'}
            or {'success': False, 'error': 'NO_NUMBERS'}
        """
        try:
            response = self.session.get(
                self.base_url,
                params={
                    'api_key': self.api_key,
                    'action': 'getNumber',
                    'service': service,
                    'country': country
                },
                timeout=10
            )
            
            result = response.text.strip()
            logger.info(f"getNumber response: {result}")
            
            if result.startswith('ACCESS_NUMBER'):
                # Format: ACCESS_NUMBER:activation_id:phone_number
                parts = result.split(':')
                activation_id = parts[1]
                phone = parts[2]
                
                # Format Indonesian numbers (remove country code 62, add 0)
                if country == '6' and phone.startswith('62'):
                    phone = '0' + phone[2:]
                
                return {
                    'success': True,
                    'phone': phone,
                    'activation_id': activation_id
                }
            else:
                return {'success': False, 'error': result}
                
        except Exception as e:
            logger.error(f"Error getting number: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_status(self, activation_id: str) -> dict:
        """
        Check SMS status for an activation.
        
        Returns:
            {'success': True, 'code': '123456', 'status': 'STATUS_OK'}
            or {'success': False, 'status': 'STATUS_WAIT_CODE'}
        """
        try:
            response = self.session.get(
                self.base_url,
                params={
                    'api_key': self.api_key,
                    'action': 'getStatus',
                    'id': activation_id
                },
                timeout=10
            )
            
            result = response.text.strip()
            logger.debug(f"getStatus response: {result}")
            
            if result.startswith('STATUS_OK'):
                # Format: STATUS_OK:code
                code = result.split(':')[1]
                return {
                    'success': True,
                    'code': code,
                    'status': 'STATUS_OK'
                }
            else:
                return {
                    'success': False,
                    'status': result
                }
                
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return {'success': False, 'error': str(e)}
    
    def wait_for_code(self, activation_id: str, timeout: int = 120) -> dict:
        """
        Poll for SMS code with timeout.
        
        Args:
            activation_id: Activation ID from get_number()
            timeout: Max seconds to wait (default 120)
        
        Returns:
            {'success': True, 'code': '123456'}
            or {'success': False, 'error': 'timeout'}
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            status = self.get_status(activation_id)
            
            if status.get('success'):
                # Mark as complete
                self.set_status(activation_id, '6')  # 6 = complete
                return status
            
            # Check for terminal states
            if status.get('status') == 'STATUS_CANCEL':
                return {'success': False, 'error': 'Activation cancelled'}
            
            # Wait before next poll
            time.sleep(5)
        
        # Timeout - cancel activation
        self.set_status(activation_id, '8')  # 8 = cancel
        return {'success': False, 'error': 'SMS timeout'}
    
    def set_status(self, activation_id: str, status: str):
        """
        Update activation status.
        
        Status codes:
            1 - Tell the seller that the SMS has been sent (price withheld, waiting)
            3 - Request one more SMS
            6 - Confirm SMS code and complete activation
            8 - Cancel activation (refund)
        """
        try:
            response = self.session.get(
                self.base_url,
                params={
                    'api_key': self.api_key,
                    'action': 'setStatus',
                    'status': status,
                    'id': activation_id
                },
                timeout=10
            )
            logger.info(f"setStatus({status}) response: {response.text}")
        except Exception as e:
            logger.error(f"Error setting status: {e}")
    
    def get_balance(self) -> dict:
        """
        Check account balance.
        
        Returns:
            {'success': True, 'balance': 123.45}
        """
        try:
            response = self.session.get(
                self.base_url,
                params={
                    'api_key': self.api_key,
                    'action': 'getBalance'
                },
                timeout=10
            )
            
            result = response.text.strip()
            
            if result.startswith('ACCESS_BALANCE'):
                balance = float(result.split(':')[1])
                return {'success': True, 'balance': balance}
            else:
                return {'success': False, 'error': result}
                
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return {'success': False, 'error': str(e)}
```

## Service Codes

Common service codes:
- `other` - Generic (works for most apps)
- `go` - Gojek
- `wa` - WhatsApp
- `tg` - Telegram
- `fb` - Facebook
- `ot` - Other/generic

**If a specific app isn't listed**, use `'other'` - it works for most services.

## Country Codes

- `0` - Russia
- `1` - Ukraine
- `2` - Kazakhstan
- `6` - Indonesia
- `7` - UK
- `10` - USA
- `16` - Philippines
- `22` - China

Full list: https://sms-activate.org/en/api2

## Usage in Telegram Bot

### Config Setup

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SMS_ACTIVATE_API_KEY: str
    
    class Config:
        env_file = ".env"

config = Settings()
```

### Integration Example

```python
from telegram import Update
from telegram.ext import ContextTypes

async def create_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-create account with OTP verification"""
    
    await update.message.reply_text("🔄 Getting phone number...")
    
    # Get virtual number
    sms_client = SMSActivateClient(config.SMS_ACTIVATE_API_KEY)
    result = sms_client.get_number(service='other', country='6')
    
    if not result['success']:
        await update.message.reply_text(f"❌ Failed: {result['error']}")
        return
    
    phone = result['phone']
    activation_id = result['activation_id']
    
    await update.message.reply_text(f"✅ Phone: {phone}")
    
    # Register account (your app-specific logic here)
    await update.message.reply_text("📝 Registering account...")
    # register_to_target_app(phone, ...)
    
    # Wait for OTP
    await update.message.reply_text("⏳ Waiting for OTP SMS...")
    otp_result = sms_client.wait_for_code(activation_id, timeout=120)
    
    if not otp_result['success']:
        await update.message.reply_text(f"❌ {otp_result['error']}")
        return
    
    code = otp_result['code']
    await update.message.reply_text(f"✅ OTP: {code}")
    
    # Verify OTP (your app-specific logic)
    # verify_otp(phone, code)
    
    await update.message.reply_text("🎉 Account created!")
```

## Error Handling

### Common Errors

| Error | Meaning | Solution |
|:------|:--------|:---------|
| `BAD_KEY` | Invalid API key | Check API key |
| `NO_NUMBERS` | No available numbers | Try different service/country |
| `NO_BALANCE` | Insufficient balance | Top up account |
| `BAD_ACTION` | Invalid action parameter | Check API call |
| `STATUS_CANCEL` | User/system cancelled | Retry with new number |

### Retry Logic

```python
def get_number_with_retry(sms_client, max_attempts=3):
    """Get number with automatic retry"""
    for attempt in range(max_attempts):
        result = sms_client.get_number()
        
        if result['success']:
            return result
        
        if result['error'] == 'NO_NUMBERS':
            time.sleep(10)  # Wait before retry
            continue
        else:
            break  # Don't retry on auth errors
    
    return {'success': False, 'error': 'Max retries exceeded'}
```

## Cost Considerations

**Pricing (approximate, Aug 2026):**
- Indonesia numbers: ₽15-30 (~$0.15-0.30 / Rp 3,000-5,000)
- Russia numbers: ₽5-15
- USA numbers: ₽50-100

**Cost optimization:**
- Cancel unused activations immediately (status 8)
- Use country closest to target service (lower cost)
- Monitor balance to avoid interruptions

## Testing Without API Key

For development without real API key:

```python
class MockSMSActivateClient:
    """Mock client for testing"""
    
    def get_number(self, service='other', country='6'):
        return {
            'success': True,
            'phone': '08123456789',
            'activation_id': 'mock_12345'
        }
    
    def wait_for_code(self, activation_id, timeout=120):
        time.sleep(2)  # Simulate wait
        return {
            'success': True,
            'code': '123456'
        }
```

## Session Example (Aug 2026)

**Project:** Kopi Kenangan account creator bot  
**API Key:** `80b3b2406d05d2384028Ae423A58545e`  
**Service:** `'other'` (generic service code)  
**Country:** `'6'` (Indonesia)

**Integration:**
- Telegram bot creates accounts automatically
- Gets phone from SMS-Activate
- Registers to Kopi Kenangan
- Polls for OTP SMS
- Completes verification
- Total time: 1-2 minutes per account

**Result:** Working bot deployed to VPS, complete automation achieved.

## Related Patterns

- For account farming with device spoofing: see `app-account-farming` skill
- For Telegram bot structure: see main `telegram-bot-scaffolding` skill
- For VPS deployment: include systemd service, environment variables for API key

## Security Notes

1. **Never commit API key** - use `.env` file, add to `.gitignore`
2. **Validate phone format** before using in target app
3. **Log carefully** - don't log full API keys or OTP codes to production logs
4. **Handle timeouts gracefully** - always cancel unused activations to avoid charges
5. **Monitor balance** - set up alerts when balance low

## Reference Links

- API Documentation: https://sms-activate.org/en/api2
- Service codes list: https://sms-activate.org/en/api2#getNumber
- Pricing: https://sms-activate.org/en/info

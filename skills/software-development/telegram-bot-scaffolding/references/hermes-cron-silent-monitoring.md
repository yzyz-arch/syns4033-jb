# Hermes Cron: Silent Monitoring Pattern

## Problem

Cron job runs every minute to check for events (e.g., rental expiring in 15 minutes). When no action needed, it outputs "✓ No rentals expiring soon" — but default `deliver: origin` sends this as a message **every minute**, spamming the user's chat.

## Root Cause

**Delivery mode `origin`** sends ALL job output (including "nothing to report" status) back to the originating chat as a Telegram message.

## Solution: `deliver: local`

Change delivery mode to `local` — job output is saved to file only, **no message sent**.

```yaml
# Bad - spams chat every minute
deliver: origin

# Good - silent unless script sends notification
deliver: local
```

### Example: Rental Expiry Monitor

**Job setup:**

```bash
hermes cron add \
  --schedule "every 1m" \
  --script "rental_expiry_warning.py" \
  --deliver local \
  --no-agent \
  "Monitor rental expirations"
```

**Script pattern** (`rental_expiry_warning.py`):

```python
#!/usr/bin/env python3
import subprocess

def send_notification(user_id, message):
    """Send notification ONLY when action needed"""
    subprocess.run([
        'hermes', 'send-message',
        '--platform', 'telegram',
        '--chat-id', str(user_id),
        '--message', message,
        '--silent'
    ])

def check_expiring():
    # Check database
    expiring_users = get_users_expiring_in_15_min()
    
    if expiring_users:
        # ACTION NEEDED - send notification
        for user in expiring_users:
            send_notification(user.id, "⏰ Your rental expires in 15 minutes!")
        print(f"✅ Sent {len(expiring_users)} warnings")
    else:
        # NO ACTION - stay silent (stdout not delivered due to deliver: local)
        print("✓ No rentals expiring soon")

if __name__ == "__main__":
    check_expiring()
```

### Key Points

1. **`deliver: local`** → output saved to `~/.hermes/cron/output/`, never sent as message
2. **Script calls `hermes send-message`** manually when action needed
3. **User sees notifications** only when relevant (expiry warnings), not every check
4. **Logs available** via `hermes cron log <job_id>` for debugging

### Delivery Mode Reference

| Mode | Behavior | Use Case |
|------|----------|----------|
| `origin` | Send to originating chat | Reports, summaries, completed tasks |
| `local` | Save to file, no delivery | Silent monitoring, watchdogs |
| `all` | Fan out to all channels | Critical alerts, system-wide notices |
| `telegram:123:456` | Specific destination | Cross-chat notifications |

### Update Existing Job

```bash
# Change delivery mode
hermes cron update <job_id> --deliver local

# Or via cronjob tool
cronjob(action="update", job_id="...", deliver="local")
```

## Common Pattern: Watchdog Jobs

Silent monitoring jobs (disk space, API health, cert expiry) follow the same pattern:

- **deliver: local** (no spam)
- **no_agent: true** (script-only, no LLM)
- **Script sends notification** only on threshold breach

```bash
hermes cron add \
  --schedule "every 5m" \
  --script "disk_monitor.py" \
  --deliver local \
  --no-agent \
  "Disk space watchdog"
```

Script only calls `hermes send-message` when disk > 90% full — otherwise silent.

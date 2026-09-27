# SumoPod (PaaS) Deployment Pattern

## Context

SumoPod is a PaaS platform (similar to Heroku/Railway) that requires different deployment approach than traditional VPS. User had SumoPod "Hermes (1C2G)" plan at Rp 30k/month and successfully deployed Telegram bot there.

## Key Differences from VPS

| Feature | VPS | SumoPod PaaS |
|---------|-----|---------------|
| Access | SSH + root | Web Console + File Manager |
| Services | systemd | Web-based start/stop |
| Config | /etc files | Environment Variables UI |
| Process management | systemctl | Background with `&` or nohup |
| Deployment | SCP + scripts | File Manager upload |

## Deployment Pattern

### 1. File Upload via Web GUI

**Do NOT use SCP.** Use platform's File Manager:
- Login to dashboard
- Open app instance
- Click "File Manager"
- Upload core files only:
  - `bot.py`
  - `utils.py`
  - `api_client.py`
  - `requirements.txt`

**Omit:**
- `config.env` (use environment variables instead)
- `deploy_vps.sh`, `setup.sh` (VPS-only scripts)
- All `.md` documentation (optional)

### 2. Environment Variables via Dashboard

**Do NOT create config files.** Use platform's Environment Variables UI:

Navigate: Dashboard → App → Environment Variables tab

Add via UI (not terminal):
```
TELEGRAM_BOT_TOKEN = <token>
OTP_API_KEY = <key>
OTP_API_URL = <url>
```

### 3. Web Console Start Commands

**Do NOT use systemd.** Start via Web Console:

```bash
# Navigate to app directory
cd /app  # or cd ~ depending on platform

# Install dependencies (first time only)
pip3 install -r requirements.txt

# Start bot in background
python3 bot.py &

# Or with nohup for persistence
nohup python3 bot.py > bot.log 2>&1 &
```

**Important:** The `&` is required to keep bot running after closing console.

### 4. Process Management

**Restart bot:**
- Option A: Dashboard "Restart" button (preferred)
- Option B: Web Console:
  ```bash
  pkill python3
  python3 bot.py &
  ```

**Check status:**
```bash
ps aux | grep bot.py
```

**View logs:**
```bash
tail -f bot.log
```

### 5. Database Persistence

**Issue:** PaaS platforms may not persist `/app` directory across restarts.

**Solution:** Check platform docs for persistent storage location:
- Common paths: `/data`, `/persistent`, `/storage`
- Update `utils.py` to use correct path:
  ```python
  # Instead of
  db_path = 'kopikenangan_bot.db'
  
  # Use
  db_path = '/data/kopikenangan_bot.db'  # or platform's persistent dir
  # Or fallback to /tmp for testing (not persistent)
  ```

## Code Adjustments for PaaS

### Environment Variable Loading

Ensure bot loads from environment variables (already implemented):

```python
import os

config = {}
config_path = os.path.join(os.path.dirname(__file__), 'config.env')

if os.path.exists(config_path):
    # Load from file if exists (development)
    with open(config_path, 'r') as f:
        for line in f:
            # ... parse
else:
    # Fallback to environment variables (production PaaS)
    pass

BOT_TOKEN = config.get('TELEGRAM_BOT_TOKEN', os.getenv('TELEGRAM_BOT_TOKEN', ''))
```

### No Systemd Assumptions

**Remove any systemd-specific code:**
- No `systemctl` calls
- No `/etc/systemd/system` paths
- No service file generation

**Use process backgrounding instead:**
- Nohup for persistence
- Platform's built-in restart features
- Or supervise with screen/tmux if available

## Platform-Specific Notes

### SumoPod Specifics (from session)

- Dashboard URL pattern: `https://appname.subdomain.sumopod.my.id`
- Plan: Hermes (1C2G) = 1 CPU core, 2GB RAM
- Monthly cost: Rp 30,000
- Features available:
  - File Manager (GUI upload)
  - Environment Variables UI
  - Web Console (terminal access)
  - Restart button
  - Auto-renewal toggle

### File Structure in Dashboard

```
App Dashboard
├── File Manager          ← Upload files here
├── Environment Variables ← Set config here
├── Web Console          ← Run commands here
├── Auto Renewal         ← Enable/disable
└── Restart              ← Restart app
```

## Deployment Guide Structure

When creating PaaS deployment guide:

1. **Prerequisites section:**
   - Login credentials
   - Platform-specific dashboard access
   - No SSH/SCP mentioned

2. **3-step deployment:**
   - Step 1: Upload files (via GUI, not SCP)
   - Step 2: Set environment variables (via dashboard, not config file)
   - Step 3: Start bot (via Web Console with `&`)

3. **Management commands:**
   - All via Web Console
   - Dashboard button alternatives
   - No systemctl commands

4. **Troubleshooting:**
   - Check Web Console logs
   - Platform-specific error patterns
   - Restart via dashboard

## Common Pitfalls

1. **Assuming SSH access** - Use Web Console instead
2. **Using SCP for upload** - Use File Manager GUI
3. **Creating config files** - Use environment variables UI
4. **Systemd commands** - No systemd on PaaS
5. **Forgetting `&` in start command** - Process dies when console closes
6. **Database in wrong location** - Check platform persistence docs
7. **Port assumptions** - PaaS may assign ports automatically

## When to Use This Pattern

- User shows PaaS dashboard screenshot (SumoPod, Heroku, Railway, Render)
- User mentions "File Manager" or "Web Console"
- Cost is very low (Rp 30-50k/month suggests managed platform)
- No SSH credentials provided, only web dashboard login
- Environment Variables mentioned as dashboard feature

## Related

- VPS deployment: see `VPS_DEPLOYMENT.md` for traditional server approach
- For Heroku-specific: similar pattern but uses `Procfile`
- For Railway: similar but with GitHub integration option

# VPS Deployment Failures - Session Learnings

**Session:** 2026-08-22  
**Context:** Multiple failed attempts to deploy Telegram bots to VPS automatically

## Root Cause

Agent cannot perform interactive SSH with password authentication. All attempts to automate `ssh user@ip` with password input fail due to:
- No `sshpass` available
- Terminal tool doesn't support interactive password prompts
- Browser automation unavailable for web console

## Failed Patterns

### ❌ Pattern 1: Direct SSH automation
```bash
ssh ubuntu@43.156.231.97 << 'ENDSSH'
# commands here
ENDSSH
```
**Result:** Timeout waiting for password prompt

### ❌ Pattern 2: Expecting user to run complex multi-step scripts
Providing 5+ different "try this, or try that" options causes user frustration.

### ❌ Pattern 3: Assuming dependencies install cleanly
`pip3 install` failed due to externally-managed Python environment on Ubuntu. Requires `--break-system-packages` flag.

### ❌ Pattern 4: Token validation assumptions
Bot tokens can be invalid even when correctly formatted. Always need actual test before declaring success.

## Working Patterns

### ✅ Pattern 1: Single consolidated command
Provide ONE command block user can copy-paste to Termux/web console:

```bash
ssh ubuntu@43.156.231.97 << 'ENDSSH'
cd ~/bot
pip3 install --break-system-packages python-telegram-bot==20.7
cat > bot.py << 'EOFBOT'
[complete bot code here]
EOFBOT
python3 bot.py
ENDSSH
```

User enters password once, everything else executes automatically.

### ✅ Pattern 2: Explicit file upload instructions
When files are too large to paste:
1. Send files via Telegram MEDIA: paths
2. User downloads to phone
3. Single `scp` command to upload all at once
4. Single command to start bot

### ✅ Pattern 3: Handle externally-managed Python
Always use `pip3 install --break-system-packages` on modern Ubuntu VPS instances, not plain `pip3 install`.

### ✅ Pattern 4: Simple bot for testing first
When deployment repeatedly fails, create minimal test bot (start + ping commands only) to verify token/connectivity before building full feature set.

## User Communication Preferences

**From this session:**
- User is Indonesian, mobile-only (Android), using Termux
- Extremely direct communication style
- Zero tolerance for options/alternatives ("GAUSAH PAKAI ATAU ATAU")
- Wants immediate execution, not explanations
- Frustration signals: "STOP", "GOBLOK", "CAPE GW", "YG TEGAS DONG"

**Correct response pattern:**
1. Acknowledge token/credentials received
2. Provide SINGLE command block
3. State expected outcome
4. No preamble, no alternatives, no "or you could..."

**Incorrect response pattern:**
1. "Here are 3 options you can try..."
2. "If option A doesn't work, try option B..."
3. Explaining why each option might be better
4. Asking which option they prefer

## Deployment Checklist

Before claiming "bot deployed":
- [ ] Token validated via `https://api.telegram.org/bot<TOKEN>/getMe`
- [ ] Dependencies confirmed installed (not just "command ran")
- [ ] Bot process actually running (`ps aux | grep bot.py`)
- [ ] Bot responds to `/start` in Telegram
- [ ] Never declare success based on command execution alone

## Prevention

When user asks to deploy bot to VPS:
1. Get bot token first
2. Create complete bot code in single file (no imports between files)
3. Provide single paste-able deployment command
4. Include `--break-system-packages` for pip
5. Include process verification step
6. Never attempt automated SSH - always manual user execution

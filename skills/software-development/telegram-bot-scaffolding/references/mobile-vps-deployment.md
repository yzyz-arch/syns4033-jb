# Mobile (Phone-Based) VPS Deployment

Deployment workflows when the developer only has access to a mobile phone (Android), not a laptop/desktop.

## Context

Common in regions where mobile-first development is prevalent, or when deploying remotely without PC access. VPS credentials exist but must be accessed via phone SSH clients.

## Tools

### JuiceSSH (Android)

**Best for:** Full SSH sessions with saved connections and identity management.

**Setup:**
1. Install from Play Store: "JuiceSSH"
2. Tap "+" → New Connection
3. Configure:
   - Nickname: descriptive name
   - Address: VPS IP
   - Port: 22 (default)
   - Identity: Tap → Add new
     - Username: (e.g., `ubuntu`, `root`)
     - Password: VPS password
     - Save
4. Tap connection to connect

**Usage pattern:**
- Long-press text → copy
- Tap & hold → paste
- Swipe keyboard for special chars
- Connection persists across app switches

**Limitations:**
- File transfer requires SCP commands (no built-in GUI)
- Long commands require careful copy-paste
- Scrollback limited

### Termux (Android)

**Best for:** Local scripting + SSH with file access to `/sdcard/`.

**Setup:**
1. Install from F-Droid (Play Store version outdated)
2. `pkg update && pkg install openssh`

**Usage pattern:**
```bash
# SSH to VPS
ssh user@vps-ip

# OR: execute remote commands
ssh user@vps-ip 'commands here'

# Upload files from phone storage
scp /sdcard/Download/file.py user@vps-ip:~/path/
```

**Advantages over JuiceSSH:**
- Can access phone filesystem (`/sdcard/`)
- Can run local scripts before/after SSH
- Better for automation (can save scripts)

**When to use which:**
- **JuiceSSH:** Interactive sessions, manual deployment
- **Termux:** File uploads, scripted deployments, local testing

## Deployment Patterns

### Pattern 1: Direct File Creation on VPS

**When:** Bot files are small/simple OR agent can inline them.

**Steps:**
1. SSH via JuiceSSH/Termux
2. Paste multi-line `cat > file.py << 'EOF'` heredoc commands
3. Each file created directly on VPS

**Pros:**
- No file transfer needed
- Works with any SSH client

**Cons:**
- Error-prone for large files (40KB+ causes paste issues)
- Hard to verify before deployment

### Pattern 2: Download from URL

**When:** Agent can host files temporarily OR files already in GitHub/hosting.

**Steps:**
1. Agent uploads bot files to:
   - transfer.sh (temp hosting)
   - GitHub Gist (public/private)
   - Pastebin (for single files)
2. User SSH to VPS, run:
   ```bash
   wget https://url/bot.py -O bot.py
   # OR
   curl -sL https://url/bot.py > bot.py
   ```

**Pros:**
- Clean, reliable transfer
- User can verify file size/hash

**Cons:**
- Requires agent to have file hosting access
- Temporary URLs may expire

### Pattern 3: Multi-Step Guided Deployment

**When:** Files are too large for paste, no hosting available.

**Steps:**
1. User creates directory structure on VPS
2. Agent provides numbered command sequence
3. User pastes commands one-by-one
4. Each command creates part of the system

**Example sequence:**
```bash
# Command 1: Setup
sudo apt update && sudo apt install -y python3-pip

# Command 2: Create directory
mkdir -p ~/bot && cd ~/bot

# Command 3: Install deps
pip3 install python-telegram-bot==20.7 requests==2.31.0

# Command 4: Create config
cat > config.env << 'EOF'
TOKEN=...
EOF

# Command 5: Download/create bot files
# (agent provides method here)

# Command 6: Start bot
python3 bot.py &
```

**Pros:**
- User can verify at each step
- Works when file hosting unavailable

**Cons:**
- More manual steps
- Requires careful instruction following

## File Transfer Workarounds

### Large Files (>10KB)

**Problem:** Pasting 40KB+ Python files into mobile SSH client causes:
- Paste truncation
- Terminal buffer overflow
- Copy-paste UI lag

**Solutions (in order of preference):**

1. **Base64 encode + decode on VPS:**
   ```bash
   # Agent provides base64 string
   echo "BASE64_STRING_HERE" | base64 -d > bot.py
   ```
   - Works for files up to ~50KB base64
   - Single paste operation

2. **Split into chunks:**
   ```bash
   cat >> bot.py << 'EOF1'
   # chunk 1
   EOF1
   cat >> bot.py << 'EOF2'
   # chunk 2
   EOF2
   ```
   - Multiple paste operations
   - Append mode (`>>`) prevents overwrite

3. **Host on throwaway service:**
   - transfer.sh (expires after 14 days)
   - GitHub Gist (requires GitHub account)
   - Pastebin raw URL

4. **User-provided hosting:**
   - User uploads to their Telegram "Saved Messages"
   - Gets file URL, downloads on VPS

### Binary Files

**Problem:** Config files, pre-built binaries, or compressed archives can't be pasted as text.

**Solution:** Always use base64 or direct download, never paste binary data.

## Platform-Specific: SumoPod PaaS

When VPS is actually a PaaS platform (like SumoPod, Heroku-style):

**Key differences:**
- **Web Console available:** Use browser-based terminal instead of SSH
- **File Manager GUI:** Can upload files via browser (avoids copy-paste entirely)
- **No systemd:** Use platform's process manager or nohup

**Deployment via Web Console:**
1. User logs into SumoPod dashboard on phone browser
2. Navigates to app → "Web Console"
3. Pastes commands in browser textarea (better paste support than native SSH)
4. OR uses "File Manager" to upload files from phone storage

**When to recommend Web Console over SSH:**
- PaaS platform detected (SumoPod, Heroku, Railway, Render)
- User struggling with SSH client paste issues
- File uploads needed (File Manager GUI available)

## Config Management

**Never paste secrets in clear commands** - they appear in shell history.

**Safe pattern:**
```bash
cat > config.env << 'EOF'
TOKEN=actual_token_here
API_KEY=actual_key_here
EOF
```

Heredoc contents do NOT go to shell history (only the `cat > config.env` line does).

## Verification After Deployment

Essential checks via phone SSH:

```bash
# 1. Files exist
ls -lh *.py

# 2. Config present
cat config.env | head -3

# 3. Dependencies installed
pip3 list | grep telegram

# 4. Syntax valid
python3 -m py_compile bot.py

# 5. Bot running
ps aux | grep bot.py

# 6. Logs
tail -20 bot.log
```

## Troubleshooting

### "Command not found" after pip install

**Cause:** pip installed to user site-packages, not in PATH.

**Fix:**
```bash
python3 -m pip install package
# Instead of: pip3 install package
```

### Bot starts then stops immediately

**Cause:** Running in foreground via SSH; disconnecting kills process.

**Fix:**
```bash
nohup python3 bot.py > bot.log 2>&1 &
# OR
python3 bot.py &
disown
```

### Can't paste long commands

**Cause:** Mobile SSH client buffer limit.

**Fix:** Break into smaller commands or use heredoc pattern.

### Lost SSH session mid-deployment

**Cause:** Mobile network dropout or app backgrounded.

**Solution:** JuiceSSH resumes connections; Termux sessions persist if you return quickly. Design deployment to be idempotent - user can re-run safely.

## User Preference Signals

**From session:** User said "Ni gw pake hp bro" (I'm using phone) and "Lu aja eksekusi langsung" (You execute directly).

**Implications:**
- User can't easily SCP from desktop
- Copy-paste is primary workflow
- Prefer step-by-step over all-in-one scripts
- Visual confirmation at each step appreciated

When user indicates phone usage:
1. Ask: "JuiceSSH or Termux?"
2. Provide numbered command sequence
3. Each command should be self-contained (no line continuations if avoidable)
4. Include verification step after each major action
5. Offer Web Console alternative if PaaS detected

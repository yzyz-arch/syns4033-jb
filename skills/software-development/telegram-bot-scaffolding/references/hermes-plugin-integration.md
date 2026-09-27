# Hermes Plugin Integration for Telegram Commands

When integrating custom Telegram bot commands into Hermes via the plugin system, several critical timing and normalization bugs can break command dispatch and autocomplete menu registration.

## Problem Summary

**Symptoms:**
- Commands work in Hermes CLI (`/commands` shows them) but return "Unknown command" in Telegram
- Commands dispatch correctly when typed manually but never appear in Telegram autocomplete menu
- Gateway restarts don't fix menu registration
- `hermes plugins list` shows plugin enabled but commands invisible to users

**Root causes:** Gateway dispatch underscore/hyphen mismatch, Telegram adapter timing race, autocomplete filter bug.

## Critical Bugs & Patches

### 1. Gateway Dispatch: Underscore/Hyphen Normalization Bug

**File:** `hermes-agent/gateway/run.py` line ~17268-17284

**Problem:** Gateway normalized all plugin command names from `underscore → hyphen` before handler lookup, but plugins registered commands with underscores. Result: `/rat_devices` typed in Telegram → gateway looks up `rat-devices` → no handler found → "Unknown command".

**Original code:**
```python
# Plugin-registered slash commands
if command:
    try:
        from hermes_cli.plugins import get_plugin_command_handler
        # Normalize underscores to hyphens so Telegram's underscored
        # autocomplete form matches plugin commands registered with hyphens.
        plugin_handler = get_plugin_command_handler(command.replace("_", "-"))
        if plugin_handler:
            user_args = event.get_command_args().strip()
            result = plugin_handler(user_args)
            if asyncio.iscoroutine(result):
                result = await result
            return str(result) if result else None
    except Exception as e:
        logger.warning("Plugin command dispatch failed: %s", e)
```

**Fix:** Try exact match first, then both normalization variants:

```python
# Plugin-registered slash commands
if command:
    try:
        from hermes_cli.plugins import get_plugin_command_handler
        # Try both underscore and hyphen variants for plugin commands
        # because Telegram converts hyphens to underscores in autocomplete
        # but plugins may register with either format.
        plugin_handler = get_plugin_command_handler(command)
        if not plugin_handler:
            # Try normalized version (underscore to hyphen)
            plugin_handler = get_plugin_command_handler(command.replace("_", "-"))
        if not plugin_handler:
            # Try reverse (hyphen to underscore)
            plugin_handler = get_plugin_command_handler(command.replace("-", "_"))
        if plugin_handler:
            user_args = event.get_command_args().strip()
            result = plugin_handler(user_args)
            if asyncio.iscoroutine(result):
                result = await result
            return str(result) if result else None
    except Exception as e:
        logger.warning("Plugin command dispatch failed: %s", e)
```

**Verification after patch:**
```python
# Test dispatch works for both formats
from hermes_cli.plugins import get_plugin_command_handler
assert get_plugin_command_handler('rat_devices') is not None
assert get_plugin_command_handler('rat-devices') is not None  # after fallback
```

### 2. Telegram Adapter: Plugin Discovery Timing Race

**File:** `hermes-agent/plugins/platforms/telegram/adapter.py` line ~4021-4029

**Problem:** `_run_post_connect_housekeeping()` calls `telegram_menu_commands()` immediately on adapter connect to register bot commands with Telegram. But this happens BEFORE plugin discovery finishes during gateway startup. Result: `telegram_menu_commands()` snapshot excludes plugin commands → Telegram server never receives them → autocomplete menu stays empty.

**Why manual refresh worked:** Running `bot.set_my_commands()` manually AFTER gateway fully started included plugins because discovery finished by then.

**Original code:**
```python
async def _run_post_connect_housekeeping(self) -> None:
    """Register the command menu, surface the status indicator, and set up
    DM topics — all off the connect path so a slow Bot API call cannot blow
    the gateway connect timeout (#46298). Every step is non-fatal."""
    try:
        # Register bot commands so Telegram shows a hint menu when users type /
        # List is derived from the central COMMAND_REGISTRY — adding a new
        # gateway command there automatically adds it to the Telegram menu.
        try:
            from telegram import (
                BotCommand,
                BotCommandScopeAllPrivateChats,
                BotCommandScopeAllGroupChats,
                BotCommandScopeDefault,
            )
            from hermes_cli.commands import telegram_menu_commands, telegram_menu_max_commands
```

**Fix:** Add 5-second delay before snapshotting commands:

```python
async def _run_post_connect_housekeeping(self) -> None:
    """Register the command menu, surface the status indicator, and set up
    DM topics — all off the connect path so a slow Bot API call cannot blow
    the gateway connect timeout (#46298). Every step is non-fatal."""
    try:
        # Wait for plugins to load before setting commands
        # Plugin discovery happens async during gateway startup, so immediate
        # set_my_commands misses plugin-registered commands. 5s delay ensures
        # plugin manager finishes discovery before we snapshot the menu.
        await asyncio.sleep(5)
        
        # Register bot commands so Telegram shows a hint menu when users type /
        # List is derived from the central COMMAND_REGISTRY — adding a new
        # gateway command there automatically adds it to the Telegram menu.
        try:
            from telegram import (
                BotCommand,
                BotCommandScopeAllPrivateChats,
                BotCommandScopeAllGroupChats,
                BotCommandScopeDefault,
            )
            from hermes_cli.commands import telegram_menu_commands, telegram_menu_max_commands
```

**Why 5 seconds:** Plugin discovery is fast (<2s typically) but async. 5s provides comfortable margin without noticeable user impact (housekeeping runs off connect path).

**Alternative if 5s feels arbitrary:** Hook into plugin discovery completion event, but that requires deeper refactor. Delay is simpler and robust.

### 3. Autocomplete Filter: Required Argument Detection Bug

**File:** `hermes_cli/commands.py` line ~593-595, ~674-679

**Problem:** `telegram_bot_commands()` function filters out plugin commands whose `args_hint` starts with `<`, treating them as "required argument commands" unsuitable for autocomplete. Rationale was that selecting such commands without args would be incomplete. But this excluded most plugin commands from the menu.

**Code:**
```python
def _requires_argument(args_hint: str) -> bool:
    """Return True when selecting a command without text would be incomplete."""
    return args_hint.strip().startswith("<")

def telegram_bot_commands() -> list[tuple[str, str]]:
    # ... built-in commands ...
    
    for name, description, args_hint in _iter_plugin_command_entries():
        if _requires_argument(args_hint):
            continue  # ❌ SKIPPED FROM MENU!
        tg_name = _sanitize_telegram_name(name)
        if tg_name:
            result.append((tg_name, description))
    return result
```

**Fix:** Remove angle brackets from `args_hint` when registering commands:

**Before (causes filter to exclude):**
```python
ctx.register_command("rat_camera", handler,
                    description="Take photo from device",
                    args_hint="<device_id> [front|back]")
# _requires_argument("<device_id> [front|back]") → True → excluded
```

**After (passes filter):**
```python
ctx.register_command("rat_camera", handler,
                    description="Take photo from device",
                    args_hint="device_id [front|back]")
# _requires_argument("device_id [front|back]") → False → included ✅
```

**Note:** This is a workaround in plugin code, not a fix to Hermes core. Ideally `_requires_argument()` logic should be revisited (built-in commands with args like `/queue` ARE included), but changing that risks breaking other things. Safer to adapt plugin registration.

## Plugin Registration Template

```python
"""
Custom Telegram commands plugin for Hermes
"""
import sys

# Add your module to path if needed
sys.path.insert(0, '/path/to/your/module')

def register(ctx):
    """Register commands with Hermes plugin system."""
    
    # Handler functions must accept raw_args: str and return str
    def example_handler(raw_args: str) -> str:
        """Handler docstring shown in help."""
        if not raw_args:
            return "Usage: /example <arg1> [arg2]"
        
        # Parse args, call your logic
        try:
            result = your_business_logic(raw_args)
            return f"✅ {result}"
        except Exception as e:
            return f"❌ Error: {e}"
    
    # Register command
    # IMPORTANT: No angle brackets < > in args_hint!
    ctx.register_command(
        "example",              # Command name (becomes /example)
        example_handler,        # Handler function
        description="Brief description for Telegram menu",
        args_hint="arg1 [optional_arg2]"  # ✅ No < > to pass filter
    )
    
    # Register multiple commands
    ctx.register_command("other", other_handler, 
                        description="Another command")
    
    print(f"✅ MyPlugin: Registered 2 commands")
```

**Handler signature:** `fn(raw_args: str) -> str | None`

**Key points:**
- Handlers are synchronous (or async if you manage event loop)
- Return `str` for response or `None` for silent
- `raw_args` is everything after command name (unparsed string)
- Parse args yourself (`raw_args.split()`, regex, argparse, etc.)

## Manual Menu Refresh Script

When gateway restarts erase menu or changes don't propagate, force update:

**File:** `refresh_telegram_menu.py`

```python
#!/usr/bin/env python3
"""Force refresh Telegram bot menu with current commands including plugins."""
import asyncio
import sys
sys.path.insert(0, 'D:/hermes/hermes-agent')  # Adjust path

from telegram import Bot, BotCommand, BotCommandScopeDefault
from hermes_cli.commands import telegram_menu_commands

# Read token from .env
with open('D:/hermes/.env') as f:
    for line in f:
        if line.startswith('TELEGRAM_BOT_TOKEN='):
            token = line.split('=', 1)[1].strip()
            break

async def refresh():
    bot = Bot(token=token)
    
    # Get commands with plugins included
    menu_commands, hidden = telegram_menu_commands(max_commands=100)
    bot_commands = [BotCommand(name, desc[:100]) for name, desc in menu_commands]
    
    # Update Telegram server
    await bot.set_my_commands(bot_commands, scope=BotCommandScopeDefault())
    
    print(f"✅ Updated Telegram menu with {len(bot_commands)} commands")
    
    # Verify
    current = await bot.get_my_commands()
    plugin_cmds = [c for c in current if 'your_prefix' in c.command]
    print(f"🔥 Your plugin commands on server: {len(plugin_cmds)}")
    for c in plugin_cmds:
        print(f"   /{c.command}")

asyncio.run(refresh())
```

**Run with Hermes venv Python:**
```bash
# NOT system Python (missing deps)
D:\hermes\hermes-agent\venv\Scripts\python.exe refresh_telegram_menu.py
```

**When to use:**
- After enabling new plugin
- Gateway restart doesn't update menu
- Commands work but autocomplete empty

## Verification Checklist

After plugin creation and gateway restart:

### 1. Plugin Enabled
```bash
hermes plugins list | grep your_plugin
# Should show "enabled"
```

### 2. Commands Registered
```python
from hermes_cli.plugins import get_plugin_commands
cmds = get_plugin_commands()
print('your_cmd' in cmds)  # Should be True
```

### 3. Handler Lookup Works
```python
from hermes_cli.plugins import get_plugin_command_handler
handler = get_plugin_command_handler('your_cmd')
print(handler)  # Should be <function>, not None

# Test with both formats (after patch #1)
assert get_plugin_command_handler('your_cmd') is not None
assert get_plugin_command_handler('your-cmd') is not None
```

### 4. Commands in Menu Function
```python
from hermes_cli.commands import telegram_bot_commands
all_cmds = telegram_bot_commands()
your_cmds = [c for c in all_cmds if 'your_prefix' in c[0]]
print(f"Found {len(your_cmds)} commands")
for cmd, desc in your_cmds:
    print(f"  /{cmd} - {desc}")
```

### 5. Commands on Telegram Server
```python
import asyncio
from telegram import Bot

async def check():
    bot = Bot(token='YOUR_TOKEN')
    current = await bot.get_my_commands()
    your_cmds = [c for c in current if 'your_prefix' in c.command]
    print(f"On server: {[c.command for c in your_cmds]}")

asyncio.run(check())
```

### 6. Test in Telegram Client
- Type `/your_cmd` manually → should work (tests dispatch)
- Type `/your` → should show autocomplete (tests menu)
- Force close Telegram app → reopen → test autocomplete again

**If manual works but autocomplete doesn't:** Client cache issue, not server issue.

## Troubleshooting

### Commands work manually but invisible in autocomplete

**Cause:** Telegram adapter called `set_my_commands` before plugin discovery finished.

**Fix:**
1. Apply patch #2 (5s delay in adapter)
2. Restart gateway
3. Wait 10 seconds after gateway start
4. Run manual refresh script
5. Force close Telegram client app

**Client cache:** Telegram mobile caches menu aggressively. Must force-stop app:
- Android: Settings → Apps → Telegram → Force Stop
- iOS: Swipe up from app switcher
- Desktop: Quit completely, wait 10s

### "Unknown command" error even though handler exists

**Cause:** Underscore/hyphen mismatch in dispatch lookup.

**Fix:**
1. Apply patch #1 (try both variants)
2. Restart gateway
3. Test: `/your_cmd` should work

**Verify handler registered correctly:**
```python
from hermes_cli.plugins import get_plugin_command_handler
print(get_plugin_command_handler('your_cmd'))  # Must not be None
```

### Commands excluded from menu (never appear server-side)

**Cause:** `args_hint` starts with `<` → filtered by `_requires_argument()`.

**Fix:**
1. Remove `<>` from `args_hint` in plugin registration
2. Restart gateway
3. Run manual refresh script
4. Verify with step 5 above

**Check if filtered:**
```python
from hermes_cli.commands import _requires_argument
hint = "<device_id> [front|back]"
print(_requires_argument(hint))  # True = will be filtered out
hint = "device_id [front|back]"
print(_requires_argument(hint))  # False = will be included ✅
```

### Python dependency errors when running refresh script

**Problem:** `ModuleNotFoundError: No module named 'sniffio'` or similar.

**Cause:** Using system Python instead of Hermes venv.

**Fix:** Use full path to venv Python:
```bash
# Windows
D:\hermes\hermes-agent\venv\Scripts\python.exe refresh_telegram_menu.py

# Linux/Mac
~/.hermes/hermes-agent/venv/bin/python refresh_telegram_menu.py
```

### Gateway logs show plugin errors on startup

**Check:**
```bash
hermes gateway logs | grep -i "plugin\|error" | tail -20
```

**Common issues:**
- Import errors: Module path not in `sys.path`
- Syntax errors: Check plugin `__init__.py`
- Permission errors: Plugin directory not readable

## Integration with Hermes Internals

**Where plugins are discovered:** `hermes_cli/plugins.py` → `discover_plugins()` function scans `$HERMES_HOME/plugins/` for directories with `plugin.yaml`.

**Registration flow:**
1. Gateway startup calls plugin discovery
2. Each plugin's `register(ctx)` function called
3. `ctx.register_command()` adds to `_plugin_commands` dict
4. Gateway command dispatcher (`run.py`) looks up via `get_plugin_command_handler()`
5. Telegram adapter (`adapter.py`) builds menu via `telegram_menu_commands()` which calls `get_plugin_commands()`

**Key insight:** Menu snapshot happens ONCE per adapter connect. If plugins finish loading AFTER snapshot, they're invisible until next restart or manual refresh.

## Related Files

- `gateway/run.py` - Command dispatch (line ~17268-17284)
- `plugins/platforms/telegram/adapter.py` - Menu registration (line ~4021+)
- `hermes_cli/commands.py` - Menu builder (`telegram_bot_commands()`, `_requires_argument()`)
- `hermes_cli/plugins.py` - Plugin discovery and handler registry

## When to Patch vs Workaround

**Patch Hermes core when:**
- Bug affects all plugins (like dispatch mismatch)
- Race condition is architectural (like timing issue)
- You have write access to Hermes source

**Workaround in plugin when:**
- Isolated to your plugin's behavior
- Core change would break other things
- Temporary until Hermes upstream fixes

**This session:** Applied both. Patches #1 and #2 are core fixes (gateway dispatch, adapter timing). Fix #3 is plugin-side workaround (avoid `<>` in args_hint).

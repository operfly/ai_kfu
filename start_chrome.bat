@echo off
setlocal

set "PORT=9222"
set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "PROFILE=H:\ai_kfu\data\chrome_profile"
set "URL=https://mms.pinduoduo.com/"

rem Check Chrome is installed
if not exist "%CHROME%" (
    echo [ERROR] Chrome not found at: %CHROME%
    echo Please install Chrome or edit this script.
    pause
    exit /b 1
)

rem Detect whether port 9222 is already in use (debug instance running)
netstat -ano | findstr /c:":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo [INFO] Chrome debug instance is already running on port %PORT%.
    echo        No need to start again. Run: python main.py
    pause
    exit /b 0
)

rem Create isolated user-data dir (holds login state, not committed)
if not exist "%PROFILE%" mkdir "%PROFILE%"

echo Starting Chrome debug instance on port %PORT% ...
echo Log in to the Pinduoduo merchant console and keep this window open.
start "" "%CHROME%" --remote-debugging-port=%PORT% --user-data-dir="%PROFILE%" "%URL%"

endlocal

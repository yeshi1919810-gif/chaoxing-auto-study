@echo off
REM =========================================================
REM launch_browser.cmd - 启动带 CDP 远程调试端口的自动化浏览器
REM 优先检测并启动 Chrome 或 Edge
REM =========================================================

set PORT=9222
set USER_PROFILE=D:\chrome_debug_profile

if exist "D:\Chrome\Application\chrome.exe" (
    echo Starting Chrome on port %PORT%...
    start "" "D:\Chrome\Application\chrome.exe" --remote-debugging-port=%PORT% --remote-allow-origins=* --user-data-dir="%USER_PROFILE%" --start-maximized "https://i.chaoxing.com"
) else if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    echo Starting Edge on port %PORT%...
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=%PORT% --remote-allow-origins=* --user-data-dir="C:\Users\%USERNAME%\.gemini\browser_profile" --start-maximized "https://i.chaoxing.com"
) else (
    echo No supported browser found in standard locations.
)

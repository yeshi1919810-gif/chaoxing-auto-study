@echo off
REM =========================================================
REM launch_browser.cmd - 启动带 CDP 远程调试端口的自动化浏览器
REM
REM 关键参数（缺一不可，否则最小化/被遮挡时视频会掉到 0.3x）：
REM   --disable-background-timer-throttling       禁用后台定时器节流
REM   --disable-backgrounding-occluded-windows    窗口被遮挡时不降频
REM   --disable-renderer-backgrounding            页面不可见时不降低渲染优先级
REM   --disable-features=CalculateNativeWinOcclusion  关掉 Windows 遮挡检测
REM   --autoplay-policy=no-user-gesture-required  允许无交互自动播放
REM =========================================================

set PORT=9222
set USER_PROFILE=D:\chrome_debug_profile
set EDGE_PROFILE=C:\Users\%USERNAME%\chaoxing_debug_profile
set COMMON=--remote-debugging-port=%PORT% --remote-allow-origins=* --start-maximized --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-features=CalculateNativeWinOcclusion --autoplay-policy=no-user-gesture-required

if exist "D:\Chrome\Application\chrome.exe" (
    echo Starting Chrome on port %PORT%...
    start "" "D:\Chrome\Application\chrome.exe" %COMMON% --user-data-dir="%USER_PROFILE%" "https://i.chaoxing.com"
) else if exist "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" (
    echo Starting Edge on port %PORT%...
    start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" %COMMON% --user-data-dir="%EDGE_PROFILE%" "https://i.chaoxing.com"
) else (
    echo No supported browser found in standard locations.
)

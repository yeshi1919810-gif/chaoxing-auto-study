# =========================================================
# keep_awake.ps1 - Windows 电源防熄屏/休眠常亮配置脚本
# =========================================================

Write-Host "Configuring Windows Power Settings for Unattended Course Study..." -ForegroundColor Cyan

# 1. 设置交流电源（接通电源）下从不关闭显示器和从不睡眠
powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0

# 2. 设置直流电源（电池模式）下从不关闭显示器和从不睡眠
powercfg /change monitor-timeout-dc 0
powercfg /change standby-timeout-dc 0

# 3. 验证当前生效配置
$videoAc = (powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | Select-String "当前交流电源设置索引").ToString().Split(":")[-1].Trim()
$sleepAc = (powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Select-String "当前交流电源设置索引").ToString().Split(":")[-1].Trim()

Write-Host "Verification:" -ForegroundColor Green
Write-Host " - VIDEOIDLE (Screen timeout): $videoAc (0x00000000 = Never)"
Write-Host " - STANDBYIDLE (Sleep timeout): $sleepAc (0x00000000 = Never)"
Write-Host "System is now permanently awake for unattended background operations." -ForegroundColor Green

$ErrorActionPreference = "SilentlyContinue"

$log       = '<INSTALL_DIR>\logs\watchdog.log'
$napcatLog = '<INSTALL_DIR>\logs\napcat-out.log'
$state     = '<INSTALL_DIR>\logs\.offline-notified'
$notifier  = '%USERPROFILE%\.dsh\profiles\desktop\node_modules\.bin\dsh-wechat-send.CMD'

function Write-Log($msg) {
    "[$(Get-Date -f 'yyyy-MM-dd HH:mm:ss')] $msg" | Out-File $log -Append -Encoding utf8
}

# ---------- 1. 进程还活着吗 ----------
$astrbot = @(Get-Process python -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like '*\qq-ai\venv\*' })

if ($astrbot.Count -eq 0) {
    Start-Process wscript.exe -ArgumentList '<INSTALL_DIR>\run-astrbot-hidden.vbs' -WindowStyle Hidden
    Write-Log "AstrBot down -> restarted"
}

$napcat = @(Get-Process node -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like '*\qq-ai\napcat\*' })

if ($napcat.Count -eq 0) {
    Start-Process wscript.exe -ArgumentList '<INSTALL_DIR>\run-napcat-hidden.vbs' -WindowStyle Hidden
    Write-Log "NapCat down -> restarted"
    return
}

# ---------- 2. 进程活着，但 QQ 账号被踢下线了吗 ----------
# 只看最近 200 行，取最后一条状态：离线 还是 在线
$tail = Get-Content $napcatLog -Tail 200 -Encoding UTF8
$lastOffline = -1
$lastOnline  = -1
for ($i = 0; $i -lt $tail.Count; $i++) {
    if ($tail[$i] -match '账号状态变更为离线') { $lastOffline = $i }
    if ($tail[$i] -match '登录成功|已登录成功')  { $lastOnline  = $i }
}

if ($lastOffline -gt $lastOnline) {
    $lastNotify = if (Test-Path $state) { (Get-Item $state).LastWriteTime } else { [datetime]::MinValue }
    if (((Get-Date) - $lastNotify).TotalMinutes -gt 60) {
        Write-Log "account offline detected (needs QR scan)"
        if ((Test-Path $notifier) -and (-not $env:WD_NO_NOTIFY)) {
            $msg = "小号掉线了，需要在 NapCat 后台重新扫码：http://127.0.0.1:6099/webui?token=<看日志> 。扫完会自动重连。"
            & $notifier $msg 2>$null | Out-Null
        }
        New-Item -ItemType File -Force -Path $state | Out-Null
    }
} elseif (Test-Path $state) {
    Remove-Item $state -Force
    Write-Log "account back online"
}

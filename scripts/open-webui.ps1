$log = '<INSTALL_DIR>\logs\napcat-out.log'

$line = Select-String -Path $log -Pattern 'WebUi Token: (\w+)' -Encoding UTF8 | Select-Object -Last 1

if (-not $line) {
    Write-Host "Token not found in $log"
    exit 1
}

$token = $line.Matches[0].Groups[1].Value
$url = "http://127.0.0.1:6099/webui?token=$token"

Write-Host "token: $token"
Write-Host "opening: $url"
Start-Process $url

# mindx 启动脚本
# 后台静默启动，不阻塞终端

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverPath = Join-Path $scriptDir "server.py"
$port = 5020

# 检查是否已在运行（通过端口占用）
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "mindx 已在运行 (PID: $($conn.OwningProcess))"
    Write-Host "http://127.0.0.1:$port"
    exit 0
}

# 清理 Python 缓存，确保新代码生效
$pycache = Join-Path $scriptDir "__pycache__"
if (Test-Path $pycache) {
    Remove-Item -Recurse -Force $pycache -ErrorAction SilentlyContinue
}

# 启动
Start-Process python -ArgumentList "`"$serverPath`"" -WindowStyle Hidden
Start-Sleep -Seconds 3

# 验证
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/status" -UseBasicParsing -TimeoutSec 5
    Write-Host "mindx 已启动 — http://127.0.0.1:$port"
} catch {
    Write-Host "mindx 启动中，请稍后刷新 http://127.0.0.1:$port"
}

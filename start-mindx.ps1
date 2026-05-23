# mindx v4.5 启动脚本
# 后台静默启动 Web 服务，不阻塞终端

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$serverPath = Join-Path $scriptDir "server.py"
$port = 5020

Write-Host "mindx v4.5"

# 检查 Python 依赖
$depsOk = $true
try { python -c "import flask" 2>$null } catch { Write-Host "[!] 缺少 flask，请运行: pip install -r requirements.txt"; $depsOk = $false }
try { python -c "import watchdog" 2>$null } catch { Write-Host "[!] 缺少 watchdog，请运行: pip install -r requirements.txt"; $depsOk = $false }
if (-not $depsOk) { exit 1 }

# 检查 MCP 依赖（可选）
$mcpOk = $true
try { python -c "import mcp" 2>$null } catch { Write-Host "[i] MCP 未安装（可选），如需 AI 集成请运行: pip install -r requirements-mcp.txt"; $mcpOk = $false }

# 检查是否已在运行（通过端口占用，排除 TIME_WAIT）
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -ne 'TimeWait' }
if ($conn) {
    Write-Host "mindx 已在运行 (PID: $($conn.OwningProcess))"
    Write-Host "Web UI : http://127.0.0.1:$port"
    if ($mcpOk) { Write-Host "MCP    : python $scriptDir\mcp_server.py" }
    exit 0
}

# 清理 Python 缓存，确保新代码生效
$pycache = Join-Path $scriptDir "__pycache__"
if (Test-Path $pycache) {
    Remove-Item -Recurse -Force $pycache -ErrorAction SilentlyContinue
}

# 启动 Web 服务
Start-Process python -ArgumentList "`"$serverPath`"" -WindowStyle Hidden
Start-Sleep -Seconds 10

# 验证
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/status" -UseBasicParsing -TimeoutSec 5
    Write-Host "mindx 已启动"
    Write-Host "Web UI : http://127.0.0.1:$port"
    if ($mcpOk) { Write-Host "MCP    : python $scriptDir\mcp_server.py" }
} catch {
    Write-Host "mindx 启动中，请稍后刷新 http://127.0.0.1:$port"
}

# mindx v4.6 停止脚本
# 停止 Web 服务 + MCP 残留进程

$port = 5020
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$stopped = $false

# 方法1：停止端口 5020 上的 Web 服务
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    # Filter out TIME_WAIT — these are dead connections with no real process
    $active = @($conn | Where-Object { $_.State -ne 'TimeWait' })

    if ($active.Count -gt 0) {
        # Collect all unique OwningProcess IDs from active connections
        $pids = @($active | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique)

        if ($pids.Count -gt 0) {
            # Take the first PID (there should typically be only one listener)
            $ownerPid = $pids[0]
            try {
                $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
                if ($proc -and $proc.ProcessName -eq "python") {
                    Stop-Process -Id $ownerPid -Force
                    Write-Host "已停止 Web 服务 (PID: $ownerPid)"
                    $stopped = $true
                }
            } catch {
                Write-Host "方法1 停止 Web 服务失败: $($_.Exception.Message)"
            }
        }
    }
}

# 方法2：停止 mcp_server.py 残留进程（AI 工具可能 spawn 过）
$procs = Get-Process python -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    try {
        $cmd = $p.CommandLine
        if ($cmd -and $cmd -like "*mcp_server.py*") {
            Stop-Process -Id $p.Id -Force
            Write-Host "已停止 MCP 服务 (PID: $($p.Id))"
            $stopped = $true
        }
    } catch {
        Write-Host "方法2 检查 MCP 进程失败: $($_.Exception.Message)"
    }
}

# 方法3：遍历所有 python 进程，找包含 mindx/server 的
foreach ($p in $procs) {
    try {
        $cmd = $p.CommandLine
        if ($cmd -and $cmd -like "*$scriptDir*server.py*") {
            if ((Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
                Stop-Process -Id $p.Id -Force
                Write-Host "已停止 server.py (PID: $($p.Id))"
                $stopped = $true
            }
        }
    } catch {
        Write-Host "方法3 检查 server.py 进程失败: $($_.Exception.Message)"
    }
}

if (-not $stopped) {
    Write-Host "mindx 未在运行"
}

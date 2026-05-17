# mindx 停止脚本

$port = 5020

# 方法1：通过端口占用找到进程
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    $ownerPid = $conn.OwningProcess
    try {
        $proc = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq "python") {
            Stop-Process -Id $ownerPid -Force
            Write-Host "已停止 mindx (PID: $ownerPid)"
            exit 0
        }
    } catch {}
}

# 方法2：遍历所有 python 进程，找包含 mindx/server 的
$procs = Get-Process python -ErrorAction SilentlyContinue
$found = $false
foreach ($p in $procs) {
    try {
        $cmd = $p.CommandLine
        if ($cmd -and ($cmd -like "*mindx*" -or $cmd -like "*server.py*")) {
            Stop-Process -Id $p.Id -Force
            Write-Host "已停止 mindx (PID: $($p.Id))"
            $found = $true
        }
    } catch {}
}

if (-not $found) {
    Write-Host "mindx 未在运行"
}

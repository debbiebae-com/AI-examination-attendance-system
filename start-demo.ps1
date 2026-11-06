# One launch opens the local API and Next.js; use dashboard buttons for demo tasks.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv first (see docs/TROUBLESHOOTING.md).' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22.12+ first.' }
function Open-DemoWindow([string]$command) {
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    Start-Process powershell.exe -ArgumentList '-NoExit', '-EncodedCommand', $encoded
}
function Test-LocalPort([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync('127.0.0.1', $port)
        return ($task.Wait(300) -and $client.Connected)
    } catch { return $false } finally { $client.Dispose() }
}
if ((Test-LocalPort 8000) -or (Test-LocalPort 3000)) {
    throw 'Port 8000 or 3000 is already in use. Stop old API/dashboard windows before launching again.'
}
$backend = (Join-Path $root 'backend').Replace("'", "''")
$dashboard = (Join-Path $root 'dashboard').Replace("'", "''")
$api = "Set-Location -LiteralPath '$backend'; "
if (Test-Path (Join-Path $root 'backend/.env')) {
    $api += 'uv run --frozen --extra vision --env-file .env uvicorn app.main:app --host 127.0.0.1 --port 8000'
} else {
    $api += 'uv run --frozen --extra vision uvicorn app.main:app --host 127.0.0.1 --port 8000'
}
Open-DemoWindow $api
Open-DemoWindow "Set-Location -LiteralPath '$dashboard'; npm ci; if (`$LASTEXITCODE -ne 0) { throw 'npm install failed' }; npm run dev -- --hostname 127.0.0.1"
Write-Host 'API and dashboard windows opened. Wait for Ready, then open http://localhost:3000'
Write-Host 'Use Demo controls for sync, camera start/stop and volunteer cleanup. Close old servers before launching again.'

for ($attempt = 0; $attempt -lt 180; $attempt++) {
    if (Test-LocalPort 3000) {
        Start-Process 'http://localhost:3000'
        exit 0
    }
    Start-Sleep -Seconds 1
}
Write-Host 'Dashboard is still starting or needs attention. Check the server windows, then open http://localhost:3000.'

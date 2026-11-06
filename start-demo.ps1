# Windows PowerShell 5.1+. All paths are relative to this checkout, not the caller's folder.
[CmdletBinding()]
param(
    [ValidateSet('Start', 'Prepare', 'Stop')][string]$Mode = 'Start',
    [switch]$Desktop,
    [switch]$NoBrowser,
    [ValidatePattern('^$|^[a-f0-9-]{36}$')][string]$Owner = ''
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$runtime = Join-Path $root '.demo-runtime'
$statePath = Join-Path $runtime 'servers.json'
$preparedPath = Join-Path $runtime 'prepared.json'
$backend = Join-Path $root 'backend'
$dashboard = Join-Path $root 'dashboard'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function Read-Json([string]$path) {
    if (Test-Path -LiteralPath $path) { return (Get-Content -Raw -LiteralPath $path | ConvertFrom-Json) }
    return $null
}
function Write-Json($value, [string]$path) {
    $temporary = "$path.tmp"
    $value | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 -LiteralPath $temporary
    Move-Item -Force -LiteralPath $temporary -Destination $path
}
function Require-Command([string]$name) {
    $command = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) { throw "Missing $name. See docs/PRESENTATION_LAUNCHER.md, then run Prepare Demo.cmd." }
    return $command.Source
}
function Test-Port([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { return ($client.ConnectAsync('127.0.0.1', $port).Wait(300) -and $client.Connected) }
    catch { return $false }
    finally { $client.Dispose() }
}
function Get-ProcessIdentity([int]$processId) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    return [pscustomobject]@{ id = [int]$process.ProcessId; created = $process.CreationDate.ToUniversalTime().ToString('o') }
}
function Test-Identity($entry) {
    if (-not $entry) { return $false }
    $actual = Get-ProcessIdentity $entry.id
    return ($actual -and $actual.created -eq $entry.created)
}
function Get-OwnedTree($entry) {
    if (-not (Test-Identity $entry)) { return @() }
    $all = @(Get-CimInstance Win32_Process)
    $ids = New-Object 'System.Collections.Generic.HashSet[int]'
    [void]$ids.Add([int]$entry.id)
    do {
        $added = $false
        foreach ($item in $all) {
            if ($ids.Contains([int]$item.ParentProcessId) -and -not $ids.Contains([int]$item.ProcessId) -and $item.CreationDate.ToUniversalTime() -ge [datetime]::Parse($entry.created).ToUniversalTime()) {
                [void]$ids.Add([int]$item.ProcessId)
                $added = $true
            }
        }
    } while ($added)
    return @($all | Where-Object { $ids.Contains([int]$_.ProcessId) } | ForEach-Object {
        [pscustomobject]@{ id = [int]$_.ProcessId; created = $_.CreationDate.ToUniversalTime().ToString('o') }
    })
}
function Test-OwnedListener($entry, [int]$port) {
    $ids = @(Get-OwnedTree $entry | ForEach-Object { $_.id })
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue)
    return (@($listeners | Where-Object { $ids -contains $_.OwningProcess }).Count -gt 0)
}
function Stop-OwnedTree($entry) {
    $tree = @(Get-OwnedTree $entry)
    # Stop the launcher root first to prevent it spawning new descendants during shutdown.
    foreach ($item in @($entry) + @($tree | Where-Object { $_.id -ne $entry.id })) {
        if (Test-Identity $item) { Stop-Process -Id $item.id -Force -ErrorAction SilentlyContinue }
    }
}
function Test-Api {
    try { return ((Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 2).status -eq 'ok') }
    catch { return $false }
}
function Test-Dashboard {
    try {
        $page = Invoke-WebRequest 'http://127.0.0.1:3000' -UseBasicParsing -TimeoutSec 3
        if ($page.StatusCode -ne 200 -or $page.Content -notmatch 'ExamLens') { return $false }
        # Also verify Next's same-origin proxy reaches this backend, not just an open TCP port.
        $live = Invoke-RestMethod 'http://127.0.0.1:3000/api/live/session' -TimeoutSec 3
        return ($null -ne $live.status)
    } catch { return $false }
}
function Wait-Ready($entry, [string]$kind) {
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-Identity $entry)) { throw "$kind exited during startup. See the local log files in .demo-runtime." }
        if ($kind -eq 'Backend' -and (Test-Api) -and (Test-OwnedListener $entry 8000)) { return }
        if ($kind -eq 'Dashboard' -and (Test-Dashboard) -and (Test-OwnedListener $entry 3000)) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$kind did not become ready within two minutes. See .demo-runtime logs. Stop Demo.cmd can clean up launcher-owned servers."
}
function Get-SourceFingerprint {
    # Skip generated directories entirely; never walk node_modules or hash face/model data.
    $files = @()
    foreach ($folder in @('app', 'components', 'lib', 'hooks', 'public', 'styles', 'tests')) {
        $path = Join-Path $dashboard $folder
        if (Test-Path -LiteralPath $path) { $files += Get-ChildItem -LiteralPath $path -Recurse -File }
    }
    $files += Get-ChildItem -LiteralPath $dashboard -File | Where-Object { $_.Name -notin @('next-env.d.ts', 'tsconfig.tsbuildinfo') }
    $desktopPath = Join-Path $root 'desktop'
    if (Test-Path -LiteralPath $desktopPath) { $files += Get-ChildItem -LiteralPath $desktopPath -File }
    $files += Get-ChildItem -LiteralPath (Join-Path $backend 'app') -Recurse -File -Filter '*.py'
    foreach ($path in @('backend/pyproject.toml', 'backend/uv.lock', 'start-demo.ps1')) { $files += Get-Item -LiteralPath (Join-Path $root $path) }
    $lines = @($files | Sort-Object FullName -Unique | ForEach-Object {
        $_.FullName.Substring($root.Length) + ':' + (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
    })
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join "`n"))))).Replace('-', '') }
    finally { $hash.Dispose() }
}
function Start-Server([string]$program, [string[]]$arguments, [string]$directory, [string]$name, [string]$run) {
    $stdout = Join-Path $runtime "$run-$name.stdout.log"
    $stderr = Join-Path $runtime "$run-$name.stderr.log"
    $process = Start-Process -FilePath $program -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
    $entry = Get-ProcessIdentity $process.Id
    if (-not $entry) { throw "$name exited immediately. See .demo-runtime logs." }
    return $entry
}
function Stop-Demo($state) {
    if ($state -and $Owner -and $state.owner -ne $Owner) {
        Write-Host 'These servers belong to another launch; they were left running.'
        return
    }
    if (-not $state) {
        Write-Host 'No launcher-managed servers found. Existing manual servers will not be touched.'
        return
    }
    if (Test-Identity $state.api) {
        if (-not (Test-OwnedListener $state.api 8000)) { throw 'Backend ownership could not be verified. No processes were stopped.' }
        $keyPath = Join-Path $backend 'data/control.key'
        if (-not (Test-Path -LiteralPath $keyPath)) { throw 'Local control key is missing. No processes were stopped.' }
        $headers = @{ 'X-Local-Control' = (Get-Content -Raw -LiteralPath $keyPath).Trim() }
        $job = Invoke-RestMethod 'http://127.0.0.1:8000/control/status' -Headers $headers -TimeoutSec 5
        if ($job.running) {
            Write-Host 'Waiting for the current demonstration task to close safely...'
            if ($job.kind -in @('camera', 'local_enroll')) {
                Invoke-RestMethod 'http://127.0.0.1:8000/control/camera/stop' -Method Post -ContentType 'application/json' -Body '{}' -Headers $headers -TimeoutSec 5 | Out-Null
            }
            $deadline = (Get-Date).AddSeconds(120)
            do {
                Start-Sleep -Seconds 1
                $job = Invoke-RestMethod 'http://127.0.0.1:8000/control/status' -Headers $headers -TimeoutSec 5
            } while ($job.running -and (Get-Date) -lt $deadline)
            if ($job.running) { throw 'A demonstration task is still running. Servers were left open; wait for it to finish and double-click Stop Demo again.' }
        }
        $live = Invoke-RestMethod 'http://127.0.0.1:8000/live/session' -TimeoutSec 5
        if ($live.status -in @('starting', 'running', 'disconnected')) { throw 'An external or unclosed recognition session is active. Close its camera window first, then try Stop Demo again.' }
    }
    Stop-OwnedTree $state.dashboard
    Stop-OwnedTree $state.api
    Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    Write-Host 'ExamLens stopped. Enrolled faces and saved attendance were not changed.'
}

# Serialize Start/Stop/Prepare across double-clicks of this checkout only.
$sha = [Security.Cryptography.SHA256]::Create()
$mutexId = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($root.ToLowerInvariant())))).Replace('-', '').Substring(0, 24)
$sha.Dispose()
$mutex = New-Object Threading.Mutex($false, "Local\ExamLens-$mutexId")
$locked = $false
$created = @()
try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) {
        if ($NoBrowser) { throw 'Another launch is still starting/preparing/stopping. Wait for it to finish and reopen ExamLens Desktop.' }
        Write-Host 'ExamLens is already starting, preparing or stopping. Wait for that window to finish.'; exit 0
    }
    $state = Read-Json $statePath
    if ($Mode -eq 'Stop') { Stop-Demo $state; exit 0 }
    if ($Mode -eq 'Prepare') {
        if (($state -and ((Test-Identity $state.api) -or (Test-Identity $state.dashboard))) -or (Test-Port 8000) -or (Test-Port 3000)) {
            throw 'Stop existing API/dashboard servers before preparing. Use Stop Demo.cmd for launcher-managed servers; close old manual server windows yourself.'
        }
        $uv = Require-Command 'uv'
        $node = Require-Command 'node'
        $npm = Require-Command 'npm.cmd'
        $version = (& $node -p 'process.versions.node').Trim().Split('.')
        if ([int]$version[0] -lt 22 -or ([int]$version[0] -eq 22 -and [int]$version[1] -lt 12)) { throw 'Install Node.js 22.12 or newer before preparing.' }
        # Invalidate old readiness before any installation/build that could fail.
        Remove-Item -LiteralPath $preparedPath -Force -ErrorAction SilentlyContinue
        Write-Host 'Preparing ExamLens. Internet may be needed for packages/models. No camera will be opened.'
        Push-Location -LiteralPath $backend
        try {
            & $uv sync --frozen --extra vision
            if ($LASTEXITCODE -ne 0) { throw 'Backend dependency preparation failed.' }
            $setupArgs = @('run', '--offline', '--no-sync')
            if (Test-Path -LiteralPath (Join-Path $backend '.env')) { $setupArgs += @('--env-file', '.env') }
            # uv stays offline; InsightFace may download the model pack during this prepare step only.
            & $uv @setupArgs python -m app.demo_setup
            if ($LASTEXITCODE -ne 0) { throw 'Face model preparation failed. Check the setup window and retry while online.' }
        } finally { Pop-Location }
        Push-Location -LiteralPath $dashboard
        try {
            & $npm ci '--include=dev'
            if ($LASTEXITCODE -ne 0) { throw 'Dashboard dependency preparation failed.' }
            & $npm run build
            if ($LASTEXITCODE -ne 0) { throw 'Dashboard production build failed.' }
        } finally { Pop-Location }
        if ($Desktop) {
            Write-Host 'Preparing the Electron desktop runtime...'
            Push-Location -LiteralPath (Join-Path $root 'desktop')
            try {
                & $npm ci '--include=dev'
                if ($LASTEXITCODE -ne 0) { throw 'Electron preparation failed. Retry Prepare Desktop App.cmd while online.' }
                if (-not (Test-Path -LiteralPath 'node_modules/electron/dist/electron.exe')) { throw 'Electron executable is missing. Do not skip npm install scripts during desktop preparation.' }
            } finally { Pop-Location }
        }
        Write-Json @{ fingerprint = Get-SourceFingerprint; build = (Get-Content -Raw -LiteralPath (Join-Path $dashboard '.next/BUILD_ID')).Trim(); prepared = (Get-Date).ToString('o') } $preparedPath
        try {
            $desktopFolder = [Environment]::GetFolderPath('Desktop')
            $shortcutName = if ($Desktop) { 'ExamLens Desktop.lnk' } else { 'ExamLens.lnk' }
            $shortcutPath = Join-Path $desktopFolder $shortcutName
            if ((Test-Path -LiteralPath $desktopFolder) -and -not (Test-Path -LiteralPath $shortcutPath)) {
                $shell = New-Object -ComObject WScript.Shell
                $shortcut = $shell.CreateShortcut($shortcutPath)
                if ($Desktop) {
                    $shortcut.TargetPath = Join-Path $root 'desktop/node_modules/electron/dist/electron.exe'
                    $shortcut.Arguments = '"' + (Join-Path $root 'desktop') + '"'
                    $shortcut.IconLocation = Join-Path $root 'desktop/icon.ico'
                } else { $shortcut.TargetPath = Join-Path $root 'Start Demo.cmd' }
                $shortcut.WorkingDirectory = $root
                $shortcut.Description = 'Start the local ExamLens presentation dashboard'
                $shortcut.Save()
            }
        } catch { Write-Host 'Desktop shortcut could not be created; Start Demo.cmd in this folder still works.' }
        if ($Desktop) { Write-Host 'Ready. Double-click ExamLens Desktop on your desktop, or Start Desktop App.cmd in this folder.' -ForegroundColor Green }
        else { Write-Host 'Ready. Double-click Start Demo.cmd. Preparation is not needed again unless the app changes.' -ForegroundColor Green }
        exit 0
    }

    $prepared = Read-Json $preparedPath
    if (-not $prepared -or -not (Test-Path -LiteralPath (Join-Path $dashboard '.next/BUILD_ID')) -or -not (Test-Path -LiteralPath (Join-Path $backend '.venv/Scripts/python.exe')) -or -not (Test-Path -LiteralPath (Join-Path $dashboard 'node_modules/next/dist/bin/next'))) {
        throw 'This checkout is not prepared. Double-click Prepare Demo.cmd once while online, then Start Demo.cmd.'
    }
    if ($prepared.fingerprint -ne (Get-SourceFingerprint) -or $prepared.build -ne (Get-Content -Raw -LiteralPath (Join-Path $dashboard '.next/BUILD_ID')).Trim()) {
        throw 'App files or the dashboard build changed. Run Prepare Demo.cmd again before presenting.'
    }
    if ($state) {
        if ((Test-Identity $state.api) -and (Test-Identity $state.dashboard) -and (Test-OwnedListener $state.api 8000) -and (Test-OwnedListener $state.dashboard 3000) -and (Test-Api) -and (Test-Dashboard)) {
            Write-Host 'ExamLens is already running. Opening its dashboard.'
            if ($NoBrowser -and $Owner -and $state.owner -match '^[a-f0-9-]{36}$') { $state.owner = $Owner; Write-Json $state $statePath }
            if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:3000' }
            exit 0
        }
        if ((Test-Identity $state.api) -or (Test-Identity $state.dashboard)) { throw 'A previous launch is incomplete. Double-click Stop Demo.cmd, then Start Demo.cmd.' }
        Remove-Item -LiteralPath $statePath -Force
    }
    if ((Test-Port 8000) -or (Test-Port 3000)) { throw 'Port 8000 or 3000 is already in use by an unmanaged server. Close the old manual server windows first. No unrelated processes were stopped.' }
    $uv = Require-Command 'uv'
    $node = Require-Command 'node'
    $run = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
    $apiArgs = @('run', '--offline', '--no-sync')
    if (Test-Path -LiteralPath (Join-Path $backend '.env')) { $apiArgs += @('--env-file', '.env') }
    $apiArgs += @('python', '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000')
    Write-Host 'Starting ExamLens backend...'
    $api = Start-Server $uv $apiArgs $backend 'backend' $run
    $created += $api
    $state = [pscustomobject]@{ api = $api; dashboard = $null; run = $run; owner = $(if ($Owner) { $Owner } else { 'launcher' }) }
    Write-Json $state $statePath
    Wait-Ready $api 'Backend'
    Write-Host 'Starting the production dashboard...'
    # Process-local overrides keep the launcher's dashboard on its own API, even if
    # a previous hosting experiment left a different BACKEND_ORIGIN in .env.local.
    $oldOrigin = $env:BACKEND_ORIGIN
    $oldKeyPath = $env:LOCAL_CONTROL_KEY_FILE
    $oldNodeEnv = $env:NODE_ENV
    try {
        $env:BACKEND_ORIGIN = 'http://127.0.0.1:8000'
        $env:LOCAL_CONTROL_KEY_FILE = Join-Path $backend 'data/control.key'
        $env:NODE_ENV = 'production'
        $web = Start-Server $node @('node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', '3000') $dashboard 'dashboard' $run
    } finally {
        $env:BACKEND_ORIGIN = $oldOrigin
        $env:LOCAL_CONTROL_KEY_FILE = $oldKeyPath
        $env:NODE_ENV = $oldNodeEnv
    }
    $created += $web
    $state.dashboard = $web
    Write-Json $state $statePath
    Wait-Ready $web 'Dashboard'
    Write-Host 'ExamLens is ready. Use Stop Demo.cmd to shut down when finished.' -ForegroundColor Green
    if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:3000' }
} catch {
    if ($created.Count -gt 0) {
        foreach ($entry in $created) { Stop-OwnedTree $entry }
        Remove-Item -LiteralPath $statePath -Force -ErrorAction SilentlyContinue
    }
    Write-Host ''
    Write-Host ('ExamLens: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'Logs (if servers were launched): .demo-runtime in this project. Keep logs private; never share .env or control.key.'
    exit 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}

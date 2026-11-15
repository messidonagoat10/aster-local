[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Python 3.11+ is required. Install it from https://www.python.org/downloads/windows/ and run this script again.'
}
$PythonVersionText = & py -3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
if ($LASTEXITCODE -ne 0 -or -not $PythonVersionText) {
    throw 'Python 3.11 or newer was not found. Install Python from https://www.python.org/downloads/windows/ and try again.'
}
try { $PythonVersion = [version]$PythonVersionText.Trim() } catch { throw 'Could not determine the installed Python version.' }
if ($PythonVersion -lt [version]'3.11') {
    throw "Python $PythonVersion is too old. Aster requires Python 3.11 or newer."
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required. Install it from https://docs.astral.sh/uv/getting-started/installation/ and run this script again.'
}
$Ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $Ollama) {
    throw 'Ollama is required. Install it from https://ollama.com/download and run this script again.'
}

Write-Host 'Installing locked Aster dependencies (including local speech recognition)…'
& uv sync --locked --extra voice
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Review the error above and retry.' }

$ServerReady = $false
try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
    $ServerReady = $true
} catch {
    Write-Host 'Starting the local Ollama service…'
    Start-Process -FilePath $Ollama.Source -ArgumentList @('serve') -WindowStyle Hidden | Out-Null
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        Start-Sleep -Seconds 1
        try {
            $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2
            $ServerReady = $true
            break
        } catch { }
    }
}
if (-not $ServerReady) { throw 'Ollama did not start on 127.0.0.1:11434. Open the Ollama app and try again.' }

$InstalledModels = (& $Ollama.Source list 2>$null | Out-String)
if ($InstalledModels -notmatch '(?m)^qwen3:4b(?:\s|$)') {
    Write-Host 'Downloading qwen3:4b. This first-time download needs internet and several GB of disk space.'
    & $Ollama.Source pull qwen3:4b
    if ($LASTEXITCODE -ne 0) { throw 'The local Qwen3 model download failed. Run: ollama pull qwen3:4b' }
}

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$DataRoot = if ($env:ASTER_DATA_DIR) { $env:ASTER_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'Aster' }
$Logs = Join-Path $DataRoot 'logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$Port = if ($env:ASTER_PORT) { $env:ASTER_PORT } else { '8765' }
$PidFile = Join-Path $DataRoot 'aster.pid'

function Test-AsterProcess([int]$CandidateId) {
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $CandidateId" -ErrorAction SilentlyContinue
    $ExpectedPython = [IO.Path]::GetFullPath((Join-Path $ProjectRoot '.venv\Scripts\python.exe'))
    return $ProcessInfo -and $ProcessInfo.ExecutablePath -ieq $ExpectedPython -and $ProcessInfo.CommandLine -match '-m\s+assistant_core'
}

if (Test-Path -LiteralPath $PidFile) {
    $OldPid = 0
    [void][int]::TryParse((Get-Content -Raw -LiteralPath $PidFile), [ref]$OldPid)
    if ($OldPid -gt 0 -and (Test-AsterProcess $OldPid)) {
        Write-Host "Aster is already running (PID $OldPid). Opening its local page."
        Start-Process "http://127.0.0.1:$Port" | Out-Null
        return
    }
}

$Process = Start-Process -FilePath $Python -ArgumentList @('-m', 'assistant_core') `
    -WorkingDirectory $ProjectRoot -RedirectStandardOutput (Join-Path $Logs 'stdout.log') `
    -RedirectStandardError (Join-Path $Logs 'stderr.log') -WindowStyle Hidden -PassThru
Set-Content -LiteralPath $PidFile -Value $Process.Id -NoNewline

$Ready = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    Start-Sleep -Seconds 1
    if ($Process.HasExited) { break }
    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2
        $Ready = $true
        break
    } catch { }
}
if (-not $Ready) {
    if (Test-AsterProcess $Process.Id) { Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    $RecentError = if (Test-Path (Join-Path $Logs 'stderr.log')) { Get-Content (Join-Path $Logs 'stderr.log') -Tail 20 | Out-String } else { '' }
    throw "Aster did not start. Check $Logs. $RecentError"
}
Start-Process "http://127.0.0.1:$Port" | Out-Null
Write-Host "Aster is running at http://127.0.0.1:$Port. Run .\stop-aster.ps1 when you are done."

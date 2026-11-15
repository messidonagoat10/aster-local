$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
$DataRoot = if ($env:ASTER_DATA_DIR) { $env:ASTER_DATA_DIR } else { Join-Path $env:LOCALAPPDATA 'Aster' }
$PidFile = Join-Path $DataRoot 'aster.pid'
if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host 'Aster is not running from this checkout.'
    return
}
$ProcessId = 0
[void][int]::TryParse((Get-Content -Raw -LiteralPath $PidFile), [ref]$ProcessId)
$ProcessInfo = if ($ProcessId -gt 0) { Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue } else { $null }
$ExpectedPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if ($ProcessInfo -and $ProcessInfo.ExecutablePath -eq $ExpectedPython -and $ProcessInfo.CommandLine -match '-m\s+assistant_core') {
    Stop-Process -Id $ProcessId -ErrorAction Stop
    Write-Host 'Stopped Aster.'
} else {
    Write-Host 'The saved process ID does not match the Aster executable in this folder; leaving it alone.'
}
Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue

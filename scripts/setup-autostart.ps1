# Configure the self-hosted GitHub Actions runner to auto-start (hidden) at each
# Windows login, and start it now. No admin required.
# Undo later by deleting the file this reports.
$ErrorActionPreference = 'Stop'

$runner = 'C:\actions-runner\run.cmd'
if (-not (Test-Path $runner)) {
    Write-Host "ERROR: runner not found at $runner - is the runner installed?"
    exit 1
}

$startup = [Environment]::GetFolderPath('Startup')
$vbs = Join-Path $startup 'ytdigest-runner.vbs'
$line = 'CreateObject("WScript.Shell").Run "C:\actions-runner\run.cmd", 0, False'
Set-Content -LiteralPath $vbs -Value $line -Encoding ASCII
Write-Host "Auto-start installed: $vbs"

if (-not (Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $runner -WorkingDirectory 'C:\actions-runner' -WindowStyle Hidden
    Write-Host "Runner started."
} else {
    Write-Host "Runner is already running."
}

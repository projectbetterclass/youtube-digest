# Registers the daily local job (scripts/daily_local.py) with Windows Task Scheduler.
#
# Checks every hour from 10:00 to midnight, as soon as the PC is on if that was missed, and
# 15 minutes after you log on. The job itself runs only if its last successful run was 12+
# hours ago (so at most twice a day); a run that failed (offline, push refused) is retried at
# the next check. Runs only while you're logged on, with no window, using this repo's .venv.
#
#   powershell -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1           # install / update
#   powershell -ExecutionPolicy Bypass -File scripts\install_daily_task.ps1 -Remove   # uninstall
param([switch]$Remove)

$Name = "YouTube library - daily"
if ($Remove) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    "Removed '$Name'."
    return
}

$Repo = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $Py)) { throw "No .venv found at $Py (create it first)." }
$Script = Join-Path $Repo "scripts\daily_local.py"

$Action = New-ScheduledTaskAction -Execute $Py -Argument "`"$Script`"" -WorkingDirectory $Repo
$Daily = New-ScheduledTaskTrigger -Daily -At 10:00
# -Daily can't take a repetition directly; borrow one from a -Once trigger (hourly for 14 h).
$Daily.Repetition = (New-ScheduledTaskTrigger -Once -At 10:00 -RepetitionInterval (New-TimeSpan -Hours 1) `
    -RepetitionDuration (New-TimeSpan -Hours 14)).Repetition
$Logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Logon.Delay = "PT15M"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $Name -Action $Action -Trigger @($Daily, $Logon) -Settings $Settings `
    -Principal $Principal -Description "Collect new uploads for the YouTube library (scripts/daily_local.py)." `
    -Force | Out-Null
"Installed '$Name': checks hourly 10:00-24:00 and 15 min after log-on; runs at most twice a day."
"Log: $env:LOCALAPPDATA\ytdigest\daily.log   Last result: $env:LOCALAPPDATA\ytdigest\daily_status.txt"

# 史灯(アカウントB)の定期実行を登録する。管理者 PowerShell で1回だけ実行する。
#
# 注意: B には既存の定期実行タスクが登録されている可能性がある。
#       二重投稿を防ぐため、このスクリプトは note-autopilot-daily-b* を
#       いったん解除してから登録し直す。実行前に下の一覧を必ず確認すること。

$ErrorActionPreference = "Stop"
$taskName = "note-autopilot-daily-b"
$project  = "C:\Users\User\Documents\note-autopilot"

Write-Host "=== 現在登録されている note-autopilot-* タスク ==="
Get-ScheduledTask -TaskName 'note-autopilot-*' -ErrorAction SilentlyContinue |
    Select-Object TaskName, State | Format-Table -AutoSize

$existing = Get-ScheduledTask -TaskName "$taskName*" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "既存の $taskName* を解除します。"
    $existing | Unregister-ScheduledTask -Confirm:$false
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -NoProfile -File `"$project\scripts\daily-b.ps1`"" `
    -WorkingDirectory $project

# 火・木・土 17:00(A の月水金日 17:00 / SoA の火金 18:30 と同時刻に重ねない)
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Tuesday, Thursday, Saturday -At 17:00

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "史灯(アカウントB) 連載小説の日次パイプライン" | Out-Null

Write-Host "=== 登録後 ==="
Get-ScheduledTask -TaskName 'note-autopilot-*' | Select-Object TaskName, State | Format-Table -AutoSize
Write-Host "登録しました: $taskName (火・木・土 17:00)"

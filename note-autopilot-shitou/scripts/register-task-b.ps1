# 史灯(アカウントB)の定期実行をまとめて登録する。管理者 PowerShell で1回だけ実行する。
#
# 登録されるタスク:
#   note-autopilot-healthcheck-b  毎日 08:00        疎通確認(Cookie失効の早期発見)
#   note-autopilot-prepare-b      月・水・金 09:00  記事の事前生成(公開の前日)
#   note-autopilot-daily-b        火・木・土 17:00  公開
#   note-autopilot-catchup-b      火・木・土 19:30  公開の再試行
#   note-autopilot-catchup2-b     火・木・土 21:30  公開の再試行(2回目)
#   note-autopilot-analyze-b      毎週月曜 07:00    分析と改善指示の更新
#
# 注意: 既存の B のタスクが残っていると二重投稿になる。
#       このスクリプトは note-autopilot-*-b と note-autopilot-daily-b* を
#       いったん解除してから登録し直す。下の一覧を必ず確認すること。

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot

Write-Host "=== 現在登録されている note-autopilot-* タスク ==="
Get-ScheduledTask -TaskName 'note-autopilot-*' -ErrorAction SilentlyContinue |
    Select-Object TaskName, State | Format-Table -AutoSize

$stale = Get-ScheduledTask -TaskName 'note-autopilot-*-b*' -ErrorAction SilentlyContinue
if ($stale) {
    Write-Host "既存の B 向けタスクを解除します: $($stale.TaskName -join ', ')"
    $stale | Unregister-ScheduledTask -Confirm:$false
}

# StartWhenAvailable: PC が落ちていて実行できなかったタスクを、起動後に取り返す
# WakeToRun:          スリープ中なら PC を起こして実行する(電源接続とBIOS設定が前提)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

function Register-ShitouTask {
    param([string]$Name, [string]$Script, $Trigger, [string]$Description)
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -NoProfile -File `"$project\scripts\$Script`"" `
        -WorkingDirectory $project
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Trigger `
        -Settings $settings -Description $Description | Out-Null
    Write-Host "登録: $Name"
}

# 投稿日: 火・木・土(A の月水金日、SoA の火金18:30 と時刻が重ならないようにしている)
$postDays = @('Tuesday', 'Thursday', 'Saturday')
# 生成日: 投稿の前日(月・水・金)。生成失敗に丸一日以上の猶予を持たせるため。
$prepDays = @('Monday', 'Wednesday', 'Friday')

Register-ShitouTask -Name "note-autopilot-healthcheck-b" -Script "healthcheck-b.ps1" `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 08:00) `
    -Description "史灯(B) 毎日の疎通確認。Cookie失効を投稿前に検知する"

Register-ShitouTask -Name "note-autopilot-prepare-b" -Script "prepare-b.ps1" `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $prepDays -At 09:00) `
    -Description "史灯(B) 記事の事前生成。公開の前日に用意する"

Register-ShitouTask -Name "note-autopilot-daily-b" -Script "daily-b.ps1" `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $postDays -At 17:00) `
    -Description "史灯(B) 連載小説の公開"

Register-ShitouTask -Name "note-autopilot-catchup-b" -Script "catchup-b.ps1" `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $postDays -At 19:30) `
    -Description "史灯(B) 公開の再試行(1回目)"

Register-ShitouTask -Name "note-autopilot-catchup2-b" -Script "catchup-b.ps1" `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $postDays -At 21:30) `
    -Description "史灯(B) 公開の再試行(2回目)"

Register-ShitouTask -Name "note-autopilot-analyze-b" -Script "analyze-b.ps1" `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 07:00) `
    -Description "史灯(B) 週次の分析と改善指示の更新"

Write-Host ""
Write-Host "=== 登録後 ==="
Get-ScheduledTask -TaskName 'note-autopilot-*' | Select-Object TaskName, State | Format-Table -AutoSize

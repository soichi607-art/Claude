# 史灯(アカウントB)の各スクリプトが共通で使う関数。dot-source して読み込む。
#   . "$PSScriptRoot\_shitou-lib.ps1"

$script:ShitouProject = Split-Path -Parent $PSScriptRoot

function Write-ShitouLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "{0} [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    Write-Host $line
    $logDir = Join-Path $script:ShitouProject "logs"
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
    $logFile = Join-Path $logDir ("shitou-{0}.log" -f (Get-Date -Format "yyyyMM"))
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Send-ShitouNotify {
    # .env の NOTIFY_WEBHOOK_URL があれば通知する。無ければログだけ。
    # 通知の失敗でパイプラインを止めない。
    param([string]$Message)
    Write-ShitouLog $Message "NOTIFY"
    try {
        $envFile = Join-Path $script:ShitouProject ".env"
        if (-not (Test-Path $envFile)) { return }
        $url = $null
        foreach ($line in Get-Content $envFile -Encoding UTF8) {
            if ($line -match '^\s*NOTIFY_WEBHOOK_URL\s*=\s*(.+?)\s*$') {
                $url = $Matches[1].Trim('"').Trim("'")
            }
        }
        if (-not $url) { return }
        $body = @{ text = "[史灯/note] $Message" } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" `
            -Body $body -TimeoutSec 15 | Out-Null
    } catch {
        Write-ShitouLog "通知の送信に失敗しました(処理は続行します): $_" "WARN"
    }
}

function Test-ShitouStopped {
    # 緊急停止中かどうか。STOP ファイルは人が消すまで残る(自動削除しない)。
    return (Test-Path (Join-Path $script:ShitouProject "data_b\STOP"))
}

function Invoke-ShitouStep {
    <#
      note_autopilot のサブコマンドを、失敗時にリトライしながら実行する。

      - 終了コード 2(緊急停止)は絶対にリトライしない。即座に呼び出し元へ返す。
      - RetryOn に挙げた終了コードのときだけ、待機してからやり直す。
      - 待機は 60秒 → 180秒 → 420秒 と伸ばす(note 側への連打を避けるため)。
      戻り値: 最後の終了コード
    #>
    param(
        [Parameter(Mandatory=$true)][string]$Command,
        [int[]]$RetryOn = @(),
        [int]$MaxAttempts = 3
    )
    $delays = @(60, 180, 420)
    for ($i = 1; $i -le $MaxAttempts; $i++) {
        Write-ShitouLog "$Command を実行します(試行 $i/$MaxAttempts)"
        & uv run python -m note_autopilot --config config.b.yaml $Command
        $code = $LASTEXITCODE

        if ($code -eq 0) { Write-ShitouLog "$Command 成功"; return 0 }
        if ($code -eq 2) {
            Send-ShitouNotify "$Command: 緊急停止中(data_b/STOP)。原因を確認し、STOPファイルを手動削除してください。"
            return 2
        }
        if ($RetryOn -notcontains $code) {
            Write-ShitouLog "$Command が終了コード $code。リトライ対象外のため中断します。" "WARN"
            return $code
        }
        if ($i -lt $MaxAttempts) {
            $wait = $delays[[Math]::Min($i - 1, $delays.Length - 1)]
            Write-ShitouLog "$Command が終了コード $code。$wait 秒待って再試行します。" "WARN"
            Start-Sleep -Seconds $wait
        } else {
            Write-ShitouLog "$Command が終了コード $code。$MaxAttempts 回試して失敗しました。" "ERROR"
        }
    }
    return $code
}

function Enter-ShitouProject {
    Set-Location $script:ShitouProject
    $env:PYTHONUTF8 = 1
}

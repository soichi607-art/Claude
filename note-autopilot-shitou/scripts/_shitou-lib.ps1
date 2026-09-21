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
        $url = Get-ShitouEnvValue -Key "NOTIFY_WEBHOOK_URL"
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

function Get-ShitouEnvValue {
    # .env から1つの値を読む。無ければ $null。
    param([string]$Key)
    try {
        $envFile = Join-Path $script:ShitouProject ".env"
        if (-not (Test-Path $envFile)) { return $null }
        foreach ($line in Get-Content $envFile -Encoding UTF8) {
            if ($line -match ("^\s*" + [regex]::Escape($Key) + "\s*=\s*(.+?)\s*$")) {
                $v = $Matches[1].Trim('"').Trim("'")
                if ($v) { return $v }
            }
        }
    } catch { }
    return $null
}

function Set-ShitouAlert {
    <#
      デスクトップに警告ファイルを置く。
      NOTIFY_WEBHOOK_URL を設定していない場合、通知に気づく手段がログしかない。
      Cookie 失効は人が直さないと復旧しないため、必ず目に入る場所に出す。
    #>
    param([string]$Message)
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        if (-not $desktop) { return }
        $path = Join-Path $desktop "【note・史灯】要対応.txt"
        $body = @(
            "note アカウントB(史灯)の自動投稿が止まっています。",
            "",
            $Message,
            "",
            "対処:",
            "  1. B専用のブラウザ/Chromeプロファイルで note.com にログインする",
            "  2. F12 → Network タブ → Doc フィルタ → F5",
            "  3. 一覧の一番上の行を右クリック → Copy → Copy as cURL (bash)",
            "  4. PowerShell で以下を実行",
            "     cd C:\Users\User\Documents\note-autopilot",
            "     powershell -ExecutionPolicy Bypass -File scripts\set-cookie.ps1 -Account B",
            "",
            "復旧すると、このファイルは翌朝の確認時に自動で消えます。",
            "記録日時: " + (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        ) -join "`r`n"
        Set-Content -Path $path -Value $body -Encoding UTF8
        Write-ShitouLog "デスクトップに警告ファイルを置きました: $path" "WARN"
    } catch {
        Write-ShitouLog "警告ファイルの作成に失敗しました: $_" "WARN"
    }
}

function Clear-ShitouAlert {
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        if (-not $desktop) { return }
        $path = Join-Path $desktop "【note・史灯】要対応.txt"
        if (Test-Path $path) {
            Remove-Item $path -Force
            Write-ShitouLog "復旧を確認したため、デスクトップの警告ファイルを削除しました。"
        }
    } catch { }
}

function Invoke-ShitouGenerate {
    <#
      analyze / generate を実行する。Gemini の無料枠切れ(終了コード4)で失敗した場合、
      .env に ANTHROPIC_API_KEY があれば config.b.fallback.yaml(llm.backend: api)で
      1回だけやり直す。

      キーが無ければフォールバックしない。従量課金を勝手に発生させないため。
    #>
    param([Parameter(Mandatory=$true)][string]$Command)

    $code = Invoke-ShitouStep -Command $Command -RetryOn @(3,4,5) -MaxAttempts 3
    if ($code -ne 4) { return $code }

    $key = Get-ShitouEnvValue -Key "ANTHROPIC_API_KEY"
    if (-not $key) {
        Write-ShitouLog "$Command が無料枠切れ(4)。ANTHROPIC_API_KEY が未設定のためフォールバックしません。" "WARN"
        return $code
    }
    $fallbackConfig = Join-Path $script:ShitouProject "config.b.fallback.yaml"
    if (-not (Test-Path $fallbackConfig)) {
        Write-ShitouLog "$Command が無料枠切れ(4)。config.b.fallback.yaml が無いためフォールバックしません。" "WARN"
        return $code
    }

    Write-ShitouLog "$Command が無料枠切れ(4)。Anthropic API へフォールバックします(従量課金が発生します)。" "WARN"
    & uv run python -m note_autopilot --config config.b.fallback.yaml $Command
    $code = $LASTEXITCODE
    if ($code -eq 0) {
        Send-ShitouNotify "$Command: Gemini の無料枠切れのため Anthropic API で生成しました(課金が発生しています)。"
    } else {
        Write-ShitouLog "フォールバックでも $Command が終了コード $code で失敗しました。" "ERROR"
    }
    return $code
}

function Enter-ShitouProject {
    Set-Location $script:ShitouProject
    $env:PYTHONUTF8 = 1
}

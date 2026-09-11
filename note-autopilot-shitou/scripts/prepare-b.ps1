# 史灯(アカウントB)記事の事前生成 — 火・木・土 09:00 実行想定
#
# 公開(17:00)の8時間前に記事を用意しておく。
# こうすると「生成の失敗」と「公開の失敗」が切り離され、
# 生成に失敗しても公開時刻までに何度でもやり直せる。

. "$PSScriptRoot\_shitou-lib.ps1"
Enter-ShitouProject

if (Test-ShitouStopped) {
    Send-ShitouNotify "事前生成: 緊急停止中(data_b/STOP)のため中止します。"
    exit 2
}

# 1) 連載の進行状態をプロンプトへ反映
uv run python scripts\shitou_state.py sync
$sync = $LASTEXITCODE
if ($sync -eq 20) { Write-ShitouLog "全話完了済みのため何もしません。"; exit 0 }
if ($sync -ne 0) {
    Send-ShitouNotify "事前生成: プロンプト生成に失敗しました(終了コード $sync)。"
    exit 1
}

# 2) すでに生成済みなら何もしない(二重生成を防ぐ)
uv run python scripts\shitou_state.py is-prepared
if ($LASTEXITCODE -eq 0) {
    Write-ShitouLog "この話は生成済みです。事前生成をスキップします。"
    exit 0
}

# 3) 収集(失敗しても続行する。連載小説はトレンドを題材に使わないため)
Invoke-ShitouStep -Command "collect" -RetryOn @(8) -MaxAttempts 2 | Out-Null

# 4) テーマ選定 → 生成
#    3=note日次上限 / 4=LLM利用不可(無料枠切れ) / 5=品質ゲート保留 はリトライする
$code = Invoke-ShitouStep -Command "analyze" -RetryOn @(3,4) -MaxAttempts 3
if ($code -eq 2) { exit 2 }
if ($code -ne 0) {
    Send-ShitouNotify "事前生成: analyze が終了コード $code。17:00 の公開前に再試行されます。"
    exit $code
}

$code = Invoke-ShitouStep -Command "generate" -RetryOn @(3,4,5) -MaxAttempts 3
if ($code -eq 2) { exit 2 }
if ($code -ne 0) {
    Send-ShitouNotify "事前生成: generate が終了コード $code。17:00 の公開前に再試行されます。"
    exit $code
}

uv run python scripts\shitou_state.py mark-prepared
Write-ShitouLog "事前生成が完了しました。17:00 に公開します。"
exit 0

# 史灯(アカウントB)記事の事前生成 — 月・水・金 09:00 実行想定(公開の「前日」)
#
# 公開は火・木・土の 17:00。その前日の朝に記事を用意しておく。
# こうすると「生成の失敗」と「公開の失敗」が切り離され、
# 生成に失敗しても公開までに丸一日以上やり直せる。
#
# 未公開の記事は常に1本だけになる(公開してから次を作る)。
# publish が複数記事をまとめて公開する実装だった場合でも、一度に複数話が
# 出てしまう事故が起きない。

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
$code = Invoke-ShitouGenerate -Command "analyze"
if ($code -eq 2) { exit 2 }
if ($code -ne 0) {
    Send-ShitouNotify "事前生成: analyze が終了コード $code。翌日の公開前に再試行されます。"
    exit $code
}

$code = Invoke-ShitouGenerate -Command "generate"
if ($code -eq 2) { exit 2 }
if ($code -ne 0) {
    Send-ShitouNotify "事前生成: generate が終了コード $code。翌日の公開前に再試行されます。"
    exit $code
}

uv run python scripts\shitou_state.py mark-prepared
Write-ShitouLog "事前生成が完了しました。翌日 17:00 に公開します。"
exit 0

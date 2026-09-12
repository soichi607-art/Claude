# 史灯(アカウントB)公開パイプライン — 火・木・土 17:00 実行想定
#
# 設計方針: 「公開に失敗しない」ためにやっていること
#   1. 記事は「前日」09:00 の prepare-b.ps1 で生成済み(生成失敗と公開失敗を切り離す)
#   2. 未生成なら、この場で生成をやり直す
#   3. publish は待機を挟んで最大3回まで再試行する
#   4. それでも失敗したら 19:30 / 21:30 の catchup-b.ps1 が再試行する
#   5. 公開できなかった話は話数を進めないので、次の投稿日にも再試行される
#
# 例外: 終了コード2(401/403/429 による緊急停止)はリトライしない。
#       アカウント凍結を避けるための安全装置であり、外してはいけない。

. "$PSScriptRoot\_shitou-lib.ps1"
Enter-ShitouProject

if (Test-ShitouStopped) {
    Send-ShitouNotify "公開: 緊急停止中(data_b/STOP)のため中止します。STOPファイルを手動削除するまで再開しません。"
    exit 2
}

# --- 1. 連載の進行状態をプロンプトへ反映 ---
uv run python scripts\shitou_state.py sync
$sync = $LASTEXITCODE
if ($sync -eq 20) { Write-ShitouLog "全話完了済みのため何もしません。"; exit 0 }
if ($sync -ne 0) {
    Send-ShitouNotify "公開: プロンプト生成に失敗しました(終了コード $sync)。"
    exit 1
}

# --- 2. 疎通確認(投稿する前に Cookie の生死を確かめる) ---
uv run python -m note_autopilot --config config.b.yaml healthcheck --live
if ($LASTEXITCODE -ne 0) {
    Send-ShitouNotify ("公開: healthcheck --live が失敗しました。Cookie 失効の可能性が高いです。" +
        "復旧後、19:30 / 21:30 の再試行で自動的に公開されます。")
    Set-ShitouAlert -Message "17:00 の公開前チェックで note へ接続できませんでした。Cookie の再取得が必要です。"
    # 記事は残るので、ここで止めても話数は進まない。次の機会に公開される。
    exit 10
}
Clear-ShitouAlert

# --- 3. 記事が未生成なら、この場で作る ---
uv run python scripts\shitou_state.py is-prepared
if ($LASTEXITCODE -ne 0) {
    Write-ShitouLog "記事が未生成のため、ここで生成します。"
    Invoke-ShitouStep -Command "collect" -RetryOn @(8) -MaxAttempts 2 | Out-Null

    $code = Invoke-ShitouGenerate -Command "analyze"
    if ($code -eq 2) { exit 2 }
    if ($code -ne 0) {
        Send-ShitouNotify "公開: analyze が終了コード $code で失敗し、本日の公開ができません。"
        exit $code
    }

    $code = Invoke-ShitouGenerate -Command "generate"
    if ($code -eq 2) { exit 2 }
    if ($code -ne 0) {
        Send-ShitouNotify ("公開: generate が終了コード $code で失敗し、本日の公開ができません。" +
            "品質ゲート保留(5)の場合、記事は output_b/hold/ にあります。")
        exit $code
    }
    uv run python scripts\shitou_state.py mark-prepared
}

# --- 4. 公開(最大3回・待機付き) ---
#     6=note投稿失敗 はリトライする。2=緊急停止 はリトライしない。
$pub = Invoke-ShitouStep -Command "publish" -RetryOn @(6) -MaxAttempts 3
if ($pub -eq 2) { exit 2 }

if ($pub -eq 0) {
    uv run python scripts\shitou_state.py advance
    Write-ShitouLog "公開に成功しました。"
} else {
    Send-ShitouNotify ("公開: publish が終了コード $pub。話数は進めていません。" +
        "19:30 と 21:30 に自動で再試行します。")
}

# --- 5. 成果計測 → 分析 → 次話への改善指示 ---
Invoke-ShitouStep -Command "feedback" -RetryOn @(8) -MaxAttempts 2 | Out-Null
uv run python scripts\shitou_analyze.py analyze

exit $pub

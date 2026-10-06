# 史灯(アカウントB)公開の再試行 — 火・木・土 19:30 と 21:30 実行想定
#
# 17:00 の公開に失敗したときの取り返し。
# publish は「未公開の合格記事」だけを対象にするため、
# すでに公開済みなら終了コード1(対象なし)で何もせずに終わる。二重投稿にはならない。

. "$PSScriptRoot\_shitou-lib.ps1"
Enter-ShitouProject

if (Test-ShitouStopped) {
    Write-ShitouLog "緊急停止中(data_b/STOP)のため再試行しません。" "WARN"
    exit 2
}

uv run python scripts\shitou_state.py sync | Out-Null
if ($LASTEXITCODE -eq 20) { exit 0 }

$pub = Invoke-ShitouStep -Command "publish" -RetryOn @(6) -MaxAttempts 2

if ($pub -eq 0) {
    uv run python scripts\shitou_state.py advance
    Send-ShitouNotify "再試行で公開に成功しました。"
    uv run python -m note_autopilot --config config.b.yaml feedback
    uv run python scripts\shitou_analyze.py analyze
    exit 0
}

if ($pub -eq 1) {
    # 対象なし = 17:00 に公開済み。正常。
    Write-ShitouLog "公開対象がありません(17:00 に公開済み)。"
    exit 0
}

Write-ShitouLog "再試行でも公開できませんでした(終了コード $pub)。" "WARN"
exit $pub

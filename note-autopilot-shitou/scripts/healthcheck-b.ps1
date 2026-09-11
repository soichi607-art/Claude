# 史灯(アカウントB)の疎通確認 — 毎日 08:00 実行想定
#
# 目的: note の Cookie 失効や仕様変更を「投稿日の朝」に見つけること。
# 週1回のヘルスチェックでは、失効したまま投稿日を迎えてしまう。
# 読み取り系のみで、書き込みは一切行わない。

. "$PSScriptRoot\_shitou-lib.ps1"
Enter-ShitouProject

if (Test-ShitouStopped) {
    Send-ShitouNotify "ヘルスチェック: 緊急停止中(data_b/STOP)です。STOPファイルを手動削除するまで投稿は行われません。"
    exit 2
}

uv run python -m note_autopilot --config config.b.yaml healthcheck --live
$code = $LASTEXITCODE

if ($code -eq 0) {
    Write-ShitouLog "ヘルスチェック 異常なし"
} else {
    Send-ShitouNotify ("ヘルスチェックが終了コード $code で失敗しました。" +
        "Cookie 失効の可能性があります。B専用ブラウザで note にログインし、" +
        "scripts\set-cookie.ps1 -Account B を実行してください。" +
        "このままだと次の投稿日に公開できません。")
}
exit $code

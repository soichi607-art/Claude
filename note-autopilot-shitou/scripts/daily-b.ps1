# 史灯(アカウントB)日次パイプライン — 火・木・土 17:00 実行想定
# 既存の daily.ps1 とは別ファイル。B は連載小説のため、前後に話数管理の処理が入る。

Set-Location C:\Users\User\Documents\note-autopilot
$env:PYTHONUTF8 = 1

# --- 1. 連載の進行状態を4つのプロンプトへ反映する(必須) ---
uv run python scripts\shitou_state.py sync
$sync = $LASTEXITCODE
if ($sync -eq 20) {
    Write-Host "[daily-b] 全話完了済みのため、本日は何もしません。"
    exit 0
}
if ($sync -ne 0) {
    Write-Error "[daily-b] プロンプト生成に失敗しました(終了コード $sync)。以降を中止します。"
    exit 1
}

# --- 2. 収集 → 選定 → 生成 ---
foreach ($cmd in "collect", "analyze", "generate") {
    uv run python -m note_autopilot --config config.b.yaml $cmd
    $code = $LASTEXITCODE
    if ($code -eq 2) { Write-Error "[daily-b] 緊急停止中(data_b/STOP)。"; exit 2 }
    if ($code -ne 0) {
        # 1=対象なし / 3=note日次上限 / 4=LLM利用不可 / 5=品質ゲート保留
        Write-Host "[daily-b] $cmd が終了コード $code で終了したため、本日の投稿は行いません。"
        exit $code
    }
}

# --- 3. 公開 ---
uv run python -m note_autopilot --config config.b.yaml publish
$pub = $LASTEXITCODE
if ($pub -eq 2) { Write-Error "[daily-b] 緊急停止中(data_b/STOP)。"; exit 2 }

# --- 4. 公開が成功したときだけ話数を1つ進める ---
if ($pub -eq 0) {
    uv run python scripts\shitou_state.py advance
} else {
    Write-Host "[daily-b] publish が終了コード $pub のため、話数は進めません(次回同じ話を再試行します)。"
}

# --- 5. 成果計測 ---
uv run python -m note_autopilot --config config.b.yaml feedback

exit $pub

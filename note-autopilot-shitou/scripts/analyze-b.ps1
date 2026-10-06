# 史灯(アカウントB)週次の分析 — 毎週月曜 07:00 実行想定
#
# 公開日以外にも PV は伸びるため、週に一度まとめて計測し直し、
# 次話への改善指示を更新する。

. "$PSScriptRoot\_shitou-lib.ps1"
Enter-ShitouProject

# 最新の PV・スキを取り込んでから分析する
uv run python -m note_autopilot --config config.b.yaml feedback
uv run python scripts\shitou_analyze.py analyze
$code = $LASTEXITCODE

Write-ShitouLog "週次分析を実行しました。レポート: output_b\reports\"
exit $code

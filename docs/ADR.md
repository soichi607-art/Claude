# ADR（Architecture Decision Records）

## ADR-001: React / Redis / Docker を採用しない（2026-09-09）
- 状況: 社内1〜数名の利用、iPhone Safari と PC ブラウザ、localhost 運用。
- 決定: FastAPI + Jinja2 + HTMX。状態はSQLiteとローカルファイル。ジョブキューはアプリ内スレッド（同時1件）で十分。
- 理由: 追加コスト0、依存最小、16GBメモリのPCで ACE-Step と共存させるため軽量に保つ。
- 影響: 複数ユーザー同時編集や分散実行は非対応（要件外）。

## ADR-002: 楽曲生成は ACE-Step 1.5 の公式 REST API 経由（2026-09-09）
- 決定: ACE-Step を別プロセス（`uv run acestep-api` または `start_api_server_xpu.bat`）で起動し、本アプリは `docs/en/API.md` に記載の `/release_task`, `/query_result`, `/v1/audio`, `/health` のみを使用する。
- 理由: 同一プロセスに torch を読み込むと本アプリの起動と安定性を損なう。公式APIは非同期ジョブ設計で本アプリのキューと相性が良い。
- 代替: Python API（INFERENCE.md）は将来検討。

## ADR-003: 歌詞・投稿文はルールベース生成（2026-09-09）
- 決定: 有料LLM禁止のため、歌詞は英日対訳フレーズバンク＋構成テンプレート、投稿文はテンプレートで生成。ACE-Step API サーバーが LM 付きで起動している場合のみ `/format_input` で歌詞整形を任意実行。
- 影響: 文学的品質は限定的。ユーザーが編集可能にする。

## ADR-004: キャラクター画像の生成は本アプリ内で行わない（2026-09-09）
- 決定: 実機に画像生成モデルを導入せず、無料GPU Notebook で生成した画像を「基準画像」としてアップロード・承認する。アプリはプロンプト・seed・ネガティブを管理する。
- 理由: 16GB/内蔵GPU の PC で画像生成モデルを常駐させると ACE-Step と競合する。
